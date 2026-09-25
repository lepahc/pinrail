"""Real Git/LockGuard and cmd startup regressions, not native build evidence.

cmd executes directly on Windows. Linux may opt in with PINRAIL_TEST_WINE=1;
that uses a fresh owned, display-disconnected Wine prefix, never ~/.wine. Only
VS discovery and (under Wine) host/path transport are substituted, not cmd output.
"""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import gate
import native_checks as native
import native_verify
import verify


def temporary_root(prefix):
    base = Path(os.environ.get('TMPDIR', ROOT / '.scratch/tests')).resolve()
    base.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=prefix, dir=base)


class ControllerCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_root('native-checkout-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'remote'
        self.repo.mkdir()
        self.git_env = verify.git_environment()
        self.git(self.repo, 'init', '--initial-branch=main', '--template=')
        self.git(self.repo, 'config', 'user.name', 'Fixture')
        self.git(self.repo, 'config', 'user.email', 'fixture@example.invalid')
        # Actual lock, policy, scripts and CRLF notices, not LF-only stand-ins.
        self.payload = {name: (ROOT / name).read_bytes() for name in (
            'Cargo.lock', '.gitattributes', 'Cargo.toml', 'LICENSE-MICROSOFT-MIT',
            'docs/licenses/microsoft-terminal-MIT.txt', 'scripts/ci/native_checks.py',
            'scripts/ci/native_verify.py')}
        for name, data in self.payload.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.git(self.repo, '-c', 'core.autocrlf=false', 'add', '.')
        self.git(self.repo, 'commit', '-m', 'controller')
        base = self.git(self.repo, 'rev-parse', 'HEAD').decode().strip()
        self.git(self.repo, 'checkout', '-b', 'candidate')
        self.git(self.repo, 'commit', '--allow-empty', '-m', 'candidate')
        head = self.git(self.repo, 'rev-parse', 'HEAD').decode().strip()
        self.git(self.repo, 'update-ref', 'refs/pull/7/head', head)
        self.git(self.repo, 'checkout', 'main')
        self.snapshot = dict(pr=7, head=head, base=base, base_ref='main', controller=base,
                             run_id='42', attempt='1', suite='native-v1')
        self.config = self.root / 'ambient.gitconfig'

    def git(self, repo, *args, env=None):
        return subprocess.check_output(['git', '-C', str(repo), *args],
                                       env=self.git_env if env is None else env,
                                       stderr=subprocess.PIPE, timeout=30)

    def checkout(self, name, autocrlf, step_env):
        self.config.write_text(f'[core]\n\tautocrlf = {autocrlf}\n')
        env = dict(self.git_env, GIT_CONFIG_GLOBAL=str(self.config)) | step_env
        controller = self.root / name
        controller.mkdir()
        # The action's pre-checkout env must affect materialization, not a later
        # status/reset. Use real init/fetch/checkout with ambient Windows policy.
        self.git(controller, 'init', '--template=', env=env)
        self.git(controller, 'fetch', '--depth=1', '--no-tags', str(self.repo), 'main', env=env)
        self.git(controller, 'checkout', '--detach', 'FETCH_HEAD', env=env)
        # Force Git to examine bytes even if index stat caching would hide drift.
        lock = controller / 'Cargo.lock'
        stat = lock.stat()
        os.utime(lock, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        return controller

    def test_native_checkout_policy_preserves_bytes_under_both_host_policies(self):
        workflow = json.loads((ROOT / '.github/workflows/native.yml').read_text())
        for job_name, job in workflow['jobs'].items():
            step = next(s for s in job['steps'] if s.get('uses', '').startswith('actions/checkout@'))
            for ambient in ('true', 'false'):
                with self.subTest(job=job_name, ambient_autocrlf=ambient):
                    name = f'{job_name}-{ambient}'
                    controller = self.checkout(name, ambient, step.get('env', {}))
                    self.assertEqual(self.config.read_text(), f'[core]\n\tautocrlf = {ambient}\n')
                    candidate = native_verify.prepare_candidate(self.snapshot, controller,
                        self.root / f'{name}-worker', remote=str(self.repo))
                    with patch.object(native, 'ROOT', controller), redirect_stdout(io.StringIO()):
                        guard = native.LockGuard(candidate)
                    for filename, expected in self.payload.items():
                        self.assertEqual((controller / filename).read_bytes(), expected, filename)
                        self.assertEqual((candidate / filename).read_bytes(), expected, filename)
                    for notice in ('LICENSE-MICROSOFT-MIT', 'docs/licenses/microsoft-terminal-MIT.txt'):
                        self.assertIn(b'\r\n', (candidate / notice).read_bytes())
                        self.assertEqual(hashlib.sha256((candidate / notice).read_bytes()).hexdigest(),
                                         '5d177f23ecfeb0ea8e050b6a5a16355e1ae9a0b286436ca8f83ed08b3795be6b')
                    self.assertEqual(verify.git(controller, 'status', '--porcelain'), b'')
                    self.assertEqual(verify.git(candidate, 'status', '--porcelain'), b'')
                    # A line-ending-only lock change must still fail, not normalize.
                    (candidate / 'Cargo.lock').write_bytes(self.payload['Cargo.lock'].replace(b'\n', b'\r\n'))
                    with self.assertRaisesRegex(native.NativeCheckError, 'lock drifted'):
                        guard.check()

    def test_unscoped_crlf_checkout_is_rejected_despite_equal_committed_lock(self):
        controller = self.checkout('unscoped', 'true', {})
        self.assertIn(b'\r\n', (controller / 'Cargo.lock').read_bytes())
        self.assertEqual(self.git(controller, 'rev-parse', 'HEAD:Cargo.lock'),
                         self.git(self.repo, 'rev-parse', 'HEAD:Cargo.lock'))
        with self.assertRaisesRegex(gate.GateError, 'controller checkout is not clean'):
            native_verify.prepare_candidate(self.snapshot, controller, self.root / 'rejected',
                                             remote=str(self.repo))
        self.assertFalse((self.root / 'rejected').exists())
        with patch.object(native, 'ROOT', controller), \
             self.assertRaisesRegex(native.NativeCheckError, 'lock drifted'):
            native.LockGuard(self.repo)


class RealCmdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wine = os.name != 'nt'
        if cls.wine and not (sys.platform == 'linux' and os.environ.get('PINRAIL_TEST_WINE') == '1'):
            raise unittest.SkipTest('requires native Windows cmd or opt-in PINRAIL_TEST_WINE=1 on Linux')
        if cls.wine and not all(shutil.which(tool) for tool in ('wine', 'wineserver')):
            raise RuntimeError('PINRAIL_TEST_WINE=1 requires installed wine and wineserver')
        temp = temporary_root('native-real-cmd-')
        cls.addClassCleanup(temp.cleanup)
        cls.root = Path(temp.name)
        # Do not dump credentials or connect display/audio endpoints through `set`.
        cls.env = {k.upper(): v for k, v in os.environ.items() if k.upper() in (
            'PATH', 'HOME', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT')}
        cls.env.update(TMPDIR=str(cls.root), TMP=str(cls.root), TEMP=str(cls.root))
        if cls.wine:
            prefix = cls.root / 'wine-prefix'
            prefix.mkdir()
            cls.env.update(WINEPREFIX=str(prefix), WINEARCH='win64', WINEDEBUG='-all',
                           WINEDLLOVERRIDES='winemenubuilder.exe=d;winex11.drv=d;winewayland.drv=d')
            cls.addClassCleanup(cls.stop_wine)
            # Initialize once, without a live display or the user's Wine state.
            with (cls.root / 'wine-init.log').open('wb') as log:
                subprocess.run(['wine', 'cmd.exe', '/d', '/s', '/c', 'exit', '0'],
                               env=cls.env, stdin=subprocess.DEVNULL, stdout=log,
                               stderr=subprocess.STDOUT, timeout=80, check=True)

    @classmethod
    def stop_wine(cls):
        for flag in ('-k', '-w'):
            subprocess.run(['wineserver', flag], env=cls.env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=True)

    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix='case-', dir=self.root))
        shutil.copyfile(ROOT / 'Cargo.lock', self.scratch / 'Cargo.lock')
        self.installation = self.scratch / 'Visual Studio (Fixture)'
        self.script = self.installation / 'Common7/Tools/VsDevCmd.bat'
        self.script.parent.mkdir(parents=True)
        env = dict(self.env, CARGO_BUILD_JOBS='2', CARGO_TARGET_DIR=str(self.scratch / 't'),
                   **{'PROGRAMFILES(X86)': str(self.scratch / 'no-installed-vs')})
        self.runner = native.Runner(self.scratch, env, self.scratch, native.LockGuard(self.scratch))
        self.real_popen = subprocess.Popen
        self.cmd_calls = 0

    def transport(self, args, **kwargs):
        if args[0] == 'fixture-vswhere.exe':
            return self.real_popen([sys.executable, '-c', f'print({str(self.installation)!r})'], **kwargs)
        if args[0] == 'taskkill.exe':  # production Runner's native Windows cleanup
            return self.real_popen(args, **kwargs)
        self.assertEqual(args[0], 'cmd.exe')
        self.cmd_calls += 1
        if self.wine:
            # Wine serializes argv to a Windows command line. Replace only the
            # host filesystem spelling; leave the production command structure
            # and quoting untouched (including the old broken one-body form).
            windows_path = 'Z:' + str(self.script).replace('/', '\\')
            args = [arg.replace(str(self.script), windows_path) for arg in args]
            print('Wine cmd command line:', subprocess.list2cmdline(args), flush=True)
            args = ['wine', *args]
        return self.real_popen(args, **kwargs)

    def run_batch(self, status):
        self.script.write_bytes(('\r\n'.join([
            '@echo off',
            # cmd splits unquoted '=' in %1..%9, unlike a C argv parser.
            'if not "%~1"=="-no_logo" exit /b 21',
            'if not "%~2"=="-arch" exit /b 22',
            'if not "%~3"=="x64" exit /b 23',
            'if not "%~4"=="-host_arch" exit /b 24',
            'if not "%~5"=="x64" exit /b 25',
            'if not "%~6"=="" exit /b 26',
            'echo FIXTURE_VS_CALLED',
            'set "VSCMD_ARG_TGT_ARCH=x64"',
            'set "INCLUDE=fixture include"',
            'set "LIB=fixture lib"',
            'set "FIXTURE_VS_VALUE=space and=equals"',
            'set "CARGO_BUILD_JOBS=99"',
            'set "TMPDIR=untrusted-vs-temp"',
            'echo VSCMD_ARG_TGT_ARCH=x64',  # plausible stdout must not mask failure
            f'exit /b {status}', '',
        ])).encode('ascii'))
        with patch.object(native, 'which', return_value='fixture-vswhere.exe'), \
             patch.object(native.subprocess, 'Popen', side_effect=self.transport):
            native.windows_environment(self.runner)

    def test_spaced_batch_path_imports_real_cmd_environment_and_keeps_limits(self):
        self.run_batch(0)
        self.assertEqual(self.cmd_calls, 1)
        for key, value in dict(VSCMD_ARG_TGT_ARCH='x64', INCLUDE='fixture include',
                               LIB='fixture lib', FIXTURE_VS_VALUE='space and=equals',
                               CARGO_BUILD_JOBS='2', TMPDIR=str(self.root)).items():
            self.assertEqual(self.runner.env[key], value)
        output = (self.runner.logs / '02-msvc-environment.stdout.log').read_text()
        self.assertIn('FIXTURE_VS_CALLED', output)
        self.assertIn('FIXTURE_VS_VALUE=space and=equals', output)
        self.runner.guard.check()

    def test_batch_failure_keeps_native_exit_and_does_not_import_plausible_stdout(self):
        with self.assertRaisesRegex(native.NativeCheckError, 'msvc-environment: command exited 17;'):
            self.run_batch(17)
        self.assertEqual(self.cmd_calls, 1)
        output = (self.runner.logs / '02-msvc-environment.stdout.log').read_text()
        self.assertIn('FIXTURE_VS_CALLED', output)
        self.assertIn('VSCMD_ARG_TGT_ARCH=x64', output)
        self.assertNotIn('FIXTURE_VS_VALUE=', output)  # && set must not run on failure
        self.assertNotIn('VSCMD_ARG_TGT_ARCH', self.runner.env)
        self.assertNotIn('FIXTURE_VS_VALUE', self.runner.env)
        self.runner.guard.check()


if __name__ == '__main__':
    unittest.main()
