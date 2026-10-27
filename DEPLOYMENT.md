# Public deployment preparation

This repository is prepared for a Render FastAPI service and a Vercel Vite
frontend. No cloud service, hosted database, migration, local data import, or
paid resource has been created by these instructions.

## Pricing and provider constraints checked 2026-10-27

- Render documents that its Free web services are intended for testing and
  hobby use, not production. They sleep after 15 minutes without traffic, use
  an ephemeral filesystem, and Render warns that free services making external
  database/API traffic can be suspended. Review the current
  [Render pricing](https://render.com/pricing) before selecting a paid compute
  plan. `render.yaml` uses the paid `starter` plan (0.5 CPU, 512 MB RAM).
- TiDB Cloud Starter is a MySQL-compatible candidate with a published free
  monthly quota (25 GiB row storage, 25 GiB columnar storage, and 250 million
  request units across eligible instances). Usage beyond the quota is billed;
  this is not an unlimited free database. Starter requires TLS on public
  connections and uses Let's Encrypt certificates. Its MySQL-compatible
  connection, TLS, and quota are documented by
  [PingCAP](https://www.pingcap.com/tidb-cloud-starter/) and the
  [connection guide](https://docs.pingcap.com/tidbcloud/connect-to-tidb-cluster-serverless/).
  Configure the Render service's outbound IP addresses in TiDB's public
  endpoint allowlist, and review current usage pricing before provisioning.
- Vercel Hobby is currently listed at **$0/month** for personal projects, with
  usage limits and HTTPS included. See [Vercel pricing](https://vercel.com/pricing).

TiDB Cloud Starter is the current low-cost recommendation, not an already
selected or provisioned database. The application still requires the database
TLS root certificate to be mounted as a Render Secret File at
`/etc/secrets/mysql-ca.pem`; TiDB documents its Let's Encrypt trust chain and
provides the official ISRG Root X1 certificate. Confirm persistence, the
account's current quota and overage pricing, and Render outbound-IP allowlist
settings before creating the database. Do not expose local XAMPP.

## Model build

Render builds the model once per deployment with
`python -m scripts.build_model`. The command downloads the documented CSV to a
temporary directory, checks its pinned SHA-256, applies the existing
stratified TF-IDF + Logistic Regression training pipeline, and writes the
artifact under `backend/models/` plus an evaluation report under
`backend/reports/`. The temporary dataset is deleted when the build exits.
This build command does not connect to MariaDB or run migrations. The model
health check loads the generated local artifact; requests do not retrain.

The training corpus is declared LGPL-3.0 by its Hugging Face mirror and is a
direct copy of a Kaggle dataset; review the attribution/license notes in
`data/README.md` before public deployment. The model artifact is generated from
that checksum-verified source; it is not downloaded from an unverified binary
source.

## Render service

`render.yaml` defines the FastAPI service. Import the GitHub repository
`dhanu-2505/Phish-Shift` in Render and review the Blueprint diff before applying
it. Applying the Blueprint creates a paid Starter service; do not confirm it
until you approve the current price in Render's dashboard. The source branch is
`main`. The build command trains/provisions the model; the start command binds
to Render's `$PORT`. `/health/ready` checks both the database and model.

Set these values privately in Render. The Blueprint generates the session
secret on Render; do not replace it with a local development secret:

- `DB_HOST`, `DB_PORT`, `DB_USER`, and `DB_PASSWORD`: the hosted MySQL
  connection values, never local `127.0.0.1`.
- `DB_NAME`: `phishshift_db`, created on the hosted database as a new,
  separate database. Local MariaDB is not touched.
- `DB_SSL_CA`: mount the provider's trusted CA certificate as Render Secret
  File `/etc/secrets/mysql-ca.pem` (for TiDB Cloud Starter, use the official
  ISRG Root X1 PEM). The app verifies the TLS certificate and server identity.
  Do not disable this verification.
- `FRONTEND_ORIGINS`: the exact HTTPS Vercel production origin after Vercel
  creates it (no wildcard and no path).

`APP_ENV`, Secure cookies, `SameSite=None`, and an independently generated
`SESSION_SECRET` are set by the Blueprint. The frontend uses same-origin
Vercel API functions, which proxy only the app's API and health routes to
`PHISHSHIFT_BACKEND_URL`; this avoids relying on cross-site third-party
cookies. Do not set `VITE_API_BASE_URL` to the Render host for this deployment.

## Hosted database schema approval gate

Do not run schema scripts until the hosted service and database are selected,
credentials are set privately, a backup/restore strategy is understood, and
you explicitly approve running the migrations.

The existing code has these additive scripts:

1. `python -m scripts.init_db` creates only missing core tables in
   `phishshift_db`: `scan_results`, `model_evaluations`, and `model_versions`.
2. `python -m scripts.migrate_auth` creates `users` and `auth_sessions` and
   adds nullable ownership to scans without assigning old unowned records.
3. `python -m scripts.migrate_project_metadata` adds dataset provenance and
   scan-kind metadata. It adds columns/indexes and does not drop tables.

They were designed and tested against local MariaDB; MySQL-family
compatibility does not prove that the hosted provider has identical DDL or
migration behavior. Review the provider/version-specific schema first. Never
import the local account, password hash, sessions, or scan history by default.
The deployment uses a new empty hosted database and starts with no user scans.

## Vercel frontend and same-origin API proxy

Import `dhanu-2505/Phish-Shift` into Vercel and set the project Root Directory
to `frontend`. Use `npm run build` and `dist` as the output directory.
`frontend/vercel.json` enables client-side route refreshes, while the
`frontend/api` functions proxy the limited `/api/*` and `/health/*` routes to
the Render backend.

Add the server-side Vercel environment variable `PHISHSHIFT_BACKEND_URL` with
the actual HTTPS Render service URL (no trailing path). This is not a `VITE_`
variable and is not included in browser JavaScript. Leave
`VITE_API_BASE_URL` unset so browser requests stay on the Vercel origin.

After Vercel supplies the real production origin, copy that exact HTTPS origin
to Render's `FRONTEND_ORIGINS`. Never guess the generated domain.

## Verification gates

Before creating test users or scans, verify the Render `/health/db`,
`/health/model`, and `/health/ready` endpoints. Register using the public
frontend and test CSRF-protected login/logout, an authenticated prediction,
history refresh, and unauthenticated access denial. Any verification scan is
real production data and requires explicit approval; do not delete it
automatically. Confirm the Vercel proxy route and cookie behavior in a real
browser because provider domains, browser privacy controls, and provider
network rules can differ.

No hosted database provider, Render URL, Vercel URL, production migration,
account, or scan is currently configured or verified.
