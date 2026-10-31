# Browser verification investigations

## Observations

The first live API browser run rendered correct two-sided depth and layout, but the no-horizontal-scroll assertion failed immediately after resizing from desktop to mobile. A fresh mobile page did not overflow. Two additional regression tests reproduced rejected lower stream sequences after a server restart and a simulation clock rewind when the book became stale.

## Hypotheses

1. Chart.js retains its desktop canvas width briefly during responsive resizing. Supported by the desktop-to-mobile-only failure; test by inspecting overflowing elements before and after resize settles.
2. The book columns have a fixed minimum width. Conflicts with the fresh-mobile success; inspect overflowing elements.
3. The search input or parameter overlay has a fixed width. Conflicts with the fresh-mobile success; inspect overflowing elements.

## Experiments

A browser DOM measurement immediately after resizing reported a 932px document at a 390px viewport. The sole overflowing element was the canvas (874px width, right edge 932px). At 100ms and 500ms, document width was 390px and no elements overflowed. This confirms hypothesis 1 and rejects 2 and 3.

The restart regression used a REST sequence of 100 followed by a fresh stream connection with sequence 2 and a different reference price; the UI never accepted the new price. The clock regression observed fewer than five elapsed simulation seconds after 6.5 real seconds without snapshots. Both failed before fixes.

## Root cause and fixes

Limit the chart canvas to its parent width while Chart.js processes responsive resizing. Scope sequence ordering to each stream connection, resetting its baseline on open. Apply clock synchronization only for a newly received snapshot, while history merging and status-only updates reuse its price without resetting time.
