# Executed local verification

## Correction: headless is not CPU-only

The historical standalone **439-test** invocation below was real and passed, but
its CPU-only/no-GPU characterization was incorrect. Three `wgpu_atlas` tests call
`request_adapter` and `request_device` even without display variables. That run
must not be described as CPU-only or as proof that no GPU-device work occurred.
The current standalone driver and trusted CI command list explicitly exclude
those three full test names. Future upstream test additions require review under
the existing exact-source inventory gate. This correction does not replace the
historical logs or claim native compositor/presentation qualification.

## Integrated reviewed-source route

Controller code and reviewed baselines tested at
`2f0b773c1654ff07eba0f1cf4394d643a609a238`, after ancestry-preserving merges of
`02d18b5acb51b6fc9392b5d5ce7127aa4ced4ee5` and
`9ee802cdef592d542b80afd4035f137f5f4ba0e1` with the pinned Microsoft notice.
Controller-code/notice SHA-256:
`a9715e9f3c6027aa0638b94a02eda96e192f50084618ff02a86541ea763fa52f`.
Documentation-only additions do not change that digest or the generated tree.

The initial source candidate is **`f0ed7dfd77382c0865f3be016d61d97a0ea1de43`**,
with exactly one parent, shared seed
`875ec5e0a0a13b44076e43bb8a46629a8d447091`.
Its independently recomputed Git tree is
**`9172499986e73a2d31f1a34d186b59cfb3cb551a`**. The clean-root verification wrote
`17947926b16aaf0962023d8c2d663bd64a1dfef6` with the same exact tree; it is a
verification artifact, not a replacement for the named candidate.

Executed against the integrated controller:

- **30 Python regression tests passed**, covering committed scope authorization,
  notice integrity, Cargo projection, checkpoint recovery, and existing drift
  gates. `--source-import` requires `reviewed-source-import`; a private-only or
  unknown scope cannot authorize it. Private evaluation is still supported.
- Real pinned Copybara prior import, independent prior verification, merge
  acceptance, no-op, current update, independent update verification, and another
  merged no-op all passed. A representative downstream source patch survived the
  actual update merge. All five forged candidate mutations were rejected,
  including full CLI recomputation against a candidate-added checker.
- Real selected update -> excluded-only checkpoint -> verification -> merged
  same-pin retry passed with the integrated lock and notices. Recovery changed
  only `PINRAIL_IMPORT.json` and `README.md`, used exactly one gated `--force`,
  and the retry used no force or new candidate ref. The additional native-pin
  review and lock exist only in the disposable fixture controller, not production.
- Direct current import from the shared seed and independent clean-root verify
  passed in reviewed-source scope. The resulting tree also equals the tree from
  the prior/current merge proof and the checkpoint proof.
- The previously build-tested `f1253a7f760652272d4e28229295b11f9b8b4283` was
  deliberately rejected as an accepted base before Copybara ran. Old trees and
  controller digests were not grandfathered in or reconstructed with old digests.
- Real private-mode current import and same-pin no-op passed using the same
  source-reviewed baselines, while emitting private-only scope.
- Full `cargo +1.98.1 metadata --locked --all-features --format-version 1`
  passed, including a repeat from inside the actual generated Git worktree:
  exactly 875 packages matching the complete committed lock, 27 workspace members,
  and no escaped path dependencies or changed tracked files/lock.

Independent Git comparison with the previously build-tested standalone candidate
changed exactly `.gitattributes`, `LICENSE-MICROSOFT-MIT`, `PINRAIL_IMPORT.json`,
and `README.md`. **Every runtime source file, Cargo/build input and asset remains
byte/mode-identical.** The exact original inventories and reviewed lock bytes at
both production pins were also compared with `02d18b5` and are unchanged. There
are 414 generated files, 28 preserved/resolved symlinks, eight retained OFL font
files, and the retained macOS `cbindgen` 0.28.0 dependency. Microsoft permission
text was independently read back and matches its pinned SHA-256 exactly.

No duplicate Rust compilation/test run was performed in this lane. The historical
Linux workspace check and 439 headless test passes below are carried-forward
coverage for identical source/build inputs, not new execution claims. Non-Linux
compilation, real compositor/GPU behavior, complete third-party/license clearance,
crate releases and consumer changes remain outside this result.

All new evidence is under `/home/chapel/Projects/pinrail-land`:

- `.scratch/controller-unit-final.log`: complete 30-test regression result.
- `.scratch/landing-proof/results.json`: integrated command exits, exact candidate,
  inventory/lock preservation and independent source/notice/count comparisons.
- `.scratch/landing-proof/local/proofs.json` and
  `.scratch/landing-proof/checkpoint/proofs.json`: complete real migration chains.
- `.scratch/landing-proof/source-initial/migration/destination.git`: **candidate
  repository**, `refs/heads/candidate` names the exact initial candidate above.
