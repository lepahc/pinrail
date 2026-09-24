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
  or unwrapping a potentially cleared position.
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

## Deferred, not silently preserved

No retained layer transitions/remap receipts, capture, no-focus clipboard,
renderer retirement API, application residency compatibility flag, component
library/editor changes, application namespaces, or HUD defaults are added.
Use upstream's `QuitMode` and current popup/layer APIs; the old donor scheduler
and Blade lifecycle must not replace the current implementation.
