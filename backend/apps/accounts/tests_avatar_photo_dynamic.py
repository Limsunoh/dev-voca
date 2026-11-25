"""프로필 사진이 무엇을 받는가를 깨뜨려 본다(models.shrink_avatar_photo, serializers.AvatarPhotoSerializer).

형식별 픽셀 상한 경계, 여러 색 모드, EXIF 회전 1~8, 깨진·가짜 WebP, 확장자·Content-Type 을
속인 파일, 빈 파일, 파일 대신 문자열. 모두 400 이고 500 이 아니며 안내 문구가 맞는가.

메모리를 덜 쓰는 길(열기 전 WebP 검사, 줄여서 펼치기, 원본 복사 없음)은 tests_avatar_photo_memory,
JPEG 표지 판정은 tests_jpeg_one_pass_dynamic, 받는 형식은 tests_security_basics 가 본다.
"""

from __future__ import annotations

import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from PIL import Image, ImageOps

from . import models as account_models
from .models import (
    AVATAR_PHOTO_MAX_PIXELS,
    AVATAR_PHOTO_MAX_PIXELS_UNSCALED,
    AVATAR_PHOTO_SIZE,
    AvatarPhotoError,
    LoginToken,
    shrink_avatar_photo,
)
from .tests import PASSWORD

User = get_user_model()

OLD = "owner.1125@example.com"
PHOTO_URL = "/api/accounts/photo/"


READ_FAIL = "사진 파일을 읽을 수 없습니다."
TOO_BIG = "사진이 너무 큽니다. 다른 사진을 골라주세요."
WRONG_FORMAT = "JPG, PNG, WEBP 사진만 올릴 수 있습니다. 다른 사진을 골라주세요."


def encode(image: Image.Image, fmt: str, **save) -> bytes:
    out = io.BytesIO()
    image.save(out, format=fmt, **save)
    return out.getvalue()


