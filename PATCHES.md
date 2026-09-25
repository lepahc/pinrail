# Downstream GPUI patches

These patches sit **above** the generated upstream import; do not put them in the
import transform. The baseline is Zed
`2c4bc2d7b2c5b7832ad964f39840d823d961cb0e`. The semantic donor is the GPUI
vendoring in See Hear Think at `82dbebecf43e1830f44f062011ea6017b0a33dfc`;
its older monolithic GPUI/Blade implementation is not copied over this cohort's
split platform crates and WGPU renderer.

## Accepted basic correctness subset

- **G1 — retry registration:** both retry paths inspect calloop registration's
  result. Failure transfers ownership to one coalesced frame Ping instead of
  leaving `RetryScheduled` without a timer. Upstream's before/after-first-present
  distinction, failed-presentation state, and compositor-paced retry remain.
- **G2 — XDG resizing:** `Window::resize` is content-sized. Expand the drawable
  by untiled client decoration insets, resize WGPU, and request redraw. Send
  logical, surface-local XDG geometry at the draw boundary, not before the
  asynchronous resize. An unsuccessful draw restores the last presented geometry
  before this adapter can issue a state-only retry commit. Popup repositioning
  and configure-driven popup geometry remain separate.
- **G3 — pointer/IME safety:** reset composition only when the original pointer
  target is the keyboard editor. After reentrant IME callbacks, validate the
  original identity, current input admission, and current pointer position
  before click accounting. Deliver to that original window, without retargeting
  or unwrapping a potentially cleared position. Recognized button releases clear
  seat-wide pressed state even when the pointer target is missing or blocked;
  window delivery admission cannot bypass that cleanup.
- **L1 — existing layer-shell safeguards:** reject OnDemand before protocol v4;
  guard the v5-only exclusive-edge request; resolve zero configure axes
  independently using the requested size, and acknowledge before resize callbacks.
  Layers do not send XDG activation requests. X11 and headless creation fail
  closed for layer-shell, including dependency-feature unification. The public
  layer variant is already unavailable on macOS, Windows, and Web, so their
  source and the shared public API are unchanged.
- **L1 — lifetime/resources:** compositor close remains unconditional, not an
  application-vetoable XDG close. Closing revokes draw/input and filters stale
  dispatch while native destruction is pending. Callback reentry cannot revive
  a closed scheduler or restore a closed input handler. Preconfigure draw is
  deferred **with** a latched redraw so the first configure can present an
  otherwise unchanged scene. Fractional-scale and viewport proxies are owned
  and destroyed, including renderer-construction failure cleanup; renderer
  teardown precedes destruction of native surface resources.

Keep upstream's layer/anchor/namespace/keyboard defaults and broad options.
Layer resize remains an ordinary size request and local redraw; this is not a
retained remap or a promise of pixel-atomic layer resizing. Existing startup
activation was already toplevel-guarded. Invalid exclusive edges retain
upstream's log-and-ignore policy; old protocol versions now also log and ignore
the unsupported exclusive-edge request rather than sending it.

## Regression custody and verification boundary

Production-used policy/effect helpers live beside the Wayland adapter in
`frame_loop.rs`, `geometry.rs`, `pointer.rs`, and `layer_policy.rs`. Their tests
are unit tests of those exact modules. A dependency-free harness can also run
them without compiling the entire native dependency graph:

```sh
mkdir -p .scratch
rustc +1.98.1 --edition=2024 --test \
  crates/gpui_linux/tests/offscreen_wayland.rs -o .scratch/offscreen-wayland-tests
.scratch/offscreen-wayland-tests
```

The initial patch checkpoint ran **18 tests successfully**. Failing-first runs
observed stranded retry ownership, wrong content/inset sizes, cross-window IME
admission and invalid click continuations, coupled zero axes, missing version
gating, geometry left pending after a failed draw, and a lost first-configure
redraw. These are helper/effect-boundary reproductions, not native UI failures.

The harness injects registration outcomes, pointer state and renderer results.
It does **not** make calloop fail an actual registration, run a compositor,
submit GPU work, or prove native IME/focus, scanout, constructor cleanup on a
real connection, or any historical Blade resize symptom. In particular, the
WGPU draw API encapsulates texture acquisition/reconfiguration/presentation;
our ordered effect trace is not proof about its internal WSI traffic.

