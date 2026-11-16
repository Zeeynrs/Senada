# Musical listening streak

Use the user's selected glowing-vinyl concept on the Stats page. Keep one original
record-and-sound-wave identity across six stages: 1, 7, 30, 100, 200 and 500 days.
Higher stages gain orbits, sound waves and highlights, rather than changing to an
unrelated symbol. Render natively in QML so the emblem stays sharp at any scale.

The emblem is dormant until a qualifying listen is made today, even if yesterday's
streak remains connected. Its silhouette still reflects the current streak while
dormant. The current streak and personal best remain separate; switching the stats
period does not change the streak. Skipping a full day breaks the current streak.

Use the existing qualification rule: 30 seconds of actual playback, or half of a
shorter song. Seeks and paused time do not qualify. Activate during playback, without
waiting for a song change. Track qualified listening days separately from completed
play records, preserving existing statistics/scrobbling behavior and history.
Refresh at local midnight. Store daily qualification locally so restarting does
not extinguish a day already earned. Count a new day's playback separately when a
song crosses midnight.

Replace the small fifth statistics tile with a dedicated, responsive streak card.
Include the day count, current stage, today's state, personal best and next milestone.
Support both themes and Indonesian/English. Keep animations finite and subtle.

Alternatives: a musical-note character would give the app a mascot identity; a
generic flame would be familiar but less specific to music. The user selected the
glowing vinyl record. No generated raster assets or runtime dependencies are needed.
