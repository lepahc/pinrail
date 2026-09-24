//! Layer-shell's version and configure contracts, independent of native resources.

pub(super) fn keyboard_supported(version: u32, on_demand: bool) -> bool {
    !on_demand || version >= 4
}

pub(super) fn configure_size(requested: [f32; 2], configured: [u32; 2]) -> [f32; 2] {
    std::array::from_fn(|axis| {
        if configured[axis] == 0 {
            requested[axis].max(1.0)
        } else {
            configured[axis] as f32
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn on_demand_requires_version_four_without_changing_other_policies() {
        for version in 1..=3 {
            assert!(!keyboard_supported(version, true));
            assert!(keyboard_supported(version, false));
        }
        assert!(keyboard_supported(4, true));
        assert!(keyboard_supported(5, true));
    }

    #[test]
    fn compositor_controls_each_nonzero_axis_independently() {
        assert_eq!(configure_size([420.0, 180.0], [0, 260]), [420.0, 260.0]);
        assert_eq!(configure_size([420.0, 180.0], [640, 0]), [640.0, 180.0]);
        assert_eq!(configure_size([420.0, 180.0], [0, 0]), [420.0, 180.0]);
        assert_eq!(configure_size([420.0, 180.0], [640, 260]), [640.0, 260.0]);
    }
}
