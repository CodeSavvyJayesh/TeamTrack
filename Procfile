web: python manage.py migrate --no-input && python manage.py bootstrap_admin && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 60 --access-logfile - --error-logfile -
