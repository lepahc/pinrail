"""Controlled command transport, not native build/GPU evidence.

The production builder, env policy, preflight branches, result validation and
subprocess runner all execute. Only native executable discovery/transport and
host identity are replaced. Fixture output and artifacts are explicitly fake.
"""
from contextlib import ExitStack, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import native_checks as native

# Separate observations/expectations from the implementation's tables.
MATRIX = (
    ('macos-arm64', 'Darwin', 'arm64', 'aarch64-apple-darwin'),
    ('macos-x86_64', 'Darwin', 'x86_64', 'x86_64-apple-darwin'),
    ('windows-x86_64', 'Windows', 'AMD64', 'x86_64-pc-windows-msvc'),
)
FIXTURE = r'''
import json, os, pathlib, sys
args = json.loads(sys.argv[1])
env = dict(os.environ)
root = pathlib.Path(env['FIXTURE_ROOT'])
with (root / 'calls.jsonl').open('a') as out:
    out.write(json.dumps({'args': args, 'env': env, 'cwd': os.getcwd()}) + '\n')
tool = pathlib.Path(args[0]).name
fault = env.get('FIXTURE_FAULT', '')
def artifact(path):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'explicitly fake native artifact for transport test\n')
def summary(passed):
    print(f'test result: ok. {passed} passed; 0 failed; 0 ignored; 0 measured; 12 filtered out; finished in 0.01s')
if tool == 'rustup':
    assert args == ['rustup', 'toolchain', 'install', '1.98.1', '--profile', 'minimal']
elif tool == 'rustc':
    host = 'x86_64-unknown-linux-gnu' if fault == 'rust-host' else env['FIXTURE_TRIPLE']
    print('rustc 1.98.1\nhost: ' + host + '\nrelease: 1.98.1')
elif tool == 'cargo':
    assert args[1] == '+1.98.1'
    if '--version' in args:
        print('cargo 1.98.1')
    else:
        assert '--locked' in args
        action = args[2]
        if action == 'metadata':
            print('{"packages": [], "resolve": {}}')
        elif action == 'check':
            if fault == 'command-failure':
                summary(99)
                sys.exit(17)
            if fault == 'lock-drift':
                pathlib.Path('Cargo.lock').write_text('changed by fixture subprocess')
        elif action == 'test' and '--no-run' not in args:
            package = args[args.index('-p') + 1]
            if fault == 'zero-tests' or fault == 'zero-' + package:
                summary(0)
            elif fault == 'ignored-only':
                print('test result: ok. 0 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out;')
            else:
                summary(1 if '--exact' in args else 5)
        elif action == 'build':
            assert '--example' in args and 'hello_world' in args
            triple = env['FIXTURE_TRIPLE']
            assert args[args.index('--target') + 1] == triple
            target = pathlib.Path(env['CARGO_TARGET_DIR']) / triple
            if triple == 'x86_64-pc-windows-msvc':
                assert '--release' in args
                artifact(target / 'release/examples/hello_world.exe')
                if fault != 'no-shader-output':
                    for name in ('shaders_bytes.rs', 'quad_vs.h', 'emoji_rasterization_ps.h'):
                        artifact(target / 'release/build/gpui_windows-fixture/out' / name)
            else:
                assert '--release' not in args
                artifact(target / 'debug/examples/hello_world')
                if fault != 'no-shader-output':
                    artifact(target / 'debug/build/gpui_apple-fixture/out/shaders.metallib')
elif tool in ('sw_vers', 'xcodebuild'):
    print('fixture native version')
elif tool == 'xcrun':
    if fault == 'missing-metal' and '--find' in args and 'metal' in args:
        print('fixture missing metal', file=sys.stderr)
        sys.exit(69)
    if '--show-sdk-path' in args:
        print(root / 'sdk')
    elif '--find' in args:
        print(root / 'tools' / args[-1])
    elif '-o' in args:
        artifact(args[args.index('-o') + 1])
    else:
        print('fixture metal version')
elif tool == 'vswhere.exe':
    print(root / 'vs')
elif tool == 'cmd.exe':
    if fault == 'vs-failure':
        print('VSCMD_ARG_TGT_ARCH=x64')
        sys.exit(13)
    print('VSCMD_ARG_TGT_ARCH=x64\nINCLUDE=fixture-include\nLIB=fixture-lib')
    print('PATH=' + env.get('PATH', ''))
    print('CARGO_BUILD_JOBS=99\nTMPDIR=untrusted-vs-temp')
elif tool == 'cl.exe':
    artifact(next(a[3:] for a in args if a.startswith('/Fo')))
elif tool == 'rc.exe':
    artifact(args[args.index('/fo') + 1])
elif tool == 'link.exe':
    artifact(next(a[5:] for a in args if a.startswith('/OUT:')))
elif tool == 'fxc.exe':
    if fault == 'fxc-failure':
        sys.exit(23)
    artifact(args[args.index('/Fo') + 1])
elif tool == 'cmake.exe':
    print('cmake fixture')
else:
    raise AssertionError('fixture refuses unrecognized command: ' + repr(args))
'''


