# Musical Streak Implementation Plan

**Goal:** A music-themed streak emblem that lights up for today's qualifying
listening and evolves at 1/7/30/100/200/500 days.
**Architecture:** Persist qualified days independently of completed plays. Emit
per-song, per-day listening progress from PlayTracker; expose today's state in
Stats.summary. Draw a reusable native emblem and display it in a responsive card.
**Tech stack:** Python, SQLite, PySide6, QML Canvas.
**Spec:** `docs/superpowers/specs/2026-11-16-music-streak-design.md`

- [x] Add failing tests for dormant-yesterday/active-today, persistence, seek/pause
  exclusion, live qualification, midnight and existing history.
- [x] Add per-day progress to `senada/plays.py` without changing finished events.
- [x] Add qualified-day storage and today's state in `senada/stats.py`, including
  midnight refresh and graceful behavior when statistics are unavailable.
- [x] Add `qml/StreakEmblem.qml` and `qml/StreakCard.qml`; register them in qmldir,
  replace the fifth Stats tile, and add bilingual copy and unreleased notes.
- [x] Render dormant/active and milestone variants, inspect narrow/light/dark
  layouts, run all tests and review the complete diff.

Keep the existing local player-controls trial intact. Do not publish a new release.

## Verification record

All 243 tests pass. New tests cover live daily qualification, pause/seek/skip
exclusion, short songs, restart persistence, period independence, broken streaks,
legacy database migration and both sides of a midnight-crossing update.
The QML test checks evolution boundaries, lit/dormant rendering, artwork bounds
and compact layouts. Actual full-app captures were inspected at 1280×800 and
900×600, including light/dark and software/OpenGL rendering.

An isolated full-app probe verified that the Stats card stays dormant at 29 seconds,
activates at 30 seconds and becomes dormant after local midnight while retaining the
connected day count. Independent review found two midnight-accounting cases;
regression tests now cover both, and the reviewer confirmed the fixes.

The legacy date import happens once, transactionally. Completed plays and
qualified daily listening remain separate so a song spanning two days cannot
award a day which did not meet its own listening threshold.
