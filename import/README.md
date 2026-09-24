# Local GPUI import controller

This directory belongs to the **controller/downstream branch**, not the generated
import tree. The root README on generated candidates is created by Copybara and
explicitly says that the import branch is not the consumer branch.

## Status and policy

The local route has executed real pinned Copybara migrations, clean-root tree
recomputation, no-op retries, merge-commit acceptance/resumption, and a downstream
source-patch survival proof. See [verification.md](verification.md).

The checked-in baselines authorize **reviewed source import into `lepahc/pinrail`**
for exactly `e71963a599c64c213aca1c607e7418503a1e787d` and
`2c4bc2d7b2c5b7832ad964f39840d823d961cb0e`, under the user-adopted
[source-notice/input treatment](../docs/license-input-review.md). This is not
complete third-party/license clearance or a legal guarantee, and does not
authorize crate releases, consumer changes, or new unknown inputs. The policy:

- Retain all GPUI platform code, optional/target/dev/build dependencies and examples
  except the exact SVG example described below. Non-Linux targets are unverified.
- Retain IBM Plex and Lilex OFL fonts together with their upstream notices.
- Retain the external macOS `cbindgen` MPL-2.0 build dependency. Its role is build
  tooling, not an assertion of MPL runtime linkage. No cbindgen source is vendored;
  its dependency package supplies its notice when fetched.
- Omit exactly `crates/gpui/examples/svg/dragon.svg` (CC BY-SA 3.0),
  `crates/gpui/examples/svg/svg.rs`, and the `[[example]] name = "svg"` manifest
  target. Other examples and all platforms remain. This is a source-distribution
  omission, not merely disabling compilation.
- Preserve original license files and symlink targets. The closure has 26 Apache-2.0
  GPUI/helper packages plus the root Cargo `scratch` patch (MIT OR Apache-2.0).
- Carry the checksum-pinned supplemental Microsoft MIT permission text from
  `docs/licenses/microsoft-terminal-MIT.txt` as `LICENSE-MICROSOFT-MIT`, alongside
  unchanged source headers. The notice is part of the trusted controller digest
  and exact generated tree. Manifest transformations cannot relicense it.

Complete third-party/file-level licensing, native SDK terms, supported build
matrix, and real downstream patch adoption remain separate review tasks.

## Prerequisites and tool pins

Linux, Bash, Git, Python with `tomllib` (3.11+), `uv`, and Java are required.
Execution was tested with Python 3.12.12 and Java 26. No Rust compilation or
dependency resolution is performed by the import/verify commands. Cargo lock
preparation and standalone qualification use **Rust/Cargo 1.98.1** explicitly
(`cargo +1.98.1`, avoiding automatic installation of other upstream targets).
`import/run` bootstraps a private environment with
hash-pinned `tomlkit==0.13.3`.

Copybara is **v20260921**, source
`db68b8a5b5a4e8fec45877c11b19ef9af2bdbc4a`, downloaded only from its fixed release
URL in `pinrail_import.py`. Every use verifies SHA-256
`3b9307e9751710f2b04422e108ccc3667b9671eb73e91ea264f5f3baaae2f771`.
An existing JAR may be supplied with `--jar`; it receives the same hash check.
There is no mutable `latest` lookup.

All scratch, Python temporary files, Java temporary files/user home, Copybara
checkouts/caches, and the uv environment live on disk under `.scratch` or the
explicit `--scratch` directory. `/tmp`, tmpfs, and ramfs migration roots are
rejected. No source build scripts run during discovery or verification.

## Commands

Run these from a **trusted controller checkout**. Commit controller code and
reviewed baselines before import; pass that exact controller commit, not a
candidate-provided revision. Every revision argument must be a literal full
lowercase 40-hex SHA. Invalid tokens are rejected before dependency bootstrap or
network access; they are never trimmed, expanded, or repaired.

### Discover / inspect

```sh
import/run discover \
  --upstream 2c4bc2d7b2c5b7832ad964f39840d823d961cb0e \
  --scratch .scratch/discovery \
  --output .scratch/unreviewed-current.json
```

`inspect` is an alias. The output contains exact upstream object IDs/modes for
all selected and intentionally omitted files; dependency edges and feature
specifications; all target/dev/build/optional path closure; package declarations;
root patches; the all-platform pinned lock cohort and selected/omitted patches;
locked external source identities; input classes; and known
separately licensed assets/tools. Discovery cannot overwrite files or write into
`import/` and **cannot approve an inventory**.

