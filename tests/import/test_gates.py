import importlib.util
import pathlib
import unittest
import json
import os
import subprocess
import tempfile
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
            record = {'scope': 'private-evaluation-only', 'review': 'unit review', 'inventory': old}
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

    def test_include_path_and_unknown_dynamic_inputs_fail_closed(self):
        for data in (b'include_bytes!("../../../secret");', b'include!(concat!(env!("SECRET"), "/file"));'):
            with self.subTest(data=data), self.assertRaisesRegex(im.GateError, 'unsafe relative path|unreviewed nonliteral'):
                im.audit_source_inputs({'pkg/file.rs': {}}, lambda _: data, [])

    def test_starlark_uses_utf8_not_unsupported_unicode_escape(self):
        config = im.config_text({'upstream': 'a'*40, 'origin_globs': ['Cargo.toml']},
                                {'README.md': 'generated — branch'.encode()}, '/local/destination.git')
        self.assertIn('generated — branch', config)
        self.assertNotIn('\\u2014', config)


if __name__ == '__main__':
    unittest.main()
