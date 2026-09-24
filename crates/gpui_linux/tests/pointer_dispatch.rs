//! CPU-only control-flow regression for the production pointer dispatcher.
//!
//! Extract the real dispatch prelude and complete Motion/Button arms without
//! rewriting them. The fixture supplies client/window/protocol type stand-ins,
//! not another implementation of dispatch. This catches guard-order regressions
//! that tests of pointer.rs alone cannot. It is NOT native Wayland/compositor,
//! protocol decoding, GPU, focus, or IME acceptance coverage.
//!
//! Run under the project's resource wrapper, with no display credentials:
//! cargo +1.98.1 test --locked -p gpui_linux --test pointer_dispatch -- --nocapture
//! Or compile this harness directly with rustc --edition=2024 --test.

use std::{fs, path::PathBuf, process::Command};

fn between<'a>(source: &'a str, start: &str, end: &str) -> &'a str {
    let start = source.find(start).expect("production start anchor changed");
    let end = start
        + source[start..]
            .find(end)
            .expect("production end anchor changed");
    &source[start..end]
}

#[test]
fn production_pointer_dispatch_regressions() {
    let client = include_str!("../src/linux/wayland/client.rs");
    let dispatch = client
        .split_once("impl Dispatch<wl_pointer::WlPointer, ()> for WaylandClientStatePtr {")
        .expect("production pointer dispatcher changed")
        .1;
    let prelude = between(
        dispatch,
        "        let client = this.get_client();",
        "        match event {",
    );
    let arms = between(
        dispatch,
        "            wl_pointer::Event::Motion {",
        "            // Axis Events",
    );
    let buttons = between(
        client,
        "fn linux_button_to_gpui(",
        "impl Dispatch<wl_pointer::WlPointer, ()>",
    );
    let fixture = include_str!("pointer_dispatch/fixture.rs")
        .replace("/* PRODUCTION_PRELUDE */", prelude)
        .replace("/* PRODUCTION_ARMS */", arms)
        .replace("/* PRODUCTION_BUTTON_MAPPING */", buttons)
        .replace(
            "/* PRODUCTION_POINTER_HELPERS */",
            include_str!("../src/linux/wayland/pointer.rs"),
        )
        .replace(
            "/* PRODUCTION_SERIAL_TRACKER */",
            include_str!("../src/linux/wayland/serial.rs"),
        );
    // Require the caller's private scratch. Never fall back to /tmp or a live
    // display, including when running the dependency-free rustc harness.
    let scratch = PathBuf::from(std::env::var_os("TMPDIR").expect("set a private TMPDIR"))
        .join(format!("pointer-dispatch-{}", std::process::id()));
    fs::create_dir(&scratch).expect("unique scratch directory");
    let source = scratch.join("probe.rs");
    let binary = scratch.join("probe");
    fs::write(&source, fixture).unwrap();
    let compile = Command::new("rustc")
        .args(["--edition=2024", "--test"])
        .arg(&source)
        .arg("-o")
        .arg(&binary)
        .env_remove("DISPLAY")
        .env_remove("WAYLAND_DISPLAY")
        .env_remove("WAYLAND_SOCKET")
        .output()
        .expect("rustc must be available");
    assert!(
        compile.status.success(),
        "fixture failed to compile (retained at {}):\n{}",
        scratch.display(),
        String::from_utf8_lossy(&compile.stderr)
    );
    let result = Command::new(&binary)
        // Helper/serial unit tests already run in the library gates. Run only
        // the dispatcher cases here; do not double-count helper coverage.
        .args(["regression::", "--test-threads=2", "--nocapture"])
        .env_remove("DISPLAY")
        .env_remove("WAYLAND_DISPLAY")
        .env_remove("WAYLAND_SOCKET")
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&result.stdout);
    let stderr = String::from_utf8_lossy(&result.stderr);
    println!("{stdout}{stderr}");
    assert!(
        result.status.success(),
        "dispatcher regression failed; fixture retained at {}",
        scratch.display()
    );
    fs::remove_dir_all(&scratch).unwrap();
}
