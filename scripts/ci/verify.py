"""Read-only worker. Import candidates stay bare Git data; main may run untrusted tests."""
import json
import os
from pathlib import Path
import subprocess
import sys

from gate import GateError, REPOSITORY, require, runtime_snapshot, sha, snapshot_value

REMOTE = f'https://github.com/{REPOSITORY}.git'
ROOT = Path(__file__).resolve().parents[2]


def git(repo, *args):
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
               GIT_TERMINAL_PROMPT='0', GIT_NO_REPLACE_OBJECTS='1')
    try:
        return subprocess.check_output(
            ['git', '-c', 'core.hooksPath=/dev/null', '-C', str(repo), *args],
            env=env, stderr=subprocess.PIPE, timeout=600)
    except subprocess.CalledProcessError as exc:
        raise GateError('Git object acquisition/inspection failed') from exc


def acquire(snapshot, scratch, remote=REMOTE):
    snapshot_value(snapshot)
    scratch = Path(scratch).resolve()
    scratch.mkdir(parents=True, exist_ok=False)
    objects = scratch / 'objects.git'
    git(scratch, 'init', '--bare', '--template=', str(objects))
    git(objects, 'fetch', '--no-tags', '--no-recurse-submodules', remote,
        f'+refs/heads/{snapshot["base_ref"]}:refs/heads/accepted',
        f'+refs/pull/{snapshot["pr"]}/head:refs/heads/candidate')
    for name, expected in [('accepted', snapshot['base']), ('candidate', snapshot['head'])]:
        actual = git(objects, 'rev-parse', f'refs/heads/{name}^{{commit}}').decode().strip()
        require(actual == expected, f'{name} changed during Git acquisition')
    return objects


def unique_json(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate candidate receipt key')
        value[key] = item
    return value


def import_command(controller, objects, snapshot, scratch):
    snapshot_value(snapshot)
    controller, objects = Path(controller).resolve(), Path(objects).resolve()
    require(git(controller, 'rev-parse', 'HEAD').decode().strip() == snapshot['controller'],
            'controller checkout mismatch')
    parents = git(objects, 'show', '-s', '--format=%P', snapshot['head']).decode().split()
    require(parents == [snapshot['base']], 'import candidate must have exactly B as its sole parent')
    entry = git(objects, 'ls-tree', snapshot['head'], '--', 'PINRAIL_IMPORT.json').decode().split()
    require(len(entry) == 4 and entry[:2] == ['100644', 'blob'], 'missing/nonregular import receipt')
    oid = sha(entry[2])
    require(int(git(objects, 'cat-file', '-s', oid)) <= 65536, 'candidate receipt too large')
    try:
        receipt = json.loads(git(objects, 'cat-file', 'blob', oid), object_pairs_hook=unique_json)
    except (ValueError, UnicodeError) as exc:
        raise GateError('invalid candidate receipt JSON') from exc
    require(isinstance(receipt, dict), 'candidate receipt must be an object')
    upstream = sha(receipt.get('upstream'))
    # The receipt is NOT authority. Only the committed controller's inventory can allow U.
    baseline = json.loads(git(controller, 'show',
                              f'{snapshot["controller"]}:import/baselines/{upstream}.json'))
    require(isinstance(baseline, dict), 'invalid committed baseline')
    scope_flag = {'private-evaluation-only': '--private-evaluation',
                  'reviewed-source-import': '--source-import'}.get(baseline.get('scope'))
    require(scope_flag is not None, 'unsupported committed baseline scope')
    return [str(controller / 'import' / 'run'), 'verify', '--upstream', upstream,
            '--controller-rev', snapshot['controller'], '--accepted-repo', str(objects),
            '--accepted-base', snapshot['base'], '--candidate-repo', str(objects),
            '--candidate-sha', snapshot['head'], '--scratch', str(Path(scratch).resolve()),
            scope_flag]


def worker_environment(scratch):
    env = {key: value for key, value in os.environ.items()
           if key not in {'GH_TOKEN', 'GITHUB_TOKEN', 'ACTIONS_RUNTIME_TOKEN',
                          'ACTIONS_ID_TOKEN_REQUEST_TOKEN', 'GITHUB_OUTPUT', 'GITHUB_ENV',
                          'GITHUB_PATH', 'GITHUB_STATE', 'GITHUB_STEP_SUMMARY'}}
    tmp = Path(scratch).resolve() / 'tmp'
    tmp.mkdir(parents=True, exist_ok=True)
    env.update(TMPDIR=str(tmp), TMP=str(tmp), TEMP=str(tmp), PYTHONDONTWRITEBYTECODE='1',
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0',
               GIT_NO_REPLACE_OBJECTS='1')
    # Preserve the workflow's pinned setup-java environment. Copybara v20260921
    # contains Java class version 69 and cannot run on the runner's Java 21.
    # No display/socket connection to a live desktop, even in a manually invoked worker.
    for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'XDG_RUNTIME_DIR'):
        env.pop(key, None)
    return env


def main():
    try:
        snapshot = runtime_snapshot()
        require(git(ROOT, 'rev-parse', 'HEAD').decode().strip() == snapshot['controller'],
                'controller checkout mismatch')
        scratch = Path(os.environ['GITHUB_WORKSPACE']).resolve() / '.scratch'
        env = worker_environment(scratch)
        objects = acquire(snapshot, scratch / 'acquire')
        if snapshot['base_ref'] == 'upstream-import':
            command = import_command(ROOT, objects, snapshot, scratch / 'verify')
            subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=2400)
        else:
            # Only this separate, secret-free/read-only job may materialize and execute C.
            # Main must contain current B so exact-head compilation covers integration.
            git(objects, 'merge-base', '--is-ancestor', snapshot['base'], snapshot['head'])
            candidate = scratch / 'candidate'
            git(objects, 'worktree', 'add', '--detach', str(candidate), snapshot['head'])
            subprocess.run([sys.executable, str(ROOT / 'scripts/ci/main_checks.py'), str(candidate)],
                           cwd=ROOT, env=env, check=True, timeout=3300)
    except (GateError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f'Worker refused/failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
