#!/usr/bin/env python3
"""Pinned, local-only GPUI migration. Never execute code from a candidate tree."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import sys
import tempfile
import tomllib
import urllib.request

import tomlkit

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = 'https://github.com/zed-industries/zed.git'
COPYBARA_VERSION = 'v20260921'
COPYBARA_SOURCE = 'db68b8a5b5a4e8fec45877c11b19ef9af2bdbc4a'
COPYBARA_SHA256 = '3b9307e9751710f2b04422e108ccc3667b9671eb73e91ea264f5f3baaae2f771'
COPYBARA_URL = f'https://github.com/google/copybara/releases/download/{COPYBARA_VERSION}/copybara_deploy.jar'
SEED = '875ec5e0a0a13b44076e43bb8a46629a8d447091'
ENTRIES = ('crates/gpui', 'crates/gpui_platform')
ROOT_FILES = ('Cargo.toml', 'Cargo.lock', 'LICENSE-APACHE', '.cargo/config.toml',
              'rust-toolchain.toml', 'rustfmt.toml', 'clippy.toml')
EXTRA_DIRS = ('assets/fonts/ibm-plex-sans', 'assets/fonts/lilex')
OMITTED = ('crates/gpui/examples/svg/dragon.svg', 'crates/gpui/examples/svg/svg.rs')
CODE_FILES = ('import/pinrail_import.py', 'import/run', 'import/requirements.txt')
RECEIPT = 'PINRAIL_IMPORT.json'


class GateError(ValueError):
    """An import is not authorized or does not match its declared inputs."""


def require(condition, message):
    if not condition:
        raise GateError(message)


def validate_sha(value):
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{40}', value),
            f'expected literal full lowercase Git SHA, got {value!r}')
    return value


def safe_path(value):
    require(isinstance(value, str) and value and not value.startswith('/') and
            all(x not in ('', '.', '..', '.git') for x in value.split('/')) and
            not any(c in value for c in '\x00\n\r\\'), f'unsafe relative path: {value!r}')
    return value


def relative_path(base, value):
    require(not value.startswith('/') and '\\' not in value, f'absolute/foreign path: {value}')
    return safe_path(posixpath.normpath(posixpath.join(base, value)))


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()


def blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def compare_entries(expected, actual):
    changes = {key: [expected.get(key), actual.get(key)] for key in sorted(expected.keys() | actual.keys())
               if expected.get(key) != actual.get(key)}
    require(not changes, 'byte/mode/path tree mismatch: ' + json.dumps(changes)[:12000])


def disk_scratch(path):
    path = Path(path).resolve()
    require(path != Path('/tmp') and Path('/tmp') not in path.parents, 'scratch must not use /tmp')
    path.mkdir(parents=True, exist_ok=True)
    fs = subprocess.check_output(['stat', '-f', '-c', '%T', str(path)], text=True).strip()
    require(fs not in ('tmpfs', 'ramfs'), f'scratch must be disk-backed, got {fs}')
    temp = path / 'tmp'
    temp.mkdir(exist_ok=True)
    os.environ.update(TMPDIR=str(temp), TMP=str(temp), TEMP=str(temp))
    tempfile.tempdir = str(temp)
    return path


def git_env():
    env = os.environ.copy()
    # No user hooks, smudge filters, credentials, signing, or alternate object dirs.
    for key in list(env):
        if key.startswith('GIT_'):
            del env[key]
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
               GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1',
               GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='core.hooksPath',
               GIT_CONFIG_VALUE_0='/dev/null', GIT_CONFIG_KEY_1='protocol.allow',
               GIT_CONFIG_VALUE_1='never', GIT_ALLOW_PROTOCOL='https:file',
               GIT_AUTHOR_NAME='Pinrail Import', GIT_AUTHOR_EMAIL='import@pinrail.invalid',
               GIT_COMMITTER_NAME='Pinrail Import', GIT_COMMITTER_EMAIL='import@pinrail.invalid')
    return env


def git(repo, *args, data=None):
    p = subprocess.run(['git', '-C', str(repo), *args], input=data, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, env=git_env())
    require(p.returncode == 0, f'git {args!r}: {p.stderr.decode(errors="replace")}')
    return p.stdout


def git_entries(repo, rev):
    validate_sha(rev)
    result = {}
    for line in git(repo, 'ls-tree', '-rz', '--full-tree', rev).split(b'\0'):
        if not line:
            continue
        info, name = line.split(b'\t', 1)
        mode, kind, sha = info.decode().split()
        name = safe_path(name.decode())
        require(kind == 'blob' and mode in ('100644', '100755', '120000'), f'unsupported tree entry {name}')
        result[name] = {'mode': mode, 'sha': sha}
    return result


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'pinrail-local-import/1'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


class Source:
    """Pinned manifest and tree discovery only; Copybara migrates actual source."""
    def __init__(self, rev, scratch):
        self.rev = validate_sha(rev)  # before ANY network operation
        self.cache = Path(scratch) / 'discovery' / rev
        self.cache.mkdir(parents=True, exist_ok=True)
        tree_path = self.cache / 'tree.json'
        if not tree_path.exists():
            # A depth-one blobless Git fetch avoids unauthenticated API rate limits.
            # No checkout and no source blobs; actual migration remains Copybara's job.
            metadata = self.cache / 'metadata.git'
            if not metadata.exists():
                git(self.cache, 'init', '--bare', str(metadata))
            git(metadata, 'fetch', '--no-tags', '--filter=blob:none', '--depth=1', UPSTREAM, rev)
            records = []
            for row in git(metadata, 'ls-tree', '-rz', '--full-tree', rev).split(b'\0'):
                if row:
                    info, name = row.split(b'\t', 1)
                    mode, kind, sha = info.decode().split()
                    records.append({'path': name.decode(), 'mode': mode, 'type': kind, 'sha': sha})
            tree_path.write_bytes(canonical({'truncated': False, 'tree': records}))
        response = json.loads(tree_path.read_bytes())
        require(response.get('truncated') is False, 'truncated upstream tree cannot authorize selection')
        self.tree = {e['path']: e for e in response['tree']}
        require(len(self.tree) == len(response['tree']), 'duplicate upstream tree paths')
        for name in self.tree:
            safe_path(name)

    def read(self, name):
        safe_path(name)
        item = self.tree.get(name)
        require(item and item['type'] == 'blob', f'missing/non-blob upstream input: {name}')
        path = self.cache / 'raw' / name
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            # Raw GitHub returns the symlink blob text, not the dereferenced target.
            # Verify it against the Git object ID exactly like every other raw input.
            data = fetch(f'https://raw.githubusercontent.com/zed-industries/zed/{self.rev}/{name}')
            path.write_bytes(data)
        data = path.read_bytes()
        require(blob_sha(data) == item['sha'], f'upstream/cache blob mismatch: {name}')
        return data


def dependency_tables(manifest):
    for scope in ('dependencies', 'dev-dependencies', 'build-dependencies'):
        yield scope, manifest.get(scope, {})
    for target, tables in sorted(manifest.get('target', {}).items()):
        for scope in ('dependencies', 'dev-dependencies', 'build-dependencies'):
            yield f'target.{target}.{scope}', tables.get(scope, {})


def resolve_closure(source):
    root = tomllib.loads(source.read('Cargo.toml').decode())
    workspace = root['workspace']
    names, packages, edges, used = {}, {}, [], set()
    pending = list(ENTRIES)
    for patch_table in root.get('patch', {}).values():
        for dep in patch_table.values():
            if isinstance(dep, dict) and 'path' in dep:
                pending.append(relative_path('', dep['path']))
    while pending:
        directory = safe_path(pending.pop(0))
        if directory in packages:
            continue
        manifest = tomllib.loads(source.read(directory + '/Cargo.toml').decode())
        package = manifest['package']
        require(package['name'] not in names, f'duplicate package name {package["name"]}')
        names[package['name']] = directory
        packages[directory] = manifest
        for scope, deps in dependency_tables(manifest):
            for alias, value in sorted(deps.items()):
                value = {'version': value} if isinstance(value, str) else value.copy()
                base = directory
                if value.pop('workspace', False):
                    require(alias in workspace['dependencies'], f'unresolved workspace dependency {alias}')
                    used.add(alias)
                    inherited = workspace['dependencies'][alias]
                    inherited = {'version': inherited} if isinstance(inherited, str) else inherited.copy()
                    # Keep package manifests byte-for-byte; this merge is inventory only.
                    inherited['features'] = inherited.get('features', []) + value.get('features', [])
                    inherited.update({k: v for k, v in value.items() if k != 'features'})
                    value, base = inherited, ''
                edge = {'from': directory, 'scope': scope, 'alias': alias, 'spec': value}
                if 'path' in value:
                    target = relative_path(base, value['path'])
                    edge['in_tree'] = target
                    pending.append(target)
                edges.append(edge)
    return root, packages, edges, sorted(used)


def check_symlinks(entries, read):
    for name, entry in entries.items():
        if entry['mode'] != '120000':
            continue
        current, seen = name, set()
        while entries[current]['mode'] == '120000':
            require(current not in seen, f'symlink cycle: {name}')
            seen.add(current)
            target = read(current).decode('utf-8')
            current = relative_path(posixpath.dirname(current), target)
            require(current in entries, f'symlink outside selected files: {name} -> {target}')


def classify(name):
    lower = name.lower()
    if 'license' in lower or 'notice' in lower or lower.endswith('ofl.txt'):
        return 'license-notice'
    if '/fonts/' in lower:
        return 'font-asset'
    if lower.endswith(('cargo.toml', 'cargo.lock')):
        return 'cargo-input'
    if lower.endswith(('build.rs', '.h', '.m', '.mm', '.metal', '.hlsl', '.wgsl', '.rc', '.xml')):
        return 'build-native-resource'
    if '/examples/' in lower:
        return 'example-source-or-asset'
    return 'package-source-or-resource'


def discover(rev, scratch):
    source = Source(rev, scratch)
    root, packages, edges, used = resolve_closure(source)
    dirs = sorted(set(packages) | set(EXTRA_DIRS))
    selected = {}
    for name, item in sorted(source.tree.items()):
        if name in ROOT_FILES or any(name.startswith(d + '/') for d in dirs):
            if item['type'] == 'tree':
                continue
            require(item['type'] == 'blob' and item['mode'] in ('100644', '100755', '120000'),
                    f'unsupported upstream object: {name}')
            selected[name] = {'mode': item['mode'], 'sha': item['sha']}
    require(all(name in selected for name in ROOT_FILES), 'missing required root inputs')
    check_symlinks(selected, source.read)
    lock = tomllib.loads(source.read('Cargo.lock').decode())
    # Full locked identities are retained, not a newly resolved subset.
    inventory = {
        'schema': 1, 'upstream': rev, 'origin': UPSTREAM, 'entry_packages': list(ENTRIES),
        'package_dirs': sorted(packages), 'extra_dirs': list(EXTRA_DIRS),
        'origin_globs': list(ROOT_FILES) + [d + '/**' for d in dirs],
        'files': selected, 'omitted_files': list(OMITTED), 'file_classes': {n: classify(n) for n in selected},
        'packages': {d: {'package': m['package'], 'features': m.get('features', {}),
                         'targets': {k: m[k] for k in ('lib', 'bin', 'example', 'test', 'bench') if k in m}}
                     for d, m in sorted(packages.items())},
        'dependency_edges': edges, 'workspace_dependencies': used,
        'root_patches': root.get('patch', {}),
        'locked_sources': sorted({p['source'] for p in lock['package'] if 'source' in p}),
        'license_findings': [
            {'input': 'crates/gpui/examples/svg/dragon.svg', 'license': 'CC-BY-SA-3.0', 'role': 'OMITTED together with SVG example target/source'},
            {'input': 'assets/fonts/ibm-plex-sans', 'license': 'OFL-1.1', 'role': 'web example font assets; reserved Plex name'},
            {'input': 'assets/fonts/lilex', 'license': 'OFL-1.1', 'role': 'web example font assets'},
            {'input': 'cbindgen', 'license': 'MPL-2.0', 'role': 'external macOS build tool, not a runtime-linking claim'},
        ],
        'audit_limits': 'Exact file/dependency input inventory, NOT complete file/external-license clearance. Native SDKs, dynamic build inputs and all platforms require separate review and build verification.',
    }
    return inventory, source, root


def baseline(controller, rev, inventory):
    path = f'import/baselines/{validate_sha(rev)}.json'
    raw = git(ROOT, 'show', f'{validate_sha(controller)}:{path}')
    review = json.loads(raw)
    require(review.get('scope') == 'private-evaluation-only', 'only private evaluation is currently authorized')
    require(review.get('review') and review.get('inventory') == inventory,
            f'unreviewed inventory/dependency/license/build input changes: {path}')
    return hashlib.sha256(raw).hexdigest()


def trusted_controller(controller):
    validate_sha(controller)
    for name in CODE_FILES:
        require(git(ROOT, 'show', f'{controller}:{name}') == (ROOT / name).read_bytes(),
                f'checker differs from selected controller: {name}')
    return hashlib.sha256(b''.join(name.encode() + b'\0' + (ROOT / name).read_bytes()
                                  for name in CODE_FILES)).hexdigest()


def omit_svg_example(data):
    doc = tomlkit.parse(data.decode())
    examples = doc.get('example', [])
    matches = [i for i, e in enumerate(examples) if e['name'] == 'svg']
    require(len(matches) == 1 and examples[matches[0]]['path'] == 'examples/svg/svg.rs',
            'unknown SVG example target; review new omission policy')
    del examples[matches[0]]
    return tomlkit.dumps(doc).encode()


def generated_files(inventory, source, controller_digest, baseline_digest):
    # TOML parser/writer, not textual section surgery. Only the SVG target is removed.
    doc = tomlkit.parse(source.read('Cargo.toml').decode())
    ws = doc['workspace']
    ws['members'] = inventory['package_dirs']
    ws['default-members'] = list(ENTRIES)
    ws.pop('exclude', None)
    ws.pop('metadata', None)
    for name in list(ws['dependencies']):
        if name not in inventory['workspace_dependencies']:
            del ws['dependencies'][name]
    receipt = {'schema': 1, 'upstream': inventory['upstream'], 'origin': UPSTREAM,
               'controller_code_sha256': controller_digest, 'reviewed_baseline_sha256': baseline_digest,
               'copybara': {'version': COPYBARA_VERSION, 'source': COPYBARA_SOURCE,
                            'url': COPYBARA_URL, 'sha256': COPYBARA_SHA256},
               'inventory_sha256': hashlib.sha256(canonical(inventory)).hexdigest(),
               'scope': 'private-evaluation-only', 'package_dirs': inventory['package_dirs'],
               'lock_policy': 'Upstream Cargo.lock bytes and root patches preserved. No dependency re-resolution performed.',
               'omitted_files': list(OMITTED),
               'license_findings': inventory['license_findings'], 'audit_limits': inventory['audit_limits']}
    readme = f'''# GENERATED UPSTREAM IMPORT — NOT THE CONSUMER BRANCH

**Do not edit this branch. Use downstream `main` for Pinrail consumers and patches.**

This tree is a mechanically selected GPUI-family snapshot from
{UPSTREAM.removesuffix('.git')}/tree/{inventory['upstream']}.
Copybara owns every path on this branch. Candidate integrity must be recomputed
using a separately reviewed controller checkout, never candidate code.

## PRIVATE EVALUATION ONLY — DISTRIBUTION POLICY NOT CLEARED

All upstream platforms, fonts and native resources in the selected closure are
retained. The CC BY-SA 3.0 dragon asset and its SVG example source/target are
explicitly omitted. Other examples are preserved. Package declarations do not
relicense bundled files. IBM Plex and Lilex fonts are OFL-1.1; cbindgen is an
external MPL-2.0 macOS build tool, retained by policy. See preserved notices and
`{RECEIPT}`. No blanket permissive-only or complete license clearance is claimed.

The root workspace membership and inherited dependency table were reduced;
the GPUI SVG example target was removed. Other member manifests, root patches
and upstream lock bytes were preserved.
No Cargo dependency update was performed. Native compilation/SDK availability
and the supported target/feature matrix require separate validation.
'''
    return {'Cargo.toml': tomlkit.dumps(doc).encode(),
            'crates/gpui/Cargo.toml': omit_svg_example(source.read('crates/gpui/Cargo.toml')),
            'README.md': readme.encode(),
            RECEIPT: canonical(receipt)}


def expected_entries(inventory, generated):
    entries = {n: e for n, e in inventory['files'].items() if n not in OMITTED}
    entries.update({n: {'mode': '100644', 'sha': blob_sha(b)} for n, b in generated.items()})
    return entries


def local_repo(path):
    path = Path(path).resolve()
    require(path.is_dir(), f'local repository required: {path}')
    git(path, 'rev-parse', '--git-dir')
    return path


def validate_parent(repo, base, controller, digest, scratch):
    validate_sha(base)
    if base == SEED:
        return True
    receipt = json.loads(git(repo, 'show', f'{base}:{RECEIPT}'))
    old_rev = validate_sha(receipt['upstream'])
    inventory, source, _ = discover(old_rev, scratch)
    approved = baseline(controller, old_rev, inventory)
    generated = generated_files(inventory, source, digest, approved)
    compare_entries(expected_entries(inventory, generated), git_entries(repo, base))
    messages = git(repo, 'log', '--format=%B', base).decode()
    require(f'GitOrigin-RevId: {old_rev}' in messages.splitlines(), 'accepted ancestry lost Copybara provenance')
    return False


def ensure_jar(path, scratch):
    path = Path(path).resolve() if path else Path(scratch) / 'tools/copybara_deploy.jar'
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fetch(COPYBARA_URL))
    with path.open('rb') as handle:
        actual = hashlib.file_digest(handle, 'sha256').hexdigest()
    require(actual == COPYBARA_SHA256, f'pinned Copybara checksum mismatch: {path}')
    return path


def config_text(inventory, generated, destination):
    writes = '\n'.join(f'    ctx.write_path(ctx.new_path({json.dumps(name)}), {json.dumps(data.decode(), ensure_ascii=False)})'
                       for name, data in generated.items())
    return f'''# Generated from the trusted controller, never read from the candidate.
def standalone(ctx):
{writes}
    ctx.set_message("Import GPUI snapshot {inventory['upstream']}\\n\\nPrivate evaluation; license policy pending.\\n")

core.workflow(
    name = "gpui",
    origin = git.origin(url = {json.dumps(UPSTREAM)}, ref = {json.dumps(inventory['upstream'])}, partial_fetch = True),
    destination = git.destination(url = {json.dumps(str(destination))}, fetch = "refs/heads/accepted", push = "refs/heads/candidate"),
    authoring = authoring.overwrite("Pinrail Import <import@pinrail.invalid>"),
    origin_files = glob({json.dumps(inventory['origin_globs'])}, exclude = {json.dumps(list(OMITTED))}),
    destination_files = glob(["**"]),
    transformations = [standalone],
    mode = "SQUASH",
    # Receipt/config bytes depend on the reviewed pin. Validate previous trees
    # independently before running; same-config historical reconstruction is wrong.
    check_last_rev_state = False,
)
'''


def run_import(args):
    validate_sha(args.upstream)
    validate_sha(args.accepted_base)
    digest = trusted_controller(args.controller_rev)
    require(args.private_evaluation, '--private-evaluation is required; publication is not approved')
    scratch = disk_scratch(args.scratch)
    repo = local_repo(args.accepted_repo)
    inventory, source, _ = discover(args.upstream, scratch)
    approved = baseline(args.controller_rev, args.upstream, inventory)
    generated = generated_files(inventory, source, digest, approved)
    initial = validate_parent(repo, args.accepted_base, args.controller_rev, digest, scratch)
    run = scratch / 'migration'
    require(not run.exists(), f'clean migration root required: {run}')
    run.mkdir()
    destination = run / 'destination.git'
    git(run, 'init', '--bare', str(destination))
    git(destination, 'fetch', '--no-tags', str(repo), f'{args.accepted_base}:refs/heads/accepted')
    jar = ensure_jar(args.jar, scratch)
    config = run / 'copy.bara.sky'
    config.write_text(config_text(inventory, generated, destination))
    home = run / 'home'
    home.mkdir()
    command = ['java', '-Xmx2g', f'-Djava.io.tmpdir={scratch / "tmp"}', f'-Duser.home={home}',
               '-jar', str(jar), 'migrate', str(config), 'gpui', args.upstream,
               f'--output-root={run / "copybara"}', '--git-origin-fetch-depth=256',
               '--git-committer-name=Pinrail Import', '--git-committer-email=import@pinrail.invalid']
    if initial:
        command.append('--init-history')
    (run / 'command.json').write_bytes(canonical(command))
    log = run / 'copybara.log'
    with log.open('wb') as handle:
        result = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, env=git_env())
    refs = git(destination, 'for-each-ref', '--format=%(refname)').decode().splitlines()
    if 'refs/heads/candidate' in refs:
        candidate = git(destination, 'rev-parse', 'refs/heads/candidate').decode().strip()
        require(result.returncode == 0, f'Copybara exit {result.returncode}; see {log}')
        parents = git(destination, 'show', '-s', '--format=%P', candidate).decode().split()
        require(parents == [args.accepted_base], 'candidate does not directly descend from accepted base')
        message = git(destination, 'show', '-s', '--format=%B', candidate).decode()
        require(f'GitOrigin-RevId: {args.upstream}' in message.splitlines(), 'candidate lacks exact origin provenance')
        noop = False
    else:
        # Only accept a no-op when the accepted tree is exactly the requested output.
        require(result.returncode in (0, 4), f'Copybara failed: exit {result.returncode}; see {log}')
        candidate, noop = args.accepted_base, True
    compare_entries(expected_entries(inventory, generated), git_entries(destination, candidate))
    tree = git(destination, 'rev-parse', f'{candidate}^{{tree}}').decode().strip()
    output = {'candidate': candidate, 'base': args.accepted_base, 'tree': tree,
              'upstream': args.upstream, 'controller': args.controller_rev, 'noop': noop,
              'candidate_repo': str(destination), 'log': str(log), 'scope': 'private-evaluation-only',
              'files': len(expected_entries(inventory, generated)), 'packages': len(inventory['package_dirs'])}
    (run / 'result.json').write_bytes(canonical(output))
    return output


def verify(args):
    validate_sha(args.candidate_sha)
    candidate_repo = local_repo(args.candidate_repo)
    actual = git_entries(candidate_repo, args.candidate_sha)
    # Always execute a new migration, not merely compare to the candidate receipt.
    result = run_import(args)
    expected = git_entries(result['candidate_repo'], result['candidate'])
    compare_entries(expected, actual)
    if args.candidate_sha != args.accepted_base:
        parents = git(candidate_repo, 'show', '-s', '--format=%P', args.candidate_sha).decode().split()
        require(parents == [args.accepted_base], 'candidate parent mismatch')
        message = git(candidate_repo, 'show', '-s', '--format=%B', args.candidate_sha).decode()
        require(f'GitOrigin-RevId: {args.upstream}' in message.splitlines(), 'candidate provenance mismatch')
    return {'verified_candidate': args.candidate_sha, 'base': args.accepted_base,
            'tree': result['tree'], 'recomputed': result, 'scope': 'private-evaluation-only'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('discover', aliases=['inspect'])
    inspect.add_argument('--upstream', required=True)
    inspect.add_argument('--scratch', required=True)
    inspect.add_argument('--output', required=True)
    for command in ('import', 'regenerate', 'verify'):
        p = commands.add_parser(command)
        p.add_argument('--upstream', required=True)
        p.add_argument('--controller-rev', required=True)
        p.add_argument('--accepted-repo', required=True)
        p.add_argument('--accepted-base', required=True)
        p.add_argument('--scratch', required=True)
        p.add_argument('--jar')
        p.add_argument('--private-evaluation', action='store_true')
        if command == 'verify':
            p.add_argument('--candidate-repo', required=True)
            p.add_argument('--candidate-sha', required=True)
    args = parser.parse_args()
    try:
        validate_sha(args.upstream)
        if args.command in ('discover', 'inspect'):
            inventory, _, _ = discover(args.upstream, disk_scratch(args.scratch))
            output = Path(args.output).resolve()
            require(not output.exists(), f'discovery never replaces files: {output}')
            require(ROOT / 'import' not in output.parents, 'discovery cannot write a reviewed baseline')
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(canonical({'scope': 'UNREVIEWED', 'review': None, 'inventory': inventory}))
            result = {'inventory': str(output), 'upstream': args.upstream,
                      'packages': len(inventory['package_dirs']), 'files': len(inventory['files'])}
        elif args.command == 'verify':
            result = verify(args)
        else:
            result = run_import(args)
        print(json.dumps(result, sort_keys=True))
    except (GateError, OSError, ValueError, KeyError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