- `.scratch/landing-proof/source-verify.stdout`: independent exact-candidate verify.
- `.scratch/landing-proof/source-worktree`: clean detached generated source tree.
- `.scratch/landing-proof/metadata-in-worktree.{stdout,stderr}`: full final metadata.
- `.scratch/landing-proof.log` and `.scratch/prove_landing.py`: orchestration log
  and exact local proof driver. The bounded systemd unit exited successfully with
  MemoryMax 10G, MemoryHigh 8G, CPUQuota 200%, TasksMax 512, two Cargo jobs, disk
  scratch and display variables unset; peak reported memory was 825.4M.

This lane performed no remote GitHub writes and added no workflow/runtime patches.
Public source landing is separately authorized, but the importer itself only
writes its local disposable candidate repository.

## Historical lane evidence

The following are historical proofs of the separate checkpoint and standalone
lanes, before their controller integration. Their artifact identities and counts
are not claims about the newly integrated controller. These are local candidates,
not published branch refs or build releases.

## Checkpoint-only regression

The focused regression used the real checksum-verified Copybara v20260921 JAR,
not a fabricated migration response. Historical checkpoint controller-code digest:
`c388a4898c0536290b54069f032ca9bbb65370550c0f54848eed031c75849afb`.
All three controller files were byte-compared with the tested fixture afterward.

**Observed RED:** `tests/import/prove_checkpoint.py` against the pre-fix source
successfully imported and merge-accepted a selected-input update to
`d528c665e1a5c4627a68813435756592d9fad69d`. Advancing to
`2c4bc2d7b2c5b7832ad964f39840d823d961cb0e` then failed with an exact-tree mismatch
for `PINRAIL_IMPORT.json` and `README.md`. Copybara reported no origin-file changes
and skipped the transforms. The failed command exited 1; logs are retained at
`.scratch/checkpoint-red2.log` and `.scratch/checkpoint-red2/checkpoint/migration/`.
An earlier harness-only cache-copy permission failure is not counted as RED.

**Observed GREEN:** the same regression passed with bounded checkpoint recovery:

- Real initial import, selected-input update, and merge acceptance.
- Ordinary empty-range invocation followed by exactly one gated `--force` run.
- Only `PINRAIL_IMPORT.json` and `README.md` changed. Both provenance markers were
  written through Copybara at the requested checkpoint; raw source, full output
  tree, and direct candidate ancestry passed their normal checks.
- Clean `verify` recomputation produced the same Git tree and native provenance.
- Merge acceptance followed by an ordinary same-pin no-op: no force, new commit,
  or candidate ref.
- **20 unit tests passed** (the original 11 retained). New recovery tests cover
  exit/diagnostic errors, transform and selection-policy drift, unreviewed inputs,
  tampered accepted bases, unrelated checkpoint/native history, bounded recovery
  failure, and final candidate parent/provenance/tree rejection. Java faults are
  injected at the process boundary in these unit tests; Git and committed approval
  checks execute. A separate native-ancestry RED caught a force attempt for an
  unrelated native marker before the second ancestry check was added.
- Additional real-JAR fault probes rejected invalid generated Starlark (exit 2)
  and a checkpoint-only `Cargo.toml` transform drift after a real empty-origin
  exit. Neither wrote a forced command, candidate ref, or success receipt. These
  probes inject only config/transform output, not a fake Copybara process result.

Exact final local artifacts:

| Artifact | SHA |
|---|---|
| Disposable reviewed fixture controller | `75b2e01d640c025925866deae4bbaf5f1bc290d4` |
| Selected-update accepted merge | `83fcdc9b3d9ec0f8c080bbff92f258a213471bcc` |
| Checkpoint candidate | `9e395008d0487092a72ef892116aa28c47a500d4` |
| Clean recomputed candidate | `16fa523ad6f1c27f5390fae624945eedf3dc671a` |
| Shared checkpoint Git tree | `f6209d195937a4b9d77a0e0222908c6d7edb67b8` |
| Accepted checkpoint / same-pin no-op | `0d67908d6180e72c0a3d989787db80089b7edb85` |

Evidence is in the checkpoint-fix worktree's ignored
`.scratch/checkpoint-green-final/proofs.json`, per-step migration logs/commands,
`.scratch/checkpoint-unit-final2.log`, and
`.scratch/checkpoint-native-ancestry-red.log`. Real negative probes and results:
`.scratch/probe-checkpoint-negatives.py` and
`.scratch/checkpoint-green-final/negative-proofs.json`.
The native-pin review was created only in the disposable fixture controller after
checking equality with the committed checkpoint inventory; no production baseline
was added. This repair did not rerun the older downstream-merge/Cargo proofs below,
perform a Rust build, or change the deliberate controller-upgrade drift boundary.

## Standalone result

Importer code tested at `1643f4dcc0200d455228288b59231a979225c157`.
The generated extraction **resolves, compiles, and passes Linux headless library
tests**, without acquiring editor-only root patches or changing the selected
dependency versions/sources/checksums. No runtime source patches were made.
Non-Linux compilation and real compositor/GPU execution remain unverified.

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
| Historical headless boundary | Display variables unset; no GUI example launched, but three GPU-device tests ran; see correction above |

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

Historical paths relative to `/home/chapel/Projects/pinrail-resolve` unless noted:

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
live GUI launch, crate publication or complete license clearance are included.
Historical GPU-device execution is explicitly identified in the correction above.
