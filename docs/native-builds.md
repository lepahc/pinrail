# Native build and CPU-test profiles

The trusted controller runs:

```text
python <controller>/scripts/ci/native_checks.py --platform PLATFORM --candidate ABSOLUTE_WORKTREE
```

Supported profiles:

| Platform | Standard hosted image | Required native Rust host |
| --- | --- | --- |
| `macos-arm64` | `macos-15` | `aarch64-apple-darwin` |
| `macos-x86_64` | `macos-15-intel` | `x86_64-apple-darwin` |
| `windows-x86_64` | `windows-2025` | `x86_64-pc-windows-msvc` |

The workflow pins Python 3.13.7 on native workers; the stdlib-only driver requires
Python 3.11 or newer and its controlled-process tests also run on Linux. The driver's own resolved location selects the
controller and `scripts/ci/rust-toolchain.toml` (Rust **1.98.1**), never candidate
Python or a candidate toolchain pin. OS/architecture and `rustc -vV` host/release
must match. Linux is rejected before launching anything; these are not cross-build
profiles or Rosetta substitutes.

## Trust and resource boundary

The route must admit an exact downstream head, run the controller-sourced script
on an ephemeral read-only/secret-free worker, and supply an existing private
absolute `TMPDIR` (or `TMP`/`TEMP`). The driver is **not a sandbox**: Cargo executes
candidate build scripts and proc macros. Do not run it on generated import
candidates, give it publisher credentials, or execute worker outputs in a privileged
job. This driver does not perform the Linux importer/source-harness suites.

The driver creates a unique short `n-*/t` target below the private temporary root.
There is no shared build cache and no global configuration write. Scratch and
stdout/stderr logs remain for the worker lifetime; the ephemeral worker owns final
removal. Printed scratch/log paths identify the evidence. Compiler output streams
with a prefix so candidate output is not interpreted as GitHub log commands.
Metadata stdout is retained in a log rather than flooding the console.

Limits: two Cargo jobs, dev/test debug information disabled, incremental builds
disabled, 64 MiB combined stdout/stderr per command. Commands share a 3,590-second
budget, leaving up to ten seconds for owned-process-tree termination (POSIX
process group or Windows `taskkill /T /F`). Stage maxima are 60 seconds for each
native-tool probe, 300 for toolchain installation/metadata, 1,200 for native check,
link-only tests and final example linking, 600 per exact native CPU selection,
and 900 per core library CPU suite. Each command receives the smaller of its stage
limit and the remaining total budget. Set an independent workflow timeout as well;
worker isolation, resource quotas and job cancellation remain route responsibilities.

Ambient `RUSTFLAGS`, `CARGO_ENCODED_RUSTFLAGS`, Rust compiler/wrapper overrides,
`CARGO_PROFILE_*` and `CARGO_TARGET_*` overrides are rejected instead of silently
changing the prescribed profiles. Repository `.cargo/config.toml` flags are retained,
including Windows static CRT, `windows_slim_errors` and `tokio_unstable`; the driver
does not set an empty `RUSTFLAGS` or rewrite ambient/global Cargo configuration.

Before work and after **every** subprocess, candidate `Cargo.lock` must equal the
controller lock byte-for-byte. The controller must retain exactly 875 unique
package identities. Every Cargo resolution/build/test command uses `--locked`.
Full target-filtered `metadata --all-features` is resolution-only; **no compile or
test command uses blanket all-features**. Lock drift, missing tools/artifacts,
nonzero native exits, timeout, malformed test summaries and zero successful tests
are failures, not skips.

## macOS: Metal, real text, link-only example

When `/Applications/Xcode_16.4.app/Contents/Developer` exists, it is selected with
`DEVELOPER_DIR` for this process tree only. Otherwise the supplied/default Xcode
selection is recorded and must pass the same probes. The driver records macOS,
Xcode and SDK identity; resolves `metal`/`metallib`; and compiles/links a tiny Metal
shader without executing it. No standalone cbindgen install is required: it is
already a locked build dependency.

- Check `gpui`, `gpui_platform`, `gpui_macos`, `gpui_apple` with `--all-targets`,
  `gpui/test-support,gpui_platform/font-kit`.
- Link their `--lib --no-run` test binaries with the same feature selection.
- Execute four **exact** `gpui_macos` tests: the null-screen display-ID policy and
  `text_system::tests::test_layout_line_{bom_char,zwnj_insertion,zwnj_edge_cases}`.
  The text tests enable `gpui_macos/font-kit` and use real system fonts, not the
  no-op text backend. Each invocation must report exactly one passed test and none
  ignored.
