"""Trusted-main exact-head check publisher. Never reads or executes candidate files."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

REPOSITORY = 'lepahc/pinrail'
REPOSITORY_ID = 1386398251
CHECKS = {'upstream-import': 'pinrail-import-integrity-v1', 'main': 'pinrail-main-v1'}
PR_ACTIONS = {'opened', 'synchronize', 'reopened', 'edited', 'ready_for_review'}
SNAPSHOT_KEYS = {'pr', 'head', 'base', 'base_ref', 'controller', 'run_id', 'attempt'}


class GateError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise GateError(message)


def sha(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{40}', value) is not None,
            'expected literal full lowercase Git SHA')
    return value


def number(value):
    require(type(value) is int and 0 < value < 2**63, 'expected positive integer')
    return value


def decimal(value):
    require(isinstance(value, str) and re.fullmatch('[1-9][0-9]{0,18}', value) is not None,
            'expected literal positive decimal identifier')
    number(int(value))
    return value


def object_value(value):
    require(isinstance(value, dict), 'expected JSON object')
    return value


def repository(value):
    value = object_value(value)
    require(value.get('full_name') == REPOSITORY and value.get('id') == REPOSITORY_ID,
            'wrong repository; fork candidates are not supported by this route')


def pull_request(value):
    value = object_value(value)
    pr_number = number(value.get('number'))
    require(value.get('state') == 'open' and value.get('merged') is False, 'PR is not open/unmerged')
    head, base = object_value(value.get('head')), object_value(value.get('base'))
    repository(head.get('repo'))
    repository(base.get('repo'))
    require(base.get('ref') in CHECKS, 'unsupported PR base')
    return {'pr': pr_number, 'head': sha(head.get('sha')), 'base': sha(base.get('sha')),
            'base_ref': base['ref']}


def request(event_name, event):
    event = object_value(event)
    repository(event.get('repository'))
    if event_name == 'pull_request_target':
        require(event.get('action') in PR_ACTIONS, 'unsupported PR action')
        result = pull_request(event.get('pull_request'))
        require(number(event.get('number')) == result['pr'], 'event PR number mismatch')
        return result
    require(event_name == 'repository_dispatch' and event.get('action') == 'pinrail-verify',
            'unsupported event')
    payload = object_value(event.get('client_payload'))
    require(set(payload) == {'pr', 'head_sha'}, 'dispatch accepts only pr and head_sha')
    return {'pr': number(payload['pr']), 'head': sha(payload['head_sha'])}


def snapshot_value(value):
    value = object_value(value)
    require(set(value) == SNAPSHOT_KEYS, 'invalid resolver snapshot fields')
    number(value['pr'])
    for key in ('head', 'base', 'controller'):
        sha(value[key])
    require(value['base_ref'] in CHECKS, 'unsupported snapshot base')
    for key in ('run_id', 'attempt'):
        decimal(value[key])
    return value


def ref(api, branch):
    result = object_value(api.call('GET', f'/git/ref/heads/{branch}'))
    obj = object_value(result.get('object'))
    require(obj.get('type') == 'commit', 'branch does not identify a commit')
    return sha(obj.get('sha'))


def live(api, pr_number, controller):
    repo = api.call('GET', '')
    repository(repo)
    require(repo.get('default_branch') == 'main', 'default branch changed')
    require(ref(api, 'main') == controller, 'controller main advanced; dispatch a fresh run')
    result = pull_request(api.call('GET', f'/pulls/{pr_number}'))
    require(result['pr'] == pr_number, 'API PR number mismatch')
    require(ref(api, result['base_ref']) == result['base'], 'PR base is not current branch head')
    require(result['head'] != result['base'], 'candidate equals accepted base')
    return result


def summary(snapshot):
    return (f"Repository: `{REPOSITORY}`\n\nPR: #{snapshot['pr']}\n\n"
            f"Controller/policy commit K: `{snapshot['controller']}`\n\n"
            f"Head C: `{snapshot['head']}`\n\n"
            f"Base B ({snapshot['base_ref']}): `{snapshot['base']}`\n\n"
            'This check reports prescribed verification, not policy review or license clearance.')


def identity(snapshot):
    return f"pinrail:{snapshot['run_id']}:{snapshot['attempt']}:{snapshot['pr']}"


def run_url(snapshot):
    return f"https://github.com/{REPOSITORY}/actions/runs/{snapshot['run_id']}/attempts/{snapshot['attempt']}"


def checked_readback(api, snapshot, check_id):
    number(check_id)
    result = object_value(api.call('GET', f'/check-runs/{check_id}'))
    require(result.get('id') == check_id and result.get('head_sha') == snapshot['head']
            and result.get('name') == CHECKS[snapshot['base_ref']]
            and result.get('external_id') == identity(snapshot)
            and result.get('details_url') == run_url(snapshot), 'check identity mismatch')
    app = object_value(result.get('app'))
    require(app.get('slug') == 'github-actions', 'unexpected publisher app')
    number(app.get('id'))  # Record actual integration ID; never guess it for a rule.
    return result


def resolve(api, event_name, event, controller, run_id, attempt):
    expected = request(event_name, event)  # Validate data before any network access.
    sha(controller)
    decimal(run_id)
    decimal(attempt)
    current = live(api, expected['pr'], controller)
    require(all(current[key] == value for key, value in expected.items()), 'stale event or retargeted PR')
    snapshot = {**current, 'controller': controller, 'run_id': run_id, 'attempt': attempt}
    created = api.call('POST', '/check-runs', {
        'name': CHECKS[current['base_ref']], 'head_sha': current['head'],
        'external_id': identity(snapshot), 'details_url': run_url(snapshot), 'status': 'in_progress',
        'output': {'title': 'Verification started', 'summary': summary(snapshot)},
    })
    check_id = number(object_value(created).get('id'))
    check = checked_readback(api, snapshot, check_id)
    require(check.get('status') == 'in_progress', 'check did not start')
    return snapshot, check_id


def complete(api, snapshot, check_id, result):
    snapshot_value(snapshot)
    checked_readback(api, snapshot, check_id)  # Never PATCH an unrelated check.
    conclusion = 'success' if result == 'success' else 'cancelled' if result == 'cancelled' else 'failure'
    reason = 'Prescribed verification finished.' if result == 'success' else 'Verifier did not succeed.'
    try:
        current = live(api, snapshot['pr'], snapshot['controller'])
        require(all(current[key] == snapshot[key] for key in current), 'PR head/base changed during verification')
    except GateError as exc:
        conclusion, reason = 'failure', str(exc)
    api.call('PATCH', f'/check-runs/{check_id}', {
        'status': 'completed', 'conclusion': conclusion,
        'completed_at': datetime.now(timezone.utc).isoformat(),
        'output': {'title': f'Verification {conclusion}', 'summary': summary(snapshot) + '\n\n' + reason},
    })
    check = checked_readback(api, snapshot, check_id)
    require(check.get('status') == 'completed' and check.get('conclusion') == conclusion,
            'check completion readback mismatch')
    return check


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GateError('GitHub API redirect refused')


class GitHub:
    def __init__(self, token):
        require(bool(token), 'missing job-scoped token')
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def call(self, method, path, body=None):
        req = urllib.request.Request(
            f'https://api.github.com/repos/{REPOSITORY}{path}', method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Authorization': f'Bearer {self.token}', 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json',
                     'User-Agent': 'pinrail-trusted-controller'})
        try:
            with self.opener.open(req, timeout=60) as response:
                raw = response.read(2_000_001)
            require(len(raw) <= 2_000_000, 'API response too large')
            return json.loads(raw)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            # Never echo an API body, request headers, or untrusted event data.
            raise GateError(f'GitHub API request failed ({type(exc).__name__})') from exc


def runtime_snapshot():
    snapshot = snapshot_value(json.loads(os.environ['SNAPSHOT']))
    require(snapshot['controller'] == sha(os.environ['CONTROLLER_SHA']), 'workflow/controller mismatch')
    require(snapshot['run_id'] == decimal(os.environ['GITHUB_RUN_ID'])
            and snapshot['attempt'] == decimal(os.environ['GITHUB_RUN_ATTEMPT']), 'workflow run mismatch')
    require(os.environ['GITHUB_REPOSITORY'] == REPOSITORY, 'wrong workflow repository')
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['resolve', 'complete'])
    args = parser.parse_args()
    try:
        require(os.environ['GITHUB_REPOSITORY'] == REPOSITORY, 'wrong workflow repository')
        api = GitHub(os.environ['GH_TOKEN'])
        if args.command == 'resolve':
            event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
            snapshot, check_id = resolve(api, os.environ['GITHUB_EVENT_NAME'], event,
                                         os.environ['CONTROLLER_SHA'], os.environ['GITHUB_RUN_ID'],
                                         os.environ['GITHUB_RUN_ATTEMPT'])
            # Fixed keys and compact JSON with validated values; never emit event text.
            with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                output.write(f'snapshot={json.dumps(snapshot, separators=(",", ":"))}\n')
                output.write(f'check_id={check_id}\nbase_ref={snapshot["base_ref"]}\n')
            report = summary(snapshot)
        else:
            snapshot = runtime_snapshot()
            check_id = int(decimal(os.environ['CHECK_ID']))
            check = complete(api, snapshot, check_id, os.environ['VERIFY_RESULT'])
            report = summary(snapshot) + (f'\n\nCheck ID: `{check_id}`; '
                     f'publisher integration ID: `{check["app"]["id"]}`; '
                     f'conclusion: `{check["conclusion"]}`.\n\nRun: {run_url(snapshot)}')
        print(report)
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
            output.write(report + '\n')
    except (GateError, KeyError, TypeError, json.JSONDecodeError, OSError) as exc:
        print(f'Gate refused: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
