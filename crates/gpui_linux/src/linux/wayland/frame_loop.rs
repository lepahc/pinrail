use std::cell::Cell;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum PresentationState {
    Unpresented,
    Presented,
    RetryBeforeFirstPresent,
    RetryAfterPresent,
}

impl PresentationState {
    pub(super) fn requires_presentation(self) -> bool {
        matches!(
            self,
            Self::RetryBeforeFirstPresent | Self::RetryAfterPresent
        )
    }

    pub(super) fn failed(self) -> Self {
        match self {
            Self::Unpresented | Self::RetryBeforeFirstPresent => Self::RetryBeforeFirstPresent,
            Self::Presented | Self::RetryAfterPresent => Self::RetryAfterPresent,
        }
    }
}

#[cfg(test)]
mod presentation_state_tests {
    use super::PresentationState;

    #[test]
    fn failure_tracks_whether_the_surface_has_presented() {
        assert_eq!(
            PresentationState::Unpresented.failed(),
            PresentationState::RetryBeforeFirstPresent
        );
        assert_eq!(
            PresentationState::RetryBeforeFirstPresent.failed(),
            PresentationState::RetryBeforeFirstPresent
        );
        assert_eq!(
            PresentationState::Presented.failed(),
            PresentationState::RetryAfterPresent
        );
        assert_eq!(
            PresentationState::RetryAfterPresent.failed(),
            PresentationState::RetryAfterPresent
        );
    }

    #[test]
    fn only_retry_states_require_presentation() {
        assert!(!PresentationState::Unpresented.requires_presentation());
        assert!(!PresentationState::Presented.requires_presentation());
        assert!(PresentationState::RetryBeforeFirstPresent.requires_presentation());
        assert!(PresentationState::RetryAfterPresent.requires_presentation());
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum FrameLoop {
    Unconfigured,
    Ticking,
    RescheduleRequested,
    PresentationFailed,
    AwaitingCallback,
    Scheduled,
    RetryScheduled,
    Parked,
    Closed,
}

pub(super) fn admit_draw(frame_loop: FrameLoop, redraw_requested: &mut bool) -> bool {
    match frame_loop {
        FrameLoop::Unconfigured => {
            // GPUI can produce a scene before the first configure. Retain the
            // request so the first legal frame submits it even if nothing changed.
            *redraw_requested = true;
            false
        }
        FrameLoop::Closed => false,
        _ => true,
    }
}

pub(super) fn schedule_frame(frame_loop: &Cell<FrameLoop>, wake: impl FnOnce()) {
    match frame_loop.get() {
        FrameLoop::Parked => {
            frame_loop.set(FrameLoop::Scheduled);
            wake();
        }
        FrameLoop::Ticking => frame_loop.set(FrameLoop::RescheduleRequested),
        // A wake is already owned, or this surface may not draw.
        _ => {}
    }
}

// Registration is injected, not the scheduler: production supplies calloop's result.
pub(super) fn schedule_retry(
    frame_loop: &Cell<FrameLoop>,
    register: impl FnOnce() -> bool,
    wake: impl FnOnce(),
) {
    frame_loop.set(FrameLoop::RetryScheduled);
    if !register() && frame_loop.get() == FrameLoop::RetryScheduled {
        // A failed insertion owns no timer. Transfer that wake to the shared ping;
        // Scheduled coalesces subsequent redraw requests until dispatch.
        frame_loop.set(FrameLoop::Scheduled);
        wake();
    }
}

#[cfg(test)]
mod retry_tests {
    use super::*;

    #[test]
    fn failed_registration_arms_one_dispatchable_wake() {
        let state = Cell::new(FrameLoop::Ticking);
        let wakes = Cell::new(0);
        schedule_retry(&state, || false, || wakes.set(wakes.get() + 1));
        assert_eq!(state.get(), FrameLoop::Scheduled);
        assert_eq!(wakes.get(), 1);
        for _ in 0..4 {
            schedule_frame(&state, || wakes.set(wakes.get() + 1));
        }
        assert_eq!(state.get(), FrameLoop::Scheduled);
        assert_eq!(wakes.get(), 1);
    }

    #[test]
    fn requests_preserve_compositor_pacing_and_terminal_states() {
        for value in [
            FrameLoop::Unconfigured,
            FrameLoop::AwaitingCallback,
            FrameLoop::PresentationFailed,
            FrameLoop::RetryScheduled,
            FrameLoop::Closed,
        ] {
            let state = Cell::new(value);
            schedule_frame(&state, || panic!("must not create another wake"));
            assert_eq!(state.get(), value);
        }
        let state = Cell::new(FrameLoop::Ticking);
        schedule_frame(&state, || panic!("tick completion owns the wake"));
        assert_eq!(state.get(), FrameLoop::RescheduleRequested);
        let state = Cell::new(FrameLoop::Parked);
        let wakes = Cell::new(0);
        schedule_frame(&state, || wakes.set(wakes.get() + 1));
        assert_eq!(state.get(), FrameLoop::Scheduled);
        assert_eq!(wakes.get(), 1);
    }

    #[test]
    fn preconfigure_draw_is_latched_for_the_first_configured_frame() {
        let mut redraw = false;
        assert!(!admit_draw(FrameLoop::Unconfigured, &mut redraw));
        assert!(redraw, "GPUI may already consider the skipped scene drawn");
        assert!(admit_draw(FrameLoop::Ticking, &mut redraw));
        let mut redraw = false;
        assert!(!admit_draw(FrameLoop::Closed, &mut redraw));
        assert!(!redraw, "closed windows must not be revived");
    }

    #[test]
    fn accepted_retry_keeps_timer_ownership() {
        let state = Cell::new(FrameLoop::PresentationFailed);
        schedule_retry(&state, || true, || panic!("timer already owns the wake"));
        assert_eq!(state.get(), FrameLoop::RetryScheduled);
    }
}
