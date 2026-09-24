import importlib.util
import pathlib
import unittest

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


if __name__ == '__main__':
    unittest.main()
