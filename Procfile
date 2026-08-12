release: python backend/manage.py migrate --noinput && python backend/manage.py createcachetable
web: python backend/manage.py collectstatic --noinput && gunicorn --chdir backend config.wsgi --bind 0.0.0.0:$PORT --workers 2
