#!/usr/bin/env python3
"""CPU-only standalone qualification in a real generated Git worktree.

Run inside the documented systemd resource scope. No GUI examples are executed.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('importer', ROOT / 'import/pinrail_import.py')
im = importlib.util.module_from_spec(spec)
spec.loader.exec_module(im)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('upstream', 'controller-rev', 'candidate-repo', 'candidate-sha', 'worktree', 'scratch'):
        parser.add_argument('--' + arg, required=True)
    parser.add_argument('--source-import', action='store_true', help='Qualify a reviewed-source-import candidate')
    args = parser.parse_args()
    im.validate_sha(args.upstream)
    im.validate_sha(args.candidate_sha)
    digest = im.trusted_controller(args.controller_rev)
    scratch = im.disk_scratch(args.scratch)
    worktree = Path(args.worktree).resolve()
    im.require(not worktree.exists(), 'a new actual Git worktree is required')
    candidate_repo = im.local_repo(args.candidate_repo)
    inventory, source, _ = im.discover(args.upstream, scratch)
    scope = im.SOURCE_SCOPE if args.source_import else im.PRIVATE_SCOPE
    approved, lock_bytes = im.baseline(args.controller_rev, args.upstream, inventory, scope)
    generated = im.generated_files(inventory, source, digest, approved, lock_bytes, scope)
    im.compare_entries(im.expected_entries(inventory, generated), im.git_entries(candidate_repo, args.candidate_sha))
    im.git(candidate_repo, 'worktree', 'add', '--detach', str(worktree), args.candidate_sha)
    target = worktree / '.scratch/target'
    temp = worktree / '.scratch/tmp'
    temp.mkdir(parents=True)
    env = os.environ.copy()
    for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET'):
        env.pop(key, None)
    env.update(CARGO_BUILD_JOBS='2', CARGO_TARGET_DIR=str(target), TMPDIR=str(temp), TMP=str(temp), TEMP=str(temp),
               CARGO_PROFILE_DEV_DEBUG='0', CARGO_PROFILE_TEST_DEBUG='0')
    results = {'candidate': args.candidate_sha, 'controller': args.controller_rev, 'upstream': args.upstream,
               'worktree': str(worktree), 'target': str(target), 'commands': [], 'status': 'running',
               'environment': {k: env.get(k) for k in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'TMPDIR',
                               'CARGO_BUILD_JOBS', 'CARGO_PROFILE_DEV_DEBUG', 'CARGO_PROFILE_TEST_DEBUG')}}

    def save():
        (scratch / 'results.json').write_bytes(im.canonical(results))

    def cargo(label, *arguments):
        command = ['cargo', '+1.98.1', *arguments]
        started = time.monotonic()
        with (scratch / f'{label}.stdout').open('wb') as out, (scratch / f'{label}.stderr').open('wb') as err:
            process = subprocess.run(command, cwd=worktree, env=env, stdout=out, stderr=err)
        results['commands'].append({'label': label, 'command': command, 'exit': process.returncode,
                                    'elapsed_seconds': round(time.monotonic() - started, 3)})
        save()
        im.require(process.returncode == 0, f'{label} failed: see {scratch}/{label}.stderr')
        im.require((worktree / 'Cargo.lock').read_bytes() == lock_bytes, 'Cargo changed the reviewed lock')
        print(label, 'passed', flush=True)

    save()
    try:
        # No target filter: metadata covers all retained platforms and all optional
        # features. This is resolution evidence, not cross-platform compilation.
        cargo('metadata', 'metadata', '--locked', '--all-features', '--format-version', '1')
        metadata = json.loads((scratch / 'metadata.stdout').read_bytes())
        projected = im.validate_lock_projection(source.read('Cargo.lock'), lock_bytes, inventory['cargo_projection'])
        locked = {(p['name'], p['version'], p.get('source')) for p in projected['package']}
        resolved = {(p['name'], p['version'], p.get('source')) for p in metadata['packages']}
        im.require(resolved == locked, 'all-feature metadata differs from the complete reviewed lock cohort')
        for package in metadata['packages']:
            if package['source'] is None:
                im.require(Path(package['manifest_path']).resolve().is_relative_to(worktree), 'path dependency escapes worktree')
        im.require(len(metadata['workspace_members']) == len(inventory['package_dirs']), 'workspace member lost')
        results['resolution'] = {'locked_packages': len(locked), 'metadata_packages': len(resolved),
                                 'workspace_members': len(metadata['workspace_members']),
                                 'new_or_changed_identities': 0, 'all_features': True, 'all_platforms': True}
        save()
        packages = ['-p', 'gpui', '-p', 'gpui_platform', '-p', 'gpui_linux', '-p', 'gpui_wgpu']
        cargo('check', 'check', '--locked', *packages, '--all-targets', '--features', 'gpui/test-support')
        cargo('workspace-check', 'check', '--locked', '--workspace', '--all-targets', '--features', 'gpui/test-support')
        # These libraries use GPUI's TestPlatform / pure protocol and shader tests,
        # not a real compositor, renderer device or application event loop.
        cargo('test', 'test', '--locked', '-p', 'gpui', '-p', 'gpui_linux', '-p', 'gpui_wgpu',
              '--lib', '--features', 'gpui/test-support', '--', '--test-threads=2')
        im.require(not im.git(worktree, 'status', '--porcelain', '--untracked-files=no'), 'build changed tracked source')
        results['status'] = 'passed'
    except Exception as error:
        results['status'] = 'failed'
        results['error'] = str(error)
        raise
    finally:
        save()
    print(json.dumps({'status': results['status'], 'results': str(scratch / 'results.json')}))


if __name__ == '__main__':
    main()
