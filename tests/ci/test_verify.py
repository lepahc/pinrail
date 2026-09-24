"""Network-free real-Git adapter tests; these do not stand in for Copybara proofs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'ci'))
import gate
import verify

U = 'e' * 40


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE).decode().strip()


class WorkerTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(os.environ.get('TMPDIR', ROOT / '.scratch' / 'tests')).resolve()
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='ci-', dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'remote'
        self.repo.mkdir()
        git(self.repo, 'init', '--initial-branch=upstream-import')
        git(self.repo, 'config', 'user.name', 'Fixture')
        git(self.repo, 'config', 'user.email', 'fixture@example.invalid')
        (self.repo / 'README').write_text('accepted\n')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-m', 'base')
        self.base = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'checkout', '-b', 'main')
        (self.repo / 'import' / 'baselines').mkdir(parents=True)
        (self.repo / 'import' / 'baselines' / f'{U}.json').write_text(
            '{"review":"test fixture only","scope":"private-evaluation-only"}')
        (self.repo / 'import' / 'run').write_text('#!/bin/sh\nexit 0\n')
        (self.repo / 'import' / 'run').chmod(0o755)
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-m', 'trusted controller fixture')
        self.controller = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'checkout', '-b', 'candidate', self.base)
        self.marker = self.root / 'candidate-executed'
        (self.repo / 'import').mkdir()
        (self.repo / 'import' / 'run').write_text(f'#!/bin/sh\ntouch {self.marker}\nexit 0\n')
        (self.repo / 'import' / 'run').chmod(0o755)
        (self.repo / 'PINRAIL_IMPORT.json').write_text(json.dumps({'upstream': U}))
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-m', 'untrusted candidate fixture')
        self.head = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'update-ref', 'refs/pull/7/head', self.head)
        self.snapshot = {'pr': 7, 'head': self.head, 'base': self.base, 'base_ref': 'upstream-import',
                         'controller': self.controller, 'run_id': '42', 'attempt': '1'}
        git(self.repo, 'checkout', 'main')

    def objects(self):
        return verify.acquire(self.snapshot, self.root / 'acquire', str(self.repo))

    def test_acquire_and_import_command_use_exact_objects_and_trusted_runner(self):
        objects = self.objects()
        self.assertIsNotNone(objects)
        self.assertEqual(git(objects, 'rev-parse', '--is-bare-repository'), 'true')
        command = verify.import_command(self.repo, objects, self.snapshot, self.root / 'verify')
        self.assertEqual(command, [str(self.repo / 'import' / 'run'), 'verify', '--upstream', U,
                                  '--controller-rev', self.controller, '--accepted-repo', str(objects),
                                  '--accepted-base', self.base, '--candidate-repo', str(objects),
                                  '--candidate-sha', self.head, '--scratch', str(self.root / 'verify'),
                                  '--private-evaluation'])
        subprocess.run(command, check=True, cwd=self.repo)
        self.assertFalse(self.marker.exists(), 'candidate script must remain inert Git data')

    def amend_candidate(self, receipt=None, parent_extra=False, symlink=False):
        git(self.repo, 'checkout', 'candidate')
        path = self.repo / 'PINRAIL_IMPORT.json'
        if receipt is not None:
            if path.is_symlink():
                path.unlink()
            path.write_text(receipt)
        if symlink:
            path.unlink()
            path.symlink_to('import/run')
        git(self.repo, 'add', '.')
        args = ['commit', '--allow-empty', '-m', 'modified candidate']
        if not parent_extra:
            args.append('--amend')
        git(self.repo, *args)
        self.head = git(self.repo, 'rev-parse', 'HEAD')
        self.snapshot['head'] = self.head
        git(self.repo, 'update-ref', 'refs/pull/7/head', self.head)
        git(self.repo, 'checkout', 'main')

    def test_candidate_receipt_is_only_untrusted_selector_for_committed_allowlist(self):
        for raw in ('{"upstream":"$(touch marker)"}', '{"upstream":"' + U + '\\n"}',
                    '{"upstream":"' + 'f' * 40 + '"}',
                    '{"upstream":"' + U + '","upstream":"' + U + '"}',
                    '[]', 'invalid json'):
            with self.subTest(raw=raw):
                self.amend_candidate(receipt=raw)
                objects = verify.acquire(self.snapshot, self.root / self.head, str(self.repo))
                with self.assertRaises(gate.GateError):
                    verify.import_command(self.repo, objects, self.snapshot, self.root / 'verify')
                self.assertFalse(self.marker.exists())

    def test_import_scope_comes_only_from_committed_controller_baseline(self):
        objects = self.objects()
        baseline = self.repo / 'import/baselines' / f'{U}.json'
        for scope in ('reviewed-source-import', 'unknown-policy'):
            baseline.write_text(json.dumps({'scope': scope, 'review': 'fixture'}))
            git(self.repo, 'add', '.')
            git(self.repo, 'commit', '-m', 'Change trusted fixture policy')
            self.snapshot['controller'] = git(self.repo, 'rev-parse', 'HEAD')
            if scope == 'reviewed-source-import':
                command = verify.import_command(self.repo, objects, self.snapshot, self.root / 'verify')
                self.assertEqual(command[-1], '--source-import')
            else:
                with self.assertRaisesRegex(gate.GateError, 'unsupported committed baseline scope'):
                    verify.import_command(self.repo, objects, self.snapshot, self.root / 'verify')

    def test_receipt_symlink_and_extra_parent_commit_are_rejected(self):
        self.amend_candidate(symlink=True)
        objects = self.objects()
        with self.assertRaises(gate.GateError):
            verify.import_command(self.repo, objects, self.snapshot, self.root / 'verify')
        # Restore a regular receipt, then add a second commit: sole parent no longer B.
        self.amend_candidate(receipt=json.dumps({'upstream': U}), parent_extra=True)
        objects = verify.acquire(self.snapshot, self.root / 'extra-parent', str(self.repo))
        with self.assertRaises(gate.GateError):
            verify.import_command(self.repo, objects, self.snapshot, self.root / 'verify')

    def test_head_and_base_movement_during_fetch_are_rejected(self):
        for ref in ('refs/pull/7/head', 'refs/heads/upstream-import'):
            with self.subTest(ref=ref):
                old = git(self.repo, 'rev-parse', ref)
                git(self.repo, 'update-ref', ref, self.controller)
                with self.assertRaises(gate.GateError):
                    verify.acquire(self.snapshot, self.root / ref.replace('/', '-'), str(self.repo))
                git(self.repo, 'update-ref', ref, old)

    def test_controller_checkout_must_match_committed_policy(self):
        objects = self.objects()
        changed = dict(self.snapshot, controller='f' * 40)
        with self.assertRaises(gate.GateError):
            verify.import_command(self.repo, objects, changed, self.root / 'verify')


if __name__ == '__main__':
    unittest.main()