Review an inventory independently, compare it with the previous controller
baseline, and commit the reviewed envelope at `import/baselines/<upstream>.json`.
The envelope requires a known scope (`reviewed-source-import` or
`private-evaluation-only`), a nonempty `review`,
the exact `inventory` value, and `cargo_lock_sha256` for the reviewed standalone
lock committed at `import/locks/<upstream>.lock`. Both baseline and lock are read
from the **specified controller commit**, never from the candidate or a dirty
working-tree replacement. There is intentionally no approval command.
Any changed file, mode, dependency, source, feature, manifest, license notice,
lockfile, or native input causes comparison against the committed baseline to
fail. A new source revision always requires a new explicit controller review.

### Import / regenerate

```sh
CONTROLLER=$(git rev-parse HEAD)
import/run import \
  --upstream 2c4bc2d7b2c5b7832ad964f39840d823d961cb0e \
  --controller-rev "$CONTROLLER" \
  --accepted-repo /absolute/path/to/local/accepted-repository \
  --accepted-base 875ec5e0a0a13b44076e43bb8a46629a8d447091 \
  --scratch .scratch/import-a \
  --source-import
```

`regenerate` performs the same operation. Exactly one explicit mode is required:
`--source-import` requires a committed `reviewed-source-import` baseline, while
`--private-evaluation` can use either known baseline scope and always produces
private-only output. There is no implied publication capability in either mode.
Switching output scope or controller code does not waive validation of old accepted
trees; bootstrap the new route from the shared seed rather than accepting drift.

The example base is the shared bootstrap
seed; subsequent runs must name the exact accepted import head. The accepted
repository is read locally, never pushed. A fresh migration subdirectory is
required. The wrapper creates its own disposable bare destination, fetches the
accepted base there, and allows Copybara to push only its local `candidate` ref.
There is no arbitrary destination URL argument and no GitHub write operation.

The last stdout line is machine-readable JSON with `candidate`, `base`, `tree`,
`upstream`, `controller`, `candidate_repo`, `noop`, `log`, `files`, `packages`, and
`scope`. Checkpoint-only recovery additionally reports `checkpoint_update: true`
(and `noop: false`) with `checkpoint_log`; otherwise those fields are `false`
and `null`. The same object is saved as `migration/result.json`. Errors exit
nonzero; the initial Copybara log remains in `migration/copybara.log` and a gated
recovery has its own `migration/checkpoint-copybara.log` and
`migration/checkpoint-command.json`. `migration/input-audit.json`
records literal include edges, generated include exceptions, native resource
inputs, and external SDK/tool requirements.

On a verified no-op, `candidate == base`; no new commit or candidate ref is
manufactured. Never publish a nearby or regenerated commit in place of the exact
checked candidate SHA. A separately authorized publisher must recheck that the
accepted head still equals `base` before updating any external ref.

### Verify a candidate

```sh
import/run verify \
  --upstream 2c4bc2d7b2c5b7832ad964f39840d823d961cb0e \
  --controller-rev "$CONTROLLER" \
  --accepted-repo /absolute/path/to/local/accepted-repository \
  --accepted-base FULL_ACCEPTED_BASE_SHA \
  --candidate-repo /absolute/path/to/local/candidate-repository \
  --candidate-sha FULL_CANDIDATE_SHA \
  --scratch .scratch/verify-a \
  --source-import
```

Replace the two uppercase placeholders with literal SHAs. Verification executes
a new Copybara migration in a clean root, compares **every Git file path, blob
ID and mode**, and checks the exact candidate parent and provenance labels. This
covers file bytes, executable bits, symlink target bytes, additions and deletions.
It does not execute candidate code, workflows, checker files or approval policy.
Candidate-added policy files are simply forbidden extra tree entries.

## Source acquisition and Cargo transforms

Discovery fetches a depth-one, blobless Git tree and reads only pinned raw
manifests, lockfile and symlink blobs, validating each raw blob against Git's
object ID. It does not clone a working copy of the editor. Copybara then performs
the **actual** migration with `git.origin(partial_fetch=True)`, explicit selected
package/root paths, no submodules, and bounded depth 256. Sparse cone expansion
can fetch some root metadata/files beyond the final selection; the final tree is
independently checked. Git server/filter behavior is not an access sandbox.

The resolver follows all declared in-tree dependency edges regardless of target,
feature, optionality, dev/build role, or proc-macro status, including renamed
workspace dependencies and `tooling/perf`. Root path patches are included too.
TOML-aware transformations retain workspace package inheritance and lints, reduce
members/default-members/inherited dependency definitions, and remove only the
SVG example target from its member manifest. Other member manifests are intact.

