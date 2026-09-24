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

## Unresolved until inventory and verification

- Exact retained framework patch manifest, including upstream-superseded fixes
  and porting of optional layer-shell, capture and clipboard capabilities.
- Separate disposition of `gpui-component` changes. They are not automatically
  part of this GPUI engine distribution or compatible with a newer GPUI cohort.
- New or changed licenses, dependencies, assets, build inputs and native SDK
  requirements beyond the specifically approved inputs above.
- Actual build/test and compositor evidence for each platform and capability.
- GitHub workflow discovery, exact-head publishing identity, check results and
  ruleset rejection behavior, until exercised and read back.

Repository administrator credentials can change repository rules. These rules
are protection against accidental/unreviewed updates, not a hard boundary
against an administrator or a compromised allowed workflow. Separating routine
and administrative credentials would require a separate explicit setup.
