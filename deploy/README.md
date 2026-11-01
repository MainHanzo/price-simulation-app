# Market Lab deployment and rollback

Production: https://d1duii6i44ll6h.cloudfront.net/price-generator/
CloudFront distribution ENRZ6SL6BBJ3U routes /price-generator* to the dedicated
price-generator service on port8002 of i-02612abe30163f72c (us-east-2).
Ticker-info remains on8000; its S3 frontend and authentication are unchanged.

The active application is server.py + price_generator/ + web/. It restores the
original Market Lab design and anonymous OHLCV models. Do not deploy the retired
Angular/FastAPI prototype as the current simulator.

## Build

```sh
uv run python -m pytest -q
node --test tests/browser/marketlab.test.mjs
docker build -f deploy/Dockerfile -t price-generator:<commit> .
```

The container uses Python3.11.9, the standard-library HTTP server, and a nonroot
user. Its context needs server.py, price_generator/, web/, and deploy/Dockerfile.
No Angular bundle or exported pip requirements are needed.

## Hosted settings

- HOST=0.0.0.0, PORT=8002, BASE_PATH=/price-generator are image defaults.
- REQUIRE_AUTH=1 makes missing AUTH_SESSION_URL fail startup.
- AUTH_SESSION_URL=https://d1duii6i44ll6h.cloudfront.net/v1/auth/session
  validates existing ticker-info cookies/bearer credentials. Authentication
  failure denies API/assets; the root serves the original sign-in page.
- RELEASE_SHA=<commit> is returned by /price-generator/health.
- The simulation uses elapsed synthetic time, with Start/Stop and the original
  asset/model/interval controls. There are no named-instrument API parameters,
  New York clock, or market-hours gates in this application.

## Stage and release

Stage a source archive in s3://ticker-info-bucket/price-generator-releases/.
Use an operator-issued short-lived presigned download for the SSM instance;
its role cannot directly read this release prefix. Keep signed URLs out of
console output and exclude credentials/caches from archives.
Build under /opt/price-generator-releases/<commit>/.

Run the candidate bound to127.0.0.1:18002:8002 with the hosted settings. Verify:

```sh
python3 tests/deployment_smoke.py \
  --base-url http://127.0.0.1:18002/price-generator \
  --release <commit> --auth-container quant-api
```

The smoke checks use the existing service token only in memory. They verify
sign-in, protected endpoints, original UI, random simulation, chart-aligned
anonymous depth, Start/Stop, and absence of instrument lookup routes.

Save the current systemd unit before switching only price-generator.service
and repeat the smoke check against the CloudFront URL. CloudFront caching is
already disabled for this route. Do not change its routing, security groups,
IAM roles, ticker-info container, or authentication secrets.

## Rollback

The untouched original standalone application remains at /opt/price-generator/.
Its systemd unit is saved at
/opt/price-generator-releases/price-generator.service.before-container.
Stop price-generator, restore that unit to/etc/systemd/system/price-generator.service,
run systemctl daemon-reload and start price-generator. For later container
releases, retain a per-release previous unit to restore the earlier image.
