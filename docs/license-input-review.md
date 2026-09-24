# Imported input and notice review

This is a bounded technical review of Zed snapshot
`2c4bc2d7b2c5b7832ad964f39840d823d961cb0e`, not complete legal clearance.
Dependency resolution/build verification and a final publication inventory are
separate gates. No manifest edit changes upstream ownership or licensing.

## Adopted treatment

- Preserve all platform source and notices.
- Retain IBM Plex and Lilex fonts under OFL-1.1, including their original notices
  and the Plex reserved-font-name statement. Do not rename/relicense the fonts.
- Retain `cbindgen` as an external MPL-2.0 macOS build dependency. This does not
  establish MPL runtime linkage or license terms for generated headers.
- Exclude the CC BY-SA 3.0 dragon SVG, its example source, and its Cargo example
  target. Disabling compilation without removing the asset would not suffice.

## Additional source-level findings

Most selected in-tree package manifests declare Apache-2.0. The root `scratch`
patch declares `MIT OR Apache-2.0`. The nested `hello_web` example is a separate
workspace with an Apache license symlink but no package `license` field; it is
not one of the root workspace's members. Preserve that distinction in counts
and avoid implying its independent dependency graph has been qualified.

The imported source contains Microsoft Terminal-derived MIT portions:

- `crates/gpui/src/platform.rs`: gamma-correction ratios.
- `crates/gpui_wgpu/src/shaders.wgsl`: contrast/gamma correction.
- `crates/gpui_windows/src/alpha_correction.hlsl`.

Their headers identify Microsoft copyright and the exact source revision
[`1283c0f5b99a2961673249fa77c6b986efb5086c`](https://github.com/microsoft/terminal/tree/1283c0f5b99a2961673249fa77c6b986efb5086c).
The exact upstream permission text is retained in
[`licenses/microsoft-terminal-MIT.txt`](licenses/microsoft-terminal-MIT.txt),
SHA-256 `5d177f23ecfeb0ea8e050b6a5a16355e1ae9a0b286436ca8f83ed08b3795be6b`.
The generated source distribution must carry this supplemental notice as well
as the unchanged source headers before public source import acceptance.

`crates/gpui_linux/src/linux/x11/clipboard.rs` preserves Zed and Arboard copyright
and explicitly offers `Apache-2.0 OR MIT` for adapted portions. Root Apache text
and the original header are retained; this is not an all-Apache authorship claim.

## Boundaries of the review

- The exact initial candidate had 412 tracked files and 28 symlinks. These are
  snapshot-specific observations, not future import limits. The importer must
  verify every selected file/mode and resolve every preserved license symlink.
- Eight bundled TTF files are covered by the two retained OFL notices.
- Remaining bundled example images are individually inventoried. A text-header
  scan did not establish independent provenance for every binary image. Retaining
  upstream package licensing evidence is not a new ownership assertion.
- External packages, native SDK/compiler terms, runtime-linked libraries,
  generated outputs, and example runtime downloads require their own scope-aware
  assessment. An in-tree manifest traversal or text scan cannot clear them.
- New file/dependency/asset/license/build-input changes require a reviewed baseline
  update. They must not be approved merely because they are under a selected
  directory. Candidate code cannot modify its own authoritative baseline.
