"""배포 확인 주소 /healthz (config/healthz.py).

Railway 의 확인 요청과 같은 꼴(http, Host 가 healthcheck.railway.app)로 보낸다.
운영 설정(https 돌리기 켜짐, ALLOWED_HOSTS 에 그 Host 없음)을 덮어써서 연다.
"""

from django.test import SimpleTestCase, override_settings

RAILWAY_HOST = "healthcheck.railway.app"


@override_settings(ALLOWED_HOSTS=["web.example"], SECURE_SSL_REDIRECT=True)
class HealthzTest(SimpleTestCase):
    def test_railway_check_gets_200_over_http_with_unknown_host(self):
        res = self.client.get("/healthz", HTTP_HOST=RAILWAY_HOST)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content, b"ok")

    def test_other_paths_with_that_host_are_still_refused(self):
        # 미들웨어가 /healthz 말고도 열어 버리면 Host 검사가 빠진다.
        res = self.client.get("/api/vocab/words/", HTTP_HOST=RAILWAY_HOST)
        self.assertEqual(res.status_code, 400)

    def test_other_paths_still_redirect_to_https(self):
        res = self.client.get("/api/vocab/words/", HTTP_HOST="web.example")
        self.assertEqual(res.status_code, 301)
        self.assertTrue(res["Location"].startswith("https://"))

    def test_only_exact_path(self):
        # /healthz/ 처럼 비슷한 주소는 그대로 지나가 Host 검사를 받는다.
        res = self.client.get("/healthz/", HTTP_HOST=RAILWAY_HOST)
        self.assertEqual(res.status_code, 400)
