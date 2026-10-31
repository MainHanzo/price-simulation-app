# Browser acceptance tests

Start the API at `http://127.0.0.1:8000` with an open simulation session and run the Angular development server at `http://127.0.0.1:4200`. Then, from `frontend/`, run:

```sh
rtk npm run test:browser
```

The saved tests use Node's test runner and Playwright with installed Google Chrome. They resolve a local `playwright` package first, then the bundled Codex runtime package. Set `PLAYWRIGHT_MODULE` to a Playwright package path when using another runtime. Set `FRONTEND_URL` if the development server uses another address. Outside Codex, install Playwright in the test environment and provide Google Chrome.

The first case exercises the real API, including live snapshots and desktop/mobile layout. The remaining cases intercept HTTP/SSE at the browser boundary to reproduce loading, disconnection, stale data, closed sessions, server restart and ticker races. No application internals are invoked.
