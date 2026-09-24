"""Recovery-boundary tests; real Git/approvals, only acquisition/Java are doubled.

Successful migrations are proved by prove_checkpoint.py against the pinned JAR.
These tests inject errors/drift at the process boundary, never a fake successful
Copybara migration as evidence of working recovery.
"""
import argparse
import copy
from contextlib import ExitStack
import importlib.util
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('importer', ROOT / 'import/pinrail_import.py')
assert spec and spec.loader
im = importlib.util.module_from_spec(spec)
spec.loader.exec_module(im)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        (ROOT / '.scratch/tests').mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=ROOT / '.scratch/tests')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.upstream = self.root / 'upstream'
        self.upstream.mkdir()
        im.git(self.upstream, 'init')
        (self.upstream / 'code.rs').write_bytes(b'// selected source\n')
        im.git(self.upstream, 'add', '.')
        im.git(self.upstream, 'commit', '-m', 'Selected change')
        self.old = im.git(self.upstream, 'rev-parse', 'HEAD').decode().strip()
        (self.upstream / 'editor').write_text('excluded')
        im.git(self.upstream, 'add', '.')
        im.git(self.upstream, 'commit', '-m', 'Excluded-only checkpoint')
        self.new = im.git(self.upstream, 'rev-parse', 'HEAD').decode().strip()
        raw = {'Cargo.toml': b'# root manifest\n', 'code.rs': b'// selected source\n'}
        files = {n: {'mode': '100644', 'sha': im.blob_sha(b)} for n, b in raw.items()}
        self.inventories = {rev: {'upstream': rev, 'files': copy.deepcopy(files),
                                  'package_dirs': [], 'origin_globs': list(files)}
                            for rev in (self.old, self.new)}
        self.source = argparse.Namespace(tree={n: dict(e, type='blob') for n, e in files.items()})
        self.controller = self.root / 'controller'
        self.controller.mkdir()
        im.git(self.controller, 'init')
        for name in im.CODE_FILES:
            (self.controller / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, self.controller / name)
        self.lock = b'version = 4\npackage = []\n'
        for rev, inventory in self.inventories.items():
            name = self.controller / f'import/baselines/{rev}.json'
            name.parent.mkdir(exist_ok=True)
            name.write_bytes(im.canonical({'scope': 'private-evaluation-only', 'review': 'Unit fixture',
                'inventory': inventory, 'cargo_lock_sha256': hashlib.sha256(self.lock).hexdigest()}))
            lock_path = self.controller / f'import/locks/{rev}.lock'
            lock_path.parent.mkdir(exist_ok=True)
            lock_path.write_bytes(self.lock)
        im.git(self.controller, 'add', '.')
        im.git(self.controller, 'commit', '-m', 'Committed controller fixture')
        self.revision = im.git(self.controller, 'rev-parse', 'HEAD').decode().strip()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(im, 'ROOT', self.controller))
        self.stack.enter_context(patch.object(im, 'UPSTREAM', str(self.upstream)))
        self.stack.enter_context(patch.object(im, 'discover', side_effect=lambda rev, _: (self.inventories[rev], self.source, {})))
        self.stack.enter_context(patch.object(im, 'Source', return_value=self.source))
        self.stack.enter_context(patch.object(im, 'ensure_jar', return_value=self.root / 'not-executed.jar'))
        self.stack.enter_context(patch.object(im, 'audit_source_inputs', return_value={}))
        self.transform = lambda inv, src, digest, approved, lock_bytes: {
            'Cargo.toml': raw['Cargo.toml'],
            'README.md': f"Checkpoint {inv['upstream']}\n".encode(),
            im.RECEIPT: im.canonical({'upstream': inv['upstream'], 'controller_code_sha256': digest,
                                     'reviewed_baseline_sha256': approved,
                                     'inventory_sha256': im.blob_sha(im.canonical(inv)), 'policy': 'unchanged'})}
        self.stack.enter_context(patch.object(im, 'generated_files', side_effect=lambda *a: self.transform(*a)))
        self.accepted = self.root / 'accepted'
        self.accepted.mkdir()
        im.git(self.accepted, 'init')
        output = {**raw, **self.transform(self.inventories[self.old], self.source,
                  im.trusted_controller(self.revision), *im.baseline(self.revision, self.old, self.inventories[self.old]))}
        for name, data in output.items():
            (self.accepted / name).write_bytes(data)
        im.git(self.accepted, 'add', '.')
        im.git(self.accepted, 'commit', '-m', f'Accepted\n\nGitOrigin-RevId: {self.old}\nCopybara-Path-RevId: {self.old}\n')
        self.base = im.git(self.accepted, 'rev-parse', 'HEAD').decode().strip()
        self.calls = []
        self.attempt = 0
        self.exit_code = 4
        self.diagnostic = True
        self.diagnostic_from = self.old
        self.force_action = None
        real_run = subprocess.run

        def process(command, **kwargs):
            if command[0] != 'java':
                return real_run(command, **kwargs)
            self.calls.append(command)
            forced = '--force' in command
            if forced and self.force_action:
                return self.force_action(command)
            message = (f'WARN: No changes from {self.diagnostic_from} up to {self.new} match any origin_files. Use --force\n'
                       if self.diagnostic else 'ERROR: unrelated configuration failure\n')
            kwargs['stdout'].write(message.encode())
            return subprocess.CompletedProcess(command, 42 if forced else self.exit_code)
        self.stack.enter_context(patch.object(im.subprocess, 'run', side_effect=process))

    def run_import(self, rev=None):
        self.attempt += 1
        self.calls = []
        self.scratch = self.root / f'run-{self.attempt}'
        return im.run_import(argparse.Namespace(upstream=rev or self.new, controller_rev=self.revision,
            accepted_repo=str(self.accepted), accepted_base=self.base, scratch=str(self.scratch),
            private_evaluation=True, jar=str(self.root / 'unused.jar')))

    def assert_no_force(self):
        self.assertTrue(all('--force' not in c for c in self.calls))
        self.assertFalse((self.scratch / 'migration/checkpoint-command.json').exists())
        self.assertFalse((self.scratch / 'migration/result.json').exists())

    def test_authorized_checkpoint_runs_exactly_one_recovery_and_propagates_failure(self):
        with self.assertRaisesRegex(im.GateError, 'Copybara checkpoint failed: exit 42'):
            self.run_import()
        self.assertEqual([('--force' in c) for c in self.calls], [False, True])
        self.assertFalse((self.scratch / 'migration/result.json').exists())

    def test_other_exit_or_diagnostic_cannot_trigger_force(self):
        for code, diagnostic, reason in [(1, True, 'Copybara failed'), (2, True, 'Copybara failed'),
                (8, True, 'Copybara failed'), (0, True, 'requires empty migration exit 4'),
                (4, False, 'requires Copybara empty-origin-range diagnostic')]:
            with self.subTest(code=code, diagnostic=diagnostic):
                self.exit_code, self.diagnostic = code, diagnostic
                with self.assertRaisesRegex(im.GateError, reason):
                    self.run_import()
                self.assertEqual(len(self.calls), 1)
                self.assert_no_force()

    def test_excluded_changes_do_not_authorize_transform_policy_drift(self):
        original = self.transform
        for kind, reason in [('cargo', 'byte/mode/path'), ('readme', 'cannot change README policy'),
                             ('receipt', 'cannot change receipt policy')]:
            def drift(inv, *args):
                value = original(inv, *args)
                if inv['upstream'] == self.new:
                    if kind == 'cargo':
                        value['Cargo.toml'] += b'# unauthorized rewrite\n'
                    elif kind == 'readme':
                        value['README.md'] += b'Broader policy\n'
                    else:
                        value[im.RECEIPT] = im.canonical({**json.loads(value[im.RECEIPT]), 'policy': 'broader'})
                return value
            self.transform = drift
            with self.subTest(kind=kind), self.assertRaisesRegex(im.GateError, reason):
                self.run_import()
            self.assertEqual(len(self.calls), 1)  # Passed accepted-base validation, reached empty origin.
            self.assert_no_force()
        self.transform = original

    def test_reviewed_selection_change_is_not_a_checkpoint_only_recovery(self):
        # Even a separately committed wider selection cannot be smuggled through
        # the empty-range recovery. It needs the ordinary selected-change route.
        self.inventories[self.new]['origin_globs'].append('extra/**')
        name = self.controller / f'import/baselines/{self.new}.json'
        name.write_bytes(im.canonical({'scope': 'private-evaluation-only', 'review': 'Wider test selection',
                                       'inventory': self.inventories[self.new],
                                       'cargo_lock_sha256': hashlib.sha256(self.lock).hexdigest()}))
        im.git(self.controller, 'add', '.')
        im.git(self.controller, 'commit', '-m', 'Commit wider selection fixture')
        self.revision = im.git(self.controller, 'rev-parse', 'HEAD').decode().strip()
        with self.assertRaisesRegex(im.GateError, 'identical reviewed input inventories'):
            self.run_import()
        self.assertEqual(len(self.calls), 1)
        self.assert_no_force()

    def test_unreviewed_inventory_or_tampered_base_stops_before_copybara(self):
        self.inventories[self.new]['extra_policy'] = 'unreviewed'
        with self.assertRaisesRegex(im.GateError, 'unreviewed inventory'):
            self.run_import()
        self.assertEqual(self.calls, [])
        self.assert_no_force()
        del self.inventories[self.new]['extra_policy']
        (self.accepted / 'code.rs').write_bytes(b'// manual drift\n')
        im.git(self.accepted, 'add', '.')
        im.git(self.accepted, 'commit', '-m', 'Tamper accepted base')
        self.base = im.git(self.accepted, 'rev-parse', 'HEAD').decode().strip()
        with self.assertRaisesRegex(im.GateError, 'byte/mode/path'):
            self.run_import()
        self.assertEqual(self.calls, [])
        self.assert_no_force()

    def test_same_pin_retry_is_true_noop_without_force(self):
        result = self.run_import(self.old)
        self.assertTrue(result['noop'])
        self.assertFalse(result['checkpoint_update'])
        self.assertEqual(result['candidate'], self.base)
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn('--force', self.calls[0])

    def test_non_forward_history_cannot_force_even_with_equal_inputs(self):
        # A valid reviewed inventory and an exact empty-range message are not
        # enough: the requested commit must really descend from the old pin.
        # Request an unrelated root with the same selected tree and an explicit
        # committed review: only the forward-ancestry gate should reject it.
        tree = im.git(self.upstream, 'rev-parse', f'{self.new}^{{tree}}').decode().strip()
        unrelated = im.git(self.upstream, 'commit-tree', tree, data=b'Unrelated root\n').decode().strip()
        self.inventories[unrelated] = {**self.inventories[self.new], 'upstream': unrelated}
        baseline = self.controller / f'import/baselines/{unrelated}.json'
        baseline.write_bytes(im.canonical({'scope': 'private-evaluation-only', 'review': 'Negative fixture',
                                          'inventory': self.inventories[unrelated],
                                          'cargo_lock_sha256': hashlib.sha256(self.lock).hexdigest()}))
        (self.controller / f'import/locks/{unrelated}.lock').write_bytes(self.lock)
        im.git(self.controller, 'add', '.')
        im.git(self.controller, 'commit', '-m', 'Review unrelated fixture')
        self.revision = im.git(self.controller, 'rev-parse', 'HEAD').decode().strip()
        self.new = unrelated
        with self.assertRaisesRegex(im.GateError, 'merge-base'):
            self.run_import()
        self.assertEqual(len(self.calls), 1)
        self.assert_no_force()

    def test_unrelated_native_marker_cannot_force_even_when_checkpoint_advances(self):
        tree = im.git(self.upstream, 'rev-parse', f'{self.old}^{{tree}}').decode().strip()
        native = im.git(self.upstream, 'commit-tree', tree, data=b'Unrelated native root\n').decode().strip()
        # Accepted raw-source equivalence passes; native ancestry is the missing
        # condition. The requested pin really DOES descend from the old receipt.
        im.git(self.accepted, 'commit', '--amend', '-m',
               f'Accepted\n\nGitOrigin-RevId: {self.old}\nCopybara-Path-RevId: {native}\n')
        self.base = im.git(self.accepted, 'rev-parse', 'HEAD').decode().strip()
        self.diagnostic_from = native
        with self.assertRaisesRegex(im.GateError, 'merge-base'):
            self.run_import()
        self.assertEqual(len(self.calls), 1)
        self.assert_no_force()

    def test_forced_candidate_still_requires_exact_parent_labels_and_tree(self):
        def forged(command):
            repo = self.scratch / 'migration/destination.git'
            tree = im.git(repo, 'rev-parse', f'{self.base}^{{tree}}').decode().strip()
            parents = [] if kind == 'parent' else ['-p', self.base]
            message = f'Forged\n\nGitOrigin-RevId: {self.new}\nCopybara-Path-RevId: {self.new}\n'
            if kind == 'labels':
                message = message.replace(self.new, self.old)
            sha = im.git(repo, 'commit-tree', tree, *parents, data=message.encode()).decode().strip()
            im.git(repo, 'update-ref', 'refs/heads/candidate', sha)
            return subprocess.CompletedProcess(command, 0)
        self.force_action = forged
        for kind, reason in [('parent', 'directly descend'), ('labels', 'exact requested origin'), ('tree', 'byte/mode/path')]:
            with self.subTest(kind=kind), self.assertRaisesRegex(im.GateError, reason):
                self.run_import()
            self.assertEqual([('--force' in c) for c in self.calls], [False, True])
            self.assertFalse((self.scratch / 'migration/result.json').exists())


if __name__ == '__main__':
    unittest.main()
