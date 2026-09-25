"""Trusted, bounded native compile/link + CPU checks on secret-free native workers.

Invoke this file from the controller, not from the candidate. The route owns worker
isolation and TMPDIR; this driver is not a sandbox for Cargo/build.rs/proc-macros.
Only Python's standard library is required (3.11+). See docs/native-builds.md.
"""
import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tomllib

ROOT = Path(__file__).resolve().parents[2]
PLATFORMS = {
    'macos-arm64': ('Darwin', ('arm64', 'aarch64'), 'aarch64-apple-darwin'),
    'macos-x86_64': ('Darwin', ('x86_64',), 'x86_64-apple-darwin'),
    'windows-x86_64': ('Windows', ('amd64', 'x86_64'), 'x86_64-pc-windows-msvc'),
}
GPU_SKIPS = (
    'wgpu_atlas::tests::before_frame_skips_uploads_for_removed_texture',
    'wgpu_atlas::tests::remove_deallocates_tile_space_for_reuse',
    'wgpu_atlas::tests::reused_texture_id_has_new_generation',
)
MAC_TESTS = (
    'window::tests::display_id_for_screen_returns_none_for_null_screen',
    'text_system::tests::test_layout_line_bom_char',
    'text_system::tests::test_layout_line_zwnj_insertion',
    'text_system::tests::test_layout_line_zwnj_edge_cases',
)
WINDOWS_TESTS = (
    'dialog::tests::task_dialog_cancellation_requires_cancel_button_or_internal_request',
    'dialog::tests::closing_owner_cancels_every_outstanding_dialog',
    'dialog::tests::closed_owner_waits_for_active_dialog_but_queued_requests_stay_cancelled',
    'dialog::tests::cancelling_one_request_does_not_cancel_its_owner_or_other_requests',
    'dialog::tests::dialogs_serialize_per_owner',
    'dialog::tests::ownerless_request_can_be_cancelled_without_a_window',
    'direct_write::tests::test_cluster_map',
    'platform::tests::test_encode_restart_arguments',
)
# This is a bounded release-path smoke, NOT the production release profile.
# In particular, the build script itself must have debug_assertions=false for FXC.
RELEASE_CONFIG = (
    'profile.release.opt-level=1', 'profile.release.debug=0',
    'profile.release.lto=false', 'profile.release.codegen-units=16',
    'profile.release.debug-assertions=false', 'profile.release.incremental=false',
    'profile.release.build-override.opt-level=0',
    'profile.release.build-override.debug=0',
    'profile.release.build-override.debug-assertions=false',
)


class NativeCheckError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise NativeCheckError(message)


def validate_host(name):
    require(name in PLATFORMS, f'unsupported native platform: {name}')
    system, machines, triple = PLATFORMS[name]
    observed = (platform.system(), platform.machine().lower())
    require(observed[0] == system and observed[1] in machines,
            f'wrong native host for {name}: {observed}; expected {system}/{machines}')
    return triple


