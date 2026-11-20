"""보안 기본기(관리자 로그인 제한, 로그인 시간당 상한, API 권한 기본값, 사진 형식)를
밖에서 직접 불러 깨뜨려 본다. tests_security_basics.py 가 정상 경로를 본다면 여기는
우회와 부작용을 본다.

- 관리자 로그인: 대소문자·공백·username 없이·슬래시 없는 주소·?next= 로 제한을 비켜갈 수
  있는지, 제한 안에서는 로그인과 next 이동이 되는지.
- 권한 기본값(IsAuthenticated): 게스트가 쓰던 길이 401 로 막히지 않았는지, 로그인이 필요한
  길은 그대로 401 인지, 검수 안 된 항목이 게스트 목록·검색·상세로 새지 않는지.
- 사진: 형식마다 AvatarPhotoView 가 200/400 으로 답하고 500 이 없는지.

비율은 get_rate 를 바꿔 좁힌다(tests_ip_throttle.py 머리말).
"""

from __future__ import annotations

import io
import secrets
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import resolve
from PIL import Image, features

from apps.learning.tests import make_words
from apps.vocab.models import Sentence, Word

from .models import LoginToken
from .throttles import (
    AdminLoginThrottle,
    AvatarPhotoThrottle,
    EmailHourlyThrottle,
)
from .views import admin_login

User = get_user_model()

ADMIN_LOGIN = "/admin/login/"
LOGIN_URL = "/api/accounts/login/"
PHOTO_URL = "/api/accounts/photo/"


def _narrow(test: TestCase, throttle_class, rate: str) -> None:
    patcher = mock.patch.object(throttle_class, "get_rate", return_value=rate)
    patcher.start()
    test.addCleanup(patcher.stop)


def _logged_in(client) -> bool:
    return "_auth_user_id" in client.session


