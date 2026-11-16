# Liquid Glass Implementation Plan

**Goal:** Add a selectable, persistent native Liquid Glass appearance.
**Architecture:** Shared artwork/ambient backdrop, reusable GlassSurface with
an optional precompiled refraction shader, existing settings storage.
**Tech stack:** Python, PySide6, Qt Quick, GLSL baked with Qt Shader Baker.
**Spec:** `docs/superpowers/specs/2026-11-16-liquid-glass-design.md`

## Constraints and review focus

- Existing off, cover, desktop and color-mode settings retain their behavior.
- No new runtime dependencies; include shader source and portable QSB asset.
- Missing artwork, software rendering, narrow layouts and mode changes must work.
- Verify opacity controls, persistence, Indonesian strings and packaging of assets.

## Tasks

- [x] Test session acceptance, persistence and mode switching in `tests/test_glass.py`.
  Run `python -m unittest tests.test_glass` before and after adding the mode.
- [x] Add `liquid` in `senada/session.py`, settings UI and Indonesian translations.
- [x] Add `qml/GlassBackdrop.qml`, `qml/GlassSurface.qml`, shader source/QSB and
  theme tokens. Register components in `qml/qmldir`.
- [x] Apply material and rounded layout to AppShell, navigation, player and settings;
  add lightweight material to shared controls.
- [x] Run all offline unit tests and QML rendering checks; inspect screenshots.
  Document activation and shader rebuilding in `docs/GUIDE.md`.

Execution is inline in the current workspace.

## Verification record

Preference tests failed before the mode was added and passed afterward. The full
suite passed (231 tests). The new rendering test runs Qt software rendering in
a separate process and checks rounded corners, finite radii, opacity, light/dark
and mode changes. Full application renders were inspected with OpenGL and software,
at 1280×800 and 900×600, in light/dark, with idle/artwork backdrops and mode switching.
The short-window sidebar tree scrolls so Settings remains reachable.

A final independent code review found no important correctness or regression
issues. Shader source rebakes to the bundled portable shader pack. `git diff
--check` passes. Existing suite ResourceWarnings and existing QML lint warnings
about context properties/singleton resolution remain; runtime render logs are clean.