def toolchain():
    channel = tomllib.loads((ROOT / 'scripts/ci/rust-toolchain.toml').read_text())['toolchain']['channel']
    require(isinstance(channel, str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', channel),
            'controller must pin a Rust release')
    return channel


class LockGuard:
    def __init__(self, candidate):
        self.path = candidate / 'Cargo.lock'
        self.expected = (ROOT / 'Cargo.lock').read_bytes()
        packages = tomllib.loads(self.expected.decode('utf-8'))['package']
        identities = {(p['name'], p['version'], p.get('source')) for p in packages}
        require(len(packages) == len(identities) == 875, 'controller lock must retain the 875-identity cohort')
        self.check()
        print('Cargo.lock sha256:', hashlib.sha256(self.expected).hexdigest(), flush=True)

    def check(self):
        require(self.path.is_file() and self.path.read_bytes() == self.expected,
                'candidate Cargo.lock drifted from the trusted 875-package lock')


@dataclass(frozen=True)
class Stage:
    name: str
    args: tuple
    timeout: int
    tests: bool = False
    exact_count: int | None = None


def build_stages(name, channel):
    """Fixed reviewed commands; neither candidate Python nor config selects them."""
    require(name in PLATFORMS, f'unsupported native platform: {name}')
    triple = PLATFORMS[name][2]
    mac = name.startswith('macos-')
    packages = ('gpui', 'gpui_platform', 'gpui_macos', 'gpui_apple') if mac else (
        'gpui', 'gpui_platform', 'gpui_windows')
    features = 'gpui/test-support,gpui_platform/font-kit' if mac else (
        'gpui/test-support,gpui_windows/test-support')

    def cargo(action, selected, extra=(), enabled: str | None = features):
        args = ['cargo', f'+{channel}', action, '--locked', '--target', triple]
        # Cargo's profile build-override tables need explicit config overrides;
        # profile-wide DEBUG env vars do not replace a manifest build-override.
        args += ['--config', 'profile.dev.build-override.debug=0',
                 '--config', 'profile.test.build-override.debug=0']
        for package in selected:
            args += ['-p', package]
        args += list(extra)
        if enabled:
            args += ['--features', enabled]
        return args

    stages = [Stage('metadata-resolution-only', (
        'cargo', f'+{channel}', 'metadata', '--locked', '--all-features',
        '--format-version', '1', '--filter-platform', triple), 300)]
    stages += [
        Stage('native-check', tuple(cargo('check', packages, ('--all-targets',) if mac else ('--lib',))), 1200),
        Stage('native-test-link', tuple(cargo('test', packages, ('--lib', '--no-run'))), 1200),
    ]
    native_package = 'gpui_macos' if mac else 'gpui_windows'
    native_features = 'gpui/test-support,gpui_macos/font-kit' if mac else features
    for test in MAC_TESTS if mac else WINDOWS_TESTS:
        args = cargo('test', (native_package,), ('--lib',), native_features)
        args += ['--', '--exact', test, '--test-threads=2', '--color=never']
        stages.append(Stage(test, tuple(args), 600, tests=True, exact_count=1))
    # One crate per invocation: a nonempty GPUI suite cannot mask an empty WGPU suite.
    for package in ('gpui', 'gpui_wgpu'):
        args = cargo('test', (package,), ('--lib',), 'gpui/test-support')
        args += ['--', '--test-threads=2', '--color=never']
        for skip in GPU_SKIPS:
            args += ['--skip', skip]
        stages.append(Stage(f'{package}-cpu', tuple(args), 900, tests=True))
    smoke = cargo('build', ('gpui',), ('--example', 'hello_world'),
                  'gpui_platform/font-kit' if mac else None)
    if not mac:
        smoke += ['--release']
        for setting in RELEASE_CONFIG:
            smoke += ['--config', setting]
    stages.append(Stage('hello-world-link-only', tuple(smoke), 1200))
    return stages


def check_test_output(output, exact_count=None):
    summaries = re.findall(
        r'^test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; '
        r'(\d+) measured; (\d+) filtered out;', output, re.MULTILINE)
    require(len(summaries) == 1, 'expected exactly one successful libtest summary')
    passed, failed, ignored, measured, _ = map(int, summaries[0])
    require(passed > 0 and failed == 0 and measured == 0,
            f'CPU selection must execute nonzero successful tests: {summaries[0]}')
    if exact_count is not None:
        require(passed == exact_count and ignored == 0,
                f'CPU selection expected {exact_count} passed, none ignored: {summaries[0]}')
    print(f'Verified CPU selection: {passed} passed, {ignored} ignored', flush=True)


def build_environment(ambient, scratch, windows=False):
    # Windows env keys are case-insensitive. Avoid duplicate Path/PATH after VS setup.
    env = {k.upper() if windows else k: v for k, v in ambient.items()}
    # Do not replace .cargo/config.toml rustflags with RUSTFLAGS, including an empty
    # string. Ambient overrides make the profile/target/runner assertion unprovable.
    forbidden = [k for k in env if k in ('RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS',
                 'RUSTC', 'RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER') or
                 k.startswith(('CARGO_PROFILE_', 'CARGO_TARGET_'))]
    require(not forbidden, f'ambient Cargo/Rust overrides are not supported: {forbidden}')
    env.update(CARGO_BUILD_JOBS='2', CARGO_INCREMENTAL='0',
               CARGO_PROFILE_DEV_DEBUG='0', CARGO_PROFILE_TEST_DEBUG='0',
               CARGO_TARGET_DIR=str(scratch / 't'), CARGO_TERM_COLOR='never',
               CARGO_TERM_PROGRESS_WHEN='never',
               TMPDIR=str(scratch), TMP=str(scratch), TEMP=str(scratch))
    return env


class Runner:
    """File-backed, bounded subprocess transport; no shell except VS env discovery.

    Output is streamed with a prefix (candidate output cannot issue Actions log
    commands) and retained in separate logs. Polling regular files avoids both
    pipe-capacity deadlocks and a child holding a pipe open after its parent exits.
    """
    def __init__(self, candidate, env, scratch, guard, *, budget=3590, max_output=64 * 1024 * 1024):
        self.cwd, self.env, self.scratch, self.guard = candidate, env, scratch, guard
        self.deadline = time.monotonic() + budget  # leave ten seconds for tree teardown
        self.max_output = max_output
        self.number = 0
        self.logs = scratch / 'logs'
        self.logs.mkdir()

    def stop(self, process):
        if os.name == 'nt':
            # Explicit native status is checked; never rely on PowerShell's $?.
            result = subprocess.run(['taskkill.exe', '/F', '/T', '/PID', str(process.pid)],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
            if result.returncode and process.poll() is None:
                process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=5)

    def run(self, name, args, timeout=60, quiet_stdout=False):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, 'native checks exceeded the total 60-minute budget')
        timeout = min(timeout, remaining)
        self.number += 1
        stem = f'{self.number:02d}-' + re.sub(r'[^a-zA-Z0-9_-]', '-', name)
        paths = [self.logs / f'{stem}.{suffix}.log' for suffix in ('stdout', 'stderr')]
        print(f'[{name}] timeout={timeout:.1f}s command={list(args)!r}', flush=True)
        print('Logs:', *map(str, paths), flush=True)
        process = None
        try:
            with paths[0].open('wb') as out, paths[1].open('wb') as err:
                process = subprocess.Popen(list(args), cwd=self.cwd, env=self.env,
                                           stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                           start_new_session=os.name != 'nt')
                started = time.monotonic()
                with paths[0].open('rb') as out_reader, paths[1].open('rb') as err_reader:
                    while True:
                        size = sum(p.stat().st_size for p in paths)
                        require(size <= self.max_output, f'{name}: command output exceeded {self.max_output} bytes')
                        for index, reader in enumerate((out_reader, err_reader)):
                            chunk = reader.read(65536)
                            if chunk and not (index == 0 and quiet_stdout):
                                print(' | ' + chunk.decode('utf-8', errors='replace').replace('\n', '\n | '), flush=True)
                        status = process.poll()
                        if status is not None:
                            # Drain all remaining bytes, with the size bound already checked.
                            for index, reader in enumerate((out_reader, err_reader)):
                                rest = reader.read(self.max_output + 1)
                                if rest and not (index == 0 and quiet_stdout):
                                    print(' | ' + rest.decode('utf-8', errors='replace').replace('\n', '\n | '), flush=True)
                            break
                        require(time.monotonic() - started < timeout, f'{name}: timed out after {timeout:.1f}s')
                        time.sleep(0.1)
                require(sum(p.stat().st_size for p in paths) <= self.max_output,
                        f'{name}: command output exceeded {self.max_output} bytes')
                require(status == 0, f'{name}: command exited {status}; see {paths}')
            output = paths[0].read_text(encoding='utf-8', errors='replace')
        except BaseException as primary:
            failures = []
            if process is not None:
                try:
                    self.stop(process)
                except (OSError, subprocess.SubprocessError) as exc:
                    failures.append(f'process cleanup failed: {exc}')
            try:
                self.guard.check()
            except (NativeCheckError, OSError) as exc:
                failures.append(str(exc))
            if failures:
                raise NativeCheckError(f'{primary}; ' + '; '.join(failures)) from primary
            raise
        self.guard.check()
        return output


