# Trusted-main GitHub verification route

This route verifies locally produced candidates; it does **not** produce/push
branches, open or approve PRs, merge, publish releases, or advance upstream on a
schedule. `main` is the controller trust root. `upstream-import` remains a generated
source branch without workflows. Only same-repository PR heads are admitted in
this initial route; fork heads fail closed.

## What is authoritative

`.github/workflows/verify.yml` uses `pull_request_target` for PRs into `main` and
`upstream-import`, and `repository_dispatch` (`pinrail-verify`) for explicit retries.
Current GitHub.com sources both events from the **default branch**, including
`pull_request_target` when the PR targets another branch. All three jobs checkout
`github.workflow_sha` as immutable controller K, never an event-supplied ref.

The required results are explicit Checks API runs on exact candidate **C**:

| Target | Reserved check name |
| --- | --- |
| `upstream-import` | `pinrail-import-integrity-v1` |
| `main` | `pinrail-main-v1` |

Ordinary workflow job checks are deliberately named differently. They are not the
required result: target-event jobs concern the controller context, and GitHub
excludes ordinary manually dispatched workflow-job checks from PR evaluation.
The API-created check's eligibility must be demonstrated on GitHub before enabling
it as a required check. Local tests are **not** that demonstration.

### Three isolated jobs

1. **Resolve/start** (`contents: read`, `pull-requests: read`, `checks: write`):
   validate event, exact repository name/ID, PR number, full lowercase SHAs and
   allowed base; re-read the open/unmerged PR, main K and actual base B; reject
   stale events and fork heads. Create an in-progress exact-C check and read it
   back. Only fixed-schema identifiers pass to the other jobs.
2. **Verify** (`contents: read`): checkout K without persisted credentials. Fetch
   B and the PR head into a fresh local bare repository using a fixed remote and
   numeric PR ref, and compare both fetched commits with the resolver snapshot.
   The import path does not checkout or execute candidate files, hooks, Cargo
   scripts, workflows or configs. The main path may execute candidate tests/build
   scripts, but only on this separate ephemeral runner, with no write token or
   secrets and no shared cache/artifact consumed by the publisher.
3. **Complete** (same narrow permissions as resolve): checkout K on another clean
   runner, consume the Actions job result, recheck live PR/head/base/main/open
   state, and finish **that check ID**. It validates name, head, external run/attempt
   identity and publisher before PATCH and reads the exact target back afterwards.
   Failure, skip and cancellation never become `success`, `neutral` or `skipped`.
   If resolve/publishing cannot run, no fresh authoritative success is created.

The summary binds repository, PR, controller K, head C, base B, run/attempt and
actual publisher integration ID. No worker output file or executable artifact is
read by the publisher. Payloads enter Python as JSON/environment data, never shell
interpolation. PR title/body and candidate-provided controller revisions are unused.

## Import adapter and policy boundary

`scripts/ci/verify.py:import_command` is the small integration adapter. It checks
that C's sole parent is B, reads a bounded regular `PINRAIL_IMPORT.json` blob with
Git (not the filesystem), validates its `upstream` as a literal SHA, and requires
`import/baselines/<upstream>.json` to exist in **K**. The other receipt fields are
not authority. The trusted importer independently validates inventory, policy,
whole-tree contents/modes and provenance by executing a new pinned Copybara
migration into a disposable **local** destination:

```text
import/run verify --upstream U --controller-rev K \
  --accepted-repo LOCALBARE --accepted-base B \
  --candidate-repo LOCALBARE --candidate-sha C \
  --scratch PROJECT_SCRATCH --source-import
```

The adapter selects `--source-import` only for a committed controller baseline
whose scope is `reviewed-source-import`; `private-evaluation-only` instead selects
`--private-evaluation`. Unknown/missing scopes fail. Candidate receipt scope is
not authority. Source acceptance is not crate-release authorization or complete
third-party/SDK/runtime license clearance. See the import controller's runbook
for tool pins, exact notice/input inventory, source scope and provenance.

Controller/workflow/helper/baseline changes into main require deliberate,
independent **source review** before owner acceptance. A green main check is only
test/compile evidence, not that review and not automatic approval of inventory,
licensing, policy or a new check publisher. There is intentionally no in-workflow
"approve this baseline" switch and no claim that an agent review is a second
GitHub reviewer identity.