class AdminLoginBypassTest(TestCase):
    """관리자 로그인 제한(2/hour 로 좁힘)을 비켜갈 수 있는가."""

    def setUp(self):
        cache.clear()
        _narrow(self, AdminLoginThrottle, "2/hour")
        self.password = secrets.token_urlsafe(16)
        User.objects.create_superuser(email="boss@example.com", password=self.password)

    def _post(self, username, password="wrong", path=ADMIN_LOGIN, **extra):
        data = {"password": password}
        if username is not None:
            data["username"] = username
        return self.client.post(path, data, **extra)

    def _burn(self):
        """정해진 2회를 틀린 비밀번호로 다 쓴다."""
        self.assertEqual(self._post("boss@example.com").status_code, 200)
        self.assertEqual(self._post("boss@example.com").status_code, 200)

    def test_admin_login_url_is_intercepted(self):
        """admin/login/ 이 admin 사이트의 login 이 아니라 세는 함수로 간다."""
        self.assertIs(resolve(ADMIN_LOGIN).func, admin_login)

    def test_case_and_whitespace_variants_share_one_count(self):
        """대소문자·앞뒤 공백·탭·줄바꿈을 바꿔도 같은 통으로 센다."""
        self._post("  BOSS@Example.COM\t")
        self._post("\nboss@EXAMPLE.com ")
        blocked = self._post("Boss@Example.Com", self.password)
        self.assertEqual(blocked.status_code, 429)
        self.assertFalse(_logged_in(self.client))

    def test_blocked_even_with_right_password(self):
        """막힌 뒤에는 맞는 비밀번호도 들어가지 못한다."""
        self._burn()
        res = self._post("boss@example.com", self.password)
        self.assertEqual(res.status_code, 429)
        self.assertFalse(_logged_in(self.client))

    def test_next_query_does_not_reset_count(self):
        """?next= 를 붙여도 같은 주소라 같이 센다."""
        self._burn()
        res = self._post("boss@example.com", self.password, path=ADMIN_LOGIN + "?next=/admin/")
        self.assertEqual(res.status_code, 429)
        self.assertFalse(_logged_in(self.client))

    def test_missing_username_is_not_a_login(self):
        """username 칸 없이 보내면 세지 않지만 로그인도 안 된다(500 아님)."""
        self._burn()
        for _ in range(3):
            res = self._post(None, self.password)
            self.assertEqual(res.status_code, 200)
            self.assertFalse(_logged_in(self.client))

    def test_email_sent_in_another_field_does_not_log_in(self):
        """username 대신 email 칸에 실어도 Admin 폼은 username 만 본다."""
        self._burn()
        res = self.client.post(ADMIN_LOGIN, {"email": "boss@example.com", "password": self.password})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(_logged_in(self.client))

    def test_repeated_username_field_counts_the_one_the_form_uses(self):
        """username 을 둘 실으면 폼과 세는 쪽이 같은 값(마지막)을 본다."""
        self._burn()
        res = self.client.post(
            ADMIN_LOGIN,
            {"username": ["other@example.com", "boss@example.com"], "password": self.password},
        )
        self.assertEqual(res.status_code, 429)
        self.assertFalse(_logged_in(self.client))

    def test_json_body_does_not_log_in(self):
        """JSON 본문은 Admin 폼이 못 읽는다. 세지 않아도 로그인이 안 되면 된다."""
        self._burn()
        res = self.client.post(
            ADMIN_LOGIN,
            {"username": "boss@example.com", "password": self.password},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(_logged_in(self.client))

    def test_path_without_slash_does_not_reach_login(self):
        """/admin/login (슬래시 없음) 은 로그인을 처리하지 않고 돌려보낸다."""
        self._burn()
        res = self._post("boss@example.com", self.password, path="/admin/login")
        self.assertIn(res.status_code, (301, 302, 404))
        self.assertFalse(_logged_in(self.client))

    def test_odd_paths_do_not_reach_login(self):
        """겹슬래시·대문자·뒤에 붙인 주소로는 로그인이 처리되지 않는다."""
        self._burn()
        for path in ("/admin//login/", "/ADMIN/LOGIN/", "/admin/login/x/", "/admin/login/%2e/"):
            with self.subTest(path=path):
                res = self._post("boss@example.com", self.password, path=path)
                self.assertNotEqual(res.status_code, 500)
                self.assertFalse(_logged_in(self.client))

    def test_page_view_still_works_when_blocked(self):
        """막힌 동안에도 GET 으로 화면은 뜬다(세는 것은 POST 뿐)."""
        self._burn()
        self._post("boss@example.com")
        self.assertEqual(self.client.get(ADMIN_LOGIN).status_code, 200)

    def test_under_limit_login_follows_next(self):
        """제한 안에서 맞는 비밀번호면 로그인하고 next 로 간다."""
        self.assertEqual(self._post("boss@example.com").status_code, 200)
        res = self.client.post(
            ADMIN_LOGIN + "?next=/admin/accounts/",
            {"username": "boss@example.com", "password": self.password, "next": "/admin/accounts/"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res["Location"], "/admin/accounts/")
        self.assertTrue(_logged_in(self.client))

    def test_offsite_next_is_not_followed(self):
        """next 에 바깥 주소를 넣어도 그리로 보내지 않는다."""
        res = self.client.post(
            ADMIN_LOGIN,
            {"username": "boss@example.com", "password": self.password, "next": "https://evil.example/"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertNotIn("evil.example", res["Location"])

    def test_blocked_reply_is_plain_korean_text(self):
        self._burn()
        res = self._post("boss@example.com")
        self.assertEqual(res.status_code, 429)
        self.assertIn("text/plain", res["Content-Type"])
        self.assertIn("뒤에 다시 해주세요", res.content.decode("utf-8"))
        self.assertIn("Retry-After", res.headers)

    def test_logged_in_staff_get_goes_to_index(self):
        """이미 로그인한 관리자가 로그인 화면을 열면 관리 첫 화면으로 간다."""
        self.client.post(ADMIN_LOGIN, {"username": "boss@example.com", "password": self.password})
        res = self.client.get(ADMIN_LOGIN)
        self.assertEqual(res.status_code, 302)

    def test_csrf_is_still_checked(self):
        """CSRF 검사를 켠 클라이언트로는 토큰 없이 POST 가 403 이다."""
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)
        res = strict.post(ADMIN_LOGIN, {"username": "boss@example.com", "password": self.password})
        self.assertEqual(res.status_code, 403)


class LoginHourlyDynamicTest(TestCase):
    """API 로그인의 이메일당 시간 상한(2/hour 로 좁힘)."""

    def setUp(self):
        cache.clear()
        _narrow(self, EmailHourlyThrottle, "2/hour")
        self.password = secrets.token_urlsafe(16)
        User.objects.create_user(email="kim@example.com", password=self.password, display_name="김")

    def _login(self, email, password="wrong-wrong-1"):
        return self.client.post(
            LOGIN_URL, {"email": email, "password": password}, content_type="application/json"
        )

    def test_case_and_space_variants_share_one_count(self):
        self.assertEqual(self._login("KIM@example.com").status_code, 400)
        self.assertEqual(self._login("  kim@EXAMPLE.com ").status_code, 400)
        self.assertEqual(self._login("kim@example.com", self.password).status_code, 429)

    def test_under_limit_login_works(self):
        self.assertEqual(self._login("kim@example.com").status_code, 400)
        self.assertEqual(self._login("kim@example.com", self.password).status_code, 200)

    def test_other_email_is_not_blocked(self):
        self._login("kim@example.com")
        self._login("kim@example.com")
        self.assertEqual(self._login("lee@example.com").status_code, 400)

    def test_garbage_bodies_are_400_not_500(self):
        for body in ([], "x", {"email": 5}, {"email": ""}, {"email": " "}, {"email": "a" * 400}):
            with self.subTest(body=body):
                res = self.client.post(LOGIN_URL, body, content_type="application/json")
                self.assertEqual(res.status_code, 400)


class GuestAccessTest(TestCase):
    """권한 기본값을 로그인 필요로 바꾼 뒤에도 게스트 길이 열려 있다."""

    @classmethod
    def setUpTestData(cls):
        make_words()
        cls.word = Word.objects.get(term="term0")
        cls.hidden_word = Word.objects.create(
            term="hiddenzz", meaning="새면 안 되는 뜻", category="git"
        )
        cls.sentence = Sentence.objects.create(
            text="push term0 to remote",
            translation="원격에 올린다",
            context="상황",
            kind="phrase",
            category="git",
            is_reviewed=True,
        )
        cls.hidden_sentence = Sentence.objects.create(
            text="hiddenzz sentence",
            translation="새면 안 되는 해석",
            kind="phrase",
            category="git",
        )

    def setUp(self):
        cache.clear()

    def assertOpen(self, res, *codes):
        self.assertNotIn(res.status_code, (401, 403), res.content[:200])
        self.assertLess(res.status_code, 500, res.content[:200])
        if codes:
            self.assertIn(res.status_code, codes, res.content[:200])

    def test_vocab_reads_are_open(self):
        for url in (
            "/api/vocab/words/",
            "/api/vocab/words/?search=term",
            f"/api/vocab/words/{self.word.pk}/",
            "/api/vocab/words/categories/",
            "/api/vocab/words/exam_subjects/",
            "/api/vocab/words/difficulties/",
            "/api/vocab/words/quiz/",
            "/api/vocab/sentences/",
            "/api/vocab/sentences/?search=term0",
            f"/api/vocab/sentences/{self.sentence.pk}/",
            "/api/vocab/sentences/kinds/",
        ):
            with self.subTest(url=url):
                self.assertOpen(self.client.get(url), 200)

    def test_sentence_quiz_is_open(self):
        self.assertOpen(self.client.get("/api/vocab/sentences/quiz/"))

    def test_grade_endpoints_are_open(self):
        for url in ("/api/vocab/words/grade/", "/api/vocab/sentences/grade/"):
            with self.subTest(url=url):
                res = self.client.post(url, {}, content_type="application/json")
                self.assertOpen(res, 400)

    def test_word_quiz_then_grade_as_guest(self):
        q = self.client.get("/api/vocab/words/quiz/").json()
        res = self.client.post(
            "/api/vocab/words/grade/",
            {"token": q["token"], "choice_id": q["choices"][0]["id"]},
            content_type="application/json",
        )
        self.assertOpen(res, 200)

    def test_talk_is_open(self):
        self.assertOpen(self.client.get("/api/vocab/talk/question/"))
        self.assertOpen(self.client.get("/api/vocab/talk/question/?kind=dev"))
        res = self.client.post("/api/vocab/talk/grade/", {}, content_type="application/json")
        self.assertOpen(res, 400)

    def test_round_start_answer_finish_as_guest(self):
        start = self.client.post("/api/learning/rounds/", content_type="application/json")
        self.assertOpen(start, 201)
        body = start.json()
        answer = self.client.post(
            "/api/learning/rounds/answer/",
            {"token": body["token"], "choice_id": body["question"]["choices"][0]["id"]},
            content_type="application/json",
        )
        self.assertOpen(answer, 200)
        finish = self.client.post(
            "/api/learning/rounds/finish/",
            {"token": answer.json()["token"]},
            content_type="application/json",
        )
        self.assertOpen(finish, 200)
        self.assertTrue(finish.json()["guest"])

    def test_leaderboards_are_open(self):
        for url in (
            "/api/learning/leaderboards/weekly/",
            "/api/learning/leaderboards/all-time/",
            "/api/learning/leaderboards/streak/",
        ):
            with self.subTest(url=url):
                self.assertOpen(self.client.get(url), 200)

    def test_account_entry_points_are_open(self):
        for url in (
            "/api/accounts/signup/",
            "/api/accounts/login/",
            "/api/accounts/google/",
            "/api/accounts/email-change/confirm/",
        ):
            with self.subTest(url=url):
                res = self.client.post(url, {}, content_type="application/json")
                self.assertOpen(res, 400)

    def test_photo_file_is_open(self):
        self.assertOpen(self.client.get(f"/api/accounts/photo/{uuid.uuid4()}/"), 404)

    def test_member_only_paths_still_need_login(self):
        for method, url in (
            ("get", "/api/accounts/me/"),
            ("post", "/api/accounts/logout/"),
            ("post", "/api/accounts/password/"),
            ("post", "/api/accounts/email-change/"),
            ("post", PHOTO_URL),
            ("delete", PHOTO_URL),
            ("post", "/api/learning/daily/"),
            ("post", "/api/learning/daily/answer/"),
            ("get", "/api/learning/review/"),
            ("post", "/api/learning/review/answer/"),
            ("get", "/api/learning/mistakes/"),
            ("get", "/api/learning/history/"),
            ("post", "/api/vocab/words/"),
            ("delete", f"/api/vocab/words/{self.word.pk}/"),
        ):
            with self.subTest(method=method, url=url):
                res = getattr(self.client, method)(url, content_type="application/json")
                self.assertEqual(res.status_code, 401)

    def test_unreviewed_items_do_not_leak_to_guest(self):
        """검수 안 된 단어·문장이 게스트 목록·검색·상세에 하나도 안 나온다."""
        for url in (
            "/api/vocab/words/?page_size=100",
            "/api/vocab/words/?search=hiddenzz",
            "/api/vocab/sentences/?page_size=100",
            "/api/vocab/sentences/?search=hiddenzz",
        ):
            with self.subTest(url=url):
                res = self.client.get(url)
                self.assertEqual(res.status_code, 200)
                self.assertNotIn("hiddenzz", res.content.decode("utf-8"))
        self.assertEqual(self.client.get(f"/api/vocab/words/{self.hidden_word.pk}/").status_code, 404)
        self.assertEqual(
            self.client.get(f"/api/vocab/sentences/{self.hidden_sentence.pk}/").status_code, 404
        )
        # 대조군: 검수된 것은 같은 검색에 나온다(필터가 아니라 검색이 비어서 통과하는 게 아님).
        self.assertIn("term0", self.client.get("/api/vocab/words/?search=term0").content.decode())

    def test_bad_pks_are_404_not_500(self):
        for pk in ("9" * 30, "abc", "-1", "0"):
            with self.subTest(pk=pk):
                self.assertEqual(self.client.get(f"/api/vocab/words/{pk}/").status_code, 404)


def _image(fmt: str, **save) -> bytes:
    out = io.BytesIO()
    mode = "P" if fmt == "GIF" else "RGB"
    Image.new(mode, (64, 64)).save(out, format=fmt, **save)
    return out.getvalue()


def _mpo() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 64), (1, 2, 3)).save(
        out, format="MPO", save_all=True, append_images=[Image.new("RGB", (64, 64))]
    )
    return out.getvalue()


class AvatarUploadFormatTest(TestCase):
    """AvatarPhotoView 로 형식마다 올려 본다. 받는 것은 200, 거절은 400, 500 은 없다."""

    def setUp(self):
        cache.clear()
        _narrow(self, AvatarPhotoThrottle, "1000/min")
        self.user = User.objects.create_user(
            email="pic@example.com", password=secrets.token_urlsafe(16), display_name="사진"
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Token {LoginToken.objects.create(user=self.user).key}"}

    def _upload(self, data: bytes, name: str, content_type: str):
        return self.client.post(
            PHOTO_URL,
            {"photo": SimpleUploadedFile(name, data, content_type=content_type)},
            **self.auth,
        )

    def test_phone_formats_are_accepted(self):
        for fmt, data, name, ctype in (
            ("JPEG", _image("JPEG"), "a.jpg", "image/jpeg"),
            ("MPO", _mpo(), "a.jpg", "image/jpeg"),
            ("PNG", _image("PNG"), "a.png", "image/png"),
            ("WEBP", _image("WEBP"), "a.webp", "image/webp"),
        ):
            with self.subTest(fmt=fmt):
                res = self._upload(data, name, ctype)
                self.assertEqual(res.status_code, 200, res.content[:200])
                self.user.refresh_from_db()
                self.assertTrue(bytes(self.user.avatar_photo).startswith(b"RIFF"))

    def test_other_formats_are_refused_with_400(self):
        cases = [
            ("GIF", _image("GIF"), "a.gif", "image/gif"),
            ("BMP", _image("BMP"), "a.bmp", "image/bmp"),
            ("TIFF", _image("TIFF"), "a.tiff", "image/tiff"),
            ("ICO", _image("ICO"), "a.ico", "image/x-icon"),
            ("PPM", _image("PPM"), "a.ppm", "image/x-portable-pixmap"),
            ("TGA", _image("TGA"), "a.tga", "image/x-tga"),
            ("text", b"just some text, not a picture\n" * 10, "a.png", "image/png"),
            ("empty", b"", "a.png", "image/png"),
        ]
        if features.check("avif"):
            cases.append(("AVIF", _image("AVIF"), "a.avif", "image/avif"))
        for fmt, data, name, ctype in cases:
            with self.subTest(fmt=fmt):
                res = self._upload(data, name, ctype)
                self.assertEqual(res.status_code, 400, res.content[:200])
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar_photo)

    def test_disguised_gif_is_refused(self):
        """이름과 Content-Type 을 PNG 로 속인 GIF 도 400 이다(내용으로 판정)."""
        res = self._upload(_image("GIF"), "a.png", "image/png")
        self.assertEqual(res.status_code, 400)

    def test_png_named_as_jpeg_is_accepted(self):
        """이름이 틀려도 내용이 PNG 면 받는다."""
        res = self._upload(_image("PNG"), "a.jpg", "image/jpeg")
        self.assertEqual(res.status_code, 200)

    def test_truncated_jpeg_is_400(self):
        data = _image("JPEG")
        res = self._upload(data[: len(data) // 2], "a.jpg", "image/jpeg")
        self.assertEqual(res.status_code, 400)

    def test_guest_upload_is_401(self):
        res = self.client.post(
            PHOTO_URL, {"photo": SimpleUploadedFile("a.png", _image("PNG"), content_type="image/png")}
        )
        self.assertEqual(res.status_code, 401)