Cargo eagerly acquires even unused root Git patches. The importer now walks the
**original Cargo.lock graph from every selected path package**, without a host
target/feature filter. It retains patches only when their package and exact Git
source are in that pinned graph (path patches remain selected workspace members).
For both reviewed snapshots this retains `async-process`, `async-task`,
`windows-capture`, `calloop`, and `scratch`; it omits `tree-sitter-language`,
`livekit`, `libwebrtc`, `notify`, `notify-types`, and `webrtc-sys`. In particular,
Windows patches are not removed merely because qualification runs on Linux.

The whole upstream lock with these relevant patches was tried first: full
`cargo metadata --locked` rejected it as needing an update. A simple lock graph
slice was also insufficient because Cargo prunes upstream feature-union edges.
The checked-in standalone locks were therefore produced by **Cargo 1.98.1
metadata**, seeded with the exact upstream lock. This was pruning, not a fresh
`generate-lockfile`, `cargo update`, or a latest-version resolution.

The original reachable graph contains 894 identities; the Cargo-pruned lock has
875. Every retained name/version/source/checksum and every retained dependency
edge must exist in the original lock; all selected local packages must remain.
Changed or new identities, edges, ambiguous lock references, missing path packages,
and unknown patch forms fail closed. The same generated lock bytes apply to both
reviewed pins; their distinct original full locks remain independently inventoried.
Full all-feature, all-platform `cargo metadata --locked` resolved all 875 packages
with 27 workspace members. This is not merely `--no-deps` metadata.

For a new pin, prepare a proposed lock only in a disposable **actual Git worktree
of a Copybara-generated candidate**, with the new pin's selected manifests and
relevant root patches. Seed `Cargo.lock` from that exact pin. Run
`cargo +1.98.1 metadata --offline --format-version 1` to let Cargo prune the seeded
lock (missing cached package downloads can stop metadata after writing the lock).
Compare the complete result using `validate_lock_projection` against the original
lock and `cargo_projection` from the new pinned inputs; any identity/edge change
is a blocker, not permission to update. Only then allow downloads with full
`cargo +1.98.1 metadata --locked --all-features --format-version 1` and review the
result and lock diff. Commit the proposed lock and its reviewed baseline hash
together. Neither discovery nor import automatically approves this input.
Normal imports execute no resolver: they install those trusted, checked bytes.

The resource audit checks literal Rust includes, manifest target/readme/license
paths, five known native build scripts and their cross-crate shader/resource
inputs. Unknown nonliteral includes, outside-selection includes, path escapes,
dangling/escaping symlinks and symlink cycles fail closed. This is **not a complete
Rust parser, build-script I/O sandbox or external license audit**; exact reviewed
source bytes and separate native-build verification remain necessary.

## Provenance and acceptance

Copybara SQUASH normally chooses the last commit affecting selected paths, even
when the requested SHA is a newer unrelated editor change. `migrate_noop_changes`
does not undo the Git origin's earlier path filtering in this pinned release.
The importer therefore uses two explicit labels:

- `GitOrigin-RevId`: the exact requested upstream snapshot, also in the generated
  receipt. This header is produced by the reviewed transformation.
- `Copybara-Path-RevId`: the native Copybara-written revision marker configured
  through `custom_rev_id`; Copybara uses this for genuine history resumption.

Before returning success, the controller proves that all selected **raw** source
objects/modes at these two revisions are identical, including the original
manifests and lockfile before transformation. It never relabels different source
bytes as the requested snapshot. Verification also compares the candidate's
native marker with the recomputed marker. Preserve both labels and merge ancestry
when accepting candidates. Merge-commit acceptance and later resumption were
executed in the local proof; squash/rebase acceptance is not the supported proof.

An **excluded-only checkpoint advance is not an output no-op**: selected source
stays unchanged, but the reviewed pin in `README.md` and `PINRAIL_IMPORT.json`
must advance. The normal Copybara invocation runs first. Only after exit 4, no
candidate, and its exact empty-origin-range diagnostic may the controller run
Copybara once more with `--force`. Recovery requires all of the following:

- The old accepted tree and both committed pin baselines passed normal validation.
- The requested pin is new, and the complete reviewed inventories differ only in
  `upstream` (including identical raw inputs, selection, dependencies and policy).
- Output outside the two checkpoint files is unchanged; README changes only its
  pin, and the receipt changes only `upstream`, `reviewed_baseline_sha256`, and
  `inventory_sha256`. Excluded editor changes do not authorize policy/config drift.
