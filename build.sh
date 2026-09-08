#!/usr/bin/env bash
# Render runs this on every deploy. Any non-zero exit aborts the deploy, which
# is what you want - a failed migration must never reach live traffic.
set -o errexit

pip install -r requirements.txt

# Hashed, compressed static files for WhiteNoise.
python manage.py collectstatic --no-input

# Schema first, then the administrator account if it does not exist yet.
python manage.py migrate
python manage.py bootstrap_admin
