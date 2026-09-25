//! Logical surface sizing. No output scale or desktop position belongs in xdg geometry.

pub(super) fn resize_axis(content: f32, inset: f32, start_tiled: bool, end_tiled: bool) -> f32 {
    content + if start_tiled { 0.0 } else { inset } + if end_tiled { 0.0 } else { inset }
}

pub(super) fn geometry_axis(
    surface: f32,
    inset: f32,
    start_tiled: bool,
    end_tiled: bool,
) -> (i32, i32) {
    let start = if start_tiled { 0.0 } else { inset };
    let end = if end_tiled { 0.0 } else { inset };
    (start as i32, ((surface - start - end) as i32).max(1))
}

// WGPU's bool distinguishes a submitted presentation from a failed acquire/draw.
// Failed draws must not leave new geometry pending for a later state-only commit.
pub(super) fn draw_with_geometry(
    last_presented: &mut Option<[i32; 4]>,
    geometry: [i32; 4],
    mut set_geometry: impl FnMut([i32; 4]),
    draw: impl FnOnce() -> bool,
) -> bool {
    set_geometry(geometry);
    let presented = draw();
    if presented {
        *last_presented = Some(geometry);
    } else if let Some(previous) = *last_presented {
        set_geometry(previous);
    }
    presented
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;

    #[test]
    fn geometry_is_staged_at_draw_and_failed_presentation_restores_old_buffer_geometry() {
        let old = [12, 12, 420, 180];
        let new = [12, 12, 420, 460];
        let last = &mut Some(old);
        let effects = RefCell::new(Vec::new());
        let presented = draw_with_geometry(
            last,
            new,
            |geometry| effects.borrow_mut().push(("geometry", geometry)),
            || {
                effects.borrow_mut().push(("draw", new));
                false
            },
        );
        assert!(!presented);
        assert_eq!(*last, Some(old));
        assert_eq!(
            *effects.borrow(),
            vec![("geometry", new), ("draw", new), ("geometry", old)]
        );
    }

    #[test]
    fn successful_present_retains_new_geometry_and_first_failure_has_no_old_buffer() {
        let new = [0, 0, 420, 180];
        let last = &mut None;
        let effects = RefCell::new(Vec::new());
        assert!(!draw_with_geometry(
            last,
            new,
            |g| effects.borrow_mut().push(g),
            || false
        ));
        assert_eq!(*last, None);
        assert_eq!(*effects.borrow(), vec![new]);
        effects.borrow_mut().clear();
        assert!(draw_with_geometry(
            last,
            new,
            |g| effects.borrow_mut().push(g),
            || true
        ));
        assert_eq!(*last, Some(new));
        assert_eq!(*effects.borrow(), vec![new]);
    }

    #[test]
    fn content_growth_and_return_include_both_client_insets() {
        for content in [180.0, 460.0, 180.0] {
            let surface = resize_axis(content, 12.0, false, false);
            assert_eq!(surface, content + 24.0);
            assert_eq!(
                geometry_axis(surface, 12.0, false, false),
                (12, content as i32)
            );
        }
    }

    #[test]
    fn tiled_edges_do_not_add_client_insets() {
        assert_eq!(resize_axis(100.0, 12.0, true, false), 112.0);
        assert_eq!(resize_axis(100.0, 12.0, false, true), 112.0);
        assert_eq!(resize_axis(100.0, 12.0, true, true), 100.0);
        assert_eq!(resize_axis(100.0, 0.0, false, false), 100.0);
        assert_eq!(geometry_axis(112.0, 12.0, true, false), (0, 100));
        assert_eq!(geometry_axis(112.0, 12.0, false, true), (12, 100));
    }

    #[test]
    fn geometry_is_logical_and_clamps_only_wire_dimensions() {
        assert_eq!(geometry_axis(101.75, 0.0, false, false), (0, 101));
        assert_eq!(geometry_axis(8.0, 12.0, false, false), (12, 1));
    }
}
