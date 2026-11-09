# Browser Stop investigation

## Observations
The new browser test samples the stock clock immediately after a click, before awaiting the asynchronous Stop response. It observed 09:30:08 then 09:30:10. HTTP freeze acceptance tests pass. Existing browser Stop tests wait for the Stopped status first. macOS, Node/Playwright with Chrome, Python 3.11.9.

## Hypotheses
1. Root hypothesis: click completion does not imply Stop HTTP completion. Supports: the new test omits the existing Stopped wait. Test: log the status after click, then await the public Stopped indicator before sampling.
2. Server continues advancing after Stop. Conflicts: HTTP acceptance tests confirm frozen session and book. Test: compare repeated stopped HTTP states.
3. A stale in-flight poll overwrites Stop temporarily. Possible due to concurrent fetches. Test: inspect post-click status and later clock after awaiting Stop; add delayed-poll regression if needed.

## Experiment
Log post-click status, await Stopped, then run the original clock freeze assertion. No production change.

## Root cause and fix
Confirmed: the diagnostic logged Running immediately after the click. Waiting for the existing Stopped status before sampling made the freeze assertion pass. The test now waits for that observable state; diagnostic logging was removed. HTTP freeze tests independently pass.

## Extreme speed validation
Review reproduced OverflowError from math.isfinite on a 401-digit integer. A regression reproduced the exception. Numeric type checks followed by bounded comparisons now reject huge integers, infinities and NaN without a float conversion, preserving the HTTP 400 contract.

## Review timing regressions
- Confirmed: changing the denominator of total_elapsed / refresh_interval accelerated quote noise late in the day. The regression observed a 167-share jump over 0.4 simulated seconds. Session phases now use stable refresh periods (opening/closing 2s, regular 8s, midday 10s, pre-open 20s); depth/spread/volume still follow their smooth curves. The regression passes.
- Confirmed: advancing a final-minute session by 60 - 5e-10 seconds finalized the candle while metadata remained 15:59:59 / closing. Close finalization now snaps engine and candle elapsed time to the exact closing boundary. The regression passes.

## Delayed-poll investigation
The existing browser request path allows a GET begun before Stop to apply its old running payload after Stop completes. Added a black-box browser test that holds the old response and gates fresh polls, then releases it after the Stopped indicator appears. A failure means stale responses can roll the UI backwards. The intended fix is a request-generation guard and suppression of polling during control requests.

## Delayed-poll result and fix
Confirmed: releasing the held GET after Stop restored Running in the UI. A generation guard now rejects old responses and polling is suppressed during control requests. The browser regression passes for stopped state and clock. Extending it to candle counts exposed consumed-but-discarded bars (1 visible vs 3 expected). Stop now includes recent history; the UI merges/deduplicates that history while preserving older loaded bars. The complete delayed-poll regression passes.

## Overtaken-Start recovery
Follow-up review and a dedicated browser regression confirmed that a pre-Start GET forwarded after the new run began consumed new-run candles. The next fresh poll now requests history after any superseded response settles and merges/deduplicates it. The regression holds the old request before forwarding, starts a new closing session, then verifies that the next poll recovers history.
