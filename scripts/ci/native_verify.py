"""Read-only exact-head native worker; never admits generated import candidates."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

from gate import GateError, NATIVE_PLATFORMS, NATIVE_SUITE, require, runtime_snapshot, snapshot_value
from verify import REMOTE, acquire, git, worker_environment

ROOT = Path(__file__).resolve().parents[2]


def prepare_candidate(snapshot, controller, scratch, *, remote=REMOTE):
    snapshot_value(snapshot, suite=NATIVE_SUITE)
    controller, scratch = Path(controller).resolve(), Path(scratch).resolve()
    require(git(controller, 'rev-parse', 'HEAD').decode().strip() == snapshot['controller'],
            'controller checkout mismatch')
    require(not git(controller, 'status', '--porcelain', '--untracked-files=all'),
            'controller checkout is not clean')
    # Own a fresh directory; never clean/reset/reuse a prior candidate or its hooks.
    scratch.mkdir(parents=True, exist_ok=False)
    objects = acquire(snapshot, scratch / 'acquire', remote, suite=NATIVE_SUITE)
    git(objects, 'merge-base', '--is-ancestor', snapshot['base'], snapshot['head'])
    candidate = scratch / 'candidate'
    git(objects, 'worktree', 'add', '--detach', str(candidate), snapshot['head'])
    require(git(candidate, 'rev-parse', 'HEAD').decode().strip() == snapshot['head'],
            'materialized candidate mismatch')
    require(not git(candidate, 'status', '--porcelain', '--untracked-files=all'),
            'materialized candidate is not clean')
    return candidate


def run_worker(snapshot, platform, controller, scratch, *, remote=REMOTE):
    require(platform in NATIVE_PLATFORMS, 'unsupported native platform')
    candidate = prepare_candidate(snapshot, controller, scratch, remote=remote)
    controller = Path(controller).resolve()
    env = worker_environment(scratch)
    # The driver's own location supplies policy/toolchain. C supplies build inputs only.
    # -E/-s reject ambient Python path/user-site injection; -B keeps K unmodified.
    subprocess.run([sys.executable, '-E', '-s', '-B', str(controller / 'scripts/ci/native_checks.py'),
                    '--platform', platform, '--candidate', str(candidate)],
                   cwd=controller, env=env, check=True, timeout=3300)
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=NATIVE_PLATFORMS, required=True)
    args = parser.parse_args()
    try:
        snapshot = runtime_snapshot(suite=NATIVE_SUITE)
        run_worker(snapshot, args.platform, ROOT,
                   Path(os.environ['GITHUB_WORKSPACE']).resolve() / '.scratch/native')
    except (GateError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f'Native worker refused/failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
