# Deploying TeamTrack

Target: **Render**, PostgreSQL, Cloudflare R2 for uploaded files.

Everything here should be done **on Hetansh's accounts**, not yours. It is his
company's data and his bill, and if you ever stop working on this it should not
be locked inside your personal logins. Add yourself as a collaborator after.

Budget roughly **₹700–1,200 a month** all in, plus about ₹900 a year for a
domain. Check current prices yourself, they change.

---

## Before you start

Five accounts, all created by Hetansh:

| Service | For | Cost |
|---|---|---|
| [Render](https://render.com) | the app and the database | free to try, ~$7/mo real |
| [Cloudflare](https://cloudflare.com) | R2 storage for uploaded files | free at this size |
| [Brevo](https://brevo.com) or [Resend](https://resend.com) | sending email | free tier is plenty |
| A domain registrar | e.g. `teamtrack.yourcompany.com` | ~₹900/year |
| GitHub | already done | free |

**On Render's free tier the app sleeps when idle**, so the first request after a
quiet spell takes about 30 seconds. Fine for testing, irritating for Shifa every
morning. Move to the paid plan before the team depends on it.

**Do not run a real team on a free database.** Free Postgres instances are
time-limited and eventually deleted. Losing months of work records to a plan
expiry is not a risk worth saving ₹600 a month over.

---

## 1. Uploaded files — do this first

Skip this and files vanish on every deploy, because Render wipes the disk each
time.

1. Cloudflare dashboard → **R2** → **Create bucket** → name it `teamtrack-media`
2. Leave it **private**. Do not enable public access. Every download in this app
   goes through a permission check, and a public bucket bypasses that entirely.
3. **Manage R2 API Tokens** → **Create API Token**
   - Permissions: **Object Read & Write**
   - Scope it to that one bucket
4. Copy these three — the secret is shown once:
   - Access Key ID
   - Secret Access Key
   - The S3 endpoint, `https://<account-id>.r2.cloudflarestorage.com`

---

## 2. Email

Gmail will not do in production: 500 messages a day, and app passwords used from
servers get flagged.

1. Sign up at Brevo, verify the sending domain or address
2. **SMTP & API** → copy the SMTP credentials
3. You need host (`smtp-relay.brevo.com`), port `587`, login, password

---

## 3. Deploy

1. Render → **New** → **Blueprint**
2. Connect the GitHub repo. Render reads `render.yaml` and creates the web
   service, the database and the nightly cron job.
3. It asks for the values marked `sync: false`. Fill in:

```
ALLOWED_HOSTS            teamtrack.onrender.com
CSRF_TRUSTED_ORIGINS     https://teamtrack.onrender.com

EMAIL_HOST               smtp-relay.brevo.com
EMAIL_HOST_USER          <from Brevo>
EMAIL_HOST_PASSWORD      <from Brevo>
DEFAULT_FROM_EMAIL       TeamTrack <no-reply@yourdomain.com>

AWS_STORAGE_BUCKET_NAME  teamtrack-media
AWS_ACCESS_KEY_ID        <from R2>
AWS_SECRET_ACCESS_KEY    <from R2>
AWS_S3_ENDPOINT_URL      https://<account-id>.r2.cloudflarestorage.com

ADMIN_EMAIL              hetansh@yourcompany.com
ADMIN_PASSWORD           <20+ random characters>
ADMIN_NAME               Hetansh Doshi
```

**`SECRET_KEY` is deliberately not in that list.** Render generates it
(`generateValue: true`), nobody ever sees it, and it never reaches GitHub or a
chat window. The development key in your local `.env` must never be reused here.

4. **Apply.** The first build takes a few minutes.

---

## 4. Immediately after the first deploy

**Delete `ADMIN_PASSWORD`** from the Render environment. The account exists now;
leaving the password in a dashboard is pointless risk. `bootstrap_admin` becomes
a no-op once the account is there.

**Sign in and change that password.**

**Send a test invitation to yourself.** If it arrives, SMTP is right.

**Upload a file, trigger a redeploy, then download it again.** Still there means
R2 is working. A 404 means uploads are going to the local disk — fix the AWS_*
variables before anyone stores real work in it.

---

## 5. Your own domain

1. Render → the service → **Settings** → **Custom Domain** → add
   `teamtrack.yourcompany.com`
2. At the registrar, add the CNAME Render shows you
3. Wait for the certificate, usually minutes
4. Update **both** variables and redeploy:

```
ALLOWED_HOSTS         teamtrack.yourcompany.com,teamtrack.onrender.com
CSRF_TRUSTED_ORIGINS  https://teamtrack.yourcompany.com,https://teamtrack.onrender.com
```

Forgetting `CSRF_TRUSTED_ORIGINS` is the classic mistake: every page loads fine
and every form submission fails with a CSRF error.

Once you are certain HTTPS works everywhere, raise `SECURE_HSTS_SECONDS` from
`3600` to `31536000`. In that order — a long HSTS on a broken certificate locks
people out of your own site for a year, and you cannot undo it from the server.

---

## 6. Backups — do not skip

These are real people's work records. Render's paid Postgres takes daily
backups; free does not. Take your own regardless:

```bash
pg_dump "$DATABASE_URL" > teamtrack-$(date +%F).sql
```

Weekly, kept somewhere that is not Render. **A backup you have never restored is
not a backup** — practise restoring one into a scratch database before you need
it for real.

---

## 7. What runs automatically

One cron job, defined in `render.yaml`:

```
python manage.py close_stale_attendance    # 00:00 IST daily
```

It closes attendance sessions nobody signed out of, caps them at
`ATTENDANCE_MAX_HOURS`, and flags them as auto-closed. Without it one forgotten
sign-out becomes a 40-hour day and every total downstream is wrong. If the
attendance figures start looking silly, check this job is still running.

---

## When something breaks

**Everything 500s right after a deploy.** Read the build log. `Missing
staticfiles manifest entry` means `collectstatic` failed — the deploy should
have aborted, so look further up for the real error.

**Forms fail with a CSRF error.** `CSRF_TRUSTED_ORIGINS` does not include the
hostname being used. It needs the `https://` prefix.

**`DisallowedHost` in the logs.** Add that hostname to `ALLOWED_HOSTS`.

**Emails silently stop.** Check Brevo for a sending limit or bounces. Every
failure is logged, so search the Render logs for `Could not email notification`.

**Uploads disappear after a deploy.** The AWS_* variables are wrong or missing,
so files went to local disk. Fix them; anything already lost is gone.

**Slow first load each morning.** That is the free plan sleeping. Upgrade.

Logs live under **Logs** on the Render service. Everything the app writes goes to
stdout, including a full traceback on any 500.

---

## Running production settings locally

Worth doing before you push anything significant:

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.production"
$env:SECRET_KEY="any-50-plus-character-string-for-local-testing-only"
$env:ALLOWED_HOSTS="localhost,127.0.0.1,testserver"
$env:DATABASE_URL="postgres://user:pass@localhost:5432/teamtrack"
$env:SECURE_SSL_REDIRECT="False"
$env:DB_SSL_REQUIRE="False"
$env:EMAIL_HOST="smtp-relay.brevo.com"
$env:EMAIL_HOST_USER="x"; $env:EMAIL_HOST_PASSWORD="x"
$env:DEFAULT_FROM_EMAIL="TeamTrack <x@example.com>"

python manage.py check --deploy
python manage.py collectstatic --no-input
python manage.py test
```

`check --deploy` should report only the two HSTS warnings, which are deliberate
until you raise `SECURE_HSTS_SECONDS`.

This exact setup has been run against PostgreSQL: **138 tests, all passing.**
