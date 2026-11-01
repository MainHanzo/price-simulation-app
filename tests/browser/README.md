# Market Lab browser acceptance

Run from the repository root:

```sh
rtk proxy node --test tests/browser/marketlab.test.mjs
```

The tests launch `.venv/bin/python server.py` on a free local port with `/price-generator` as its base path and authentication disabled, then stop that process on completion. They use installed Google Chrome and either a local Playwright package, `PLAYWRIGHT_MODULE`, or the bundled Codex Playwright runtime. No hosted credentials or running development servers are required.

Coverage includes the original asset/model/interval controls and chart styling, the original CSS checksum, Start/Stop, full-width desktop and mobile chart flow, reference-price agreement with the current-bar payload, ten levels per side, and recovery from state-poll errors. Screenshots are saved under `/tmp/marketlab-after-{desktop,mobile}.png`. Before the new panel was added, `CAPTURE_BASELINE=1` saved the matching `/tmp/marketlab-before-{desktop,mobile}.png` files.
