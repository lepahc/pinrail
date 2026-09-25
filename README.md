# Pinrail

Pinrail is a standalone GPUI-family workspace with a small downstream framework
patch series. It retains upstream crate names and platform source; it is not a
new renderer or an application-specific widget library.

- **`main`** is the downstream development/consumer branch.
- **`upstream-import`** is generated. Do not hand-edit it or add runtime patches.
- Current source pin: Zed `2c4bc2d7b2c5b7832ad964f39840d823d961cb0e`.
- The reviewed lock retains the exact selected upstream dependency cohort. Do not
  mix published GPUI packages into it solely because a version string matches.

## Build and test

Initial qualification is Linux with Rust **1.98.1**. Install the native development
libraries listed in [the CI workflow](.github/workflows/verify.yml), plus `uv` for
controller tests. Run Cargo with `--locked`; a lock change requires review.

```sh
cargo +1.98.1 check --locked --workspace --all-targets --features gpui/test-support
```

The trusted test driver runs importer/CI regressions, full locked metadata, the
workspace check, CPU-only GPUI/wgpu tests, and Linux library/integration tests:

```sh
mkdir -p .scratch/tmp
systemd-run --user --wait --pipe --collect \
  -p MemoryMax=10G -p MemoryHigh=8G -p CPUQuota=200% -p TasksMax=512 \
  --working-directory="$PWD" \
  env -u DISPLAY -u WAYLAND_DISPLAY -u WAYLAND_SOCKET \
  TMPDIR="$PWD/.scratch/tmp" \
  python3 scripts/ci/main_checks.py "$PWD"
```

Three atlas tests explicitly request GPU devices and are excluded from this
CPU-only profile. Removing display variables alone does not prevent GPU use.
Headless control-flow tests do not establish compositor, native focus/IME, pixel,
or presentation behavior. Other platforms are retained but not execution-qualified.
The separate `hello_web` example workspace is not covered by root-workspace gates.

## Downstream scope

[PATCHES.md](PATCHES.md) describes the adopted retry-registration, XDG resize,
pointer/IME reentry, release-state, and existing layer-shell safeguards, their
regression coverage, and its limitations. Retained-layer transitions, capture,
serial-free clipboard, component-library changes and consumer migrations remain
separate work—not silently included here.

## Repeated imports and provenance

Use [the local import controller](import/README.md) to discover an exact upstream
SHA, review inventories/lock/notices, and produce a candidate. The generated tree
cannot approve its own inputs. Accept it through the trusted
[GitHub verification route](docs/github-route.md), then merge the accepted import
into `main` preserving ancestry. Controller policy changes and source candidates
are separate reviews. No automatic upstream advancement is installed.

`PINRAIL_IMPORT.json` describes the generated baseline; `main` intentionally adds
controller files and downstream changes on top. It is not a claim that the
patched downstream tree equals the generated import tree.

## Licensing and distribution boundary

Preserve the upstream Apache notices, bundled OFL font notices, supplemental
[Microsoft MIT notice](LICENSE-MICROSOFT-MIT), and file-level declarations.
The separately licensed dragon SVG example is omitted by reviewed policy;
`cbindgen` remains an external MPL-2.0 macOS build tool. See the bounded
[source/input review](docs/license-input-review.md).

Source-import acceptance is not complete third-party/SDK/generated-output license
clearance or permission to publish crates. No registry release or migration of
existing application consumers is part of this bootstrap.
