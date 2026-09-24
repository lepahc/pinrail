"""Explicit, committed source-import authorization; no publication capability."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('authorization_importer', ROOT / 'import/pinrail_import.py')
assert spec and spec.loader
im = importlib.util.module_from_spec(spec)
spec.loader.exec_module(im)


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        (ROOT / '.scratch/tests').mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=ROOT / '.scratch/tests')
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        im.git(self.repo, 'init')
        self.rev = 'a' * 40
        self.inventory = {'upstream': self.rev, 'files': {'safe.rs': {'mode': '100644', 'sha': 'b' * 40}}}
        self.lock = b'version = 4\npackage = []\n'
        self.path = self.repo / f'import/baselines/{self.rev}.json'
        self.path.parent.mkdir(parents=True)
        lock_path = self.repo / f'import/locks/{self.rev}.lock'
        lock_path.parent.mkdir()
        lock_path.write_bytes(self.lock)

    def commit_scope(self, scope):
        self.path.write_bytes(im.canonical({'scope': scope, 'review': 'Explicit test-only review',
            'inventory': self.inventory, 'cargo_lock_sha256': hashlib.sha256(self.lock).hexdigest()}))
        im.git(self.repo, 'add', '.')
        im.git(self.repo, 'commit', '-m', 'Review fixture scope')
        return im.git(self.repo, 'rev-parse', 'HEAD').decode().strip()

    def test_source_import_requires_committed_source_scope(self):
        private = self.commit_scope('private-evaluation-only')
        source = self.commit_scope('reviewed-source-import')
        with patch.object(im, 'ROOT', self.repo):
            with self.assertRaisesRegex(im.GateError, 'not authorized for reviewed source import'):
                im.baseline(private, self.rev, self.inventory, 'reviewed-source-import')
            self.assertEqual(im.baseline(source, self.rev, self.inventory, 'reviewed-source-import')[1], self.lock)
            self.assertEqual(im.baseline(source, self.rev, self.inventory, 'private-evaluation-only')[1], self.lock)
            self.assertEqual(im.baseline(private, self.rev, self.inventory)[1], self.lock)

    def test_unknown_scope_and_new_inputs_fail_closed(self):
        unknown = self.commit_scope('complete-license-clearance')
        source = self.commit_scope('reviewed-source-import')
        with patch.object(im, 'ROOT', self.repo):
            with self.assertRaisesRegex(im.GateError, 'unknown baseline scope'):
                im.baseline(unknown, self.rev, self.inventory)
            with self.assertRaisesRegex(im.GateError, 'unknown requested scope'):
                im.baseline(source, self.rev, self.inventory, 'crate-publication')
            with self.assertRaisesRegex(im.GateError, 'unreviewed inventory'):
                im.baseline(source, self.rev, {**self.inventory, 'new-license': 'unknown'}, 'reviewed-source-import')

    def test_exactly_one_explicit_mode_required_before_discovery(self):
        for private, source in [(False, False), (True, True)]:
            args = argparse.Namespace(upstream=self.rev, accepted_base=im.SEED,
                private_evaluation=private, source_import=source)
            with self.subTest(private=private, source=source), patch.object(im, 'discover', side_effect=AssertionError('no acquisition')):
                with self.assertRaisesRegex(im.GateError, 'exactly one of --private-evaluation or --source-import'):
                    im.run_import(args)

    def test_generated_scope_not_a_complete_clearance_claim(self):
        class Inputs:
            def read(self, name):
                return {'Cargo.toml': b'[workspace]\nmembers=[]\n[workspace.dependencies]\n',
                    'Cargo.lock': b'version = 4\npackage = []\n',
                    'crates/gpui/Cargo.toml': b'[package]\nname="gpui"\n[[example]]\nname="svg"\npath="examples/svg/svg.rs"\n'}[name]
        inventory = {'upstream': self.rev, 'package_dirs': [], 'workspace_dependencies': [],
                     'license_findings': [], 'audit_limits': 'No complete clearance'}
        for scope in ('private-evaluation-only', 'reviewed-source-import'):
            generated = im.generated_files(inventory, Inputs(), 'd' * 64, 'e' * 64, self.lock, scope)
            receipt = json.loads(generated[im.RECEIPT])
            self.assertEqual(receipt['scope'], scope)
            self.assertIn(b'LICENSE-MICROSOFT-MIT', generated['README.md'])
            self.assertIn(b'No blanket permissive-only or complete license clearance', generated['README.md'])
            config = im.config_text({**inventory, 'origin_globs': []}, generated, '/local/destination.git', scope)
            if scope == 'reviewed-source-import':
                self.assertIn(b'REVIEWED SOURCE IMPORT', generated['README.md'])
                self.assertNotIn('Private evaluation; license policy pending.', config)
                self.assertIn('Reviewed source import; not complete third-party/license clearance.', config)
            else:
                self.assertIn(b'PRIVATE EVALUATION ONLY', generated['README.md'])


if __name__ == '__main__':
    unittest.main()
