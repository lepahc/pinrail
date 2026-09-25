"""Real local Git and subprocess proofs; no native builds or network required."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import gate
import verify


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE).decode().strip()


class NativeWorkerTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(os.environ.get('TMPDIR', ROOT / '.scratch/tests')).resolve()
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='ci-native-', dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'remote'
        self.repo.mkdir()
        git(self.repo, 'init', '--initial-branch=main')
        git(self.repo, 'config', 'user.name', 'Fixture')
        git(self.repo, 'config', 'user.email', 'fixture@example.invalid')
        self.marker = self.root / 'candidate-driver-executed'
        self.receipt = self.root / 'trusted-driver.json'
        driver = self.repo / 'scripts/ci/native_checks.py'
        driver.parent.mkdir(parents=True)
        driver.write_text('import json, os, sys\nfrom pathlib import Path\n'
                          f'Path({str(self.receipt)!r}).write_text(json.dumps('
                          '{"argv": sys.argv, "env": dict(os.environ), "cwd": os.getcwd()}))\n')
        (self.repo / 'README').write_bytes(b'base\nLF bytes\n')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-m', 'trusted controller')
        self.base = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'checkout', '-b', 'candidate')
        driver.write_text(f'from pathlib import Path\nPath({str(self.marker)!r}).touch()\n')
        (self.repo / 'README').write_bytes(b'candidate\nLF bytes\n')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-m', 'untrusted candidate driver')
        self.head = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'update-ref', 'refs/pull/7/head', self.head)
        git(self.repo, 'checkout', 'main')
        self.snapshot = {'pr': 7, 'head': self.head, 'base': self.base, 'base_ref': 'main',
                         'controller': self.base, 'run_id': '42', 'attempt': '1', 'suite': 'native-v1'}

    def test_environment_removes_all_action_and_git_injection_capabilities(self):
        forbidden = {'GH_TOKEN', 'GITHUB_TOKEN', 'GITHUB_OUTPUT', 'GITHUB_ENV', 'GITHUB_PATH',
                     'GITHUB_STATE', 'GITHUB_STEP_SUMMARY', 'GITHUB_EVENT_PATH',
                     'ACTIONS_RUNTIME_TOKEN', 'ACTIONS_CACHE_URL', 'ACTIONS_RESULTS_URL',
                     'ACTIONS_ID_TOKEN_REQUEST_URL', 'ACTIONS_ID_TOKEN_REQUEST_TOKEN',
                     'GIT_CONFIG_COUNT', 'GIT_CONFIG_KEY_0', 'GIT_CONFIG_VALUE_0', 'GIT_DIR',
                     'GIT_WORK_TREE', 'GIT_CONFIG_PARAMETERS', 'GIT_ASKPASS', 'SSH_ASKPASS',
                     'PYTHONPATH', 'PYTHONHOME', 'DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET',
                     'XDG_RUNTIME_DIR'}
        with patch.dict(os.environ, {key: 'sentinel' for key in forbidden}):
            env = verify.worker_environment(self.root / 'scratch')
        self.assertEqual(forbidden.intersection(env), set())
        self.assertEqual(env['GIT_CONFIG_GLOBAL'], os.devnull)
        self.assertEqual(env['GIT_CONFIG_NOSYSTEM'], '1')
        self.assertEqual(env['GIT_NO_REPLACE_OBJECTS'], '1')
        self.assertEqual(env['TMP'], env['TMPDIR'])
        self.assertEqual(env['TEMP'], env['TMPDIR'])
        self.assertTrue(Path(env['TMPDIR']).is_dir())

    def test_exact_downstream_is_clean_and_only_controller_driver_executes(self):
        import native_verify
        for platform in ('macos-arm64', 'macos-x86_64', 'windows-x86_64'):
            scratch = self.root / platform
            with patch.dict(os.environ, {'GH_TOKEN': 'secret', 'ACTIONS_RUNTIME_TOKEN': 'secret',
                                         'GITHUB_OUTPUT': 'must-not-survive'}):
                candidate = native_verify.run_worker(self.snapshot, platform, self.repo, scratch,
                                                      remote=str(self.repo))
            self.assertEqual(git(candidate, 'rev-parse', 'HEAD'), self.head)
            self.assertEqual(git(candidate, 'status', '--porcelain'), '')
            self.assertEqual((candidate / 'README').read_bytes(), b'candidate\nLF bytes\n')
            receipt = json.loads(self.receipt.read_text())
            self.assertEqual(receipt['argv'], [str(self.repo / 'scripts/ci/native_checks.py'),
                                              '--platform', platform, '--candidate', str(candidate)])
            self.assertEqual(receipt['cwd'], str(self.repo))
            self.assertFalse({'GH_TOKEN', 'ACTIONS_RUNTIME_TOKEN', 'GITHUB_OUTPUT'} & receipt['env'].keys())
            self.assertTrue(Path(receipt['env']['TMPDIR']).is_relative_to(scratch))
            self.assertFalse(self.marker.exists())

    def test_rejects_other_suites_platforms_and_controller_before_acquisition(self):
        import native_verify
        cases = [(dict(self.snapshot, base_ref='upstream-import'), 'macos-arm64'),
                 (dict(self.snapshot, suite='legacy'), 'macos-arm64'),
                 ({k: v for k, v in self.snapshot.items() if k != 'suite'}, 'macos-arm64'),
                 (dict(self.snapshot, controller='a' * 40), 'macos-arm64'),
                 (self.snapshot, 'windows-arm64'), (self.snapshot, 'macos-arm64\n')]
        for index, (snapshot, platform) in enumerate(cases):
            scratch = self.root / str(index)
            with self.subTest(snapshot=snapshot, platform=platform), self.assertRaises(gate.GateError):
                native_verify.run_worker(snapshot, platform, self.repo, scratch, remote=str(self.repo))
            self.assertFalse(scratch.exists())
            self.assertFalse(self.receipt.exists())

    def test_fetch_races_and_nonancestor_fail_without_running_driver(self):
        import native_verify
        controller = self.root / 'separate-controller'
        subprocess.run(['git', 'clone', '--no-hardlinks', str(self.repo), str(controller)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for index, ref in enumerate(('refs/pull/7/head', 'refs/heads/main')):
            old = git(self.repo, 'rev-parse', ref)
            git(self.repo, 'update-ref', ref, self.base if index == 0 else self.head)
            expected = 'candidate changed' if index == 0 else 'accepted changed'
            with self.assertRaisesRegex(gate.GateError, expected):
                native_verify.prepare_candidate(self.snapshot, controller, self.root / f'race-{index}',
                                                remote=str(self.repo))
            git(self.repo, 'update-ref', ref, old)
        # Real unrelated commit with a valid current base; not a snapshot-format rejection.
        git(self.repo, 'checkout', '--orphan', 'unrelated')
        git(self.repo, 'commit', '-m', 'not descended from B')
        head = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'update-ref', 'refs/pull/7/head', head)
        git(self.repo, 'checkout', 'main')
        with self.assertRaises(gate.GateError):
            native_verify.run_worker(dict(self.snapshot, head=head), 'macos-arm64', self.repo,
                                     self.root / 'unrelated', remote=str(self.repo))
        self.assertFalse(self.receipt.exists())

    def test_hostile_global_git_config_and_hooks_never_run(self):
        import native_verify
        hooks = self.root / 'hooks'
        hooks.mkdir()
        marker = self.root / 'hook-executed'
        hook = hooks / 'post-checkout'
        hook.write_text(f'#!/bin/sh\ntouch "{marker}"\n')
        hook.chmod(0o755)
        config = self.root / 'gitconfig'
        config.write_text(f'[core]\n\thooksPath = {hooks}\n\tautocrlf = true\n'
                          '[filter "evil"]\n\tsmudge = false\n\trequired = true\n')
        with patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': str(config), 'GIT_CONFIG_COUNT': '1',
                                     'GIT_CONFIG_KEY_0': 'core.hooksPath', 'GIT_CONFIG_VALUE_0': str(hooks)}):
            candidate = native_verify.prepare_candidate(self.snapshot, self.repo, self.root / 'safe',
                                                        remote=str(self.repo))
        self.assertFalse(marker.exists())
        self.assertEqual((candidate / 'README').read_bytes(), b'candidate\nLF bytes\n')
        # Local controller configuration also cannot supply hooks to the Git helper.
        git(self.repo, 'config', 'core.hooksPath', str(hooks))
        verify.git(self.repo, 'checkout', '--detach', self.base)
        self.assertFalse(marker.exists())

    def test_dirty_controller_and_reused_scratch_are_rejected(self):
        import native_verify
        (self.repo / 'README').write_text('dirty controller')
        with self.assertRaises(gate.GateError):
            native_verify.run_worker(self.snapshot, 'macos-arm64', self.repo, self.root / 'dirty',
                                     remote=str(self.repo))
        git(self.repo, 'checkout', '--', 'README')
        scratch = self.root / 'reused'
        native_verify.prepare_candidate(self.snapshot, self.repo, scratch, remote=str(self.repo))
        with self.assertRaises((gate.GateError, FileExistsError)):
            native_verify.run_worker(self.snapshot, 'macos-arm64', self.repo, scratch, remote=str(self.repo))
        self.assertFalse(self.receipt.exists())

    def test_real_driver_failure_propagates(self):
        import native_verify
        (self.repo / 'scripts/ci/native_checks.py').write_text('raise SystemExit(19)\n')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-m', 'failing trusted driver')
        base = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'checkout', '-b', 'new-candidate')
        git(self.repo, 'commit', '--allow-empty', '-m', 'new head')
        head = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'update-ref', 'refs/pull/7/head', head)
        git(self.repo, 'checkout', 'main')
        snapshot = dict(self.snapshot, controller=base, base=base, head=head)
        with self.assertRaises(subprocess.CalledProcessError) as failure:
            native_verify.run_worker(snapshot, 'windows-x86_64', self.repo, self.root / 'failure',
                                     remote=str(self.repo))
        self.assertEqual(failure.exception.returncode, 19)


if __name__ == '__main__':
    unittest.main()
