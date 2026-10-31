# Existing CloudFront deployment

The production route is `https://d1duii6i44ll6h.cloudfront.net/price-generator/`.
CloudFront distribution `ENRZ6SL6BBJ3U` routes `/price-generator*` to port 8002
on `i-02612abe30163f72c` in `us-east-2`. The ticker-info API remains on port
8000 and its frontend remains in S3. Deploy only the dedicated price-generator
service; CloudFront routing and ticker-info authentication stay in place.

## Build a release

```sh
uv sync --frozen
uv run python -m pytest -q
uv export --frozen --no-dev --no-emit-project --output-file deploy/requirements.txt
cd frontend
npm ci
npm run build -- --base-href /price-generator/
```

The Docker build context must contain `app/`, `deploy/Dockerfile`,
`deploy/login.html`, the generated `deploy/requirements.txt`, and
`frontend/dist/frontend/browser/`. Exclude caches and local environment files.
Build with `docker build -f deploy/Dockerfile -t price-generator:<commit> .`.
The exported requirements retain the lockfile's versions and hashes.

## Hosted configuration

- Entrypoint: `app.hosted:application`; one worker, port 8002.
- `BASE_PATH=/price-generator` (default).
- `AUTH_SESSION_URL=https://d1duii6i44ll6h.cloudfront.net/v1/auth/session`
  is required. Missing configuration prevents startup; unavailable authentication
  returns 503. Cookie and bearer credentials are forwarded only to that service.
- `RELEASE_SHA=<commit>` identifies the running release in the public
  `/price-generator/health` response.
- `STATIC_DIR=/srv/static` and `LOGIN_PAGE_PATH=/srv/deploy/login.html` are set
  by the image. The login page preserves ticker-info's existing `/v1/auth/login`
  flow and its HttpOnly session cookie.
- `SIMULATION_DT` is optional; the original default simulated session is retained.

## Stage, verify, and switch

Upload the code/build archive under
`s3://ticker-info-bucket/price-generator-releases/<commit>.tar.gz`, then use the
existing instance's SSM access to download and build it under
`/opt/price-generator-releases/<commit>/`. Keep this archive free of credentials.

Run a candidate container bound to `127.0.0.1:18002:8002` with the hosted
configuration above. Before switching, run:

```sh
python3 tests/deployment_smoke.py \
  --base-url http://127.0.0.1:18002/price-generator \
  --release <commit> --auth-container quant-api
```

The smoke test reads the existing ticker-info service token into memory on the
instance, never prints it, and exercises only external HTTP interfaces. The
default simulated session must still be open for the two-update streaming check.

Keep the previous `/etc/systemd/system/price-generator.service` as
`/opt/price-generator-releases/price-generator.service.before-container` before
the first container deployment. Stop only `price-generator.service`, install the
container service with the verified image, and start it on port 8002. Retain
`/opt/price-generator/` unchanged as the original application rollback.
Repeat the smoke test against the CloudFront URL and verify the UI in a browser
with an existing ticker-info session. No CloudFront invalidation is normally
needed: the existing price-generator behavior disables caching.

## Rollback

Stop the candidate service, restore the saved systemd unit, run
`systemctl daemon-reload`, then start `price-generator.service` again. Its old
source and login integration remain at `/opt/price-generator/`. For subsequent
container releases, save the current unit before switching and restore that unit
to return to the prior immutable image. Do not restart ticker-info or change its
secrets during a price-generator release.
