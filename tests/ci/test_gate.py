"""Local transport-double tests: exercise real event/freshness/publisher decisions."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'ci'))
import gate

K, B, C, D = ('a' * 40, 'b' * 40, 'c' * 40, 'd' * 40)
REPO = {'id': 1386398251, 'full_name': 'lepahc/pinrail', 'default_branch': 'main'}


def pr():
    return {'number': 7, 'state': 'open', 'merged': False,
            'head': {'sha': C, 'repo': copy.deepcopy(REPO)},
            'base': {'sha': B, 'ref': 'upstream-import', 'repo': copy.deepcopy(REPO)}}


def event():
    return {'action': 'synchronize', 'number': 7,
            'repository': copy.deepcopy(REPO), 'pull_request': pr()}


def dispatch():
    return {'action': 'pinrail-verify', 'repository': copy.deepcopy(REPO),
            'client_payload': {'pr': 7, 'head_sha': C}}


class API:
    """Only transport is faked; no fake resolution/authorization decisions."""
    def __init__(self):
        self.pr = pr()
        self.repo = copy.deepcopy(REPO)
        self.refs = {'main': K, 'upstream-import': B}
        self.checks = {}
        self.writes = []
        self.reads = []
        self.corrupt_readback = False

    def call(self, method, path, body=None):
        if method == 'GET':
            self.reads.append(path)
            if path == '':
                return copy.deepcopy(self.repo)
            if path == '/pulls/7':
                return copy.deepcopy(self.pr)
            if path.startswith('/git/ref/heads/'):
                return {'object': {'type': 'commit', 'sha': self.refs[path.rsplit('/', 1)[1]]}}
            if path.startswith('/check-runs/'):
                value = copy.deepcopy(self.checks[int(path.rsplit('/', 1)[1])])
                if self.corrupt_readback:
                    value['head_sha'] = D
                return value
        elif method == 'POST' and path == '/check-runs':
            self.writes.append((method, path, copy.deepcopy(body)))
            value = {**body, 'id': len(self.checks) + 1,
                     'app': {'id': 15368, 'slug': 'github-actions'},
                     'html_url': 'https://github.com/lepahc/pinrail/runs/1'}
            self.checks[value['id']] = value
            return copy.deepcopy(value)
        elif method == 'PATCH' and path.startswith('/check-runs/'):
            self.writes.append((method, path, copy.deepcopy(body)))
            value = self.checks[int(path.rsplit('/', 1)[1])]
            value.update(body)
            return copy.deepcopy(value)
        raise AssertionError((method, path, body))


class GateTests(unittest.TestCase):
    def start(self, api=None, evt=None, name='pull_request_target'):
        api = api or API()
        return api, gate.resolve(api, name, evt or event(), K, '42', '1')

    def test_exact_head_check_records_controller_base_and_name(self):
        api, started = self.start()
        self.assertIsNotNone(started)
        snapshot, check_id = started
        check = api.checks[check_id]
        self.assertEqual(check['head_sha'], C)
        self.assertEqual(check['name'], 'pinrail-import-integrity-v1')
        self.assertEqual(check['status'], 'in_progress')
        for identifier in (K, B, C):
            self.assertIn(identifier, check['output']['summary'])
        self.assertIn(f'/check-runs/{check_id}', api.reads)
        finished = gate.complete(api, snapshot, check_id, 'success')
        self.assertEqual(finished['conclusion'], 'success')
        self.assertEqual(api.reads[-1], f'/check-runs/{check_id}')

    def test_main_check_is_distinct(self):
        api = API()
        api.pr['base'].update(ref='main', sha=K)
        evt = event()
        evt['pull_request'] = copy.deepcopy(api.pr)
        _, (snapshot, check_id) = self.start(api, evt)
        self.assertEqual(api.checks[check_id]['name'], 'pinrail-main-v1')
        self.assertEqual(gate.complete(api, snapshot, check_id, 'success')['conclusion'], 'success')

    def test_dispatch_reads_current_pr_and_base(self):
        api, (snapshot, check_id) = self.start(evt=dispatch(), name='repository_dispatch')
        self.assertEqual(api.checks[check_id]['head_sha'], C)
        self.assertEqual(gate.complete(api, snapshot, check_id, 'success')['conclusion'], 'success')

    def test_identifiers_are_literal_full_lowercase_shas(self):
        self.assertEqual(gate.sha(C), C)
        for bad in ('c' * 39, 'C' * 40, 'c' * 41, C + '\n', ' ' + C, '--help', None, True, 12):
            with self.subTest(bad=bad), self.assertRaises(gate.GateError):
                gate.sha(bad)

    def test_invalid_dispatch_fails_before_any_api_call(self):
        changes = [lambda e: e.update(action='other'),
                   lambda e: e.update(client_payload=[]),
                   lambda e: e['client_payload'].update(pr=True),
                   lambda e: e['client_payload'].update(pr=0),
                   lambda e: e['client_payload'].update(pr='7'),
                   lambda e: e['client_payload'].update(head_sha=C + '\n'),
                   lambda e: e['client_payload'].update(controller_sha=K),
                   lambda e: e['client_payload'].pop('head_sha'),
                   lambda e: e['repository'].update(full_name='elsewhere/pinrail'),
                   lambda e: e['repository'].update(id=1)]
        for change in changes:
            api, evt = API(), dispatch()
            change(evt)
            with self.subTest(event=evt), self.assertRaises(gate.GateError):
                gate.resolve(api, 'repository_dispatch', evt, K, '42', '1')
            self.assertEqual(api.reads, [])
            self.assertEqual(api.writes, [])

    def test_unsupported_and_malformed_pr_events(self):
        for name in ('pull_request', 'push', 'workflow_dispatch', 'workflow_run'):
            with self.subTest(name=name), self.assertRaises(gate.GateError):
                gate.request(name, event())
        changes = [lambda e: e.update(action='closed'),
                   lambda e: e.update(number=8),
                   lambda e: e['pull_request']['head'].update(sha='$(touch marker)'),
                   lambda e: e['pull_request']['base'].update(ref='other'),
                   lambda e: e['pull_request']['base'].update(sha='short'),
                   lambda e: e['pull_request']['head']['repo'].update(full_name='fork/pinrail'),
                   lambda e: e['pull_request'].update(state='closed')]
        for change in changes:
            evt = event()
            change(evt)
            with self.subTest(event=evt), self.assertRaises(gate.GateError):
                gate.request('pull_request_target', evt)

    def test_start_rejects_stale_or_retargeted_event_without_writes(self):
        changes = [lambda a: a.pr['head'].update(sha=D),
                   lambda a: a.refs.update(main=D),
                   lambda a: a.refs.update(**{'upstream-import': D}),
                   lambda a: a.pr.update(state='closed'),
                   lambda a: a.pr.update(merged=True),
                   lambda a: a.pr['base'].update(ref='main', sha=K),
                   lambda a: a.repo.update(default_branch='other')]
        for change in changes:
            api = API()
            change(api)
            with self.subTest(change=change), self.assertRaises(gate.GateError):
                self.start(api)
            self.assertEqual(api.writes, [])

    def test_all_stale_completions_fail_closed_on_original_head(self):
        changes = [lambda a: a.pr['head'].update(sha=D),
                   lambda a: a.refs.update(main=D),
                   lambda a: a.refs.update(**{'upstream-import': D}),
                   lambda a: a.pr['base'].update(sha=D),
                   lambda a: a.pr['base'].update(ref='main', sha=K),
                   lambda a: a.pr.update(state='closed'),
                   lambda a: a.pr.update(merged=True),
                   lambda a: a.pr['head']['repo'].update(id=1)]
        for change in changes:
            api, (snapshot, check_id) = self.start()
            change(api)
            finished = gate.complete(api, snapshot, check_id, 'success')
            with self.subTest(change=change):
                self.assertEqual(finished['conclusion'], 'failure')
                self.assertEqual(finished['head_sha'], C)

    def test_failed_skipped_and_cancelled_verifiers_never_pass(self):
        for result, expected in [('failure', 'failure'), ('skipped', 'failure'),
                                 ('cancelled', 'cancelled'), ('', 'failure'), ('neutral', 'failure')]:
            api, (snapshot, check_id) = self.start()
            self.assertEqual(gate.complete(api, snapshot, check_id, result)['conclusion'], expected)

    def test_completion_cannot_retarget_check_id_or_publisher(self):
        for key, value in [('head_sha', D), ('name', 'pinrail-main-v1'),
                           ('external_id', 'other-run'), ('app', {'id': 1, 'slug': 'other'})]:
            api, (snapshot, check_id) = self.start()
            api.checks[check_id][key] = value
            with self.subTest(key=key), self.assertRaises(gate.GateError):
                gate.complete(api, snapshot, check_id, 'success')
            self.assertEqual(len(api.writes), 1)

    def test_start_verifies_readback_instead_of_trusting_post(self):
        api = API()
        api.corrupt_readback = True
        with self.assertRaises(gate.GateError):
            self.start(api)

    def test_snapshot_cannot_choose_a_different_workflow_or_run(self):
        _, (snapshot, _) = self.start()
        env = {'SNAPSHOT': json.dumps(snapshot), 'CONTROLLER_SHA': K,
               'GITHUB_RUN_ID': '42', 'GITHUB_RUN_ATTEMPT': '1',
               'GITHUB_REPOSITORY': REPO['full_name']}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(gate.runtime_snapshot(), snapshot)
        for key, value in [('CONTROLLER_SHA', D), ('GITHUB_RUN_ID', '43'),
                           ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_REPOSITORY', 'fork/pinrail')]:
            with self.subTest(key=key), patch.dict(os.environ, dict(env, **{key: value}), clear=True):
                with self.assertRaises(gate.GateError):
                    gate.runtime_snapshot()
        for changed in (dict(snapshot, extra='command'), dict(snapshot, pr=True),
                        dict(snapshot, head=C + '\n'), dict(snapshot, run_id='42\n')):
            with self.subTest(changed=changed), self.assertRaises(gate.GateError):
                gate.snapshot_value(changed)

    def test_completion_readback_detects_failed_patch_application(self):
        api, (snapshot, check_id) = self.start()
        original = api.call

        def transport(method, path, body=None):
            if method == 'PATCH':
                return dict(api.checks[check_id], status='completed', conclusion='success')
            return original(method, path, body)

        api.call = transport
        with self.assertRaisesRegex(gate.GateError, 'completion readback'):
            gate.complete(api, snapshot, check_id, 'success')

    def test_live_api_failure_cannot_publish_success(self):
        api, (snapshot, check_id) = self.start()
        original = api.call

        def transport(method, path, body=None):
            if method == 'GET' and path == '/pulls/7':
                raise gate.GateError('GitHub API request failed')
            return original(method, path, body)

        api.call = transport
        self.assertEqual(gate.complete(api, snapshot, check_id, 'success')['conclusion'], 'failure')

    def test_payload_titles_are_not_used_as_commands_or_check_output(self):
        evt = event()
        marker = '$(touch /SHOULD_NOT_EXIST)\n::error::injected'
        evt['pull_request']['title'] = marker
        evt['pull_request']['body'] = marker
        api, (snapshot, check_id) = self.start(evt=evt)
        gate.complete(api, snapshot, check_id, 'success')
        self.assertNotIn(marker, json.dumps(api.writes))


if __name__ == '__main__':
    unittest.main()
