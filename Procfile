web: gunicorn config.wsgi:application --workers 2 --bind 0.0.0.0:$PORT --timeout 60
release: python manage.py migrate --noinput
