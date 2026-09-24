#!/usr/bin/env python3
"""Real Copybara selected update -> excluded-only checkpoint -> merged retry.

The extra native-pin approval exists only in a disposable controller clone. No
production baseline, upstream repository or original discovery cache is changed.
"""
import argparse
import importlib.util
import json
import hashlib
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('importer', ROOT / 'import/pinrail_import.py')
assert spec and spec.loader
im = importlib.util.module_from_spec(spec)
spec.loader.exec_module(im)
PRIOR = 'e71963a599c64c213aca1c607e7418503a1e787d'
SELECTED = 'd528c665e1a5c4627a68813435756592d9fad69d'
CHECKPOINT = '2c4bc2d7b2c5b7832ad964f39840d823d961cb0e'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch', required=True)
    parser.add_argument('--jar', required=True)
    parser.add_argument('--discovery-cache', type=Path,
                        help='Optional read-only cache to COPY; raw inputs are still hash-checked')
    args = parser.parse_args()
    root = Path(args.scratch).resolve()
    assert not root.exists(), 'proof root must be new'
    im.disk_scratch(root)
    results = {}

    def save(label, value):
        results[label] = value
        (root / 'proofs.json').write_bytes(im.canonical(results))
        print(label, json.dumps(value), flush=True)

    # Exercise the current source, even before committing a TDD implementation,
    # without bypassing trusted_controller's committed-byte check.
    controller = root / 'controller'
    im.git(root, 'clone', '--no-hardlinks', str(ROOT), str(controller))
    for name in im.CODE_FILES:
        shutil.copyfile(ROOT / name, controller / name)
    im.ROOT = controller
    cache = root / 'inputs'
    if args.discovery_cache:
        shutil.copytree(args.discovery_cache.resolve(), cache / 'discovery')
    selected, _, _ = im.discover(SELECTED, cache)
    checkpoint, _, _ = im.discover(CHECKPOINT, cache)
    original_controller = im.git(controller, 'rev-parse', 'HEAD').decode().strip()
    _, lock_bytes = im.baseline(original_controller, CHECKPOINT, checkpoint)
    assert {k: v for k, v in selected.items() if k != 'upstream'} == {
        k: v for k, v in checkpoint.items() if k != 'upstream'}
    prior, _, _ = im.discover(PRIOR, cache)
    assert prior['files'] != selected['files'], 'must exercise a selected-input update first'
    review = {'scope': 'private-evaluation-only',
              'review': 'Test fixture only: native snapshot has exactly the already reviewed checkpoint inputs. Not a production approval.',
              'inventory': selected, 'cargo_lock_sha256': hashlib.sha256(lock_bytes).hexdigest()}
    (controller / f'import/baselines/{SELECTED}.json').write_bytes(im.canonical(review))
    (controller / f'import/locks/{SELECTED}.lock').write_bytes(lock_bytes)
    im.git(controller, 'add', 'import')
    im.git(controller, 'commit', '-m', 'Checkpoint regression fixture: controller and native-pin review')
    revision = im.git(controller, 'rev-parse', 'HEAD').decode().strip()
    im.trusted_controller(revision)
    save('fixture_controller', revision)

    def run(label, upstream, repo, base, candidate=None):
        scratch = root / label
        shutil.copytree(cache / 'discovery', scratch / 'discovery')
        command = [str(ROOT / '.scratch/venv/bin/python'), str(controller / 'import/pinrail_import.py'),
                   'verify' if candidate else 'import', '--upstream', upstream,
                   '--controller-rev', revision, '--accepted-repo', str(repo), '--accepted-base', base,
                   '--scratch', str(scratch), '--jar', str(Path(args.jar).resolve()), '--private-evaluation']
        if candidate:
            command += ['--candidate-repo', candidate['candidate_repo'], '--candidate-sha', candidate['candidate']]
        process = subprocess.run(command, capture_output=True, text=True, env=im.git_env())
        (root / f'{label}.stdout').write_text(process.stdout)
        (root / f'{label}.stderr').write_text(process.stderr)
        if process.returncode:
            save(label, {'exit': process.returncode, 'error': process.stderr})
        assert process.returncode == 0, process.stderr
        output = json.loads(process.stdout)
        save(label, output)
        # Retain newly discovered native marker metadata for the next step.
        for discovered in (scratch / 'discovery').iterdir():
            if not (cache / 'discovery' / discovered.name).exists():
                shutil.copytree(discovered, cache / 'discovery' / discovered.name)
        return output

    accepted = root / 'accepted.git'
    im.git(root, 'init', '--bare', str(accepted))

    def accept(label, output, parent):
        im.git(accepted, 'fetch', '--no-tags', output['candidate_repo'], output['candidate'])
        merge = im.git(accepted, 'commit-tree', output['tree'], '-p', parent, '-p', output['candidate'],
                       data=b'Accept checked import with merge ancestry\n').decode().strip()
        im.git(accepted, 'update-ref', 'refs/heads/upstream-import', merge)
        assert im.git(accepted, 'rev-parse', 'refs/heads/upstream-import').decode().strip() == merge
        assert im.git(accepted, 'show', '-s', '--format=%P', merge).decode().split() == [parent, output['candidate']]
        save(label, merge)
        return merge

    first = run('first', PRIOR, controller, im.SEED)
    first_merge = accept('first_merge', first, im.SEED)
    changed = run('selected-update', SELECTED, accepted, first_merge)
    assert not changed['noop'] and changed['tree'] != first['tree']
    selected_merge = accept('selected_merge', changed, first_merge)
    advanced = run('checkpoint', CHECKPOINT, accepted, selected_merge)
    assert not advanced['noop'], 'a new checkpoint is NOT a no-op'
    assert advanced['checkpoint_update'] is True
    repo, commit = advanced['candidate_repo'], advanced['candidate']
    assert im.git(repo, 'show', '-s', '--format=%P', commit).decode().split() == [selected_merge]
    # Independent delta oracle: only these two checkpoint-bearing files may change.
    paths = im.git(repo, 'diff-tree', '--no-commit-id', '--name-only', '-r', selected_merge, commit).decode().splitlines()
    assert paths == ['PINRAIL_IMPORT.json', 'README.md'], paths
    receipt = json.loads(im.git(repo, 'show', f'{commit}:{im.RECEIPT}'))
    assert receipt['upstream'] == CHECKPOINT
    assert CHECKPOINT.encode() in im.git(repo, 'show', f'{commit}:README.md')
    assert im.commit_provenance(repo, commit, CHECKPOINT) == CHECKPOINT
    im.validate_effective_origin(CHECKPOINT, checkpoint, cache)
    normal_command = json.loads((root / 'checkpoint/migration/command.json').read_bytes())
    forced_command = json.loads((root / 'checkpoint/migration/checkpoint-command.json').read_bytes())
    assert '--force' not in normal_command
    assert forced_command == normal_command + ['--force']
    assert 'match any origin_files' in (root / 'checkpoint/migration/copybara.log').read_text()
    # Exercise verify's recomputation and native-provenance equivalence too.
    checked = run('verify-checkpoint', CHECKPOINT, accepted, selected_merge, candidate=advanced)
    assert checked['tree'] == advanced['tree']
    checkpoint_merge = accept('checkpoint_merge', advanced, selected_merge)
    repeated = run('same-pin-retry', CHECKPOINT, accepted, checkpoint_merge)
    assert repeated['noop'] and repeated['candidate'] == checkpoint_merge
    assert repeated['checkpoint_update'] is False
    assert not (root / 'same-pin-retry/migration/checkpoint-command.json').exists()
    assert 'refs/heads/candidate' not in im.git(repeated['candidate_repo'], 'for-each-ref', '--format=%(refname)').decode().splitlines()
    assert im.git(repeated['candidate_repo'], 'rev-list', '--count', '--all') == im.git(accepted, 'rev-list', '--count', checkpoint_merge)
    save('status', 'passed')


if __name__ == '__main__':
    main()
