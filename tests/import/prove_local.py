#!/usr/bin/env python3
"""Real public-upstream/local-Git proofs. No compilation or remote writes."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import shutil

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('importer', ROOT / 'import/pinrail_import.py')
im = importlib.util.module_from_spec(spec)
spec.loader.exec_module(im)
PRIOR = 'e71963a599c64c213aca1c607e7418503a1e787d'
CURRENT = '2c4bc2d7b2c5b7832ad964f39840d823d961cb0e'


def tree_from_entries(repo, entries):
    children = {}
    for name, entry in entries.items():
        current = children
        parts = name.split('/')
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = entry
    def emit(node):
        data = b''
        for name, child in sorted(node.items()):
            if 'mode' in child:
                mode, kind, sha = child['mode'], 'blob', child['sha']
            else:
                mode, kind, sha = '040000', 'tree', emit(child)
            data += f'{mode} {kind} {sha}\t{name}'.encode() + b'\0'
        return im.git(repo, 'mktree', '-z', data=data).decode().strip()
    return emit(children)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch', required=True)
    parser.add_argument('--jar', required=True)
    parser.add_argument('--source-import', action='store_true', help='Exercise reviewed source scope instead of private evaluation')
    parser.add_argument('--discovery-cache', type=Path, help='Copy an existing read-only discovery cache')
    args = parser.parse_args()
    root = Path(args.scratch).resolve()
    assert not root.exists(), 'proof root must be new'
    im.disk_scratch(root)
    controller = im.git(ROOT, 'rev-parse', 'HEAD').decode().strip()
    im.trusted_controller(controller)
    results = {'controller': controller}

    def cli(label, command, rev, accepted_repo, accepted_base, *extra, expect_failure=False):
        if args.discovery_cache:
            shutil.copytree(args.discovery_cache.resolve(), root / label / 'discovery')
        cmd = [str(ROOT / 'import/run'), command, '--upstream', rev, '--controller-rev', controller,
               '--accepted-repo', str(accepted_repo), '--accepted-base', accepted_base,
               '--scratch', str(root / label), '--jar', str(Path(args.jar).resolve()),
               '--source-import' if args.source_import else '--private-evaluation', *extra]
        process = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        (root / f'{label}.stdout').write_text(process.stdout)
        (root / f'{label}.stderr').write_text(process.stderr)
        if expect_failure:
            assert process.returncode != 0, process.stdout
            assert 'byte/mode/path tree mismatch' in process.stderr, process.stderr
            value = {'rejected': True, 'stderr': str(root / f'{label}.stderr')}
        else:
            assert process.returncode == 0, process.stderr
            value = json.loads(process.stdout)
        results[label] = value
        (root / 'proofs.json').write_bytes(im.canonical(results))
        print(label, json.dumps(value), flush=True)
        return value

    first = cli('first', 'import', PRIOR, ROOT, im.SEED)
    second = cli('second-clean', 'verify', PRIOR, ROOT, im.SEED,
                 '--candidate-repo', first['candidate_repo'], '--candidate-sha', first['candidate'])
    assert second['tree'] == first['tree']
    accepted = root / 'accepted.git'
    im.git(root, 'init', '--bare', str(accepted))

    def accept(candidate, parent):
        im.git(accepted, 'fetch', '--no-tags', candidate['candidate_repo'], candidate['candidate'])
        commit = im.git(accepted, 'commit-tree', candidate['tree'], '-p', parent, '-p', candidate['candidate'],
                        data=b'Accept checked import with a merge commit\n').decode().strip()
        im.git(accepted, 'update-ref', 'refs/heads/upstream-import', commit)
        assert im.git(accepted, 'rev-parse', 'refs/heads/upstream-import').decode().strip() == commit
        return commit

    prior_accepted = accept(first, im.SEED)
    results['prior_accepted_merge'] = prior_accepted
    repeat = cli('repeat-after-merge', 'import', PRIOR, accepted, prior_accepted)
    assert repeat['noop'] and repeat['candidate'] == prior_accepted
    assert im.git(repeat['candidate_repo'], 'rev-list', '--count', '--all') == im.git(accepted, 'rev-list', '--count', 'refs/heads/upstream-import')

    # A real downstream source commit on an actual Git worktree, not a copied tree.
    downstream = root / 'downstream'
    im.git(accepted, 'worktree', 'add', '--detach', str(downstream), prior_accepted)
    source = downstream / 'crates/gpui/src/gpui.rs'
    marker = b'// Representative downstream source patch: retained across upstream import merges.\n'
    source.write_bytes(marker + source.read_bytes())
    im.git(downstream, 'add', 'crates/gpui/src/gpui.rs')
    im.git(downstream, 'commit', '-m', 'Keep representative downstream source patch')
    patch_commit = im.git(downstream, 'rev-parse', 'HEAD').decode().strip()

    updated = cli('update-after-merge', 'import', CURRENT, accepted, prior_accepted)
    assert not updated['noop'] and updated['tree'] != first['tree']
    current_accepted = accept(updated, prior_accepted)
    current_repeat = cli('repeat-current', 'import', CURRENT, accepted, current_accepted)
    assert current_repeat['noop'] and current_repeat['candidate'] == current_accepted
    im.git(downstream, 'merge', '--no-ff', current_accepted, '-m', 'Integrate accepted GPUI import')
    assert source.read_bytes().startswith(marker)
    assert json.loads((downstream / im.RECEIPT).read_text())['upstream'] == CURRENT
    results['downstream'] = {'path': str(downstream), 'patch_commit': patch_commit,
                              'merged': im.git(downstream, 'rev-parse', 'HEAD').decode().strip(),
                              'current_accepted_merge': current_accepted, 'source_patch_survived': True}
    # A clean recomputation of the actual update also checks source resumption.
    cli('verify-update', 'verify', CURRENT, accepted, prior_accepted,
        '--candidate-repo', updated['candidate_repo'], '--candidate-sha', updated['candidate'])

    expected = im.git_entries(updated['candidate_repo'], updated['candidate'])
    repo = updated['candidate_repo']
    injected = im.git(repo, 'hash-object', '-w', '--stdin', data=b'candidate cannot install its own checker\n').decode().strip()
    escape = im.git(repo, 'hash-object', '-w', '--stdin', data=b'../../../../etc/passwd').decode().strip()
    cases = {}
    entries = copy.deepcopy(expected)
    entries['crates/gpui/src/gpui.rs']['sha'] = injected
    cases['bytes'] = entries
    entries = copy.deepcopy(expected)
    entries['crates/gpui/src/gpui.rs']['mode'] = '100755'
    cases['mode'] = entries
    entries = copy.deepcopy(expected)
    entries['crates/gpui/LICENSE-APACHE']['sha'] = escape
    cases['symlink'] = entries
    entries = copy.deepcopy(expected)
    del entries['crates/gpui/src/gpui.rs']
    cases['deletion'] = entries
    entries = copy.deepcopy(expected)
    entries['import/baselines/candidate-controlled.json'] = {'mode': '100644', 'sha': injected}
    cases['candidate-checker-addition'] = entries
    rejected = {}
    for label, entries in cases.items():
        tree = tree_from_entries(repo, entries)
        sha = im.git(repo, 'commit-tree', tree, '-p', prior_accepted,
                     data=f'Forged candidate\n\nGitOrigin-RevId: {CURRENT}\n'.encode()).decode().strip()
        try:
            im.compare_entries(expected, im.git_entries(repo, sha))
        except im.GateError:
            rejected[label] = sha
        else:
            raise AssertionError(f'accepted {label}')
    results['negative_commits_rejected'] = rejected
    # CLI proof that even candidate-added policy files do not replace the checker.
    cli('verify-malicious-candidate', 'verify', CURRENT, accepted, prior_accepted,
        '--candidate-repo', repo, '--candidate-sha', rejected['candidate-checker-addition'], expect_failure=True)
    (root / 'proofs.json').write_bytes(im.canonical(results))
    print(json.dumps({'proofs': str(root / 'proofs.json'), 'status': 'passed'}))


if __name__ == '__main__':
    main()
