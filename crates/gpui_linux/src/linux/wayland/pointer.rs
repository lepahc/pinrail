//! Pointer/IME targeting shared by the real button dispatcher and offscreen tests.

pub(super) fn ime_target<T>(
    keyboard: Option<T>,
    pointer: &T,
    same: impl FnOnce(&T, &T) -> bool,
) -> Option<T> {
    keyboard.filter(|keyboard| same(keyboard, pointer))
}

pub(super) fn press_position<T, P>(
    original: &T,
    current: Option<&T>,
    position: Option<P>,
    same: impl FnOnce(&T, &T) -> bool,
    accepts_input: impl FnOnce(&T) -> bool,
) -> Option<P> {
    if !same(original, current?) || !accepts_input(original) {
        return None;
    }
    position
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;

    #[test]
    fn press_only_resets_composition_in_the_pointer_target() {
        assert_eq!(ime_target(Some(1), &2, |a, b| a == b), None);
        assert_eq!(ime_target(None, &2, |a, b| a == b), None);
        assert_eq!(ime_target(Some(2), &2, |a, b| a == b), Some(2));
    }

    #[test]
    fn reentrant_retarget_does_not_deliver_or_change_click_state() {
        let original = 1;
        let mut target = Some(1);
        let mut position = Some((10, 20));
        let clicks = Cell::new(0);
        let mut callback = || {
            target = Some(2);
            position = Some((30, 40));
        };
        callback();
        if press_position(
            &original,
            target.as_ref(),
            position,
            |a, b| a == b,
            |_| true,
        )
        .is_some()
        {
            clicks.set(clicks.get() + 1);
        }
        assert_eq!(clicks.get(), 0);
    }

    #[test]
    fn closed_or_blocked_target_rejects_continuation() {
        assert_eq!(
            press_position(&1, Some(&1), Some(20), |a, b| a == b, |_| false),
            None
        );
    }

    #[test]
    fn lost_focus_or_position_rejects_continuation() {
        assert_eq!(
            press_position(&1, None, Some(20), |a, b| a == b, |_| true),
            None
        );
        assert_eq!(
            press_position(&1, Some(&1), None::<i32>, |a, b| a == b, |_| true),
            None
        );
    }

    #[test]
    fn continuation_uses_current_position_not_the_pre_callback_position() {
        let position = Cell::new(Some(10));
        let callback = || position.set(Some(20));
        callback();
        assert_eq!(
            press_position(&1, Some(&1), position.get(), |a, b| a == b, |_| true),
            Some(20)
        );
    }
}