def png16(width: int, height: int, color_type: int, channels: int) -> bytes:
    """비트 깊이 16 인 PNG. 한 줄마다 필터 바이트 0 + 채널당 2바이트."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    row = b"\x00" + b"\x80\x00" * channels * width
    ihdr = struct.pack(">IIBBBBB", width, height, 16, color_type, 0, 0, 0)
    signature = b"\x89PNG\r\n\x1a\n"
    return (
        signature
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )


def decoded(raw: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(raw))
    image.load()
    return image


class PixelLimitEdgeTest(SimpleTestCase):
    """경계 바로 위·아래. 한 번에 풀려 줄여서 펼치는 보통 JPEG 와, 그러지 못하는 그림(PNG·WEBP,
    긴 JPEG, 프로그레시브 JPEG)의 상한이 다르다."""

    # 4000 x 4000 = 16,000,000. 하나 더 넓히면 16,004,000.
    AT = (4000, 4000)
    OVER = (4001, 4000)

    def test_png_정확히_1600만은_받고_넘으면_거절(self):
        self.assertEqual(self.AT[0] * self.AT[1], AVATAR_PHOTO_MAX_PIXELS_UNSCALED)
        at = shrink_avatar_photo(encode(Image.new("L", self.AT), "PNG"))
        self.assertEqual(decoded(at).size, (AVATAR_PHOTO_SIZE, AVATAR_PHOTO_SIZE))
        with self.assertRaisesMessage(AvatarPhotoError, TOO_BIG):
            shrink_avatar_photo(encode(Image.new("L", self.OVER), "PNG"))

    def test_webp_정확히_1600만은_받고_넘으면_열기_전에_거절(self):
        at = encode(Image.new("RGB", self.AT), "WEBP", lossless=True)
        self.assertTrue(shrink_avatar_photo(at).startswith(b"RIFF"))
        over = encode(Image.new("RGB", self.OVER), "WEBP", lossless=True)
        with (
            mock.patch.object(Image, "open", side_effect=AssertionError("열었다")),
            self.assertRaisesMessage(AvatarPhotoError, TOO_BIG),
        ):
            shrink_avatar_photo(over)

    def test_손실_webp_도_머리말로_거절(self):
        """VP8(손실) 머리말은 VP8L 과 크기 자리가 다르다."""
        over = encode(Image.new("RGB", self.OVER), "WEBP", quality=10)
        with (
            mock.patch.object(Image, "open", side_effect=AssertionError("열었다")),
            self.assertRaisesMessage(AvatarPhotoError, TOO_BIG),
        ):
            shrink_avatar_photo(over)

    def test_jpeg_정확히_5천만은_받고_넘으면_거절(self):
        at = (10000, 5000)
        self.assertEqual(at[0] * at[1], AVATAR_PHOTO_MAX_PIXELS)
        self.assertTrue(
            shrink_avatar_photo(encode(Image.new("L", at), "JPEG", quality=5)).startswith(b"RIFF")
        )
        with self.assertRaisesMessage(AvatarPhotoError, TOO_BIG):
            shrink_avatar_photo(encode(Image.new("L", (10001, 5000)), "JPEG", quality=5))

    def test_줄지_않는_긴_jpeg_는_낮은_상한을_쓴다(self):
        """배율은 짧은 변으로 정해진다. 짧은 변이 1024 미만이면 원래 크기로 펼쳐지므로 1,600만이 상한이다."""
        ok = (1023, 15640)
        over = (1023, 15641)
        self.assertLessEqual(ok[0] * ok[1], AVATAR_PHOTO_MAX_PIXELS_UNSCALED)
        self.assertGreater(over[0] * over[1], AVATAR_PHOTO_MAX_PIXELS_UNSCALED)
        self.assertTrue(
            shrink_avatar_photo(encode(Image.new("L", ok), "JPEG", quality=5)).startswith(b"RIFF")
        )
        for size in (over, (49999, 1000)):
            with self.subTest(size=size), self.assertRaisesMessage(AvatarPhotoError, TOO_BIG):
                shrink_avatar_photo(encode(Image.new("L", size), "JPEG", quality=5))

    def test_줄어드는_긴_jpeg_는_5천만_안쪽이면_받는다(self):
        """짧은 변이 2048 이면 1/4 로 펼쳐 300만이 된다."""
        raw = encode(Image.new("L", (2048, 24000), 77), "JPEG", quality=5)
        self.assertTrue(shrink_avatar_photo(raw).startswith(b"RIFF"))

    def test_보통_jpeg_는_1600만_초과도_받는다(self):
        raw = encode(Image.new("RGB", self.OVER, (10, 20, 30)), "JPEG", quality=20)
        self.assertTrue(shrink_avatar_photo(raw).startswith(b"RIFF"))

    def test_가드_webp_머리말_검사를_빼면_열어서야_거절한다(self):
        """머리말 검사가 실제로 먼저 거르는지. 상한을 크게 잡아 무력화하면 Image.open 에 닿는다."""
        over = encode(Image.new("RGB", self.OVER), "WEBP", lossless=True)
        with (
            mock.patch.object(account_models, "AVATAR_PHOTO_MAX_PIXELS_UNSCALED", 10**12),
            mock.patch.object(Image, "open", side_effect=AssertionError("열었다")),
            self.assertRaisesMessage(AssertionError, "열었다"),
        ):
            shrink_avatar_photo(over)


class ModesTest(SimpleTestCase):
    """색 모드가 달라도 500 없이 256 정사각 WebP 가 나온다."""

    def assert_ok(self, raw: bytes) -> Image.Image:
        out = decoded(shrink_avatar_photo(raw))
        self.assertEqual(out.format, "WEBP")
        self.assertEqual(out.size, (AVATAR_PHOTO_SIZE, AVATAR_PHOTO_SIZE))
        return out

    def test_cmyk_jpeg(self):
        self.assert_ok(encode(Image.new("CMYK", (900, 700), (0, 255, 0, 0)), "JPEG"))

    def test_흑백_jpeg_png(self):
        self.assert_ok(encode(Image.new("L", (700, 900), 128), "JPEG"))
        self.assert_ok(encode(Image.new("L", (700, 900), 128), "PNG"))
        self.assert_ok(encode(Image.new("1", (300, 300), 1), "PNG"))

    def test_16비트_png(self):
        self.assert_ok(encode(Image.new("I;16", (600, 400), 40000), "PNG"))
        # Pillow 는 16비트 컬러 PNG 를 못 쓴다. 직접 만든다(색 형식 2=RGB, 6=RGBA).
        for color_type, channels in ((2, 3), (6, 4)):
            with self.subTest(color_type=color_type):
                self.assert_ok(png16(300, 200, color_type, channels))

    def test_팔레트_png_투명색_포함(self):
        image = Image.new("P", (500, 500), 0)
        image.putpalette([255, 0, 0, 0, 0, 255] + [0] * 762)
        image.paste(1, (250, 0, 500, 500))
        out = self.assert_ok(encode(image, "PNG", transparency=0))
        # 투명했던 쪽은 투명하게 남는다.
        self.assertEqual(out.getpixel((10, 128))[3], 0)

    def test_투명_webp(self):
        image = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        image.paste((0, 200, 0, 255), (200, 0, 400, 400))
        out = self.assert_ok(encode(image, "WEBP", lossless=True))
        self.assertEqual(out.getpixel((10, 128))[3], 0)
        self.assertEqual(out.getpixel((250, 128))[3], 255)

    def test_애니메이션_webp_는_첫_장으로(self):
        frames = [Image.new("RGB", (300, 300), c) for c in ((250, 0, 0), (0, 0, 250))]
        raw = encode(
            frames[0], "WEBP", save_all=True, append_images=frames[1:], duration=100, lossless=True
        )
        out = self.assert_ok(raw).convert("RGB")
        self.assertGreater(out.getpixel((128, 128))[0], 200)

    def test_애니메이션_webp_도_캔버스_크기로_거절(self):
        frames = [Image.new("RGB", (4001, 4000)), Image.new("RGB", (4001, 4000), (1, 1, 1))]
        raw = encode(frames[0], "WEBP", save_all=True, append_images=frames[1:], lossless=True)
        with self.assertRaisesMessage(AvatarPhotoError, TOO_BIG):
            shrink_avatar_photo(raw)


class ExifOrientationTest(SimpleTestCase):
    """EXIF 회전 1~8. 왼쪽 위 사분면만 빨강인 그림이 돌린 뒤 어디로 가는지 본다."""

    # 원본(가로 400x200)의 빨강 사분면이 각 Orientation 을 적용한 뒤 어느 쪽에 오는가.
    # ImageOps.exif_transpose 를 그대로 기대값으로 쓴다(Pillow 가 정한 뜻을 따른다).
    def sample(self, fmt: str, orientation: int) -> tuple[bytes, Image.Image]:
        image = Image.new("RGB", (400, 200), (0, 0, 220))
        image.paste((220, 0, 0), (0, 0, 200, 100))
        exif = Image.Exif()
        exif[0x0112] = orientation
        raw = encode(image, fmt, exif=exif)
        expected = ImageOps.exif_transpose(decoded(raw))
        return raw, ImageOps.fit(expected, (AVATAR_PHOTO_SIZE, AVATAR_PHOTO_SIZE))

    def test_회전_1에서_8까지(self):
        corners = [
            (20, 20),
            (AVATAR_PHOTO_SIZE - 20, 20),
            (20, AVATAR_PHOTO_SIZE - 20),
            (AVATAR_PHOTO_SIZE - 20, AVATAR_PHOTO_SIZE - 20),
        ]
        for fmt in ("JPEG", "PNG", "WEBP"):
            for orientation in range(1, 9):
                with self.subTest(fmt=fmt, orientation=orientation):
                    raw, expected = self.sample(fmt, orientation)
                    out = decoded(shrink_avatar_photo(raw)).convert("RGB")
                    for corner in corners:
                        red_out = out.getpixel(corner)[0] > 150
                        red_expected = expected.getpixel(corner)[0] > 150
                        self.assertEqual(red_out, red_expected, corner)

    def test_회전값이_엉뚱해도_500_이_아니다(self):
        for value in (0, 9, 65535):
            with self.subTest(value=value):
                image = Image.new("RGB", (300, 200), (1, 2, 3))
                exif = Image.Exif()
                exif[0x0112] = value
                self.assertTrue(
                    shrink_avatar_photo(encode(image, "JPEG", exif=exif)).startswith(b"RIFF")
                )


class BrokenAndFakeFilesTest(SimpleTestCase):
    def test_머리말은_webp_인데_내용이_깨졌다(self):
        good = encode(Image.new("RGB", (300, 300), (5, 6, 7)), "WEBP", quality=80)
        broken = good[:40] + bytes(len(good) - 40)
        with self.assertRaisesMessage(AvatarPhotoError, READ_FAIL):
            shrink_avatar_photo(broken)

    def test_webp_가_중간에_잘렸다(self):
        good = encode(Image.new("RGB", (300, 300), (5, 6, 7)), "WEBP", quality=80)
        with self.assertRaises(AvatarPhotoError):
            shrink_avatar_photo(good[: len(good) // 2])

    def test_riff_머리말만_맞춘_가짜(self):
        cases = {
            "청크 없음": b"RIFF\x00\x00\x00\x00WEBP",
            "VP8 인데 시작 부호 틀림": b"RIFF" + bytes(4) + b"WEBPVP8 " + bytes(40),
            "VP8L 인데 서명 틀림": b"RIFF" + bytes(4) + b"WEBPVP8L" + bytes(40),
            "VP8X 머리말만": b"RIFF" + bytes(4) + b"WEBPVP8X" + bytes(18),
            "WAVE": b"RIFF" + bytes(4) + b"WAVEfmt " + bytes(40),
        }
        for name, raw in cases.items():
            with self.subTest(name):
                with self.assertRaises(AvatarPhotoError):
                    shrink_avatar_photo(raw)

    def test_vp8x_가_작다고_하고_속은_크면(self):
        """VP8X 캔버스는 1x1 이라 적고 안의 VP8L 은 4001x4000 이다. 500 이나 큰 펼침 없이 거절."""
        inner = encode(Image.new("RGB", (4001, 4000)), "WEBP", lossless=True)
        vp8l = inner[12:]  # "VP8L" 청크부터
        vp8x = b"VP8X" + (10).to_bytes(4, "little") + bytes(4) + bytes(3) + bytes(3)
        body = b"WEBP" + vp8x + vp8l
        raw = b"RIFF" + len(body).to_bytes(4, "little") + body
        with self.assertRaises(AvatarPhotoError):
            shrink_avatar_photo(raw)

    def test_빈_파일과_이미지_아닌_파일(self):
        with self.assertRaisesMessage(AvatarPhotoError, "비어 있습니다"):
            shrink_avatar_photo(b"")
        with self.assertRaisesMessage(AvatarPhotoError, WRONG_FORMAT):
            shrink_avatar_photo(b"%PDF-1.4 not a photo")

    def test_받지_않는_형식(self):
        for fmt in ("GIF", "BMP", "TIFF", "ICO"):
            with self.subTest(fmt=fmt):
                with self.assertRaisesMessage(AvatarPhotoError, WRONG_FORMAT):
                    shrink_avatar_photo(encode(Image.new("RGB", (64, 64)), fmt))


class PhotoUploadApiTest(TestCase):
    """엔드포인트로 직접. 무엇을 보내도 400 이고 500 이 아니다."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email=OLD, password=PASSWORD)
        self.login = LoginToken.objects.create(user=self.user)

    def upload(self, data, **extra):
        return self.client.post(
            PHOTO_URL, data, HTTP_AUTHORIZATION=f"Token {self.login.key}", **extra
        )

    def assert_photo_error(self, res, message: str):
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(res.json()["photo"], [message])
        self.user.refresh_from_db()
        self.assertIsNone(self.user.avatar_photo)

    def test_로그인_없이는_401(self):
        png = encode(Image.new("RGB", (64, 64)), "PNG")
        res = self.client.post(PHOTO_URL, {"photo": SimpleUploadedFile("a.png", png, "image/png")})
        self.assertEqual(res.status_code, 401)

    def test_정상_jpeg_는_저장된다(self):
        raw = encode(Image.new("RGB", (800, 600), (1, 2, 3)), "JPEG")
        res = self.upload({"photo": SimpleUploadedFile("a.jpg", raw, "image/jpeg")})
        self.assertEqual(res.status_code, 200, res.content)
        self.user.refresh_from_db()
        self.assertTrue(bytes(self.user.avatar_photo).startswith(b"RIFF"))

    def test_확장자와_content_type_을_속인_파일(self):
        res = self.upload(
            {"photo": SimpleUploadedFile("cat.jpg", b"#!/bin/sh\necho hi\n", "image/jpeg")}
        )
        self.assert_photo_error(res, WRONG_FORMAT)

    def test_gif_를_jpg_로_속였다(self):
        gif = encode(Image.new("RGB", (64, 64)), "GIF")
        res = self.upload({"photo": SimpleUploadedFile("cat.jpg", gif, "image/jpeg")})
        self.assert_photo_error(res, WRONG_FORMAT)

    def test_png_를_txt_로_보내도_사진으로_받는다(self):
        png = encode(Image.new("RGB", (64, 64), (9, 9, 9)), "PNG")
        res = self.upload({"photo": SimpleUploadedFile("note.txt", png, "text/plain")})
        self.assertEqual(res.status_code, 200, res.content)

    def test_빈_파일(self):
        res = self.upload({"photo": SimpleUploadedFile("a.png", b"", "image/png")})
        self.assertEqual(res.status_code, 400)
        self.assertIn("photo", res.json())

    def test_파일_대신_문자열(self):
        res = self.upload({"photo": "not-a-file"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("photo", res.json())

    def test_photo_없음(self):
        res = self.upload({})
        self.assertEqual(res.status_code, 400)
        self.assertIn("photo", res.json())

    def test_json_으로_보내면_415(self):
        res = self.upload({"photo": "x"}, content_type="application/json")
        self.assertEqual(res.status_code, 415)

    def test_큰_png_는_너무_크다는_안내(self):
        raw = encode(Image.new("L", (4001, 4000)), "PNG")
        res = self.upload({"photo": SimpleUploadedFile("a.png", raw, "image/png")})
        self.assert_photo_error(res, TOO_BIG)

    def test_큰_webp_는_열기_전에_너무_크다는_안내(self):
        raw = encode(Image.new("RGB", (4001, 4000)), "WEBP", lossless=True)
        with mock.patch.object(Image, "open", side_effect=AssertionError("열었다")):
            res = self.upload({"photo": SimpleUploadedFile("a.webp", raw, "image/webp")})
        self.assert_photo_error(res, TOO_BIG)

    def test_업로드_필드가_pillow_로_미리_열지_않는다(self):
        """ImageField 였으면 serializer 가 먼저 Image.open 을 부른다. 한 번(shrink)만 열어야 한다."""
        raw = encode(Image.new("RGB", (64, 64), (9, 9, 9)), "PNG")
        with mock.patch.object(Image, "open", wraps=Image.open) as opened:
            res = self.upload({"photo": SimpleUploadedFile("a.png", raw, "image/png")})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(opened.call_count, 1)
