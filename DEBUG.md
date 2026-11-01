# Restored Market Lab browser release check

## Observations
- Hosted release 9906b5a passes authenticated API smoke checks; state includes aligned order_book.
- Existing Chrome session renders restored controls/chart and the new panel, but panel stays Ready to start even while the simulation runs.
- Four fresh-browser acceptance checks pass locally.

## Hypotheses
### H1: Existing browser retains original app.js (ROOT HYPOTHESIS)
- Supports: original script URL app.js is reused; original controls work while new book hook does not.
- Conflicts: reload was performed, but that can revalidate cached files.
- Test: hard reload the same browser without changing application state.
### H2: Hosted image contains old app.js
- Supports: hosted-only symptom.
- Conflicts: source archive comes from verified commit and includes new script.
- Test: inspect running container script for the renderer.
### H3: New renderer throws during polling
- Supports: panel does not update.
- Conflicts: same script passes fresh-browser tests and chart keeps updating.
- Test: inspect browser error logs, then compare hard-reload behavior.

## Experiments
- Browser error log contains no application errors. Keyboard hard reload did not produce an authenticated app.js request in the service journal, so it did not disprove caching.
- Running container app.js/index.html SHA256 hashes match the verified source exactly, rejecting H2.
- Service journal shows no authenticated unversioned app.js request after HTML refresh. A direct versioned script request reached the service and returned 200, confirming the resource URL controls whether a fresh script is requested.
- Public HTTP regression test rejects reuse of the previous unversioned script and checks the new resource loads. Both root and hosted-prefix cases fail before the fix.

## Root Cause
Existing browsers retained the original unversioned app.js while loading the new HTML panel.

## Fix
Give the changed script a content-version query in the HTML. This keeps the existing interface unchanged while making the browser request the new code. Repeat public HTTP, browser, and hosted acceptance checks after publishing.
