import importlib.util
import pathlib
import unittest
import json
import os
import subprocess
import tempfile
import hashlib
import tomllib
import tomlkit
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('importer', ROOT / 'import/pinrail_import.py')
im = importlib.util.module_from_spec(spec)
spec.loader.exec_module(im)


class GateTests(unittest.TestCase):
    def test_sha_is_literal_full_lowercase_hex_before_acquisition(self):
        good = '2c4bc2d7b2c5b7832ad964f39840d823d961cb0e'
        self.assertEqual(im.validate_sha(good), good)
        for bad in [good[:12], good.upper(), good + '\n', ' ' + good, 'main', 'g' * 40]:
            with self.subTest(bad=bad), self.assertRaises(im.GateError):
                im.validate_sha(bad)

    def test_exact_tree_rejects_bytes_modes_links_additions_deletions(self):
        expected = {'code': {'mode': '100644', 'sha': 'a' * 40},
                    'notice': {'mode': '120000', 'sha': 'b' * 40}}
        im.compare_entries(expected, expected)
        for actual in [
            {**expected, 'code': {'mode': '100644', 'sha': 'c' * 40}},
            {**expected, 'code': {'mode': '100755', 'sha': 'a' * 40}},
            {**expected, 'notice': {'mode': '120000', 'sha': 'c' * 40}},
            {**expected, 'checker.py': {'mode': '100644', 'sha': 'a' * 40}},
            {'code': expected['code']},
        ]:
            with self.subTest(actual=actual), self.assertRaises(im.GateError):
                im.compare_entries(expected, actual)

    def test_only_svg_example_is_omitted_preserving_platforms_and_other_examples(self):
        manifest = b'''[package]\nname = "gpui"\n[features]\nwayland = []\n[[example]]\nname = "hello_world"\npath = "examples/hello_world.rs"\n[[example]]\nname = "svg"\npath = "examples/svg/svg.rs"\n'''
        import tomllib
        result = tomllib.loads(im.omit_svg_example(manifest).decode())
        self.assertEqual(result['example'], [{'name': 'hello_world', 'path': 'examples/hello_world.rs'}])
        self.assertEqual(result['features'], {'wayland': []})
        with self.assertRaises(im.GateError):
            im.omit_svg_example(manifest.replace(b'examples/svg/svg.rs', b'other.rs'))

    def test_wrapper_rejects_bad_sha_before_dependency_bootstrap(self):
        result = subprocess.run(['/usr/bin/bash', str(ROOT / 'import/run'), 'discover', '--upstream', 'main'],
                                env={**os.environ, 'PATH': '/nonexistent'}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Expected literal full lowercase Git SHA', result.stderr)
        self.assertNotIn('uv', result.stderr)
        with patch.object(im, 'fetch', side_effect=AssertionError('network must not run')):
            with self.assertRaises(im.GateError):
                im.Source('main', ROOT / '.scratch/not-created')

    def test_symlinks_reject_escape_dangling_and_cycles(self):
        files = {'LICENSE': {'mode': '100644'}, 'pkg/LICENSE': {'mode': '120000'}}
        im.check_symlinks(files, lambda name: b'../LICENSE')
        for target in (b'../../secret', b'/etc/passwd', b'../missing', b'LICENSE'):
            with self.subTest(target=target), self.assertRaises(im.GateError):
                im.check_symlinks(files, lambda name: target)

    def test_committed_controller_baseline_not_candidate_or_working_file(self):
        (ROOT / '.scratch/tests').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / '.scratch/tests') as temp:
            repo = pathlib.Path(temp)
            im.git(repo, 'init')
            rev = 'a' * 40
            filename = repo / f'import/baselines/{rev}.json'
            filename.parent.mkdir(parents=True)
            old = {'files': {'safe.rs': {'sha': 'b'*40, 'mode': '100644'}}, 'dependencies': ['approved']}
            lock = b'version = 4\npackage = []\n'
            lock_path = repo / f'import/locks/{rev}.lock'
            lock_path.parent.mkdir()
            lock_path.write_bytes(lock)
            record = {'scope': 'private-evaluation-only', 'review': 'unit review', 'inventory': old,
                      'cargo_lock_sha256': hashlib.sha256(lock).hexdigest()}
            filename.write_bytes(im.canonical(record))
            im.git(repo, 'add', '.')
            im.git(repo, 'commit', '-m', 'Trusted review')
            controller = im.git(repo, 'rev-parse', 'HEAD').decode().strip()
            changed = json.loads(json.dumps(old))
            changed['dependencies'].append('unapproved')
            filename.write_bytes(im.canonical({**record, 'inventory': changed}))
            with patch.object(im, 'ROOT', repo):
                im.baseline(controller, rev, old)
                with self.assertRaises(im.GateError):
                    im.baseline(controller, rev, changed)

    def test_cargo_closure_includes_renamed_optional_target_build_dev_and_patches(self):
        raw = {
            'Cargo.toml': '''[workspace.dependencies]\nrenamed = { package="real", path="crates/real", default-features=false }\n[patch.crates-io]\npatcher = { path="tooling/patcher" }\n''',
            'crates/gpui/Cargo.toml': '''[package]\nname="gpui"\n[dependencies]\nrenamed = { workspace=true, optional=true, features=["extra"] }\n[target.'cfg(windows)'.build-dependencies]\nwin = {path="../win"}\n[dev-dependencies]\ntester={path="../tester"}\n''',
            'crates/gpui_platform/Cargo.toml': '[package]\nname="platform"\n',
            'crates/real/Cargo.toml': '[package]\nname="real"\n[lib]\nproc-macro=true\n',
            'crates/win/Cargo.toml': '[package]\nname="win"\n',
            'crates/tester/Cargo.toml': '[package]\nname="tester"\n',
            'tooling/patcher/Cargo.toml': '[package]\nname="patcher"\n',
        }
        class Inputs:
            def read(self, name):
                return raw[name].encode()
        _, packages, edges, inherited = im.resolve_closure(Inputs())
        self.assertEqual(set(packages), {'crates/gpui', 'crates/gpui_platform', 'crates/real', 'crates/win', 'crates/tester', 'tooling/patcher'})
        self.assertEqual(inherited, ['renamed'])
        edge = next(e for e in edges if e['alias'] == 'renamed')
        self.assertEqual(edge['spec'], {'package': 'real', 'path': 'crates/real', 'default-features': False, 'optional': True, 'features': ['extra']})
        raw['crates/gpui/Cargo.toml'] += '\n[build-dependencies]\nescape = {path="../../../secret"}\n'
        with self.assertRaises(im.GateError):
            im.resolve_closure(Inputs())

    def test_generated_workspace_drops_unreachable_git_patch_before_cargo_acquisition(self):
        import tomllib
        root = '''[workspace]
members = ["crates/gpui", "crates/gpui_platform"]
resolver = "2"
[workspace.dependencies]
[patch.crates-io]
unrelated-editor = {git="https://invalid.invalid/editor", rev="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
'''
        gpui = '''[package]
name="gpui"
version="0.1.0"
[[example]]
name="svg"
path="examples/svg/svg.rs"
'''
        platform = '[package]\nname="gpui_platform"\nversion="0.1.0"\n'
        lock = '''version = 4
[[package]]
name="gpui"
version="0.1.0"
[[package]]
name="gpui_platform"
version="0.1.0"
'''
        raw = {'Cargo.toml': root, 'Cargo.lock': lock, 'crates/gpui/Cargo.toml': gpui,
               'crates/gpui_platform/Cargo.toml': platform}
        class Inputs:
            def read(self, name):
                return raw[name].encode()
        inventory = {'upstream': 'a'*40, 'package_dirs': list(im.ENTRIES),
                     'workspace_dependencies': [], 'license_findings': [], 'audit_limits': 'fixture'}
        generated = im.generated_files(inventory, Inputs(), 'digest', 'baseline', lock.encode())
        # Exercise Cargo itself: retaining the unrelated patch makes even offline
        # metadata attempt acquisition before resolving this dependency-free workspace.
        im.disk_scratch(ROOT / '.scratch/tests')
        with tempfile.TemporaryDirectory(dir=ROOT / '.scratch/tests') as temp:
            path = pathlib.Path(temp)
            for name, data in {**{n: v.encode() for n, v in raw.items()}, **generated}.items():
                target = path / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            for directory in im.ENTRIES:
                src = path / directory / 'src/lib.rs'
                src.parent.mkdir()
                src.write_text('')
            result = subprocess.run(['cargo', '+1.98.1', 'metadata', '--offline', '--locked',
                                     '--format-version', '1'], cwd=path, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({p['name'] for p in json.loads(result.stdout)['packages']}, {'gpui', 'gpui_platform'})
        self.assertFalse(tomllib.loads(generated['Cargo.toml'].decode()).get('patch'))

    def test_lock_projection_preserves_transitive_platform_patches_and_source_identity(self):
        root = {'workspace': {'dependencies': {}}, 'patch': {'crates-io': {
            'windows-alias': {'package': 'windows-real', 'git': 'https://example.invalid/windows', 'rev': 'b'*40},
            'same-name-wrong-source': {'package': 'registry-lib', 'git': 'https://example.invalid/unrelated'},
            'unrelated': {'git': 'https://example.invalid/editor'}}}}
        lock = {'version': 4, 'package': [
            {'name': 'gpui', 'version': '1.0.0', 'dependencies': ['bridge']},
            {'name': 'gpui_platform', 'version': '1.0.0'},
            {'name': 'bridge', 'version': '1.0.0', 'source': 'registry+https://example.invalid/index',
             'checksum': 'a'*64, 'dependencies': ['windows-real', 'registry-lib 1.0.0']},
            {'name': 'windows-real', 'version': '2.0.0',
             'source': 'git+https://example.invalid/windows?rev=' + 'b'*40 + '#' + 'b'*40},
            {'name': 'registry-lib', 'version': '1.0.0', 'source': 'registry+https://example.invalid/index', 'checksum': 'c'*64},
            {'name': 'registry-lib', 'version': '2.0.0', 'source': 'registry+https://example.invalid/index', 'checksum': 'd'*64},
        ]}
        raw = {'Cargo.toml': root, 'Cargo.lock': lock, **{
            d+'/Cargo.toml': {'package': {'name': d.split('/')[-1], 'version': '1.0.0'}} for d in im.ENTRIES}}
        class Inputs:
            def read(self, name):
                return tomlkit.dumps(raw[name]).encode()
        projection = im.cargo_projection(Inputs(), im.ENTRIES)
        self.assertEqual(set(projection['kept_patches']['crates-io']), {'windows-alias'})
        self.assertEqual({(p['name'], p['version']) for p in projection['locked_packages']},
                         {('gpui', '1.0.0'), ('gpui_platform', '1.0.0'), ('bridge', '1.0.0'),
                          ('windows-real', '2.0.0'), ('registry-lib', '1.0.0')})
        lock['package'][2]['dependencies'][-1] = 'registry-lib'
        with self.assertRaisesRegex(im.GateError, 'ambiguous locked dependency'):
            im.cargo_projection(Inputs(), im.ENTRIES)
        lock['package'][2]['dependencies'][-1] = 'editor-path'
        lock['package'].append({'name': 'editor-path', 'version': '1.0.0'})
        with self.assertRaisesRegex(im.GateError, 'escapes selected path closure'):
            im.cargo_projection(Inputs(), im.ENTRIES)

    def test_projected_lock_rejects_version_source_checksum_edges_and_missing_members(self):
        import copy
        original = {'version': 4, 'package': [
            {'name': 'gpui', 'version': '0.1.0', 'dependencies': ['used']},
            {'name': 'used', 'version': '1.0.0', 'source': 'registry+https://example.invalid/index',
             'checksum': 'a'*64, 'dependencies': ['optional']},
            {'name': 'optional', 'version': '1.0.0', 'source': 'registry+https://example.invalid/index', 'checksum': 'b'*64},
            {'name': 'editor', 'version': '1.0.0', 'source': 'registry+https://example.invalid/index', 'checksum': 'c'*64}]}
        projection = {'locked_packages': original['package'][:3]}
        pruned = copy.deepcopy(original)
        pruned['package'] = pruned['package'][:2]
        del pruned['package'][1]['dependencies']
        encode = lambda data: tomlkit.dumps(data).encode()
        im.validate_lock_projection(encode(original), encode(pruned), projection)
        for field, value in [('version', '1.0.1'), ('source', 'git+https://example.invalid/replacement#'+'d'*40), ('checksum', 'e'*64)]:
            changed = copy.deepcopy(pruned)
            changed['package'][1][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(im.GateError, 'version/source/checksum'):
                im.validate_lock_projection(encode(original), encode(changed), projection)
        changed = copy.deepcopy(pruned)
        changed['package'][1]['dependencies'] = ['gpui']
        with self.assertRaisesRegex(im.GateError, 'locked dependency edge'):
            im.validate_lock_projection(encode(original), encode(changed), projection)
        changed = copy.deepcopy(pruned)
        changed['package'].pop(0)
        with self.assertRaisesRegex(im.GateError, 'lost an in-tree'):
            im.validate_lock_projection(encode(original), encode(changed), projection)
        changed = copy.deepcopy(pruned)
        changed['package'].append(original['package'][-1])
        with self.assertRaisesRegex(im.GateError, 'version/source/checksum'):
            im.validate_lock_projection(encode(original), encode(changed), projection)

    def test_include_path_and_unknown_dynamic_inputs_fail_closed(self):
        for data in (b'include_bytes!("../../../secret");', b'include!(concat!(env!("SECRET"), "/file"));'):
            with self.subTest(data=data), self.assertRaisesRegex(im.GateError, 'unsafe relative path|unreviewed nonliteral'):
                im.audit_source_inputs({'pkg/file.rs': {}}, lambda _: data, [])

    def test_starlark_uses_utf8_not_unsupported_unicode_escape(self):
        config = im.config_text({'upstream': 'a'*40, 'origin_globs': ['Cargo.toml']},
                                {'README.md': 'generated — branch'.encode()}, '/local/destination.git')
        self.assertIn('generated — branch', config)
        self.assertNotIn('\\u2014', config)

    def test_pinned_jar_hash_is_checked_even_for_explicit_local_path(self):
        (ROOT / '.scratch/tests').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / '.scratch/tests') as temp:
            jar = pathlib.Path(temp) / 'copybara.jar'
            jar.write_bytes(b'not the pinned release')
            with patch.object(im, 'fetch', side_effect=AssertionError('must not replace explicit jar')):
                with self.assertRaisesRegex(im.GateError, 'checksum mismatch'):
                    im.ensure_jar(jar, temp)

    def test_provenance_requires_unique_requested_and_native_markers(self):
        (ROOT / '.scratch/tests').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / '.scratch/tests') as temp:
            repo = pathlib.Path(temp)
            im.git(repo, 'init')
            requested, native = 'a'*40, 'b'*40
            message = f'Import\n\nGitOrigin-RevId: {requested}\nCopybara-Path-RevId: {native}\n'
            im.git(repo, 'commit', '--allow-empty', '-m', message)
            commit = im.git(repo, 'rev-parse', 'HEAD').decode().strip()
            self.assertEqual(im.commit_provenance(repo, commit, requested), native)
            for bad in [message + f'GitOrigin-RevId: {native}\n',
                        message.replace('Copybara-Path-RevId:', 'Unknown-RevId:'),
                        message.replace(requested, 'c'*40)]:
                im.git(repo, 'commit', '--allow-empty', '-m', bad)
                commit = im.git(repo, 'rev-parse', 'HEAD').decode().strip()
                with self.assertRaises(im.GateError):
                    im.commit_provenance(repo, commit, requested)


if __name__ == '__main__':
    unittest.main()
