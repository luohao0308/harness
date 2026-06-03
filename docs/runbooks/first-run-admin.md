# First-Run Admin Runbook

This runbook covers the first production login path. Dev bearer tokens are
enabled only when `APP_ENV` is `development` or `test`; production and staging
must use JWTs or API keys.

## Required Secrets

Generate the startup secrets before starting the API:

```bash
python3 scripts/generate-runtime-secrets.py
```

Set `AUTH_JWT_SECRET`, `HARNESS_SECRET_ENCRYPTION_KEY`, and
`HARNESS_SECRET_ENCRYPTION_KEY_ID` in the API runtime environment. The JWT
secret signs login tokens; the Harness secret-encryption key encrypts business
integration secrets stored in `stored_secrets`. Generate and store both on the
server or deployment secret manager side. Do not generate or expose
`HARNESS_SECRET_ENCRYPTION_KEY` in the Agent Console frontend.

The API refuses to boot when `AUTH_JWT_SECRET` is missing,
shorter than 32 characters, or still equals the example placeholder
`replace-with-openssl-rand-hex-32`.

## Bootstrap On First Boot

For an empty `users` table, set one initial owner account before the first API
startup:

```bash
eval "$(python3 scripts/generate-runtime-secrets.py)"
export AUTH_JWT_SECRET HARNESS_SECRET_ENCRYPTION_KEY HARNESS_SECRET_ENCRYPTION_KEY_ID
HARNESS_INITIAL_ADMIN_EMAIL=admin@example.com
HARNESS_INITIAL_ADMIN_PASSWORD='replace-with-a-strong-password'
```

On startup the API creates:

- one active user with the normalized email;
- one default organization;
- one accepted owner membership.

When any user already exists, startup skips bootstrap and does not create a
second admin.

After the first successful login, remove or clear
`HARNESS_INITIAL_ADMIN_EMAIL` and `HARNESS_INITIAL_ADMIN_PASSWORD`, then restart
the API container. Keep `AUTH_JWT_SECRET` stable or existing JWTs and signed
pagination cursors become invalid. Keep `HARNESS_SECRET_ENCRYPTION_KEY` stable
or previously stored business secrets cannot be decrypted without a rotation
and re-encryption migration.

## Login And Smoke Tokens

Get a JWT with the initial admin credentials:

```bash
curl --noproxy '*' -sS http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"replace-with-a-strong-password"}'
```

Export the returned `access_token` for smoke tests:

```bash
export HARNESS_AUTH_TOKEN='<access_token>'
export HARNESS_ADMIN_TOKEN='<access_token>'
export HARNESS_OPERATOR_TOKEN='<access_token>'
python3 scripts/smoke-test-docker.py
python3 scripts/smoke-test-agent-run.py
```

`HARNESS_OPERATOR_TOKEN` may use an operator or viewer-scoped token when that
role exists. An owner token also passes the service-health checks.

## CLI Fallback

Use the CLI when the API has already started without bootstrap variables, or
when an operator needs to create another owner through a controlled shell.

From the repository checkout:

```bash
DATABASE_URL="$DATABASE_URL" \
AUTH_JWT_SECRET="$AUTH_JWT_SECRET" \
python3 scripts/create-admin.py --email admin@example.com
```

Inside the Docker image, use the module path because the root `scripts/`
directory is not part of the API image:

```bash
docker compose -f compose.production.yml exec api-server \
  python -m app.cli.create_admin --email admin@example.com
```

The command prompts for the password when `--password` is omitted.

## Legacy Dev Seed Cleanup

Historical migration `20260604_0030_create_auth_rbac.py` seeded
`dev-admin` and `dev-engineer` rows for early development. The follow-up
migration `20260605_0032_remove_legacy_admin_seed.py` removes only those known
legacy rows when their original dev password hash still matches. It does not
rewrite historical migrations and does not delete real customer users.
