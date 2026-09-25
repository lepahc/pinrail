# Bootstrap decisions and scope

## User decisions

- Pinrail is a reusable GPUI distribution for Bewit and other Rust applications,
  not an application-specific widget library or a new renderer.
- Keep generated upstream imports separate from downstream framework changes.
  Protect both branches and use a repeatable Copybara-based import route.
- Preserve all upstream platform source. Initial qualification may use Linux
  builds and isolated/headless tests; other platforms must remain explicitly
  unverified rather than being silently removed.
- Retain upstream OFL fonts and the MPL-2.0 `cbindgen` macOS build dependency
  under their existing licenses, with applicable notices. Exclude the separately
  licensed CC BY-SA 3.0 dragon SVG example and its asset.
- Start with the basic engine correctness series: retry-registration recovery,
  XDG content-size/presentation ordering, pointer/IME reentry safety, and
  applicable safeguards for existing layer-shell APIs. Defer retained-layer
  transitions, custom capture, serial-free clipboard, and component changes.
- Use a trusted-`main` Actions route rather than allowing an import candidate to
  provide its own authoritative checker. Repository enforcement must still be
  exercised and verified before being called installed.
- Land the reviewed source snapshots into `lepahc/pinrail`, carrying the adopted
  source notices and exact inventories. This is narrow source-import authority,
  not complete third-party/license clearance or a legal guarantee. The controller
  requires explicit `--source-import` and committed `reviewed-source-import`
  scope; private evaluation remains a separate mode.
- Do not migrate consumers, publish packages/releases, schedule automatic
  upstream advancement, buy services, create broad credentials, or launch on
  the live desktop as part of this bootstrap.

These decisions are not complete legal clearance of external dependencies,
source files, SDKs, generated output, or runtime distributions. A package's
license declaration is evidence, not a substitute for file-level notices.
A manifest rewrite cannot relicense source. Build-tool licensing is distinct
from the licensing of generated output or application runtime linkage.

## Implementation choices to validate

- `upstream-import` is generated; `main` is the downstream consumer/development
  branch. Both start at one shared root commit.
- Start from a full pinned Zed revision in the existing source audit and use a
  preceding real revision to demonstrate update behavior. The upstream pin is
  an implementation selection, not a user-mandated latest-version policy.
- Pin the Copybara executable by release and SHA-256. Preserve original crate
  paths, dependency cohort, root lock selection and required resources.
- Candidate imports and controller/policy changes are different reviews. An
  import candidate cannot approve its own inventory or replace its checker.
- Integrate accepted imports into `main` with merge ancestry; do not squash
  away the recurring upstream relationship.
- Prefer a manually dispatched GitHub workflow if it can establish a trusted,
  exact-candidate check without new credentials. Local operation remains valid.
- Use PR-required branch rulesets, required checks once exercised, and block
  deletion and force-push. Do not require linear history or enable GitHub's
  separate Restrict updates rule. Choose review counts compatible with the
  actual single-account maintenance arrangement.

These choices must be backed by executed results before being called working.

## Verification status and remaining scope

- The adopted basic patch groups and release-state repair are independently
  reviewed and Linux CPU-qualified; see `patch-manifest.md` and `../PATCHES.md`.
  Upstream-superseded fixes are not copied.
- Any future adoption of the explicitly deferred retained-layer, capture,
  clipboard or component capabilities. `gpui-component` is not automatically
  part of this engine distribution or compatible with a newer GPUI cohort.
- New or changed licenses, dependencies, assets, build inputs and native SDK
  requirements beyond the specifically approved inputs above.
- Other-platform builds and native compositor/GPU evidence remain separate.
- Exercised GitHub discovery, exact-head source checks and ruleset rejections are
  recorded in `github-route.md`. Downstream main's actual live check and required
  rule must be verified before its acceptance; a live fork-namespace spoof test
  remains unperformed rather than inferred from local rejection tests.

Repository administrator credentials can change repository rules. These rules
are protection against accidental/unreviewed updates, not a hard boundary
against an administrator or a compromised allowed workflow. Separating routine
and administrative credentials would require a separate explicit setup.
