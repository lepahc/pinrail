"""Native suite decisions with only the GitHub transport replaced."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import gate
from test_gate import API, C, D, K, event, dispatch

SUITE = 'native-v1'
PLATFORMS = ('macos-arm64', 'macos-x86_64', 'windows-x86_64')
JOBS_PATH = '/actions/runs/42/attempts/1/jobs?per_page=100'


class NativeAPI(API):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pr['base'].update(ref='main', sha=K)
        self.jobs = [{'id': i + 10, 'run_id': 42, 'run_attempt': 1,
                      'name': f'Native worker ({platform})', 'status': 'completed',
                      'conclusion': 'success'} for i, platform in enumerate(PLATFORMS)]
        self.jobs.extend([{'id': 20, 'name': 'Resolve native snapshot'},
                          {'id': 21, 'name': 'Publish native result'}])
        self.total = None

    def call(self, method, path, body=None):
        if method == 'GET' and path == JOBS_PATH:
            self.reads.append(path)
            return {'total_count': len(self.jobs) if self.total is None else self.total,
                    'jobs': copy.deepcopy(self.jobs)}
        return super().call(method, path, body)


def native_event(api):
    result = event()
    result['pull_request'] = copy.deepcopy(api.pr)
    return result


def native_dispatch():
    result = dispatch()
    result['action'] = 'pinrail-native-verify'
    return result


class NativeGateTests(unittest.TestCase):
    def start(self, api=None, use_dispatch=False):
        api = api or NativeAPI()
        return api, gate.resolve(api, 'repository_dispatch' if use_dispatch else 'pull_request_target',
                                 native_dispatch() if use_dispatch else native_event(api),
                                 K, '42', '1', suite=SUITE)

    def finish(self, api, started, result='success'):
        return gate.complete(api, *started, result, suite=SUITE)

    def test_native_check_has_distinct_name_snapshot_and_suite_identity(self):
        for normalized in (True, False):
            for use_dispatch in (True, False):
                api, started = self.start(NativeAPI(normalize_details_url=normalized), use_dispatch)
                snapshot, check_id = started
                self.assertEqual(snapshot['suite'], 'native-v1')
                check = api.checks[check_id]
                self.assertEqual(check['head_sha'], C)
                self.assertEqual(check['name'], 'pinrail-native-v1')
                self.assertEqual(check['external_id'], 'pinrail:native-v1:42:1:7')
                finished = self.finish(api, started)
                self.assertEqual(finished['conclusion'], 'success')
                self.assertIn(JOBS_PATH, api.reads)
                self.assertEqual(api.reads[-1], f'/check-runs/{check_id}')
                self.assertEqual(api.reads.count(f'/check-runs/{check_id}'), 3)

    def test_every_platform_and_matrix_must_succeed(self):
        for result in ('failure', 'cancelled', 'skipped'):
            for index in range(3):
                api, started = self.start()
                api.jobs[index]['conclusion'] = result
                with self.subTest(result=result, index=index):
                    self.assertNotEqual(self.finish(api, started)['conclusion'], 'success')
            api, started = self.start()
            self.assertNotEqual(self.finish(api, started, result)['conclusion'], 'success')

    def test_job_collection_is_complete_current_and_literal(self):
        changes = [lambda a: a.jobs.pop(0),
                   lambda a: a.jobs.append(copy.deepcopy(a.jobs[0])),
                   lambda a: a.jobs[0].update(run_id=43),
                   lambda a: a.jobs[0].update(run_attempt=2),
                   lambda a: a.jobs[0].update(run_id='42'),
                   lambda a: a.jobs[0].update(run_attempt=True),
                   lambda a: a.jobs[0].update(status='in_progress'),
                   lambda a: a.jobs[0].update(conclusion='neutral'),
                   lambda a: a.jobs[0].update(conclusion=None),
                   lambda a: a.jobs[0].update(name='Native worker (linux)'),
                   lambda a: a.jobs.append(dict(a.jobs[0], name='Native worker (windows-arm64)')),
                   lambda a: setattr(a, 'total', 101),
                   lambda a: setattr(a, 'total', 4)]
        for change in changes:
            api, started = self.start()
            change(api)
            with self.subTest(change=change), self.assertRaises(gate.GateError):
                self.finish(api, started)
            self.assertEqual([w[0] for w in api.writes], ['POST'])
        for result in ('', 'neutral', {}, True, 'success\n'):
            api, started = self.start()
            with self.subTest(result=result), self.assertRaises(gate.GateError):
                self.finish(api, started, result)
            self.assertEqual(len(api.writes), 1)

    def test_native_dispatch_cannot_change_suite_platforms_or_command(self):
        changes = [lambda e: e.update(action='pinrail-verify'),
                   lambda e: e['client_payload'].update(platform='macos-arm64'),
                   lambda e: e['client_payload'].update(platforms=list(PLATFORMS)),
                   lambda e: e['client_payload'].update(suite='native-v1'),
                   lambda e: e['client_payload'].update(command='true'),
                   lambda e: e['client_payload'].update(head_sha=C + '\n'),
                   lambda e: e['client_payload'].update(pr=True),
                   lambda e: e['client_payload'].update(pr='7'),
                   lambda e: e['repository'].update(id=1)]
        for change in changes:
            api, evt = NativeAPI(), native_dispatch()
            change(evt)
            with self.subTest(event=evt), self.assertRaises(gate.GateError):
                gate.resolve(api, 'repository_dispatch', evt, K, '42', '1', suite=SUITE)
            self.assertEqual(api.reads, [])
            self.assertEqual(api.writes, [])
        for name in ('push', 'workflow_dispatch', 'pull_request', 'workflow_run'):
            api = NativeAPI()
            with self.assertRaises(gate.GateError):
                gate.resolve(api, name, native_event(api), K, '42', '1', suite=SUITE)
            self.assertEqual(api.reads, [])

    def test_import_forks_and_nonmain_are_excluded_before_work(self):
        for use_dispatch in (True, False):
            for change in (lambda a: a.pr['base'].update(ref='upstream-import', sha='b' * 40),
                           lambda a: a.pr['base'].update(ref='other'),
                           lambda a: a.pr['head']['repo'].update(id=1),
                           lambda a: a.pr['head']['repo'].update(full_name='fork/pinrail'),
                           lambda a: a.pr.update(state='closed'),
                           lambda a: a.pr.update(merged=True)):
                api = NativeAPI()
                change(api)
                with self.subTest(dispatch=use_dispatch, change=change), self.assertRaises(gate.GateError):
                    self.start(api, use_dispatch)
                self.assertEqual(api.writes, [])
                if not use_dispatch:
                    self.assertEqual(api.reads, [])

    def test_native_snapshots_cannot_cross_legacy_or_unknown_suites(self):
        api, (native, check_id) = self.start()
        legacy = {k: v for k, v in native.items() if k != 'suite'}
        with self.assertRaises(gate.GateError):
            gate.complete(api, native, check_id, 'success')
        with self.assertRaises(gate.GateError):
            gate.complete(api, legacy, check_id, 'success', suite=SUITE)
        for value in (dict(native, suite='legacy'), dict(native, suite='unknown'),
                      dict(native, platform='macos-arm64'), dict(native, base_ref='upstream-import')):
            with self.assertRaises(gate.GateError):
                gate.snapshot_value(value, suite=SUITE)
        for suite in ('native', 'main', '', None):
            with self.assertRaises(gate.GateError):
                gate.resolve(api, 'repository_dispatch', native_dispatch(), K, '42', '1', suite=suite)
        self.assertEqual(len(api.writes), 1)
        with self.assertRaises(gate.GateError):
            gate.request('repository_dispatch', native_dispatch())

    def test_runtime_binds_controller_run_attempt_repository_and_suite(self):
        _, (snapshot, _) = self.start()
        env = {'SNAPSHOT': json.dumps(snapshot), 'CONTROLLER_SHA': K,
               'GITHUB_RUN_ID': '42', 'GITHUB_RUN_ATTEMPT': '1',
               'GITHUB_REPOSITORY': 'lepahc/pinrail'}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(gate.runtime_snapshot(suite=SUITE), snapshot)
            with self.assertRaises(gate.GateError):
                gate.runtime_snapshot()
        for key, value in [('CONTROLLER_SHA', D), ('GITHUB_RUN_ID', '43'),
                           ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_REPOSITORY', 'fork/pinrail')]:
            with patch.dict(os.environ, dict(env, **{key: value}), clear=True):
                with self.assertRaises(gate.GateError):
                    gate.runtime_snapshot(suite=SUITE)

    def test_native_rejects_wrong_publisher_id_even_with_matching_slug(self):
        api, started = self.start()
        api.checks[started[1]]['app']['id'] = 15369
        with self.assertRaisesRegex(gate.GateError, 'publisher'):
            self.finish(api, started)
        self.assertEqual(len(api.writes), 1)

    def test_native_start_rejects_stale_events_before_creating_check(self):
        for change in (lambda a: a.pr['head'].update(sha=D),
                       lambda a: a.pr['base'].update(sha=D),
                       lambda a: a.refs.update(main=D),
                       lambda a: a.repo.update(default_branch='other')):
            api = NativeAPI()
            evt = native_event(api)
            change(api)
            with self.assertRaises(gate.GateError):
                gate.resolve(api, 'pull_request_target', evt, K, '42', '1', suite=SUITE)
            self.assertEqual(api.writes, [])

    def test_stale_completion_fails_on_original_exact_head(self):
        changes = [lambda a: a.pr['head'].update(sha=D),
                   lambda a: a.pr['base'].update(sha=D),
                   lambda a: a.refs.update(main=D),
                   lambda a: a.pr['base'].update(ref='upstream-import', sha='b' * 40),
                   lambda a: a.pr.update(state='closed'),
                   lambda a: a.pr.update(merged=True),
                   lambda a: a.repo.update(default_branch='other'),
                   lambda a: a.pr['head']['repo'].update(id=1)]
        for change in changes:
            api, started = self.start()
            change(api)
            check = self.finish(api, started)
            self.assertEqual(check['conclusion'], 'failure')
            self.assertEqual(check['head_sha'], C)

    def test_native_readback_checks_identity_before_and_after_patch(self):
        changes = {'id': 2, 'head_sha': D, 'name': 'pinrail-main-v1',
                   'external_id': 'pinrail:42:1:7',
                   'details_url': 'https://github.com/lepahc/pinrail/runs/2',
                   'app': {'id': 1, 'slug': 'other'}}
        for phase in ('resolve', 'before-patch', 'after-patch'):
            for key, wrong in changes.items():
                api = NativeAPI()
                started = None if phase == 'resolve' else self.start(api)[1]
                original = api.call

                def transport(method, path, body=None):
                    value = original(method, path, body)
                    if (method == 'GET' and path.startswith('/check-runs/') and
                            (phase != 'after-patch' or len(api.writes) == 2)):
                        value[key] = wrong
                    return value

                api.call = transport
                with self.subTest(phase=phase, key=key), self.assertRaises(gate.GateError):
                    self.start(api) if started is None else self.finish(api, started)
                self.assertEqual(len(api.writes), 2 if phase == 'after-patch' else 1)


if __name__ == '__main__':
    unittest.main()
