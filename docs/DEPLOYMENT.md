# Deployment

Development runs on SQLite with `DEBUG=True` and no external services.
Production changes four things: the database, the email backend, how static and
media files are served, and the settings module.

## 1. Settings module

```bash
export DJANGO_SETTINGS_MODULE=config.settings.production
```

`config/settings/production.py` turns off `DEBUG`, switches to PostgreSQL and
SMTP, and enables HSTS, secure cookies and `SECURE_SSL_REDIRECT`. It assumes TLS
terminates at a reverse proxy and reads `X-Forwarded-Proto`.

## 2. Dependencies

Uncomment the production block in `requirements.txt`:

```
psycopg[binary]==3.2.3
gunicorn==23.0.0
whitenoise==6.8.2
```

## 3. Environment

Copy `.env.example` and fill in real values. Every one of these is required in
production and none has a safe default:

```
SECRET_KEY=            # a fresh 50+ character random string, not the dev one
DEBUG=False
ALLOWED_HOSTS=teamtrack.example.com
DB_NAME=  DB_USER=  DB_PASSWORD=  DB_HOST=  DB_PORT=5432
EMAIL_HOST=  EMAIL_PORT=587  EMAIL_HOST_USER=  EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=TeamTrack <noreply@example.com>
```

Never commit `.env`. It is in `.gitignore` already.

## 4. Database

```bash
python manage.py migrate
python manage.py createsuperuser
```

## 5. Static files

```bash
python manage.py collectstatic --noinput
```

Serve `/static/` from `STATIC_ROOT` with nginx, or add WhiteNoise to
`MIDDLEWARE` directly after `SecurityMiddleware`.

## 6. Media files - important

**Do not serve `MEDIA_URL` from the web server.** Uploaded files are private:
every download goes through `storage.views.FileDownloadView`, which checks
permission first. Exposing `/media/` directly would bypass that check entirely
and make every private file readable by anyone who guesses a URL.

For efficiency in production, change `FileDownloadView.get()` to return an
empty response carrying an `X-Accel-Redirect` header pointing at an
`internal;` nginx location. nginx then sends the bytes and the permission check
stays exactly where it is.

```nginx
location /protected/ {
    internal;
    alias /srv/teamtrack/media/;
}
```

## 7. Run

```bash
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
```

## 8. Verify

```bash
python manage.py check --deploy
```

Expect no warnings. `python manage.py test` should still pass against the
production settings module.

## Scheduled jobs

Only one, and it is optional:

```bash
python manage.py sync_google_forms
```

Safe to schedule before Google is connected - it reports the integration is
dormant and exits successfully.
