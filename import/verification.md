# Executed local verification

Importer code tested at `1643f4dcc0200d455228288b59231a979225c157`.
Documentation and test-driver changes do not change the importer-code digest.
These are private local candidates, not published branch refs or build releases.

## Standalone result

The generated extraction now **resolves, compiles, and passes Linux headless
library tests**, without acquiring editor-only root patches or changing the
selected dependency versions/sources/checksums. No runtime source patches were
made. Non-Linux compilation and real compositor/GPU execution remain unverified.

| Check | Actual outcome |
|---|---|
| Importer gate suite | 14 tests passed |
| Unrelated patch regression RED | Real offline Cargo metadata attempted to acquire `unrelated-editor` and exited 101 before the fix |
| Unrelated patch regression GREEN | Same generated dependency-free fixture passed full offline locked metadata after selection |
| Original full lock + relevant patches | Full locked metadata rejected the lock as needing an update |
| Static reachable lock graph slice | Still rejected by locked metadata; Cargo needed feature-edge pruning |
| Reviewed Cargo-pruned lock | 875 identities, no new/changed versions, sources, checksums or retained edges |
| Full `metadata --locked --all-features` | 875 packages, exactly equal to the reviewed lock; 27 workspace members; no target filter |
| Linux `check --locked --all-targets` | Passed for `gpui`, `gpui_platform`, `gpui_linux`, `gpui_wgpu`, with `gpui/test-support` |
| Linux `check --locked --workspace --all-targets` | Passed for the entire extracted workspace with `gpui/test-support` |
| Linux `test --locked --lib` | GPUI 359, Linux platform 42, wgpu support 38: **439 passed**, zero failures/ignored/filtered |
| Source/lock after check and tests | Tracked tree unchanged; reviewed lock bytes unchanged |
| Resource boundary | systemd user unit, MemoryMax 10G, MemoryHigh 8G, CPUQuota 200%, TasksMax 512; Cargo jobs/test threads 2 |
| Headless boundary | DISPLAY/WAYLAND_DISPLAY/WAYLAND_SOCKET unset; no GUI example or GPU-device test executed |

The build used Rust/Cargo **1.98.1**, a fresh worktree-private target directory,
disk-backed short TMPDIR, and dev/test debug information disabled. The bounded
unit completed successfully in 4min 41.823s; systemd reported 2.5G peak memory.
Warnings for upstream profile overrides naming omitted editor packages remain;
these harmless profile entries were not broadened into another transformation.

### Exact native commands

Executed in `/home/chapel/Projects/pinrail-check`, a real detached worktree from the
new generated bare destination, not a source-directory copy:

```sh
cargo +1.98.1 metadata --locked --all-features --format-version 1
cargo +1.98.1 check --locked -p gpui -p gpui_platform -p gpui_linux -p gpui_wgpu \
  --all-targets --features gpui/test-support
cargo +1.98.1 check --locked --workspace --all-targets --features gpui/test-support
cargo +1.98.1 test --locked -p gpui -p gpui_linux -p gpui_wgpu \
  --lib --features gpui/test-support -- --test-threads=2
```

