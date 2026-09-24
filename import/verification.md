# Executed local verification

The original full proof used controller
`51ab65187b4fbead02e2f3c6ee7492adb6318c54`; those historical results follow the
focused checkpoint regression below. Documentation-only commits do not change
the controller-code digest. These are private local candidates, not published
branch refs or build releases.

## Checkpoint-only regression

The focused regression used the real checksum-verified Copybara v20260921 JAR,
not a fabricated migration response. Current controller-code digest:
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

## Original full-proof results

| Check | Actual outcome |
|---|---|
| Unit gate suite | 11 tests passed |
| Real first Copybara import | Prior upstream `e71963a599c64c213aca1c607e7418503a1e787d`; 27 packages, 412 final files |
| Second clean-root recomputation | Same prior Git tree, different commit metadata/commit ID |
| Candidate accepted through merge commit | Both ancestry and provenance preserved |
| Repeat after acceptance | No-op, candidate equals accepted base; no extra commit |
| Real later upstream import | `2c4bc2d7b2c5b7832ad964f39840d823d961cb0e`; different source tree |
| Update recomputed from another clean root | Same later Git tree |
| Representative downstream source patch | Survived actual import merge in a real Git worktree |
| Candidate byte / executable-mode / symlink / deletion / added-checker changes | All five real forged commits rejected |
| Full verify command against candidate-added policy | Recomputed with trusted controller and rejected extra candidate policy file |
| Repeat after later merge acceptance | No-op again |
| Tampered accepted base | Rejected before Copybara started |
| Cargo metadata, `--no-deps --locked` | Passed for both snapshots; 27 members, 42 remaining example targets, no `svg` target |
| Full offline Cargo metadata | Blocked by uncached root `libwebrtc` Git patch; no unlocked retry or dependency update |
| Native compilation/platform tests | Not run by this controller verification |

The source update changed original `Cargo.toml`, `Cargo.lock`,
`crates/gpui/src/window.rs`, and `crates/gpui_macos/src/window.rs`; the resolved
in-tree dependency-edge inventory stayed equal. Both new root input blobs were
explicitly reviewed in the private baseline, not accepted as an automatic update.

## Exact artifacts

- Shared seed: `875ec5e0a0a13b44076e43bb8a46629a8d447091`
- First candidate: `0fcbe42b7e2f013dcb0e83fbbbad5508cecf0335`
- Prior tree: `625041a99901a8d9846e9f59477d405c55c23614`
- Second clean prior candidate: `832f9cb613de3ad75c3a37493b7b5ec67458d255`
- Prior accepted merge: `51c077dd5f8847afb8dadd0550b64513dba8113c`
- Later candidate: `213bbf97a7fc1cc24f15f46baf8671366854d573`
- Later tree: `d261dde9dea04ca16ae4ace1ff5c8a5e251e95fd`
- Clean recomputed later candidate: `6150f2b8991772dcee1339b1e4678c81d5c6ed49`
- Later accepted merge: `35adc3d95b680abb217785dff5b15cd84e85dd59`
- Representative downstream patch: `fa0ed4eade9c9398dda0533f3fa0caea46ec4a7e`
- Downstream merge retaining it: `6735cd02f1953fe253f09559356481e6ced771f6`

The later candidate message contains:

```text
GitOrigin-RevId: 2c4bc2d7b2c5b7832ad964f39840d823d961cb0e
Copybara-Path-RevId: d528c665e1a5c4627a68813435756592d9fad69d
```

The requested revision changes an unrelated editor UI file after the last selected
path-affecting commit. Exact raw selected-tree equivalence was checked. The second
label is Copybara's native history/resumption marker; the first is the requested
snapshot checkpoint. See the provenance section in [README.md](README.md).

## Evidence locations

All paths below are relative to the controller worktree and ignored by Git:

- `.scratch/proof-run3/proofs.json`: complete successful end-to-end receipts.
- `.scratch/proof-run3/<step>/migration/copybara.log`: actual Copybara run logs.
- `.scratch/proof-run3/<step>/migration/command.json`: exact Java invocations.
- `.scratch/proof-run3/<step>/migration/input-audit.json`: 29 literal include
  edges, three reviewed generated includes, five native build scripts/resources.
- `.scratch/proof-run3/update-after-merge/migration/destination.git`: later
  candidate repository; `refs/heads/candidate` names the exact checked commit.
- `.scratch/proof-run3/accepted.git`: local acceptance history only.
- `.scratch/proof-run3/downstream`: actual downstream proof worktree.
- `.scratch/proof-run3/<step>/discovery/<upstream>/`: bounded metadata Git
  repository, exact tree records and raw manifest/lock/symlink inputs.
- `.scratch/proof-run3/<step>/migration/copybara/`: Copybara origin caches and
  sparse migration/destination checkouts, not a manually copied source tree.
- `.scratch/proofs/e2e-run3.log`: successful end-to-end driver output.
- `.scratch/proofs/repeat-current.json`: later acceptance retry receipt.
- `.scratch/proofs/tampered-base.stderr`: accepted-base drift rejection.
- `.scratch/proofs/metadata-current.json`: successful no-deps Cargo metadata.
- `.scratch/proofs/metadata-current-full.stderr`: genuine offline-fetch blocker.
- `.scratch/proofs/red-gates.log`: initial observed failures for malformed SHA
  acceptance and missing byte/mode/path checks.
- `.scratch/proofs/unit-gates-final.log`: final 11-test passing gate suite.

Earlier unsuccessful proof logs are retained separately. They caught Starlark's
unsupported JSON `\u` escapes and Copybara SQUASH path-filtered revision selection;
the final route uses literal UTF-8 and explicit dual provenance labels. No failed
run was reported as successful.

No GitHub writes, credentials, consumer modifications, native GUI/GPU tests,
crate publication, or complete license clearance are part of this evidence.
