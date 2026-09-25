//! Fast, dependency-free harness for the exact modules used by the Wayland backend.
//! These are policy/effect-boundary tests, not compositor, GPU, or native input tests.
//! They also run as unit tests with the owning backend; this harness permits running
//! them with `rustc --test` while the workspace's native dependencies are unavailable.

#[path = "../src/linux/wayland/frame_loop.rs"]
mod frame_loop;
#[path = "../src/linux/wayland/geometry.rs"]
mod geometry;
#[path = "../src/linux/wayland/layer_policy.rs"]
mod layer_policy;
#[path = "../src/linux/wayland/pointer.rs"]
mod pointer;
