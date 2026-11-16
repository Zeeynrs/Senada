# Player controls trial

**Goal:** Try the preferred icon layout from the two interactive mockups.

**Design:** Keep Lyrics, Queue, mute, the volume slider and Full screen directly
available. Move Sleep timer, Equalizer & Audio Effects, Devices and Mini player
into a More controls menu. Show a dot and the timer status on More controls when
the sleep timer is running. Separate panel controls from volume with a hairline.
Use modest spacing and keep the transport clear at the 900 px minimum width.

**Scope:** A reversible local UI trial. Keep the existing audio/device popups,
timer choices and keyboard shortcuts. Do not publish a release for this trial.

**Implementation:**

- [x] Simplify the right-hand controls in `qml/PlayerBar.qml` and reuse existing
  popups; position popups after the menu closes.
- [x] Let `SleepTimerButton.qml` open its existing menu from a supplied anchor.
- [x] Add English/Indonesian text and an unreleased changelog entry.
- [x] Check actual QML rendering and interactions at 1280×800 and 900×600,
  including timer status, audio/device popups, volume, and light/dark themes.
- [x] Run `python -m unittest discover -s tests` and `git diff --check`.

Use direct UI interaction and geometry checks for this low-impact layout change;
retain the existing automated tests for audio and timer behavior.

## Verification

All 232 tests pass. A temporary isolated full-app probe drove actual mouse input
through Lyrics/Queue toggles, More controls, the audio and device popups, timer
selection/status, mute/unmute and volume adjustment. Geometry checks at 1280×800
and 900×600 confirmed that tools and transport do not overlap. Both OpenGL and
software rendering passed, including light/dark theme changes.

The device list was found to exceed short windows with many outputs. It now
scrolls inside a height limit derived from the space above the player bar.
The controls are ready for evaluation in the app.