Full backend compilation and native qualification were not run at this source
checkpoint: the generated workspace dependency projection needed independent
repair before native builds. After integrating that corrected import, run the
following with a private target directory, the build resource budget, and no
live display credentials:

```sh
env -u DISPLAY -u WAYLAND_DISPLAY -u WAYLAND_SOCKET \
  CARGO_TARGET_DIR="$PWD/.scratch/target" \
  cargo +1.98.1 check --locked -p gpui_linux --all-targets
env -u DISPLAY -u WAYLAND_DISPLAY -u WAYLAND_SOCKET \
  CARGO_TARGET_DIR="$PWD/.scratch/target" \
  cargo +1.98.1 test --locked -p gpui_linux --no-default-features --features wayland --lib
```

Formatting, `git diff --check`, and offline `cargo metadata --no-deps` were also
checked. Metadata parsing does not establish dependency resolution or a native
compile. Non-Linux platform execution and isolated-compositor/GPU qualification
remain separate checks, not implied by the source-compatible API.

## Independent standalone-cohort review

Review target: `e8828a381dad39faed387aaad040613971af4090`, cherry-picked onto
standalone import `f1253a7f760652272d4e28229295b11f9b8b4283`.
**Original review requested changes; the G3 blocker is repaired and independently
approved in the closure section below.**

- **G3 regression:** `client.rs:2321-2323` rejects both presses and releases when
  the target is blocked. A press followed by a blocking Dialog child and then a
  release without pointer leave/enter bypasses `button_pressed = None` at
  `client.rs:2387`. After the child closes, Motion can report a button still down.
  Keep seat-wide release cleanup independent of per-window delivery admission;
  preserve all press/IME target revalidation. No material repair was applied by
  the reviewer.
- An exact-source Button-arm probe reproduces this regression with stand-in
  client/window/protocol types: the release case passes on the unpatched import
  and fails on this patch. Its ordinary release control passes on both; the IME
  retarget control fails on the baseline and passes on this patch. This is
  source-bound control-flow evidence, not native dispatch or compositor proof.
- `cargo +1.98.1 check --locked --workspace --all-targets --features
  gpui/test-support` passes. The CPU-only library gate passes **452 tests**:
  gpui 359, gpui_linux 58, gpui_wgpu 35. Three GPU-device atlas tests are explicitly
  filtered, since display-variable removal does not prevent adapter creation.
  The Cargo-built `offscreen_wayland` harness passes **18 tests**, overlapping the
  helper cases in the library run rather than adding 18 independent contracts.
- Gates used a private target and `.scratch/tmp`, no display credentials, two
  Cargo jobs/test threads, debug info disabled, and a user systemd unit capped at
  MemoryMax=10G, MemoryHigh=8G, CPUQuota=200%, TasksMax=512. Cargo.lock remains
  byte-identical to the import with **875 package identities**; no manifests or
  dependency sources were changed.
- Local evidence is in `.scratch/qualification/`: `summary.json` contains exact
  commands, commit, environment and lock digest; the corresponding gate logs,
  `pointer-probe-summary.json`, source-bound probe generator and both probe logs
  retain the results. An initial unfiltered test invocation was stopped during
  dependency compilation, before any test executable ran, then rerun with the
  three GPU cases excluded.

G1 timer admission and Ping routing, G2 content/inset sizing and the real WGPU
resize/acquire/reconfigure/present paths, and L1 configure/close/resource guards
were source-traced. The existing helper tests do not establish actual calloop
admission failure, WSI-internal geometry atomicity, native focus/IME or compositor
acceptance. No GUI/compositor/GPU-device work or other-platform execution was
performed in that review. Its blocker was subsequently repaired and the
dispatcher-level regression was independently rerun before approval.

### G3 release repair — independently approved

The repair scopes the original-target lookup and blocked-window guard to the
Pressed arm. The Released arm again clears seat state before any optional window
delivery. Blocked windows still reject MouseUp in `handle_input`; missing targets
receive nothing. Press-only serial tracking, pointer-targeted IME reset, and
post-callback target/admission/position revalidation are unchanged. No dependency,
manifest, public API, renderer, or unrelated runtime change is included.