def single_path(output, label, *, directory=False):
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    require(len(lines) == 1, f'{label}: expected exactly one path, got {lines!r}')
    path = Path(lines[0])
    require(path.is_absolute() and (path.is_dir() if directory else path.is_file()),
            f'{label}: missing or invalid path: {path}')
    return path


def nonempty(path):
    require(path.is_file() and path.stat().st_size > 0, f'missing or empty build artifact: {path}')


def mac_preflight(runner):
    xcode = Path('/Applications/Xcode_16.4.app/Contents/Developer')
    if xcode.is_dir():
        runner.env['DEVELOPER_DIR'] = str(xcode)
    print('DEVELOPER_DIR:', runner.env.get('DEVELOPER_DIR', '(xcode-select default)'), flush=True)
    runner.run('macos-version', ['sw_vers'])
    runner.run('xcode-version', ['xcodebuild', '-version'])
    single_path(runner.run('macos-sdk', ['xcrun', '--sdk', 'macosx', '--show-sdk-path']), 'macOS SDK', directory=True)
    for tool in ('metal', 'metallib'):
        single_path(runner.run(f'find-{tool}', ['xcrun', '--sdk', 'macosx', '--find', tool]), tool)
    runner.run('metal-version', ['xcrun', '--sdk', 'macosx', 'metal', '--version'])
    # Prove the installed tools work, not merely that xcrun knows their names.
    source, air, library = (runner.scratch / name for name in ('probe.metal', 'probe.air', 'probe.metallib'))
    source.write_text('#include <metal_stdlib>\nusing namespace metal;\nkernel void probe(device float *p [[buffer(0)]], uint i [[thread_position_in_grid]]) { p[i] = 0; }\n')
    runner.run('metal-preflight', ['xcrun', '--sdk', 'macosx', 'metal', '-c', str(source), '-o', str(air)])
    nonempty(air)
    runner.run('metallib-preflight', ['xcrun', '--sdk', 'macosx', 'metallib', str(air), '-o', str(library)])
    nonempty(library)


