# release: 배포마다 1회, web 이 뜨기 전에 실행된다. 되돌릴 수 없는 DB 변경은 여기.
release: python backend/manage.py migrate --noinput

# collectstatic 은 web 안에서 돈다. Railway 의 release 는 별도 컨테이너라
# 거기서 모은 staticfiles/ 가 web 으로 전달되지 않기 때문이다.
# gunicorn 앞에 두므로 워커가 뜨기 전에 1회만 실행된다.
web: python backend/manage.py collectstatic --noinput && gunicorn --chdir backend config.wsgi --bind 0.0.0.0:$PORT --workers 2