`crates/gpui_linux/tests/pointer_dispatch.rs` is a retained Cargo integration
harness. It compiles the current production dispatcher prelude and **complete
Motion/Button arms**, button mapping, pointer helpers and serial tracker directly
from source; it does not carry a copied dispatcher or a substitute state reducer.
Its fixture supplies client/window/protocol/event types, blocked-window admission,
IME callback hooks, and simplified timing/distance/cursor dependencies. The probes
exercise actual extracted guard ordering and effects, but do **not** establish
native dispatcher type integration, protocol decoding, a real blocking Dialog,
compositor/focus/IME behavior, GPU output, or multi-click geometry. The separate
workspace check type-checks the actual backend. Source-anchor/type changes fail
compilation or extraction instead of silently using a stale implementation.

Observed RED on `e8828a381dad39faed387aaad040613971af4090` (before the production
edit): **8 passed, 2 failed** inside the probe; Cargo harness exit **101**. Both
blocked-target and missing-target releases left `Some(Left)` instead of `None`.
Observed GREEN with the same test: **10 passed, 0 failed**, Cargo harness **1
passed**, exit **0**. The wrapper is not an additional independent contract.
Release cases include subsequent Motion and an ordinary press/release control.
Safety cases cover blocked presses, press-only serial/selection authority,
non-target keyboard editors, and both IME callback branches retargeting, blocking,
losing target/position, or updating the current position. The probe filters out
its 10 included helper/serial unit tests to avoid recounting them.

Exact focused RED/GREEN command (both runs used this environment and resource
wrapper; RED preceded the source edit):

```sh
systemd-run --user --wait --pipe --collect \
  -p MemoryMax=10G -p MemoryHigh=8G -p CPUQuota=200% -p TasksMax=512 \
  --working-directory="$PWD" \
  env -u DISPLAY -u WAYLAND_DISPLAY -u WAYLAND_SOCKET \
  TMPDIR="$PWD/.scratch/tmp" CARGO_TARGET_DIR="$PWD/.scratch/target" \
  CARGO_BUILD_JOBS=2 RUST_TEST_THREADS=2 \
  CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 \
  cargo +1.98.1 test --locked -p gpui_linux --test pointer_dispatch \
  -- --test-threads=2 --nocapture
```

The repaired source also passes the workspace all-target check with
`gpui/test-support`, the **452-test** CPU-only library gate (359 gpui, 58 Linux,
35 WGPU), the **18-test** overlapping `offscreen_wayland` helper harness, and
scoped rustfmt checks. The library gate explicitly retains all three skips:
`wgpu_atlas::tests::before_frame_skips_uploads_for_removed_texture`,
`wgpu_atlas::tests::remove_deallocates_tile_space_for_reuse`, and
`wgpu_atlas::tests::reused_texture_id_has_new_generation`. Display-variable
exclusion alone is not a GPU barrier. All gates used the wrapper above with two
jobs/threads; no live display, compositor or GPU-device test was run.

Local evidence is retained separately from the original review evidence in
`.scratch/qualification/release-repair-{red,green}.log`,
`release-repair-summary.json`, `release-repair-gates.py` and corresponding named
gate logs. The summary records exact gate arguments, tested source digests,
environment and unchanged lock digest. Cargo.lock remains byte-identical to the
standalone import with **875 package identities**. Original reviewer notes and
probe evidence are preserved. A separate closure review approved the repair at
`5367a01fcb55226f68374204924774782eb9e336`: it reran the ten dispatcher cases,
the eighteen overlapping helper cases, scoped formatting and diff checks, and
independently reconstructed the exact pre-fix source probe to reproduce both
release-state failures. Blocked delivery remains rejected by the production
window handler; seat cleanup no longer depends on delivery admission. These are
source-bound control-flow and compile results, not native compositor acceptance.

## Deferred, not silently preserved

No retained layer transitions/remap receipts, capture, no-focus clipboard,
renderer retirement API, application residency compatibility flag, component
library/editor changes, application namespaces, or HUD defaults are added.
Use upstream's `QuitMode` and current popup/layer APIs; the old donor scheduler
and Blade lifecycle must not replace the current implementation.