def which(tool, env):
    return shutil.which(tool, path=env.get('PATH', ''))


def windows_environment(runner):
    env = runner.env
    default = Path(env.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    vswhere = str(default) if default.is_file() else which('vswhere.exe', env)
    if vswhere:
        installation = single_path(runner.run('visual-studio', [vswhere, '-utf8', '-latest', '-products', '*',
            '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath']),
            'Visual Studio', directory=True)
        script = installation / 'Common7/Tools/VsDevCmd.bat'
        require(script.is_file(), f'Visual Studio developer environment missing: {script}')
        require(not any(c in str(script) for c in '\r\n"%&|<>^!'), 'unsafe Visual Studio installation path')
        # Keep cmd tokens separate: Popen's Windows list2cmdline would backslash-
        # escape the nested path quotes in a single body, which cmd cannot parse.
        output = runner.run('msvc-environment', ['cmd.exe', '/d', '/s', '/c', 'call',
            str(script), '-no_logo', '-arch=x64', '-host_arch=x64', '&&', 'set'], quiet_stdout=True)
        imported = {}
        for line in output.splitlines():
            key, sep, value = line.partition('=')
            if sep and key and not key.startswith('='):
                imported[key.upper()] = value
        require(imported.get('VSCMD_ARG_TGT_ARCH') == 'x64', 'VS environment did not select x64')
        # VsDevCmd may alter many discovery variables; keep our limits and temp paths.
        protected = {k: v for k, v in env.items() if k.startswith(('CARGO_', 'RUSTUP_')) or k in ('TMPDIR', 'TMP', 'TEMP')}
        env.update(imported)
        env.update(protected)
    # Preconfigured Rust/MSVC workers are also supported, but must pass real C/SDK probes.
    require(env.get('INCLUDE') and env.get('LIB'), 'MSVC/Windows SDK INCLUDE and LIB are missing; install VS C++ tools')
    require(env.get('VSCMD_ARG_TGT_ARCH', 'x64') == 'x64', 'MSVC environment is not x64')


def fxc_path(env):
    explicit = env.get('GPUI_FXC_PATH')
    if explicit is not None:
        return single_path(explicit, 'GPUI_FXC_PATH')
    found = which('fxc.exe', env)
    if found:
        return single_path(found, 'FXC')
    roots = []
    if env.get('WINDOWSSDKDIR'):
        roots.append(Path(env['WINDOWSSDKDIR']) / 'bin')
    roots.append(Path(env.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')) / 'Windows Kits/10/bin')
    for root in roots:
        versions = [p for p in root.glob('*') if re.fullmatch(r'\d+(?:\.\d+)+', p.name)]
        for version in sorted(versions, key=lambda p: tuple(map(int, p.name.split('.'))), reverse=True):
            path = version / 'x64/fxc.exe'
            if path.is_file():
                return path.resolve()
    raise NativeCheckError('missing shader compiler fxc.exe (Windows SDK)')


def windows_preflight(runner):
    windows_environment(runner)
    tools = {}
    for name in ('cl.exe', 'link.exe', 'rc.exe', 'cmake.exe'):
        found = which(name, runner.env)
        require(found is not None, f'missing native tool: {name}')
        tools[name] = str(single_path(found, name))
        print(f'{name}: {tools[name]}', flush=True)
    for key in ('VCTOOLSVERSION', 'WINDOWSSDKDIR', 'WINDOWSSDKVERSION'):
        print(f'{key}: {runner.env.get(key, "(preconfigured)")}', flush=True)
    runner.run('cmake-version', [tools['cmake.exe'], '--version'])
    c, obj, rc, res, exe = (runner.scratch / f'probe.{s}' for s in ('c', 'obj', 'rc', 'res', 'exe'))
    c.write_text('#include <windows.h>\nint main(void) { return 0; }\n')
    rc.write_text('1 RCDATA { 1, 2, 3 }\n')
    runner.run('msvc-compile', [tools['cl.exe'], '/Bv', '/MT', '/c', str(c), f'/Fo{obj}'])
    nonempty(obj)
    runner.run('sdk-resource', [tools['rc.exe'], '/nologo', '/fo', str(res), str(rc)])
    nonempty(res)
    runner.run('msvc-link', [tools['link.exe'], str(obj), str(res), f'/OUT:{exe}', '/SUBSYSTEM:CONSOLE', '/MACHINE:X64'])
    nonempty(exe)  # link only; do not execute this or the GUI example
    compiler = fxc_path(runner.env)
    runner.env['GPUI_FXC_PATH'] = str(compiler)
    print('GPUI_FXC_PATH:', compiler, flush=True)
    source, output = runner.scratch / 'probe.hlsl', runner.scratch / 'probe.cso'
    source.write_text('float4 main(float4 pos : POSITION) : SV_POSITION { return pos; }\n')
    runner.run('fxc-preflight', [str(compiler), '/T', 'vs_4_0', '/E', 'main', '/Fo', str(output), str(source)])
    nonempty(output)


def verify_build_artifacts(name, env):
    target = Path(env['CARGO_TARGET_DIR']) / PLATFORMS[name][2]
    mac = name.startswith('macos-')
    profile = 'debug' if mac else 'release'
    nonempty(target / profile / 'examples' / ('hello_world' if mac else 'hello_world.exe'))
    shader = 'gpui_apple-*/out/shaders.metallib' if mac else 'gpui_windows-*/out/shaders_bytes.rs'
    artifacts = list((target / profile / 'build').glob(shader))
    require(artifacts, f'missing default-path native shader output: {shader}')
    for artifact in artifacts:
        nonempty(artifact)
        if not mac:
            for header in ('quad_vs.h', 'emoji_rasterization_ps.h'):
                nonempty(artifact.parent / header)
        print('Verified native shader artifact:', artifact, flush=True)


def run_checks(name, candidate):
    triple = validate_host(name)  # Linux/wrong architecture must fail before any spawn/build.
    candidate = Path(candidate)
    require(candidate.is_absolute(), '--candidate must be an absolute worktree path')
    candidate = candidate.resolve(strict=True)
    require((candidate / 'Cargo.toml').is_file(), 'candidate is missing Cargo.toml')
    guard = LockGuard(candidate)
    channel = toolchain()
    tmp = os.environ.get('TMPDIR') or os.environ.get('TMP') or os.environ.get('TEMP')
    require(tmp and Path(tmp).is_absolute() and Path(tmp).is_dir(), 'route must supply an existing private absolute TMPDIR/TMP/TEMP')
    # A unique short target avoids stale build/shader artifacts and Windows MAX_PATH.
    scratch = Path(tempfile.mkdtemp(prefix='n-', dir=tmp)).resolve()
    print('Native scratch (retained for worker lifetime):', scratch, flush=True)
    env = build_environment(os.environ, scratch, name.startswith('windows-'))
    runner = Runner(candidate, env, scratch, guard)
    runner.run('install-rust', ['rustup', 'toolchain', 'install', channel, '--profile', 'minimal'], timeout=300)
    rust = runner.run('rust-host', ['rustc', f'+{channel}', '-vV'])
    require(re.findall(r'^host: (\S+)$', rust, re.MULTILINE) == [triple],
            f'Rust host does not match required native target {triple}')
    require(re.findall(r'^release: (\S+)$', rust, re.MULTILINE) == [channel], 'Rust release does not match controller pin')
    runner.run('cargo-version', ['cargo', f'+{channel}', '--version'])
    if name.startswith('macos-'):
        mac_preflight(runner)
    else:
        windows_preflight(runner)
    for stage in build_stages(name, channel):
        output = runner.run(stage.name, stage.args, stage.timeout, quiet_stdout=stage.name == 'metadata-resolution-only')
        if stage.tests:
            check_test_output(output, stage.exact_count)
    verify_build_artifacts(name, env)
    guard.check()
    print(f'Native checks passed: {name}; compile/link/shaders + selected CPU tests only', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=PLATFORMS, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        run_checks(args.platform, args.candidate)
    except (NativeCheckError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f'Native checks failed: {exc}', file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