## Main checks and integration seam

`scripts/ci/main_checks.py`, loaded from K, prescribes commands against C. It:

- fails if the candidate lacks Cargo manifests/lockfile, importer or test suites;
- installs Python dependencies from K's hash-pinned importer requirements;
- runs candidate `tests/ci` and `tests/import` unittest suites;
- installs the exact Rust release in K's `scripts/ci/rust-toolchain.toml`, before
  importer tests which themselves invoke Cargo (the pin exists before main has
  the generated source's root toolchain file);
- runs full all-feature locked Cargo metadata, the entire workspace all-target
  Linux check with test support, GPUI/wgpu headless library tests, and Linux
  `--tests` so retained pointer-dispatch/offscreen integration regressions execute
  rather than merely compile. Linux library tests run once through that command.

The exact head must contain B as an ancestor; strict up-to-date checks remain
necessary at merge time. The commands match the qualified Linux profile, use two
Cargo jobs/test threads and disable dev/test debug information. A passing
`pinrail-main-v1` is Linux evidence, not GPU/compositor, other-platform or
application qualification.
The three `wgpu_atlas` tests that request actual adapters/devices are explicitly
excluded by full test name; removing display variables alone is not CPU isolation.
Compilation can execute candidate build scripts; never move it into a write-token
job. No display is connected and no GUI program is deliberately launched.

Ubuntu 24.04 supplies Python. Copybara v20260921's main class is class version 69;
the runner's Java 21 is insufficient. The workflow installs the exact Linux x64
Temurin 25.0.4.1+1 archive with SHA-256
`dbb698396d478e7fa2b1e50f4103324b2a99b90569ee27c33f2261f9215cf41e` and preserves that
JAVA_HOME instead of downgrading it. Every action is commit-pinned; uv is
version/checksum-pinned with cache upload disabled. Copybara and Python hashes
belong to the importer. The hosted
runner image and Ubuntu package repository are not immutable build environments.
Temporary directories are under the workspace `.scratch`, not `/tmp`.

## Native extension: separately qualified exact-head aggregate

`.github/workflows/native.yml` adds **`pinrail-native-v1`**, not another
`pinrail-main-v1`. Historical Linux greens never count as native qualification.
The new workflow admits automatic `pull_request_target` events **only into main**
and the separate `repository_dispatch` event `pinrail-native-verify`. Same-repository,
open/unmerged PR admission and current controller/base/head checks remain mandatory.
Import-target PRs are rejected before creating a check or scheduling native work;
native workers never install or run the importer, Java, or uv.

The workflow is written in YAML's JSON subset so stdlib-only CI tests can inspect
its event/job/permission/matrix structure without adding a YAML dependency. It is
also validated with actionlint. The existing Linux/import workflow and its default
gate command, snapshot schema, check names and external IDs remain compatible.
The native resolver/publisher explicitly invoke `gate.py ... --suite native-v1`:

- Native snapshots require `suite: native-v1`. Other suites/extra fields fail;
  legacy snapshots are not native authorization and vice versa.
- Native checks use external ID `pinrail:native-v1:RUN:ATTEMPT:PR` and bind exact C,
  native check name, run URL (or GitHub's exact normalized check URL), and observed
  GitHub Actions publisher integration **15368**. Identity is read back after
  creation and before/after completion PATCH, using the shared gate logic.
- Resolve and complete stay on Ubuntu 24.04 with five-minute limits. Complete adds
  `actions: read` solely to read this run attempt's job conclusions. Neither job
  materializes C or consumes worker artifacts, caches, outputs, or executable files.

### Fixed read-only native matrix

| Platform argument | Standard hosted runner | Python architecture |
| --- | --- | --- |
| `macos-arm64` | `macos-15` | `arm64` |
| `macos-x86_64` | `macos-15-intel` | `x64` |
| `windows-x86_64` | `windows-2025` | `x64` |

All three platforms are mandatory; dispatch cannot select a subset or override
commands, suite, controller, or runner. Each job has `contents: read` only, a
60-minute limit, and no `continue-on-error`. Matrix `max-parallel: 2` bounds native
concurrency; `fail-fast: false` lets each admitted platform report its actual result.
Every checkout is K = `github.workflow_sha`, without persisted credentials,
submodules or LFS. Each native workflow checkout action sets process-scoped
`GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=core.autocrlf`, and
`GIT_CONFIG_VALUE_0=false` **before** materializing K. This overrides the Windows
Git default without writing global config, aligns K with the sanitized candidate
checkout, and preserves `.gitattributes`' exact CRLF permission notices. Neither
the clean-tree check nor the byte-for-byte lock guard normalizes line endings.
Actions are commit-pinned. `actions/setup-python` v6.2.0 is pinned
to `a309ff8b426b58ec0e2a45f0f869d46889d02405` (retrieved from its tag and action source),
with Python **3.13.7** and explicit architecture; no package cache or pip-install
input is enabled. Both shell entrypoints invoke the action's absolute `python-path`
with `-E -s -B`, not a Windows Store alias or an ambient Python chosen from C.
The published Python version manifest lists all three selected OS/architecture assets.

`native_verify.py` reuses the read-only Git adapter. It validates native snapshot,
platform, clean controller checkout and exact K before acquisition; fetches B/C
from the fixed repository into a fresh bare object store; verifies both SHAs and
B ancestry; then creates a clean detached worktree at C. It neither resets nor
reuses old worktrees. Git ignores system/user configuration and ambient Git
overrides; `os.devnull` supplies the platform's null config path, a private empty
directory disables hooks portably, and checkout disables automatic CRLF conversion.
The candidate subprocess receives private workspace-local TMPDIR/TMP/TEMP and no
GH/GITHUB/ACTIONS control variables, ambient Python path, Git injection settings or
display connection. This is an ephemeral read-only job boundary, not a sandbox
against runner escapes or arbitrary native build-script behavior.

Only K's driver is executed, using this fixed interface:

```text
python <controller>/scripts/ci/native_checks.py \
  --platform {macos-arm64,macos-x86_64,windows-x86_64} \
  --candidate <absolute-downstream-worktree>
```

That driver owns native host/SDK/toolchain preflight, compile/link and explicitly
selected CPU tests. The adapter limits it to 3300 seconds within the job's outer
60-minute budget. It does not run a GUI or promote a check based on a log string.

### Aggregate completion and retry

Completion requires both `needs.verify.result == success` **and** exactly one
completed successful job for each fixed `Native worker (PLATFORM)` name in
`GET /actions/runs/RUN/attempts/ATTEMPT/jobs`. The gate validates job run/attempt/ID,
complete collection count, unique required names/IDs, and admitted conclusions.
It never relies on a matrix job output that another leg could overwrite. Missing,
duplicate, unknown, truncated or old-attempt job metadata is rejected, leaving no
new success. Failed/cancelled/skipped jobs fail the aggregate. Head/base/controller
movement, closing/retargeting or repository drift also fail completion on original C.
If cancellation prevents the publisher from running, the in-progress check is not
success. A malformed API response cannot be manually waived into a green check.

Retry only the exact current head of an eligible main-target PR:

```sh
gh api --method POST repos/lepahc/pinrail/dispatches \
  -f event_type=pinrail-native-verify \
  -F "client_payload[pr]=$PR_NUMBER" \
  -f "client_payload[head_sha]=$CANDIDATE_SHA"
```

Prefer a fresh dispatch to partial job reruns: snapshots and all platform results
are bound to one run attempt. Native retry does not refresh the separate Linux
`pinrail-main-v1` check. No Actions execution-policy change is needed or permitted;
keep the all-path, no-exemption policy admitting only the two existing event types.

**Installation is not native qualification.** Bootstrap the controller through an
ordinary PR and the existing strict Linux requirement. Keep the native check
non-required until a subsequent exact-head PR demonstrates all three real hosted
profiles, native shader/link evidence, nonzero selected tests, and authoritative
check GET readbacks/eligibility. Only then separately promote `pinrail-native-v1`
as an additional strict, app-bound requirement alongside `pinrail-main-v1`. This
source change installs no branch rule and claims no successful macOS/Windows run.
GPU/native pixels, IME/focus/clipboard, minimum OS versions, signing, packaging,
releases, Windows ARM64 and WASM remain outside this qualification.

Local `tests/ci/test_native_gate.py` uses a transport double but real authorization,
freshness and publishing decisions; `test_native_verify.py` uses real Git fixtures
and a real inert trusted-driver subprocess (not native builds). Workflow regression
tests cover event, job, permissions, fixed runner matrix, limits and fail-closed
completion wiring. These proofs do not replace live native or GitHub acceptance.

## Local producer and explicit retry

Use the importer locally with its reviewed controller and baseline. Recheck the
accepted destination head before pushing an ordinary fresh candidate branch and
opening a PR into `upstream-import`. Preserve the original candidate commit and
its provenance using a merge commit; do not squash/rebase recurring imports.
After import acceptance, merge the accepted import head into a separate downstream
integration branch and open its tested PR into main. No bot producer is installed.

A repository dispatch may retry either supported PR target. With `PR_NUMBER` set
to the integer PR number and `CANDIDATE_SHA` set to the exact full current head:

```sh
gh api --method POST repos/lepahc/pinrail/dispatches \
  -f event_type=pinrail-verify \
  -F "client_payload[pr]=$PR_NUMBER" \
  -f "client_payload[head_sha]=$CANDIDATE_SHA"
```

No controller, arbitrary repository, executable command or baseline override is
accepted in the payload. A changed base requires regenerating an import candidate
(or updating a main integration branch); it cannot be waived by retry. A changed
main/controller requires a fresh dispatch. GitHub's old-event reruns preserve K;
"rerun failed jobs" can also preserve an old resolver attempt, which this route
rejects. Prefer a fresh dispatch over a partial rerun.

**Check URL normalization pitfall:** GitHub Actions has returned
`https://github.com/lepahc/pinrail/runs/<check_id>` as `details_url` instead of the
submitted `https://github.com/lepahc/pinrail/actions/runs/<run_id>/attempts/<attempt>`.
An echo-only API fixture missed this and resolve failed with `check identity mismatch`.
Readback accepts only those two exact URLs for the expected repository/check/run;
the external ID still binds run, attempt and PR, alongside head, name and publisher
checks. Do not ignore an arbitrary URL or manually mark the check successful. After
landing a controller repair, use a fresh dispatch and verify the exact check via GET.

## Required repository configuration — separate deployment

The workflow cannot enforce these settings from within itself. The administrator
must deploy, read back, and exercise them separately:

- Keep default branch `main` and the repository's default token read-only; do not
  grant Actions permission to approve PRs or give routine bypass actors.
- Restrict **all workflow paths**, without actor exemptions, to default-branch
  sourced events `pull_request_target` and `repository_dispatch` using the
  repository Actions execution policy. Merely giving this workflow read-only
  defaults does not constrain another workflow.
- Require the exact named check on each exact branch, bound to the **observed**
  GitHub Actions publisher integration ID. Never guess that ID or use an ordinary
  job name. Enable strict up-to-date evaluation.
- Require PRs, block deletion and non-fast-forward updates, and preserve merge
  ancestry. Do not require linear history, enable Restrict updates, or install a
  permanent broad bypass to get bootstrap unstuck. Approval counts must reflect
  actual distinct authorized reviewer accounts.

**Name plus GitHub Actions app is not workflow identity.** Another allowed
candidate-controlled workflow could spoof the same name/app. Execution policy and
its real enforcement are essential to the stronger boundary. Fork-namespace check
behavior and same-name spoof resistance also require a live proof. An alternative
organization-required pinned workflow is a distinct, owner-controlled design, not
silently configured here.

Main advancement during verification fails completion, conservatively even for
documentation changes. After a check is published there remains a race with later
base/controller changes: use strict branch rules, revalidate open PRs, and rotate
the required check version for incompatible controller/policy changes. No check
summary alone revokes old green evidence. Administrators, accepted malicious main
changes, compromised tools or runner escapes remain outside this boundary.

## Verification and rollout checklist

Local, network-free controller/real-Git adapter tests:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/ci -v
# If installed, also validate Actions expressions and schema:
actionlint .github/workflows/verify.yml .github/workflows/native.yml
```

Tests cover malformed literal identifiers/events/payloads, repository/base
constraints, stale head/base/controller/open state, non-success job outcomes,
wrong check identities, exact readback, and bare candidate acquisition/receipt
parsing/trusted runner selection. The API transport is a local test double that
models observed Actions URL normalization as well as URL echoing; it does not prove
native API behavior or required-check eligibility. A fresh live run and exact-check
GET readbacks remain necessary. The Git fixtures are real. The fixture importer is
deliberately inert and does **not** claim to prove Copybara regeneration. Run the
separate importer proofs for that.

Before calling the GitHub route operational, demonstrate and retain readbacks of:

1. Main-only workflow discovery for a PR targeting workflow-free upstream-import.
2. Exact-C check creation and observed app identity, successful required-result
   evaluation for both automatic PR and repository-dispatch triggers.
3. Valid/invalid import candidates, stale/retargeted/closed PRs and failure/cancel
   cases; a green controller workflow alone must never authorize merging.
4. Same-name check spoof attempts (including fork context) denied by execution
   policy/publisher binding, plus direct-update/deletion/force-push rejection on
   equivalently protected disposable refs.
5. Real accepted merge ancestry/tree/provenance, subsequent importer resumption,
   and downstream compile/regression success without live-desktop interaction.

### Bootstrap deployment evidence

The controller landed through [PR #1](https://github.com/lepahc/pinrail/pull/1)
and its live readback/native-test repair through
[PR #3](https://github.com/lepahc/pinrail/pull/3). The generated source landed
through [PR #2](https://github.com/lepahc/pinrail/pull/2), preserving candidate
`f0ed7dfd77382c0865f3be016d61d97a0ea1de43` and accepted import merge
`e85dd4a8848dcf41e7b442ddf8feeb3d40890183`.

- Fresh repository-dispatch [run 36075901062](https://github.com/lepahc/pinrail/actions/runs/36075901062)
  regenerated the exact source tree successfully. Check `107886935244` was read
  back on the candidate SHA with publisher `github-actions`, integration ID
  `15368`; GitHub recognized it as required and accepted the ordinary PR merge.
- [PR #4](https://github.com/lepahc/pinrail/pull/4) added a candidate workflow to
  an otherwise valid import. Its automatic target-event verifier rejected the
  extra path; exact-head check `107887277984` failed and the PR was blocked.
  The candidate's same-name push and ordinary PR workflows produced startup
  failures with no jobs/checks. The push annotation explicitly reported the
  disallowed event. The negative PR was closed and its branch removed.
- All-path Actions policy `5570` admits only `pull_request_target` and
  `repository_dispatch`, without exemptions. Both branch rules require PRs and
  merge ancestry, forbid deletion/non-fast-forward updates, and have no bypass.
  The upstream-import rule additionally requires strict
  `pinrail-import-integrity-v1`, bound to observed integration `15368`.
- A disposable ref with an exact copy of the import rules rejected a direct
  update, force update, deletion and [PR #5](https://github.com/lepahc/pinrail/pull/5)
  merge without its required check. Each failed write left the ref unchanged.
  That PR, temporary rule and both probe refs were subsequently cleaned up.
- Running the importer against accepted merge `e85dd4a` with controller
  `edd80846b0de3f2097df3e21e62cbfea5aace7c1` returned `noop: true`, the same
  accepted commit/tree, and `checkpoint_update: false`.
- The combined downstream tree passed full locked metadata (875 packages,
  27 members), workspace all-target checking, 27 CI and 30 importer tests,
  452 CPU-only library tests, 18 overlapping offscreen helpers, and the retained
  dispatcher wrapper's ten regression cases. Three GPU-device tests were
  explicitly filtered. Downstream acceptance must still bind its actual PR head
  to a live `pinrail-main-v1` result and enable that strict required context before
  merging; consult current PR/check/ruleset readbacks, not this historical note.

This establishes the exercised same-repository paths, not the entire checklist:
no live fork-namespace spoof probe was performed. Fork heads are deliberately
unsupported and rejected in controller tests. Staleness/cancellation coverage is
local contract coverage unless accompanied by a specific live run. Native
compositor/GPU and non-Linux execution remain unqualified.

### GitHub sources

- [Default-branch pull_request_target source change](https://github.blog/changelog/2025-11-07-actions-pull_request_target-and-environment-branch-protections-changes/)
- [Events and repository_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [Secure use of pull_request_target](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)
- [Troubleshooting required status checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
- [Workflow execution protections](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/actions-policies/workflow-execution-protections)
- [Checks API](https://docs.github.com/en/rest/checks/runs)