- Execute the separate GPUI/WGPU CPU suites described below.
- Build, **do not run**, `gpui`'s `hello_world` example with
  `gpui_platform/font-kit`. Require both the linked executable and nonempty
  `gpui_apple` `shaders.metallib` from this fresh target.

The native Mac backend is Metal, not WGPU. `runtime_shaders` is not enabled as a
fallback. Metal atlas/headless-renderer tests, native pasteboard tests, ignored
visual tests and optional screen capture are excluded from execution. A modern
hosted build does not prove compatibility with the configured minimum macOS OS
version or qualify AppKit main-thread behavior.

## Windows: MSVC/SDK, manifest, FXC release-path smoke

Discover Visual Studio with `vswhere` and initialize its x64 `VsDevCmd.bat`
environment. An already configured MSVC environment is accepted when vswhere is
absent, but still must pass every tool probe. The driver checks `INCLUDE`/`LIB`,
locates `cl.exe`, `link.exe`, `rc.exe`, CMake, records tool/SDK paths and versions,
and actually compiles a C file including `windows.h`, compiles a resource and links
a tiny executable without running it. Native command exit codes are checked
directly, including the `cmd.exe` developer-environment wrapper.

FXC is resolved to **one existing executable file**: explicit `GPUI_FXC_PATH`, then
PATH, then a numerically newest installed x64 Windows SDK. A malformed explicit
path fails rather than silently falling back. A tiny HLSL vertex shader must
compile successfully before Cargo starts; the chosen path is passed as
`GPUI_FXC_PATH` to avoid the build script's multi-line `where.exe` fallback.

- Check `gpui`, `gpui_platform`, `gpui_windows` libraries; link their library test
  binaries with `--no-run` and `gpui/test-support,gpui_windows/test-support`.
  Including `gpui_platform` compiles the Windows manifest resource even in debug.
- Execute six exact `dialog::tests::*` policy tests listed in the trusted driver,
  plus `direct_write::tests::test_cluster_map` and
  `platform::tests::test_encode_restart_arguments`. Each invocation must pass
  exactly one test, none ignored. The dialog selection is a fixed allowlist, not a
  module-prefix invocation that could pick up future interactive tests.
- Execute the separate GPUI/WGPU CPU suites.
- Build, **do not run**, the default-feature `gpui` `hello_world` example with
  `--release`. This exercises `gpui_windows/build.rs`'s
  `cfg(not(debug_assertions))` FXC pipeline and final native linking. Require the
  resulting executable, generated `shaders_bytes.rs`, and representative first/
  last shader headers from the fresh release target.

This is a **bounded release-path smoke**, not production release optimization:
Cargo command-line profile overrides set release opt-level **1**, debug **0**,
LTO **false**, codegen-units **16**, incremental **false**, debug-assertions
**false**. Release build-script overrides use opt-level **0**, debug **0** and,
critically, debug-assertions **false** too. Disabling assertions only for the final
library is insufficient: the FXC branch is selected when compiling its build script.

Do not execute DirectX emoji/device tests, WARP atlas tests, native clipboard,
native dialogs or optional screen capture in this profile. Software WARP is not a
pure CPU policy test or evidence about physical GPU presentation.

## Shared core CPU profile and evidence limits

Run `cargo test --lib --features gpui/test-support` separately for `gpui` and
`gpui_wgpu`, with two libtest threads and these exact named exclusions, matching
the existing Linux main profile:

- `wgpu_atlas::tests::before_frame_skips_uploads_for_removed_texture`
- `wgpu_atlas::tests::remove_deallocates_tile_space_for_reuse`
- `wgpu_atlas::tests::reused_texture_id_has_new_generation`

Each crate must independently report one successful libtest summary with a
nonzero passed count. One crate's passing tests cannot mask another's zero tests.
Ignored tests are not enabled. Link-only stages do not count as executed tests.

Local verification:

```sh
python3 -m unittest discover -s tests/ci -v
```

`tests/ci/test_native_checks.py` exercises the actual builder, environment policy,
preflight choices, subprocess transport, time/output bounds, lock guards and
failure/test-count checks using controlled Python child processes for all three
platforms. Fixture artifacts and tool output are deliberately fake. **Those tests
are not native compile/link/shader results.** Only completed native hosted runs
qualify these profiles; no GPU, GUI, pixels, IME/focus, clipboard, accessibility,
minimum-OS compatibility, signing or packaging qualification is claimed.
