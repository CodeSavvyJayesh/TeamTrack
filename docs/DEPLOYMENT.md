# Deploying TeamTrack on Railway

Railway + PostgreSQL + Cloudflare R2 for uploaded files.

Do this on **Hetansh's accounts**, not yours. It is his company's data and his
bill, and if you ever stop working on this it should not be locked inside your
personal logins. Add yourself as a collaborator afterwards.

Railway gives new accounts a small trial credit, then runs about **$5/month**
for a service this size, plus the database. Verify current prices yourself.

---

## 1. Uploaded files - do this first

Railway wipes the container filesystem on every deploy. Skip this step and every
uploaded file disappears the first time you push a change.

1. Cloudflare dashboard → **R2** → **Create bucket** → `teamtrack-media`
2. Leave it **private**. Do not enable public access - every download in this
   app goes through a permission check, and a public bucket bypasses it.
3. **Manage R2 API Tokens** → **Create API Token** → **Object Read & Write**,
   scoped to that bucket
4. Copy these three (the secret is shown once):
   - Access Key ID
   - Secret Access Key
   - Endpoint, `https://<account-id>.r2.cloudflarestorage.com`

You can deploy without this and add it later, but do not let anyone upload real
work until it is done.

## 2. Email

Gmail is not suitable in production - 500 messages a day, and app passwords used
from servers get flagged. Sign up at [Brevo](https://brevo.com), verify your
sending address, and take the SMTP credentials from **SMTP & API**.

## 3. Deploy

1. [railway.app](https://railway.app) → sign in with GitHub
2. **New Project** → **Deploy from GitHub repo** → pick `TeamTrack`
3. Railway reads `railway.json` and starts building. It will fail the first time
   because there is no database yet - that is expected.
4. In the project, **New** → **Database** → **Add PostgreSQL**.
   Railway injects `DATABASE_URL` into the web service automatically.
5. Open the web service → **Variables** → paste these in:

```
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=<50+ random characters, generated fresh - see below>
TIME_ZONE=Asia/Kolkata

EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_HOST_USER=<from Brevo>
EMAIL_HOST_PASSWORD=<from Brevo>
DEFAULT_FROM_EMAIL=TeamTrack <no-reply@yourdomain.com>

AWS_STORAGE_BUCKET_NAME=teamtrack-media
AWS_ACCESS_KEY_ID=<from R2>
AWS_SECRET_ACCESS_KEY=<from R2>
AWS_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com

ADMIN_EMAIL=hetansh@yourcompany.com
ADMIN_PASSWORD=<20+ random characters>
ADMIN_NAME=Hetansh Doshi

INVITATION_EXPIRY_DAYS=7
MAX_UPLOAD_SIZE_MB=10
ATTENDANCE_MAX_HOURS=9
```

Generate the secret key locally and paste the output:

```powershell
python -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(60)))"
```

Never reuse the key from your local `.env`. It has been in terminals and chat
windows all week.

**You do not need to set `ALLOWED_HOSTS` or `CSRF_TRUSTED_ORIGINS`.**
`config/settings/production.py` reads Railway's own `RAILWAY_PUBLIC_DOMAIN` and
fills both in. Getting those two wrong is the most common way a first Django
deploy fails, so they are handled for you.

6. **Settings** → **Networking** → **Generate Domain**. That is your link.
7. Redeploy. `railway.json` runs migrations, creates the administrator, and
   starts gunicorn.

## 4. Immediately after the first successful deploy

**Delete `ADMIN_PASSWORD` from Variables.** The account exists now; leaving the
password in a dashboard is pointless risk. `bootstrap_admin` becomes a no-op.

**Sign in and change that password.**

**Send a test invitation to yourself.** If it arrives, SMTP is right.

**Upload a file, redeploy, then download it again.** Still there means R2 works.
A 404 means uploads went to the container disk and the `AWS_*` variables are
wrong - fix that before anyone stores real work.

## 5. The nightly cleanup

Railway charges for cron, so this runs free on GitHub Actions instead:
`.github/workflows/close-stale-attendance.yml`, daily at 00:00 IST.

Add two repository secrets (**Settings → Secrets and variables → Actions**):

| Secret | Value |
|---|---|
| `DATABASE_URL` | the **public** Postgres URL from Railway's database → Variables |
| `SECRET_KEY` | any 50+ character string; this job renders no pages |

Then **Actions → Close stale attendance → Run workflow** to test it now rather
than finding out at midnight.

Without this job one forgotten sign-out becomes a 40-hour "day" and every
attendance total is wrong.

## 6. Your own domain

**Settings → Networking → Custom Domain**, add the CNAME at your registrar, wait
for the certificate. Then set `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
explicitly to include both the custom domain and the railway.app one - the
auto-detection only knows about Railway's.

Once HTTPS is confirmed everywhere, raise `SECURE_HSTS_SECONDS` from `3600` to
`31536000`. In that order - a long HSTS on a broken certificate locks people out
of your own site for a year, and you cannot undo it from the server.

## 7. Backups

Real people's work records.

```bash
pg_dump "$DATABASE_URL" > teamtrack-$(date +%F).sql
```

Weekly, stored somewhere that is not Railway. **A backup you have never restored
is not a backup** - practise restoring one into a scratch database.

---

## When something breaks

Logs: Railway → the service → **Deployments** → click the active one. Everything
the app writes goes to stdout, including a full traceback on any 500.

**Build fails on `collectstatic`.** Read further up for the real error. The
deploy aborts deliberately rather than shipping a broken build.

**`DisallowedHost`.** `RAILWAY_PUBLIC_DOMAIN` was not set - usually because you
have not generated a domain yet. Do step 6 of the deploy.

**CSRF error on every form, pages load fine.** You added a custom domain but did
not add it to `CSRF_TRUSTED_ORIGINS`. It needs the `https://` prefix.

**Emails stop.** Check Brevo for a sending limit or bounces. Every failure is
logged - search for `Could not email notification`.

**Uploads disappear after a deploy.** The `AWS_*` variables are wrong, so files
went to the container disk. Anything already lost is gone.

---

## Running production settings locally

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.production"
$env:SECRET_KEY="any-50-plus-character-string-for-local-testing-only"
$env:ALLOWED_HOSTS="localhost,127.0.0.1,testserver"
$env:DATABASE_URL="postgres://user:pass@localhost:5432/teamtrack"
$env:SECURE_SSL_REDIRECT="False"; $env:DB_SSL_REQUIRE="False"
$env:EMAIL_HOST="smtp-relay.brevo.com"
$env:EMAIL_HOST_USER="x"; $env:EMAIL_HOST_PASSWORD="x"
$env:DEFAULT_FROM_EMAIL="TeamTrack <x@example.com>"

python manage.py check --deploy
python manage.py test
```

This exact setup has been run against PostgreSQL: **138 tests, all passing.**
`check --deploy` reports only the two HSTS warnings, which are deliberate until
you raise `SECURE_HSTS_SECONDS`.
