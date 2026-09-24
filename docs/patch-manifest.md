# Downstream patch inventory

**Adopted bootstrap scope: G1, G2, G3 and applicable L1 safeguards.**
These groups are selected for semantic porting onto current upstream APIs; their
implementation and verification status is recorded separately. Retained-layer,
capture, no-focus clipboard and component features are explicitly deferred.

The donor is the locally modified published GPUI 0.2.2 and gpui-component 0.5.1
cohort at See Hear Think revision `82dbebecf43e1830f44f062011ea6017b0a33dfc`.
BFG revision `23b05aa6d5920cd75c63f0d45ebe93bdf172c457` contains byte-identical
vendored copies, not an independent patch list. Archive checksums used to
establish changes:

- GPUI 0.2.2: `979b45cfa6ec723b6f42330915a1b3769b930d02b2d505f9697f8ca602bee707`.
- gpui-component 0.5.1: `d021d46b4088d3d93a57ccdf443da85695a77272108caca2f6fe5369f584966a`.

Comparison upstream:
[Zed `2c4bc2d7b2c5b7832ad964f39840d823d961cb0e`](https://github.com/zed-industries/zed/tree/2c4bc2d7b2c5b7832ad964f39840d823d961cb0e).
This inventory is source evidence, not executed regression or native acceptance.

## Already upstream or superseded

Do not copy these implementations over current upstream:

- **U1:** throttled configure acknowledgement, demand-driven Wayland scheduling,
  async refresh and next-frame wake behavior. Current presentation-failure states
  must be retained; G1 is a distinct remaining failure path.
- **U2:** local zero-window residency flag. Current `QuitMode::Explicit` provides
  the application lifetime choice without another backend flag.
- **U3:** improved selection serial routing. Preserve current typed arrival-order
  serial handling and press-only serials used by popup grabs. This does not grant
  serial-free clipboard authority.
- **U4:** basic layer-shell creation and input regions. Current
  `WindowKind::LayerShell` is partial overlap, not retained hide/remap equivalence.

## Adopted initial correctness series — implementation under verification

- **G1 — retry-registration failure recovery.** Recover one coalesced wake if
  calloop rejects retry-timer admission. Preserve current failed-presentation
  handling. Donor regression intent: `tests/gpui_wayland_contract.rs`.
- **G2 — XDG resize semantics and presentation ordering.** Treat requested bounds
  as content-sized, account for client insets, and coordinate geometry with the
  draw/resize path. Preserve popup configure semantics. Donor app regression:
  `src/ui/workspace_tests.rs`; WGPU-specific ordering must be verified anew.
- **G3 — pointer/IME and callback reentry safety.** Reset composition only in the
  pointer-targeted keyboard editor. Recheck original target and current pointer
  position after callbacks before click-state effects. Donor coverage:
  `tests/point_capture_platform.rs`, `tests/attended_layer_input.rs`.
- **L1 — existing layer-shell safeguards.** Validate protocol versions and
  unsupported backends; resolve zero configure axes independently; prevent
  inappropriate activation; retain unconditional compositor-close behavior and
  cleanup. Generalize onto current upstream APIs instead of imposing donor HUD
  defaults. Coverage intent: `gpui_wayland_contract`, `recorder_layer_protocol`.

## Deferred optional platform capabilities — not part of bootstrap

- **L2 + L3 + R1 — retained interactive layers.** Dynamic options, suspend/remap,
  generation-fenced configure/resize cancellation, stacking replay and exact
  installed-input authority must move as one correctness unit. Blade's surface
  retirement cannot be copied into WGPU: `unconfigure_surface()` retaining a
  surface does not prove retirement of asynchronous WSI activity. Existing
  socket/lifecycle tests require adaptation plus independent renderer evidence.
- **P1 — owning-connection one-shot output acquisition.** WLR screencopy,
  output-generation tracking, cancellation/timeouts, bounded SHM and off-main
  pixel reading. Not equivalent to upstream's `scap` feature. The donor's
  layer-shell admission dependency is an explicit design choice to revisit.
- **P2 — no-focus clipboard transport.** Serial-free text/file/multi-MIME offers,
  independent endpoint policy, bounded FD transfers, unique-copy receipts and
  readback. Unsupported/inherited endpoints fail closed. Donor coverage lives in
  `tests/clipboard_protocol.rs`, not in the vendored package.
- **D1 — diagnostics and test controls.** Port only controls needed by adopted
  behavior, retaining default-off/nonblocking diagnostics. Public diagnostic APIs
  and environment names are not automatically adopted.

## Deferred component library — separate source and cohort

No component package is part of the generated Zed import. Before adopting it,
select its own baseline and resolve a single coherent GPUI dependency cohort.
Current Zed still calls core GPUI `0.2.2`, but that does not establish compatibility
with the old published proc-macro/platform/component packages.

- **C1:** identity-bearing atomic inline tokens, movement and Undo/Redo.
- **C2:** decorated-span layout/hit mapping; isolate ordinary-input corrections.
- **C3:** first-scene wrapping and native content-height measurement.
- **C4:** selectable read-only inputs retaining state and history.
- **C5:** button hover foreground correctness.
- **C6:** transparent/rounded root styling.
- **C7:** scoped input colors.
- **C8:** optional content-free action observations and test controls.

Recorder/Review/History routes, placement choices, image-reference label policy,
thumbnail/file lifetimes and application persistence remain outside the engine.

## Regression custody and evidence limits

Important donor tests live outside `third_party`, including protocol/socket
fixtures and application-level input/layout tests. Merely importing a package
would lose them. Rehome meaningful regression intent against the actual ported
implementation, not a duplicate reducer or assertions tied only to old paths.

Pure state tests, serialized Wayland traffic and TestPlatform tests are not
compositor/pixel/focus/IME acceptance. `wl_display.sync` proves request ordering,
not presentation. Historical native results do not qualify this new WGPU port.
No consumer dependency migration is authorized by this manifest.