- Both the previous requested checkpoint and native Copybara resumption revision
  are ancestors of the new pin, proven by a separate blobless depth-256 fetch.
  Missing ancestry, including history outside this bound, fails closed.

The recovery must exit successfully and produce a direct-child candidate with
exact expected bytes/modes/paths and valid native/raw-source equivalence. Errors
are not retried, and no provenance marker is manually edited. For this forced
checkpoint, Copybara writes the requested pin as its native resumption marker;
the next merged same-pin retry is an ordinary verified no-op without `--force`.
There is no user-facing force/drift-bypass switch.

`check_last_rev_state` is disabled because a pin-specific generated receipt cannot
be reconstructed using the next pin's constant transformation. Before invoking
Copybara, this controller instead recomputes and checks the *entire accepted base*
against its own committed baseline. Changed controller code digests fail this old
base comparison intentionally; controller-transform upgrades require a separately
reviewed migration, not an automatic waiver.

## Tests and authority boundary

```sh
import/run --help
.scratch/venv/bin/python -m unittest discover -s tests/import -v
.scratch/venv/bin/python tests/import/prove_local.py \
  --scratch .scratch/new-proof-root \
  --source-import \
  --jar /absolute/path/to/verified/copybara_deploy.jar
.scratch/venv/bin/python tests/import/prove_checkpoint.py \
  --scratch .scratch/new-checkpoint-proof-root \
  --source-import \
  --jar /absolute/path/to/verified/copybara_deploy.jar
```

The end-to-end commands perform public upstream reads and local Git writes only.
They retain per-step stdout/stderr, Copybara logs and `proofs.json`, use real bare
repositories/worktrees, and fail on the first failed acceptance criterion.
The focused checkpoint proof exercises a selected update, an excluded-only
advance, clean recomputation, merge acceptance, and same-pin retry. Its extra
native-pin baseline exists only in a disposable controller clone after checking
full input equality with the committed checkpoint baseline; it never approves a
new production baseline. An optional `--discovery-cache` copies an existing
cache read-only to save discovery traffic; pinned raw blobs are still verified.

### CPU-only standalone qualification

`tests/import/prove_standalone.py` verifies the exact candidate tree against the
trusted controller, creates a fresh actual Git worktree, then runs full locked
all-feature metadata, Linux all-target checks for `gpui`, `gpui_platform`,
`gpui_linux`, and `gpui_wgpu`, a full-workspace Linux all-target check, and library
tests for `gpui`, `gpui_linux`, and `gpui_wgpu`. It checks the complete metadata
identity set against the reviewed
lock, forbids path dependencies outside that worktree, and checks that Cargo did
not modify the lock or tracked source. It does not execute GUI examples.

Invoke it under the resource boundary (replace uppercase placeholders):

```sh
systemd-run --user --wait --pipe --collect \
  -p MemoryMax=10G -p MemoryHigh=8G -p CPUQuota=200% -p TasksMax=512 \
  --working-directory="$PWD" \
  env -u DISPLAY -u WAYLAND_DISPLAY -u WAYLAND_SOCKET \
  CARGO_BUILD_JOBS=2 TMPDIR="$PWD/.scratch/tmp" \
  .scratch/venv/bin/python tests/import/prove_standalone.py \
  --source-import \
  --upstream FULL_UPSTREAM_SHA --controller-rev FULL_CONTROLLER_SHA \
  --candidate-repo /absolute/path/to/migration/destination.git \
  --candidate-sha FULL_CANDIDATE_SHA \
  --worktree /absolute/path/to/new-short-worktree \
  --scratch .scratch/standalone
```

The driver uses a worktree-private target directory and disk-backed temporary
directory, two Cargo jobs/test threads, and disables dev/test debug information
for bounded memory/disk use. It retains separate command output and `results.json`.
Linux native development libraries (pkg-config, fontconfig, xkbcommon/X11/Wayland,
OpenSSL and the corresponding compiler/linker tools) must already be installed.
The CPU-only test profile explicitly skips the three `wgpu_atlas` tests that
request actual adapters/devices. Removing display variables alone does not stop
GPU access. Remaining tests use the test platform or pure protocol/shader validation; this
is **not compositor, window, pixel, GPU-device, or non-Linux execution proof**.

This controller has no credentials or repository-protection authority. A caller
must choose a trusted controller SHA and accepted base outside the candidate;
an attacker allowed to choose those authorities can choose different policy.
Local checks do not make an administrator credential tamper-proof. GitHub
workflow discovery, required-check publisher binding, protection, and publication
are separate integration tasks and are not claimed by this local implementation.
