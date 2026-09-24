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
  --scratch PROJECT_SCRATCH --private-evaluation
```

**Current limitation:** the importer interface and baselines are private-evaluation
only. This flag does not authorize public distribution or clear licenses. The
adapter must change alongside a separately reviewed public-baseline interface;
do not merely delete the flag or silently approve a new inventory. See the import
controller's own runbook for tool pins, source scope, provenance and licensing.

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
- installs the exact Rust release declared in K, not a candidate-selected release;
- runs locked no-dependency Cargo metadata and compiles `gpui`/`gpui_platform`
  plus their tests with Wayland and X11 selected.

The exact head must contain B as an ancestor; strict up-to-date checks remain
necessary at merge time. The final Cargo command is the native-integration adapter:
extend it with the independently verified port regression commands once integrated.
The initial command list is **not** a claim of successful Linux compilation,
native behavior, GPU/compositor, other-platform or application qualification.
Compilation can execute candidate build scripts; never move it into a write-token
job. No display is connected and no GUI program is deliberately launched.

Ubuntu 24.04 supplies Python and Java 21 (the worker selects `JAVA_HOME_21_X64` if
present). Every action is commit-pinned; uv is version/checksum-pinned with cache
upload disabled. Copybara and Python hashes belong to the importer. The hosted
runner image and Ubuntu package repository are not immutable build environments.
Temporary directories are under the workspace `.scratch`, not `/tmp`.

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
actionlint .github/workflows/verify.yml
```

Tests cover malformed literal identifiers/events/payloads, repository/base
constraints, stale head/base/controller/open state, non-success job outcomes,
wrong check identities, exact readback, and bare candidate acquisition/receipt
parsing/trusted runner selection. The API transport is a local test double; the
Git fixtures are real. The fixture importer is deliberately inert and does **not**
claim to prove Copybara regeneration. Run the separate importer proofs for that.

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

This implementation was locally tested, not deployed by its author. No remote
settings, checks, workflows, PRs or branch refs were written during implementation.

### GitHub sources

- [Default-branch pull_request_target source change](https://github.blog/changelog/2025-11-07-actions-pull_request_target-and-environment-branch-protections-changes/)
- [Events and repository_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [Secure use of pull_request_target](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)
- [Troubleshooting required status checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
- [Workflow execution protections](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/actions-policies/workflow-execution-protections)
- [Checks API](https://docs.github.com/en/rest/checks/runs)
