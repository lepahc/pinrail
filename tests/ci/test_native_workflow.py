"""Deployment contract checks; native.yml uses YAML's JSON subset for stdlib parsing.

These validate trusted wiring, not execution on macOS/Windows. Runtime gates and
real-Git acquisition are exercised separately, without native build dependencies.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate workflow key: {key}')
        result[key] = value
    return result


class NativeWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = json.loads((ROOT / '.github/workflows/native.yml').read_text(),
                                  object_pairs_hook=unique)

    def test_only_default_branch_sourced_events_and_fixed_native_suite(self):
        workflow = self.workflow
        self.assertEqual(workflow['on'], {
            'pull_request_target': {'branches': ['main'],
                                    'types': ['opened', 'synchronize', 'reopened', 'edited', 'ready_for_review']},
            'repository_dispatch': {'types': ['pinrail-native-verify']}})
        self.assertEqual(workflow['permissions'], {})
        self.assertEqual(workflow['env']['CONTROLLER_SHA'], '${{ github.workflow_sha }}')
        self.assertEqual(set(workflow['jobs']), {'resolve', 'verify', 'complete'})
        for key in ('resolve', 'complete'):
            job = workflow['jobs'][key]
            self.assertEqual(job['runs-on'], 'ubuntu-24.04')
            command = job['steps'][-1]['run']
            self.assertEqual(command, f'python3 -E -s -B controller/scripts/ci/gate.py {key} --suite native-v1')
            self.assertLessEqual(job['timeout-minutes'], 5)

    def test_matrix_is_fixed_complete_standard_bounded_and_fail_closed(self):
        worker = self.workflow['jobs']['verify']
        self.assertEqual(worker['needs'], 'resolve')
        self.assertEqual(worker['name'], 'Native worker (${{ matrix.platform }})')
        self.assertEqual(worker['runs-on'], '${{ matrix.runner }}')
        self.assertEqual(worker['permissions'], {'contents': 'read'})
        self.assertEqual(worker['timeout-minutes'], 60)
        self.assertEqual(worker['strategy'], {
            'fail-fast': False, 'max-parallel': 2, 'matrix': {'include': [
                {'platform': 'macos-arm64', 'runner': 'macos-15', 'python-architecture': 'arm64'},
                {'platform': 'macos-x86_64', 'runner': 'macos-15-intel', 'python-architecture': 'x64'},
                {'platform': 'windows-x86_64', 'runner': 'windows-2025', 'python-architecture': 'x64'}]}})
        self.assertNotIn('outputs', worker)
        for job in self.workflow['jobs'].values():
            self.assertNotIn('continue-on-error', job)
            for step in job['steps']:
                self.assertNotIn('continue-on-error', step)

    def test_every_checkout_is_exact_controller_without_credentials_or_submodules(self):
        for job in self.workflow['jobs'].values():
            checkouts = [s for s in job['steps'] if s.get('uses', '').startswith('actions/checkout@')]
            self.assertEqual(len(checkouts), 1)
            checkout = checkouts[0]
            self.assertEqual(checkout['uses'], 'actions/checkout@11d5960a326750d5838078e36cf38b85af677262')
            self.assertEqual(checkout['with']['repository'], 'lepahc/pinrail')
            self.assertEqual(checkout['with']['ref'], '${{ github.workflow_sha }}')
            self.assertEqual(checkout['with']['path'], 'controller')
            for option in ('persist-credentials', 'submodules', 'lfs'):
                self.assertIs(checkout['with'][option], False)

    def test_worker_uses_pinned_explicit_python_and_only_native_adapter(self):
        steps = self.workflow['jobs']['verify']['steps']
        self.assertEqual(len(steps), 4)
        setup = steps[1]
        self.assertEqual(setup['uses'], 'actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405')
        self.assertEqual(setup['id'], 'python')
        self.assertEqual(setup['with'], {'python-version': '3.13.7',
                         'architecture': '${{ matrix.python-architecture }}', 'check-latest': False,
                         'allow-prereleases': False, 'freethreaded': False, 'update-environment': False})
        mac, windows = steps[2:]
        self.assertEqual((mac['if'], mac['shell']), ("runner.os == 'macOS'", 'bash'))
        self.assertEqual((windows['if'], windows['shell']), ("runner.os == 'Windows'", 'pwsh'))
        self.assertEqual(mac['run'], '"$TRUSTED_PYTHON" -E -s -B controller/scripts/ci/native_verify.py --platform "$NATIVE_PLATFORM"')
        self.assertEqual(windows['run'], '& $env:TRUSTED_PYTHON -E -s -B controller/scripts/ci/native_verify.py --platform $env:NATIVE_PLATFORM\nif ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }')
        for step in (mac, windows):
            self.assertEqual(step['env'], {'TRUSTED_PYTHON': '${{ steps.python.outputs.python-path }}',
                             'NATIVE_PLATFORM': '${{ matrix.platform }}',
                             'SNAPSHOT': '${{ needs.resolve.outputs.snapshot }}'})
        for job in self.workflow['jobs'].values():
            for step in job['steps']:
                if 'uses' in step:
                    self.assertRegex(step['uses'], r'^(actions/checkout|actions/setup-python)@[0-9a-f]{40}$')
        self.assertNotRegex(json.dumps(self.workflow), r'secrets\.|upload-artifact|download-artifact|setup-uv|setup-java|actions/cache')

    def test_publisher_consumes_only_resolver_and_actions_results(self):
        jobs = self.workflow['jobs']
        self.assertEqual(jobs['resolve']['permissions'],
                         {'contents': 'read', 'pull-requests': 'read', 'checks': 'write'})
        self.assertEqual(jobs['resolve']['name'], 'Resolve native snapshot')
        self.assertEqual(jobs['complete']['name'], 'Publish native result')
        self.assertEqual(jobs['complete']['permissions'],
                         {'contents': 'read', 'pull-requests': 'read', 'checks': 'write', 'actions': 'read'})
        self.assertEqual(jobs['complete']['needs'], ['resolve', 'verify'])
        self.assertEqual(jobs['complete']['if'], "always() && needs.resolve.result == 'success'")
        self.assertEqual(jobs['resolve']['outputs'], {'snapshot': '${{ steps.start.outputs.snapshot }}',
                                                     'check_id': '${{ steps.start.outputs.check_id }}'})
        steps = jobs['complete']['steps']
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[-1]['env'], {'GH_TOKEN': '${{ github.token }}',
                         'SNAPSHOT': '${{ needs.resolve.outputs.snapshot }}',
                         'CHECK_ID': '${{ needs.resolve.outputs.check_id }}',
                         'VERIFY_RESULT': '${{ needs.verify.result }}'})
        self.assertNotIn('needs.verify.outputs', json.dumps(jobs['complete']))


if __name__ == '__main__':
    unittest.main()