The repeatable driver and complete resource-wrapper invocation are documented in
[README.md](README.md#cpu-only-standalone-qualification).

## Dependency and inventory review

- Original full locks: 1,827 packages at prior pin
  `e71963a599c64c213aca1c607e7418503a1e787d`, 1,828 at current pin
  `2c4bc2d7b2c5b7832ad964f39840d823d961cb0e`.
- Original selected all-platform lock graph: 894 identities at both pins.
- Cargo-pruned standalone lock: 875 identities at both pins. Both committed lock
  files have SHA-256 `28b6928013a634785f7725ef0e0e65c4fa15afb0ef044a1a8dc3e22201372bfb`.
- Retained root patches: `async-process`, `async-task`, `windows-capture`, `calloop`,
  `scratch`. Removed only unreachable patches: `tree-sitter-language`, `livekit`,
  `libwebrtc`, `notify`, `notify-types`, `webrtc-sys`.
- Original file/mode/path/license inventory is unchanged by this repair; the
  baseline additions are the explicit all-platform Cargo cohort/patch selection
  and the reviewed standalone-lock digest. All 27 local packages remain.
- OFL fonts/notices and the macOS MPL-2.0 `cbindgen` 0.28.0 build dependency remain.
  Only the previously approved dragon asset/SVG example omission applies.
- New/changed versions, sources, checksums, dependency edges, unknown patch forms,
  ambiguous lock references and missing local packages are rejected. Baseline and
  lock inputs come from the specified committed controller, not the candidate or
  a dirty working file. A committed replacement lock without its reviewed digest
  is also rejected.

This is technical private-evaluation evidence, **not complete external/file-level
license clearance or permission to publish**.

## Regenerated Copybara proofs

Changing importer transformations intentionally makes old accepted trees invalid.
The old `213bbf97a7fc1cc24f15f46baf8671366854d573` candidate was rejected before
Copybara; the new proofs restarted from the shared seed, without weakening that
gate or changing a real remote.

| Check | Actual outcome |
|---|---|
| Real first import / clean-root verify | Same prior tree, different commit IDs |
| Merge-commit acceptance and repeat | No-op; candidate equals accepted merge |
| Real later upstream update / clean-root verify | Same current tree across clean roots |
| Representative downstream source patch | Survived real import merge in an actual Git worktree |
| Later accepted merge repeat | No-op again |
| Candidate bytes/mode/symlink/deletion/added-checker changes | All five real forged commits rejected |
| Full verify against candidate-added policy | Trusted recomputation rejected extra candidate policy |

### Exact build-proven artifacts

- Shared seed: `875ec5e0a0a13b44076e43bb8a46629a8d447091`
- Prior candidate: `d905dbfcb0477b175091f63409638dff2666fef7`
- Prior tree: `684c444b1e7645ae341dc1fcaefe921a28dfdd0a`
- Prior accepted merge: `246dd7e665eb2524b8bae3b2b192129e2437654d`
- **Current candidate built/tested:** `f1253a7f760652272d4e28229295b11f9b8b4283`
- **Current tree:** `418123879b005491755245f2991ab259c970a79d`
- Clean current recomputation: `32a3c5417ba46311fa761b9bec788bf8316e043f`
- Current accepted merge: `aaed65cb76d7efe1e52de9a5525080d661c1c44e`
- Downstream patch: `dfac5a95414680b7fe8e8c430cb4f3a9bfe14def`
- Downstream merge retaining it: `c7e6c6a214b07de738de7ca18097ab2bdc5c110f`

The current candidate preserves both provenance labels:

```text
GitOrigin-RevId: 2c4bc2d7b2c5b7832ad964f39840d823d961cb0e
Copybara-Path-RevId: d528c665e1a5c4627a68813435756592d9fad69d
```

Raw selected-tree equivalence, including original manifests/lock before their
transformation, was verified at those two revisions.

## Retained evidence

Paths relative to this controller worktree unless noted:

- `.scratch/proof-resolution/proofs.json`: regenerated real migration, no-op,
  merge-resumption, source-patch survival, and malicious candidate receipts.
- `.scratch/proof-final/proofs.json`: successful second entire proof with the
  later no-op included in the driver; both trees equal the first run. Its later
  candidate `e11f74410258f3c92a687f9efdfc0bb3b4939a19` has the same source tree as
  the exact built/tested candidate above.
- `.scratch/proof-resolution/update-after-merge/migration/destination.git`:
  generated bare repository containing the exact built candidate.
- `.scratch/proof-resolution/<step>/migration/copybara.log`: actual migration logs.
- `.scratch/repeat-current.json`: exact later-merge no-op result.
- `.scratch/old-base-rejection.json`: intentional rejection of the pre-repair tree.
- `.scratch/red-patch-acquisition.log`, `.scratch/green-patch-acquisition.log`:
  observed real Cargo regression evidence.
- `.scratch/full-lock-metadata.stderr`, `.scratch/graph-lock-metadata.stderr`:
  actual failed locked-resolution probes, not hidden or called successful.
- `.scratch/standalone/results.json`, `.scratch/standalone.log`: exact native
  commands, exit codes, counts, sanitized display environment and resource result.
- `.scratch/standalone/{metadata,check,test}.{stdout,stderr}`: complete native logs.
- `.scratch/standalone/workspace-check.{stdout,stderr}`: additional full-workspace
  Linux all-target check under the same resource/display/target-directory boundary.
- `.scratch/unit-gates.log`: all 14 gate tests passed.
- `/home/chapel/Projects/pinrail-check`: clean tracked build worktree; private target
  is `.scratch/target`, temporary files are `.scratch/tmp`.

No GitHub writes, credentials, consumer modifications, runtime patch adoption,
GUI/GPU execution, crate publication or complete license clearance are included.