class NativeTests(unittest.TestCase):
    def setUp(self):
        base = Path(os.environ.get('TMPDIR', ROOT / '.scratch/tests')).resolve()
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='native-test-', dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.candidate = self.root / 'candidate'
        self.candidate.mkdir()
        shutil.copyfile(ROOT / 'Cargo.lock', self.candidate / 'Cargo.lock')
        (self.candidate / 'Cargo.toml').write_text('[workspace]\n')
        (self.root / 'tools').mkdir()
        (self.root / 'sdk').mkdir()
        for name in ('cl.exe', 'rc.exe', 'link.exe', 'cmake.exe', 'fxc.exe', 'vswhere.exe', 'metal', 'metallib'):
            (self.root / 'tools' / name).touch()
        vs = self.root / 'vs/Common7/Tools/VsDevCmd.bat'
        vs.parent.mkdir(parents=True)
        vs.touch()
        self.fixture = self.root / 'process_fixture.py'
        self.fixture.write_text(FIXTURE)
        self.real_popen = subprocess.Popen

    def calls(self):
        file = self.root / 'calls.jsonl'
        return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []

    def transport(self, args, **kwargs):
        # Exercise the actual runner against a real controlled child process.
        return self.real_popen([sys.executable, str(self.fixture), json.dumps(args)], **kwargs)

    def environment(self, triple, fault=''):
        env = dict(PATH=os.environ.get('PATH', ''), TMPDIR=str(self.root),
                   FIXTURE_ROOT=str(self.root), FIXTURE_TRIPLE=triple, FIXTURE_FAULT=fault,
                   PROGRAMFILES=str(self.root), **{'PROGRAMFILES(X86)': str(self.root)},
                   INCLUDE='preconfigured-include', LIB='preconfigured-lib')
        for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT'):
            if key in os.environ:
                env[key] = os.environ[key]
        return env

    def contexts(self, matrix, fault='', missing=(), vs=True, extra_env=None):
        name, system, machine, triple = matrix
        stack = ExitStack()
        stack.enter_context(patch.dict(os.environ, self.environment(triple, fault) | (extra_env or {}), clear=True))
        stack.enter_context(patch.object(native.platform, 'system', return_value=system))
        stack.enter_context(patch.object(native.platform, 'machine', return_value=machine))
        stack.enter_context(patch.object(native.subprocess, 'Popen', side_effect=self.transport))
        def lookup(tool, path=None):
            if tool in missing or (not vs and tool == 'vswhere.exe'):
                return None
            file = self.root / 'tools' / tool
            return str(file) if file.exists() else None
        stack.enter_context(patch.object(native.shutil, 'which', side_effect=lookup))
        stack.enter_context(redirect_stdout(io.StringIO()))
        return stack

    def run_fixture(self, matrix, **kwargs):
        with self.contexts(matrix, **kwargs):
            native.run_checks(matrix[0], self.candidate)

    def test_all_three_platforms_run_prescribed_builder_env_preflight_and_transport(self):
        for matrix in MATRIX:
            with self.subTest(platform=matrix[0]):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                self.run_fixture(matrix)
                calls = self.calls()
                cargo = [c for c in calls if c['args'][0] == 'cargo' and '--locked' in c['args']]
                self.assertTrue(cargo)
                for call in calls:
                    self.assertEqual(call['cwd'], str(self.candidate))
                    env = call['env']
                    self.assertEqual(env['CARGO_BUILD_JOBS'], '2')
                    self.assertEqual(env['CARGO_INCREMENTAL'], '0')
                    self.assertEqual(env['CARGO_PROFILE_DEV_DEBUG'], '0')
                    self.assertEqual(env['CARGO_PROFILE_TEST_DEBUG'], '0')
                    self.assertNotIn('RUSTFLAGS', env)
                    self.assertNotIn('CARGO_ENCODED_RUSTFLAGS', env)
                    self.assertEqual(Path(env['CARGO_TARGET_DIR']).parent, Path(env['TMPDIR']))
                    self.assertNotEqual(Path(env['CARGO_TARGET_DIR']).parent, self.candidate)
                for call in cargo:
                    args = call['args']
                    if args[2] == 'metadata':
                        self.assertIn('--all-features', args)
                        self.assertEqual(args[args.index('--filter-platform') + 1], matrix[3])
                    else:
                        self.assertNotIn('--all-features', args)
                        self.assertIn('profile.dev.build-override.debug=0', args)
                        self.assertIn('profile.test.build-override.debug=0', args)
                        self.assertEqual(args[args.index('--target') + 1], matrix[3])
                args_list = [c['args'] for c in cargo]
                self.assertTrue(any('--no-run' in a for a in args_list))
                self.assertEqual(args_list[-1][2], 'build')
                self.assertIn('hello_world', args_list[-1])
                self.assertFalse(any(a[2] == 'run' for a in args_list))
                if matrix[0].startswith('macos'):
                    check = next(a for a in args_list if a[2] == 'check')
                    self.assertIn('--all-targets', check)
                    self.assertTrue({'gpui', 'gpui_platform', 'gpui_macos', 'gpui_apple'}.issubset(check))
                    self.assertIn('gpui/test-support,gpui_platform/font-kit', check)
                    self.assertNotIn('runtime_shaders', str(args_list))
                    self.assertTrue(any('metallib' in c['args'] and '-o' in c['args'] for c in calls))
                else:
                    check = next(a for a in args_list if a[2] == 'check')
                    self.assertTrue({'gpui', 'gpui_platform', 'gpui_windows', '--lib'}.issubset(check))
                    self.assertIn('--release', args_list[-1])
                    settings = {a for a in args_list[-1] if a.startswith('profile.')}
                    self.assertTrue({'profile.release.debug-assertions=false',
                        'profile.release.build-override.debug-assertions=false',
                        'profile.release.lto=false', 'profile.release.opt-level=1',
                        'profile.release.codegen-units=16'}.issubset(settings))
                    self.assertEqual(cargo[-1]['env']['GPUI_FXC_PATH'], str(self.root / 'tools/fxc.exe'))
                    self.assertTrue(any(Path(c['args'][0]).name == 'rc.exe' for c in calls))

    def test_executable_selection_excludes_native_graphics_and_preserves_exact_cpu_allowlist(self):
        expected_mac = {
            'window::tests::display_id_for_screen_returns_none_for_null_screen',
            'text_system::tests::test_layout_line_bom_char',
            'text_system::tests::test_layout_line_zwnj_insertion',
            'text_system::tests::test_layout_line_zwnj_edge_cases',
        }
        expected_windows = {
            'dialog::tests::task_dialog_cancellation_requires_cancel_button_or_internal_request',
            'dialog::tests::closing_owner_cancels_every_outstanding_dialog',
            'dialog::tests::closed_owner_waits_for_active_dialog_but_queued_requests_stay_cancelled',
            'dialog::tests::cancelling_one_request_does_not_cancel_its_owner_or_other_requests',
            'dialog::tests::dialogs_serialize_per_owner',
            'dialog::tests::ownerless_request_can_be_cancelled_without_a_window',
            'direct_write::tests::test_cluster_map', 'platform::tests::test_encode_restart_arguments',
        }
        for matrix in MATRIX:
            with self.subTest(platform=matrix[0]):
                selected = [s for s in native.build_stages(matrix[0], '1.98.1') if s.tests]
                exact = [s for s in selected if '--exact' in s.args]
                names = {s.args[s.args.index('--exact') + 1] for s in exact}
                self.assertEqual(names, expected_windows if matrix[0].startswith('windows') else expected_mac)
                self.assertTrue(all(s.exact_count == 1 for s in exact))
                core = [s for s in selected if '--exact' not in s.args]
                self.assertEqual([s.args[s.args.index('-p') + 1] for s in core], ['gpui', 'gpui_wgpu'])
                for stage in core:
                    skips = [stage.args[i+1] for i, token in enumerate(stage.args) if token == '--skip']
                    self.assertEqual(set(skips), {
                        'wgpu_atlas::tests::before_frame_skips_uploads_for_removed_texture',
                        'wgpu_atlas::tests::remove_deallocates_tile_space_for_reuse',
                        'wgpu_atlas::tests::reused_texture_id_has_new_generation',
                    })
                self.assertNotIn('--ignored', str(selected))
                self.assertNotIn('screen-capture', str(selected))
                self.assertTrue(all('--lib' in s.args for s in selected))

    def test_candidate_cannot_choose_python_commands_or_toolchain(self):
        script = self.candidate / 'scripts/ci/native_checks.py'
        script.parent.mkdir(parents=True)
        sentinel = self.root / 'candidate-executed'
        script.write_text(f'from pathlib import Path; Path({str(sentinel)!r}).touch()')
        (script.parent / 'rust-toolchain.toml').write_text('[toolchain]\nchannel="untrusted"\n')
        (self.candidate / 'rust-toolchain.toml').write_text('[toolchain]\nchannel="nightly"\n')
        self.run_fixture(MATRIX[0])
        self.assertFalse(sentinel.exists())
        calls = self.calls()
        self.assertFalse(any('untrusted' in str(c['args']) or 'nightly' in str(c['args']) for c in calls))
        self.assertEqual(calls[0]['args'], ['rustup', 'toolchain', 'install', '1.98.1', '--profile', 'minimal'])

    def test_wrong_and_unknown_host_fail_before_any_child(self):
        for name, system, machine in (('macos-arm64', 'Linux', 'aarch64'),
                                      ('macos-arm64', 'Darwin', 'x86_64'),
                                      ('macos-x86_64', 'Darwin', 'arm64'),
                                      ('windows-x86_64', 'Windows', 'ARM64'),
                                      ('untrusted-platform', 'Linux', 'x86_64')):
            with self.subTest(name=name, machine=machine), patch.object(native.platform, 'system', return_value=system), \
                 patch.object(native.platform, 'machine', return_value=machine), \
                 patch.object(native.subprocess, 'Popen') as spawn:
                with self.assertRaisesRegex(native.NativeCheckError, 'host|unsupported'):
                    native.run_checks(name, self.candidate)
                spawn.assert_not_called()

    def test_rust_host_mismatch_stops_before_native_tools_and_cargo_build(self):
        for matrix in MATRIX:
            with self.subTest(platform=matrix[0]):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                with self.assertRaisesRegex(native.NativeCheckError, 'Rust host'):
                    self.run_fixture(matrix, fault='rust-host')
                self.assertEqual([c['args'][0] for c in self.calls()], ['rustup', 'rustc'])

    def test_failure_and_zero_tests_stop_before_final_link(self):
        for fault, pattern in (('command-failure', 'exited 17'), ('zero-tests', 'nonzero'),
                               ('ignored-only', 'nonzero')):
            with self.subTest(fault=fault):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                with self.assertRaisesRegex(native.NativeCheckError, pattern):
                    self.run_fixture(MATRIX[2], fault=fault)
                self.assertFalse(any(c['args'][:3] == ['cargo', '+1.98.1', 'build'] for c in self.calls()))

    def test_lock_drift_rejected_before_and_after_child_execution(self):
        lock = self.candidate / 'Cargo.lock'
        lock.write_bytes(lock.read_bytes() + b'\n')
        with self.contexts(MATRIX[0]), self.assertRaisesRegex(native.NativeCheckError, 'lock drifted'):
            native.run_checks(MATRIX[0][0], self.candidate)
        self.assertEqual(self.calls(), [])
        shutil.copyfile(ROOT / 'Cargo.lock', lock)
        with self.assertRaisesRegex(native.NativeCheckError, 'lock drifted'):
            self.run_fixture(MATRIX[0], fault='lock-drift')
        self.assertEqual(self.calls()[-1]['args'][2], 'check')

    def test_each_core_library_must_execute_nonzero_tests(self):
        for package in ('gpui', 'gpui_wgpu'):
            with self.subTest(package=package):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                with self.assertRaisesRegex(native.NativeCheckError, 'nonzero'):
                    self.run_fixture(MATRIX[0], fault='zero-' + package)
                last = self.calls()[-1]['args']
                self.assertEqual(last[last.index('-p') + 1], package)
                self.assertNotIn('--exact', last)

    def test_xcode_16_4_is_selected_locally_when_installed(self):
        real_is_dir = Path.is_dir
        def is_dir(path):
            return str(path) == '/Applications/Xcode_16.4.app/Contents/Developer' or real_is_dir(path)
        with patch.object(Path, 'is_dir', is_dir):
            self.run_fixture(MATRIX[0], extra_env={'DEVELOPER_DIR': '/previous/selection'})
        call = next(c for c in self.calls() if c['args'][0] == 'xcodebuild')
        self.assertEqual(call['env']['DEVELOPER_DIR'], '/Applications/Xcode_16.4.app/Contents/Developer')

    def test_missing_windows_resource_compiler_is_a_preflight_failure(self):
        with self.assertRaisesRegex(native.NativeCheckError, 'missing native tool: rc.exe'):
            self.run_fixture(MATRIX[2], missing=('rc.exe',))
        self.assertFalse(any('--locked' in c['args'] for c in self.calls()))

    def test_missing_shader_tools_fail_not_skip(self):
        cases = ((MATRIX[0], dict(fault='missing-metal'), 'exited 69'),
                 (MATRIX[1], dict(fault='missing-metal'), 'exited 69'),
                 (MATRIX[2], dict(missing=('fxc.exe',)), 'missing shader compiler'),
                 (MATRIX[2], dict(fault='fxc-failure'), 'exited 23'))
        for matrix, kwargs, message in cases:
            with self.subTest(platform=matrix[0], kwargs=kwargs):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                with self.assertRaisesRegex(native.NativeCheckError, message):
                    self.run_fixture(matrix, **kwargs)
                self.assertFalse(any('--locked' in c['args'] for c in self.calls()))

    def test_preconfigured_windows_without_vswhere_still_probes_real_tools(self):
        self.run_fixture(MATRIX[2], vs=False)
        tools = {Path(c['args'][0]).name for c in self.calls()}
        self.assertTrue({'cl.exe', 'link.exe', 'rc.exe', 'cmake.exe', 'fxc.exe'}.issubset(tools))
        self.assertNotIn('cmd.exe', tools)

    def test_windows_devenv_nonzero_is_not_hidden_by_plausible_stdout(self):
        with self.assertRaisesRegex(native.NativeCheckError, 'exited 13'):
            self.run_fixture(MATRIX[2], fault='vs-failure')
        self.assertEqual(Path(self.calls()[-1]['args'][0]).name, 'cmd.exe')

    def test_fxc_requires_single_existing_file_and_chooses_numeric_newest_sdk(self):
        for path in (str(self.root / 'tools'), 'missing.exe',
                     str(self.root / 'tools/fxc.exe') + '\n' + str(self.root / 'tools/rc.exe')):
            with self.subTest(path=path), self.assertRaises(native.NativeCheckError):
                native.fxc_path({'GPUI_FXC_PATH': path})
        for version in ('10.0.9.0', '10.0.10.0'):
            path = self.root / 'sdk/bin' / version / 'x64/fxc.exe'
            path.parent.mkdir(parents=True)
            path.touch()
        with patch.object(native.shutil, 'which', return_value=None):
            self.assertEqual(native.fxc_path({'WINDOWSSDKDIR': str(self.root / 'sdk')}),
                             self.root / 'sdk/bin/10.0.10.0/x64/fxc.exe')

    def test_missing_shader_output_fails_even_when_cargo_exits_zero(self):
        for matrix in (MATRIX[0], MATRIX[2]):
            with self.subTest(platform=matrix[0]), self.assertRaisesRegex(native.NativeCheckError, 'native shader output'):
                self.run_fixture(matrix, fault='no-shader-output')

    def test_ambient_overrides_rejected_without_mutating_original_or_global_config(self):
        for key in ('RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_TARGET_DIR',
                    'CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_RUNNER', 'CARGO_PROFILE_RELEASE_DEBUG_ASSERTIONS'):
            with self.subTest(key=key), self.assertRaisesRegex(native.NativeCheckError, 'ambient'):
                native.build_environment({key: 'unsafe'}, self.root)
        env = {'PATH': 'original', 'CARGO_HOME': 'keep-global-config'}
        changed = native.build_environment(env, self.root)
        self.assertEqual(env, {'PATH': 'original', 'CARGO_HOME': 'keep-global-config'})
        self.assertEqual(changed['CARGO_HOME'], 'keep-global-config')

    def test_summary_rejects_empty_ignored_malformed_or_aggregated_success(self):
        good = 'test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 4 filtered out;\n'
        for bad in ('', 'running 1 test', good + good, good.replace('1 passed', '0 passed'),
                    good.replace('0 failed', '1 failed'), good.replace('0 ignored', '1 ignored'),
                    good.replace('1 passed', '2 passed')):
            with self.subTest(output=bad), self.assertRaises(native.NativeCheckError):
                native.check_test_output(bad, exact_count=1)
        with redirect_stdout(io.StringIO()):
            native.check_test_output(good, exact_count=1)

    def test_cli_unknown_platform_and_real_linux_host_are_nonzero_without_native_execution(self):
        for args in (['--platform', 'freebsd', '--candidate', str(self.candidate)],
                     ['--platform', 'macos-arm64', '--candidate', str(self.candidate)]):
            # Direct CLI host rejection is specifically Linux-only; transport fixtures above are portable.
            if sys.platform != 'linux' and args[1] == 'macos-arm64':
                continue
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/ci/native_checks.py'), *args],
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('install-rust', result.stdout)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        base = Path(os.environ.get('TMPDIR', ROOT / '.scratch/tests')).resolve()
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='native-runner-', dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.checked = 0
        class Guard:
            def check(inner):
                self.checked += 1
        self.guard = Guard()

    def runner(self, **kwargs):
        return native.Runner(self.root, dict(os.environ), self.root, self.guard, **kwargs)

    def test_large_stdout_and_stderr_are_drained_and_native_status_checked(self):
        runner = self.runner()
        with redirect_stdout(io.StringIO()):
            output = runner.run('large', [sys.executable, '-c',
                'import sys; sys.stdout.write("a"*200000); sys.stderr.write("b"*200000)'], timeout=10)
        self.assertEqual(len(output), 200000)
        self.assertEqual(self.checked, 1)
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(native.NativeCheckError, 'exited 7'):
            runner.run('fails', [sys.executable, '-c', 'print("plausible success"); raise SystemExit(7)'])
        self.assertEqual(self.checked, 2)
        self.assertIn('plausible success', (self.root / 'logs/02-fails.stdout.log').read_text())

    def test_timeout_stops_real_owned_process_and_retains_partial_log(self):
        runner = self.runner()
        started = time.monotonic()
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(native.NativeCheckError, 'timed out'):
            runner.run('hang', [sys.executable, '-c',
                'import time; print("started", flush=True); time.sleep(30)'], timeout=0.2)
        self.assertLess(time.monotonic() - started, 10)
        self.assertIn('started', (self.root / 'logs/01-hang.stdout.log').read_text())
        self.assertEqual(self.checked, 1)

    def test_primary_child_status_survives_cleanup_and_lock_failures(self):
        runner = self.runner()
        class BadGuard:
            def check(self):
                raise native.NativeCheckError('lock changed')
        runner.guard = BadGuard()
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(native.NativeCheckError, 'exited 7.*lock changed'):
            runner.run('failed-lock', [sys.executable, '-c', 'raise SystemExit(7)'])
        runner.guard = self.guard
        with patch.object(runner, 'stop', side_effect=OSError('teardown failed')), \
             redirect_stdout(io.StringIO()), \
             self.assertRaisesRegex(native.NativeCheckError, 'exited 7.*teardown failed'):
            runner.run('failed-cleanup', [sys.executable, '-c', 'raise SystemExit(7)'])

    def test_total_budget_and_output_bound_are_fail_closed(self):
        runner = self.runner(max_output=1024)
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(native.NativeCheckError, 'output exceeded'):
            runner.run('noisy', [sys.executable, '-c', 'print("x"*100000)'])
        runner.deadline = time.monotonic() - 1
        with patch.object(native.subprocess, 'Popen') as spawn, self.assertRaisesRegex(native.NativeCheckError, 'total 60-minute'):
            runner.run('late', [sys.executable, '-c', 'print("must not run")'])
        spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
