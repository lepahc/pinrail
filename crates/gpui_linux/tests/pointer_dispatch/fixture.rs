// Type stand-ins for the exact-source dispatcher harness. No native connection,
// protocol decoding, real dialog, renderer, or IME implementation is constructed.
// Blocked means the admission result of a blocking child (or closed window).
// Cursor effects deliberately panic: these cases must never take that path.
#![allow(dead_code)]
use std::{
    cell::{Cell, RefCell},
    rc::Rc,
    time::{Duration, Instant},
};
extern crate self as collections;
pub use std::collections::HashMap;
mod pointer {
    /* PRODUCTION_POINTER_HELPERS */
}
mod serial {
    /* PRODUCTION_SERIAL_TRACKER */
}
use serial::{SerialKind, SerialTracker};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum NavigationDirection {
    Back,
    Forward,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum MouseButton {
    Left,
    Right,
    Middle,
    Navigate(NavigationDirection),
}
#[derive(Clone, Copy, Debug, PartialEq)]
struct Point {
    x: f32,
    y: f32,
}
fn px(value: f32) -> f32 {
    value
}
fn point(x: f32, y: f32) -> Point {
    Point { x, y }
}
#[derive(Clone, Copy)]
enum WEnum<T> {
    Value(T),
}
mod wl_pointer {
    use super::WEnum;
    #[derive(Clone, Copy, PartialEq, Eq)]
    pub enum ButtonState {
        Pressed,
        Released,
        Other,
    }
    pub enum Event {
        Motion {
            surface_x: f64,
            surface_y: f64,
        },
        Button {
            serial: u32,
            button: u32,
            state: WEnum<ButtonState>,
        },
    }
}
#[derive(Debug, PartialEq)]
struct MouseDownEvent {
    button: MouseButton,
    position: Point,
    modifiers: (),
    click_count: usize,
    first_mouse: bool,
}
#[derive(Debug, PartialEq)]
struct MouseUpEvent {
    button: MouseButton,
    position: Point,
    modifiers: (),
    click_count: usize,
}
#[derive(Debug, PartialEq)]
struct MouseMoveEvent {
    position: Point,
    pressed_button: Option<MouseButton>,
    modifiers: (),
}
#[derive(Debug, PartialEq)]
enum PlatformInput {
    MouseDown(MouseDownEvent),
    MouseUp(MouseUpEvent),
    MouseMove(MouseMoveEvent),
}
#[derive(Debug, PartialEq)]
enum ImeInput {
    UnmarkText,
    InsertText(String),
}
#[derive(Clone)]
struct Window(Rc<WindowInner>);
#[derive(Default)]
struct WindowInner {
    blocked: Cell<bool>,
    events: RefCell<Vec<PlatformInput>>,
    ime_events: RefCell<Vec<ImeInput>>,
    ime: RefCell<Option<Box<dyn FnMut()>>>,
}
impl Window {
    fn new() -> Self {
        Self(Rc::new(WindowInner::default()))
    }
    fn is_blocked(&self) -> bool {
        self.0.blocked.get()
    }
    fn ptr_eq(&self, other: &Self) -> bool {
        Rc::ptr_eq(&self.0, &other.0)
    }
    // Production WaylandWindowState::handle_input also rejects blocked windows.
    fn handle_input(&self, event: PlatformInput) {
        if !self.is_blocked() {
            self.0.events.borrow_mut().push(event);
        }
    }
    fn handle_ime(&self, input: ImeInput) {
        self.0.ime_events.borrow_mut().push(input);
        let callback = self.0.ime.borrow_mut().take();
        if let Some(mut callback) = callback {
            callback();
        }
    }
    fn primary_output_scale(&self) -> f32 {
        panic!("cursor path outside probe")
    }
}
#[derive(Clone, Copy, PartialEq, Eq)]
enum CursorStyle {
    Arrow,
}
struct Cursor;
impl Cursor {
    fn set_icon(&mut self, _: &(), _: u32, _: (), _: f32) {
        panic!("cursor path outside probe")
    }
}
struct CursorShapeDevice;
impl CursorShapeDevice {
    fn set_shape(&self, _: u32, _: ()) {
        panic!("cursor path outside probe")
    }
}
fn to_shape(_: CursorStyle) {
    panic!("cursor path outside probe")
}
fn cursor_style_to_icon_names(_: CursorStyle) {
    panic!("cursor path outside probe")
}
#[derive(Default)]
struct Compose {
    resets: usize,
}
impl Compose {
    fn reset(&mut self) {
        self.resets += 1;
    }
}
struct ClickState {
    last_click: Instant,
    last_mouse_button: Option<MouseButton>,
    last_location: Point,
    current_count: usize,
}
struct State {
    serial_tracker: SerialTracker,
    mouse_focused_window: Option<Window>,
    keyboard_focused_window: Option<Window>,
    composing: bool,
    text_input: Option<()>,
    pre_edit_text: Option<String>,
    compose_state: Option<Compose>,
    mouse_location: Option<Point>,
    click: ClickState,
    button_pressed: Option<MouseButton>,
    modifiers: (),
    enter_token: Option<()>,
    cursor_style: Option<CursorStyle>,
    cursor_shape_device: Option<CursorShapeDevice>,
    wl_pointer: Option<()>,
    cursor: Cursor,
    ime_resets: usize,
}
impl State {
    fn restore_cursor_after_hide(&mut self) {}
}
struct Client(Rc<RefCell<State>>);
impl Client {
    fn get_client(&self) -> Rc<RefCell<State>> {
        self.0.clone()
    }
    fn disable_ime(&self) {
        let mut state = self.0.borrow_mut();
        state.composing = false;
        state.ime_resets += 1;
    }
    fn enable_ime(&self) {}
}
// Click timing/distance are not under test; fixtures always start without a
// preceding click. These stand-ins must not be used to claim multi-click proof.
fn is_within_click_distance(a: Point, b: Point) -> bool {
    a == b
}
const DOUBLE_CLICK_INTERVAL: Duration = Duration::from_millis(400);
/* PRODUCTION_BUTTON_MAPPING */
mod runtime {
    use super::*;
    pub(super) fn dispatch(this: &mut Client, event: wl_pointer::Event) {
        /* PRODUCTION_PRELUDE */
        match event {
/* PRODUCTION_ARMS */
        }
    }
}

#[cfg(test)]
mod regression {
    use super::*;
    use wl_pointer::ButtonState::{Pressed, Released};

    fn fixture() -> (Client, Window) {
        let window = Window::new();
        let state = State {
            serial_tracker: SerialTracker::new(),
            mouse_focused_window: Some(window.clone()),
            keyboard_focused_window: Some(window.clone()),
            composing: false,
            text_input: None,
            pre_edit_text: None,
            compose_state: None,
            mouse_location: Some(point(10.0, 20.0)),
            click: ClickState {
                last_click: Instant::now(),
                last_mouse_button: None,
                last_location: point(0.0, 0.0),
                current_count: 0,
            },
            button_pressed: None,
            modifiers: (),
            enter_token: Some(()),
            cursor_style: None,
            cursor_shape_device: None,
            wl_pointer: None,
            cursor: Cursor,
            ime_resets: 0,
        };
        (Client(Rc::new(RefCell::new(state))), window)
    }
    fn button(client: &mut Client, state: wl_pointer::ButtonState, serial: u32) {
        runtime::dispatch(
            client,
            wl_pointer::Event::Button {
                serial,
                button: 0x110,
                state: WEnum::Value(state),
            },
        );
    }
    fn motion(client: &mut Client) {
        runtime::dispatch(
            client,
            wl_pointer::Event::Motion {
                surface_x: 30.0,
                surface_y: 40.0,
            },
        );
    }
    fn assert_last_motion(window: &Window, pressed_button: Option<MouseButton>) {
        assert_eq!(
            window.0.events.borrow().last(),
            Some(&PlatformInput::MouseMove(MouseMoveEvent {
                position: point(30.0, 40.0),
                pressed_button,
                modifiers: (),
            }))
        );
    }
    fn arm_ime(client: &Client, compose_fallback: bool) {
        let mut state = client.0.borrow_mut();
        if compose_fallback {
            state.pre_edit_text = Some("composed".into());
            state.compose_state = Some(Compose::default());
        } else {
            state.composing = true;
            state.text_input = Some(());
        }
    }

    #[test]
    fn release_after_blocking_child_does_not_leave_motion_dragging() {
        let (mut client, window) = fixture();
        button(&mut client, Pressed, 17);
        motion(&mut client);
        assert_last_motion(&window, Some(MouseButton::Left)); // Positive control.
        window.0.blocked.set(true); // Dialog opens, with no Leave/Enter.
        button(&mut client, Released, 18);
        assert_eq!(
            window.0.events.borrow().len(),
            2,
            "blocked target must not receive MouseUp"
        );
        assert_eq!(
            client.0.borrow().button_pressed,
            None,
            "release must clear seat state before window admission"
        );
        window.0.blocked.set(false); // Dialog closes, still no Leave/Enter.
        motion(&mut client);
        assert_last_motion(&window, None);
        assert_eq!(
            client
                .0
                .borrow()
                .serial_tracker
                .get(SerialKind::MousePress)
                .as_raw(),
            17
        );
    }

    #[test]
    fn release_without_pointer_target_does_not_leave_motion_dragging() {
        // Exercise missing target independently of missing position.
        for clear_position in [false, true] {
            let (mut client, window) = fixture();
            button(&mut client, Pressed, 17);
            assert_eq!(client.0.borrow().button_pressed, Some(MouseButton::Left));
            client.0.borrow_mut().mouse_focused_window = None;
            if clear_position {
                client.0.borrow_mut().mouse_location = None;
            }
            button(&mut client, Released, 18);
            assert_eq!(
                client.0.borrow().button_pressed,
                None,
                "seat cleanup cannot require a delivery target"
            );
            assert_eq!(window.0.events.borrow().len(), 1);
            client.0.borrow_mut().mouse_focused_window = Some(window.clone());
            motion(&mut client);
            assert_last_motion(&window, None);
        }
    }

    #[test]
    fn ordinary_release_delivers_without_resetting_ime_or_replacing_press_serial() {
        let (mut client, window) = fixture();
        button(&mut client, Pressed, 17);
        arm_ime(&client, false);
        button(&mut client, Released, 18);
        assert_eq!(
            window.0.events.borrow().last(),
            Some(&PlatformInput::MouseUp(MouseUpEvent {
                button: MouseButton::Left,
                position: point(10.0, 20.0),
                modifiers: (),
                click_count: 1,
            }))
        );
        assert_eq!(
            client
                .0
                .borrow()
                .serial_tracker
                .get(SerialKind::MousePress)
                .as_raw(),
            17
        );
        assert_eq!(
            client
                .0
                .borrow()
                .serial_tracker
                .selection_serial()
                .unwrap()
                .as_raw(),
            17
        );
        assert!(client.0.borrow().composing);
        assert_eq!(client.0.borrow().ime_resets, 0);
        assert!(window.0.ime_events.borrow().is_empty());
        motion(&mut client);
        assert_last_motion(&window, None);
    }

    #[test]
    fn blocked_press_records_serial_but_not_ime_or_click_effects() {
        let (mut client, window) = fixture();
        arm_ime(&client, false);
        window.0.blocked.set(true);
        button(&mut client, Pressed, 17);
        assert_eq!(
            client
                .0
                .borrow()
                .serial_tracker
                .get(SerialKind::MousePress)
                .as_raw(),
            17
        );
        assert!(client.0.borrow().composing);
        assert_eq!(client.0.borrow().ime_resets, 0);
        assert_eq!(client.0.borrow().click.current_count, 0);
        assert_eq!(client.0.borrow().button_pressed, None);
        assert!(window.0.events.borrow().is_empty());
        assert!(window.0.ime_events.borrow().is_empty());
    }

    #[test]
    fn press_does_not_reset_a_different_keyboard_editor() {
        for fallback in [false, true] {
            let (mut client, pointer) = fixture();
            let keyboard = Window::new();
            client.0.borrow_mut().keyboard_focused_window = Some(keyboard.clone());
            arm_ime(&client, fallback);
            button(&mut client, Pressed, 17);
            assert_eq!(client.0.borrow().ime_resets, 0);
            assert_eq!(client.0.borrow().click.current_count, 1);
            assert_eq!(pointer.0.events.borrow().len(), 1);
            assert!(pointer.0.ime_events.borrow().is_empty());
            assert!(keyboard.0.ime_events.borrow().is_empty());
            let state = client.0.borrow();
            if fallback {
                assert_eq!(state.pre_edit_text.as_deref(), Some("composed"));
                assert_eq!(state.compose_state.as_ref().unwrap().resets, 0);
            } else {
                assert!(state.composing);
            }
        }
    }

    fn reject_ime_reentry(change: fn(&mut State, &Window)) {
        // Exercise both callbacks: text-input UnmarkText and compose InsertText.
        for fallback in [false, true] {
            let (mut client, window) = fixture();
            arm_ime(&client, fallback);
            let state = client.0.clone();
            let original = window.clone();
            *window.0.ime.borrow_mut() =
                Some(Box::new(move || change(&mut state.borrow_mut(), &original)));
            let last_click = client.0.borrow().click.last_click;
            button(&mut client, Pressed, 17);
            assert_eq!(
                window.0.ime_events.borrow().len(),
                1,
                "callback must be reached"
            );
            let state = client.0.borrow();
            assert_eq!(state.click.current_count, 0);
            assert_eq!(state.click.last_mouse_button, None);
            assert_eq!(state.click.last_location, point(0.0, 0.0));
            assert_eq!(state.click.last_click, last_click);
            assert_eq!(state.button_pressed, None);
            assert!(state.enter_token.is_some());
            assert!(window.0.events.borrow().is_empty());
            if let Some(current) = &state.mouse_focused_window {
                assert!(
                    current.0.events.borrow().is_empty(),
                    "must not retarget the press"
                );
            }
        }
    }
    #[test]
    fn ime_reentry_retarget_rejects_press() {
        reject_ime_reentry(|state, _| state.mouse_focused_window = Some(Window::new()));
    }
    #[test]
    fn ime_reentry_block_rejects_press() {
        reject_ime_reentry(|_, window| window.0.blocked.set(true));
    }
    #[test]
    fn ime_reentry_missing_target_rejects_press() {
        reject_ime_reentry(|state, _| state.mouse_focused_window = None);
    }
    #[test]
    fn ime_reentry_missing_position_rejects_press() {
        reject_ime_reentry(|state, _| state.mouse_location = None);
    }
    #[test]
    fn ime_reentry_same_target_uses_current_position() {
        for fallback in [false, true] {
            let (mut client, window) = fixture();
            arm_ime(&client, fallback);
            let state = client.0.clone();
            *window.0.ime.borrow_mut() = Some(Box::new(move || {
                state.borrow_mut().mouse_location = Some(point(50.0, 60.0))
            }));
            button(&mut client, Pressed, 17);
            assert_eq!(
                window.0.events.borrow().as_slice(),
                &[PlatformInput::MouseDown(MouseDownEvent {
                    button: MouseButton::Left,
                    position: point(50.0, 60.0),
                    modifiers: (),
                    click_count: 1,
                    first_mouse: true,
                })]
            );
            assert_eq!(client.0.borrow().click.last_location, point(50.0, 60.0));
            assert_eq!(client.0.borrow().button_pressed, Some(MouseButton::Left));
            let expected = if fallback {
                ImeInput::InsertText("composed".into())
            } else {
                ImeInput::UnmarkText
            };
            assert_eq!(window.0.ime_events.borrow().as_slice(), &[expected]);
            if fallback {
                assert_eq!(client.0.borrow().compose_state.as_ref().unwrap().resets, 1);
            } else {
                assert_eq!(client.0.borrow().ime_resets, 1);
            }
        }
    }
}
