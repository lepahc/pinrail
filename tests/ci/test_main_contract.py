"""Configuration checks for the deliberately trusted command list and worker env."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'ci'))
import gate
import main_checks
import verify


class MainContractTests(unittest.TestCase):
    def setUp(self):
        base = Path(os.environ.get('TMPDIR', ROOT / '.scratch' / 'tests')).resolve()
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='ci-main-', dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.controller, self.candidate = self.root / 'controller', self.root / 'candidate'
        self.controller.mkdir()
        self.candidate.mkdir()
        toolchain = self.controller / 'scripts/ci/rust-toolchain.toml'
        toolchain.parent.mkdir(parents=True)
        toolchain.write_text('[toolchain]\nchannel="1.98.1"\n')
        (self.controller / 'rust-toolchain.toml').write_text('[toolchain]\nchannel="untrusted-root"\n')
        for name in ('Cargo.toml', 'Cargo.lock', 'import/pinrail_import.py',
                     'tests/ci/test_sample.py', 'tests/import/test_sample.py'):
            path = self.candidate / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    def test_main_commands_use_controller_pins_not_candidate_configuration(self):
        (self.candidate / 'rust-toolchain.toml').write_text('[toolchain]\nchannel="untrusted"\n')
        commands = main_checks.commands(self.controller, self.candidate, self.root / 'scratch')
        self.assertEqual(commands[1][-1], str(self.controller / 'import/requirements.txt'))
        self.assertIn('--require-hashes', commands[1])
        self.assertIn(['rustup', 'toolchain', 'install', '1.98.1', '--profile', 'minimal'], commands)
        self.assertIn(['cargo', '+1.98.1', 'metadata', '--locked', '--all-features', '--format-version', '1'], commands)
        self.assertIn(['cargo', '+1.98.1', 'check', '--locked', '--workspace', '--all-targets',
                       '--features', 'gpui/test-support'], commands)
        self.assertEqual(commands[-1], ['cargo', '+1.98.1', 'test', '--locked', '-p', 'gpui',
                                       '-p', 'gpui_linux', '-p', 'gpui_wgpu', '--lib',
                                       '--features', 'gpui/test-support', '--', '--test-threads=2',
                                       '--skip', 'wgpu_atlas::tests::before_frame_skips_uploads_for_removed_texture',
                                       '--skip', 'wgpu_atlas::tests::remove_deallocates_tile_space_for_reuse',
                                       '--skip', 'wgpu_atlas::tests::reused_texture_id_has_new_generation'])
        install_index = next(i for i,c in enumerate(commands) if c[0] == 'rustup')
        first_tests = next(i for i,c in enumerate(commands) if '-m' in c)
        self.assertLess(install_index, first_tests, 'importer tests invoke the pinned Cargo')
        self.assertEqual([c[5] for c in commands if '-m' in c], ['tests/ci', 'tests/import'])
        self.assertNotIn('untrusted', str(commands))

    def test_main_missing_inputs_fail_instead_of_skipping_verification(self):
        for name in ('Cargo.toml', 'Cargo.lock', 'import/pinrail_import.py',
                     'tests/ci/test_sample.py', 'tests/import/test_sample.py'):
            path = self.candidate / name
            path.unlink()
            with self.subTest(name=name), self.assertRaises(gate.GateError):
                main_checks.commands(self.controller, self.candidate, self.root / 'scratch')
            path.touch()

    def test_worker_does_not_inherit_write_control_or_display_environment(self):
        secret_names = ('GH_TOKEN', 'GITHUB_TOKEN', 'ACTIONS_RUNTIME_TOKEN',
                        'ACTIONS_ID_TOKEN_REQUEST_TOKEN', 'GITHUB_OUTPUT', 'GITHUB_ENV',
                        'GITHUB_PATH', 'GITHUB_STATE', 'GITHUB_STEP_SUMMARY',
                        'DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'XDG_RUNTIME_DIR')
        with patch.dict(os.environ, {key: 'sentinel' for key in secret_names}):
            env = verify.worker_environment(self.root)
        for key in secret_names:
            self.assertFalse(key in env, f'{key} survived worker sanitization')
        self.assertEqual(env['TMPDIR'], str(self.root / 'tmp'))
        self.assertEqual(env['GIT_CONFIG_GLOBAL'], '/dev/null')
        self.assertTrue(Path(env['TMPDIR']).is_dir())

    def test_worker_keeps_setup_java_instead_of_downgrading_to_runner_java21(self):
        with patch.dict(os.environ, {'JAVA_HOME': '/pinned/jdk25', 'JAVA_HOME_21_X64': '/runner/jdk21',
                                     'PATH': '/pinned/jdk25/bin:/usr/bin'}):
            env = verify.worker_environment(self.root)
        self.assertEqual(env['JAVA_HOME'], '/pinned/jdk25')
        self.assertEqual(env['PATH'], '/pinned/jdk25/bin:/usr/bin')


if __name__ == '__main__':
    unittest.main()
