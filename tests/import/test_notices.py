import hashlib
import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('notice_importer', ROOT / 'import/pinrail_import.py')
assert spec is not None and spec.loader is not None
im = importlib.util.module_from_spec(spec)
spec.loader.exec_module(im)

EXPECTED = '5d177f23ecfeb0ea8e050b6a5a16355e1ae9a0b286436ca8f83ed08b3795be6b'
NOTICE_PATH = 'docs/licenses/microsoft-terminal-MIT.txt'


class NoticeTests(unittest.TestCase):
    def generated(self):
        class Inputs:
            def read(self, name):
                return {
                    'Cargo.toml': b'[workspace]\nmembers=[]\n[workspace.dependencies]\n',
                    'Cargo.lock': b'version = 4\npackage = []\n',
                    'crates/gpui/Cargo.toml': b'[package]\nname="gpui"\n[[example]]\nname="svg"\npath="examples/svg/svg.rs"\n',
                }[name]
        inventory = {'upstream': 'a' * 40, 'package_dirs': [], 'workspace_dependencies': [],
                     'license_findings': [], 'audit_limits': 'test fixture'}
        return im.generated_files(inventory, Inputs(), 'b' * 64, 'c' * 64,
                                  b'version = 4\npackage = []\n')

    def test_generated_tree_carries_pinned_microsoft_permission_text(self):
        generated = self.generated()
        self.assertIn('LICENSE-MICROSOFT-MIT', generated)
        notice = generated['LICENSE-MICROSOFT-MIT']
        self.assertEqual(hashlib.sha256(notice).hexdigest(), EXPECTED)
        self.assertIn(b'copyright notice and this permission notice', notice)
        self.assertIn(b'LICENSE-MICROSOFT-MIT -text whitespace=cr-at-eol', generated['.gitattributes'])
        self.assertIn(NOTICE_PATH, im.CODE_FILES)

    def test_tampered_supplemental_notice_cannot_be_generated(self):
        parent = ROOT / '.scratch/tests'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as tmp:
            fake_root = pathlib.Path(tmp)
            notice = fake_root / NOTICE_PATH
            notice.parent.mkdir(parents=True)
            notice.write_bytes(b'permission terms silently removed')
            with patch.object(im, 'ROOT', fake_root):
                with self.assertRaisesRegex(im.GateError, 'notice checksum'):
                    self.generated()


if __name__ == '__main__':
    unittest.main()
