"""Trusted command list for main candidates; run only on a secret-free ephemeral worker.

The native integration adapter is the final cargo command. This is compile/source-test
coverage, not a compositor or GUI qualification. Missing inputs fail rather than skip.
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib

from gate import GateError, require

ROOT = Path(__file__).resolve().parents[2]


def commands(controller, candidate, scratch):
    controller, candidate, scratch = Path(controller), Path(candidate), Path(scratch)
    for path in ('Cargo.toml', 'Cargo.lock', 'import/pinrail_import.py'):
        require((candidate / path).is_file(), f'main candidate missing {path}')
    for suite in ('ci', 'import'):
        require(any((candidate / 'tests' / suite).glob('test_*.py')), f'main candidate missing {suite} tests')
    toolchain = tomllib.loads((controller / 'scripts/ci/rust-toolchain.toml').read_text())['toolchain']['channel']
    require(isinstance(toolchain, str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', toolchain),
            'main controller must pin a Rust release')
    python = str(scratch / 'main-venv' / 'bin' / 'python')
    return [
        ['uv', 'venv', '--python', 'python3', str(scratch / 'main-venv')],
        ['uv', 'pip', 'sync', '--python', python, '--require-hashes', str(controller / 'import/requirements.txt')],
        ['rustup', 'toolchain', 'install', toolchain, '--profile', 'minimal'],
        [python, '-m', 'unittest', 'discover', '-s', 'tests/ci', '-v'],
        [python, '-m', 'unittest', 'discover', '-s', 'tests/import', '-v'],
        ['cargo', f'+{toolchain}', 'metadata', '--locked', '--all-features', '--format-version', '1'],
        ['cargo', f'+{toolchain}', 'check', '--locked', '--workspace', '--all-targets',
         '--features', 'gpui/test-support'],
        ['cargo', f'+{toolchain}', 'test', '--locked', '-p', 'gpui', '-p', 'gpui_linux', '-p', 'gpui_wgpu',
         '--lib', '--features', 'gpui/test-support', '--', '--test-threads=2',
         # These atlas tests request actual adapters/devices even without a display.
         '--skip', 'wgpu_atlas::tests::before_frame_skips_uploads_for_removed_texture',
         '--skip', 'wgpu_atlas::tests::remove_deallocates_tile_space_for_reuse',
         '--skip', 'wgpu_atlas::tests::reused_texture_id_has_new_generation'],
    ]


def main():
    require(len(sys.argv) == 2, 'expected one candidate checkout path')
    candidate = Path(sys.argv[1]).resolve()
    scratch = ROOT / '.scratch'
    scratch.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, UV_CACHE_DIR=str(scratch / 'uv-cache'),
               CARGO_TARGET_DIR=str(scratch / 'target'), CARGO_BUILD_JOBS='2',
               CARGO_PROFILE_DEV_DEBUG='0', CARGO_PROFILE_TEST_DEBUG='0')
    for command in commands(ROOT, candidate, scratch):
        print('Running prescribed command:', ' '.join(command), flush=True)
        subprocess.run(command, cwd=candidate, env=env, check=True, timeout=2700)


if __name__ == '__main__':
    try:
        main()
    except (GateError, OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        print(f'Main checks failed: {exc}', file=sys.stderr)
        sys.exit(1)
