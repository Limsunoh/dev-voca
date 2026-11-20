"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application
from django.db.backends.signals import connection_created

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# 웹 요청의 DB 쿼리는 하나에 10초까지만 기다린다. 행 잠금을 기다리는 시간도 든다.
#
# 웹 서버는 스레드 여덟 개로 요청을 받는데, 스레드 방식의 gunicorn 은 오래 걸리는
# 요청을 끊지 않는다(DEPLOY.md 시작 명령). DB 가 멈추거나 잠금이 안 풀리면 요청마다
# 스레드를 하나씩 붙잡고, 여덟이 다 잡히면 사이트가 켜진 채 아무 응답도 못 한다.
#
# 여기서 거는 이유: 이 파일은 gunicorn(과 runserver)만 읽는다. 시작 명령의 migrate,
# 정리 크론, manage.py shell·test 는 읽지 않아 상한이 없다. 큰 표를 다시 쓰는
# 마이그레이션이 10초에 잘리면 배포가 깨진다. 값을 환경변수로 받지 않는 것도 같은
# 이유다. Railway 변수는 같은 시작 명령의 migrate 와 `railway ssh` 로 돌리는
# manage.py 에도 들어가고, 정리 크론(cleanup 서비스)이 참조를 걸면 그쪽에도 들어간다.
# ASGI 로 옮기면 아래 등록도 asgi.py 로 옮긴다. 안 옮기면 상한이 조용히 빠진다.
# 로컬 runserver(DEBUG 켜짐)에서 재현하면 한 요청이 수십 초를 잡는다. 끊긴 뒤 디버그
# 500 화면이 지역 변수의 QuerySet 을 다시 평가해 같은 쿼리가 또 10초씩 기다린다.
#
# 10초인 이유: Next 서버가 읽기 요청을 10초에 포기한다(frontend/src/lib/api/client.ts
# 의 READ_TIMEOUT_MS). 쓰기와 관리자 화면의 일괄 처리도 같은 10초에 걸린다. 걸리면
# 그 트랜잭션은 되돌려지고 대개 500 이 된다(일일공부 정산처럼 실패를 삼키고 로그만
# 남기는 곳도 있다). 어느 쪽이든 Sentry 에 남는다. 운영에서 가장 느렸던 요청은 0.4초,
# 단어 100만 개에서 잰 가장 느린 목록은 1.1초다.
STATEMENT_TIMEOUT_MS = 10_000


def _cap_statement_time(sender, connection, **kwargs) -> None:
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute(f'SET statement_timeout = {STATEMENT_TIMEOUT_MS}')


connection_created.connect(_cap_statement_time)

application = get_wsgi_application()
