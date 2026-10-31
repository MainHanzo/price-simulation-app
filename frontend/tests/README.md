# Browser acceptance tests

Start the API at `http://127.0.0.1:8000` with an open simulation session and run the Angular development server at `http://127.0.0.1:4200`. Then, from `frontend/`, run:

```sh
rtk npm run test:browser
```

The saved tests use Node's test runner and Playwright with installed Google Chrome. They resolve a local `playwright` package first, then the bundled Codex runtime package. Set `PLAYWRIGHT_MODULE` to a Playwright package path when using another runtime. Set `FRONTEND_URL` if the development server uses another address. Outside Codex, install Playwright in the test environment and provide Google Chrome.

The first case exercises the real API, including live snapshots and desktop/mobile layout. The remaining cases intercept HTTP/SSE at the browser boundary to reproduce loading, disconnection, stale data, closed sessions, server restart and ticker races. No application internals are invoked.

The hosted-path case serves the actual local app with `<base href="/price-generator/">` at `/price-generator/`, forwards its assets to the development server, and intercepts API responses. It verifies that configuration, history, parameter updates and the order-book stream all use the hosted origin and path prefix, including the default same-origin session cookie behavior. It requires no hosted credentials.

Hosted builds use the document base path for API URLs. Build with `rtk npm run build -- --base-href /price-generator/` to request `/price-generator/api/...` on the same origin. Root-path development on `localhost`, `127.0.0.1` or `::1` retains the API fallback at `http://127.0.0.1:8000`.
