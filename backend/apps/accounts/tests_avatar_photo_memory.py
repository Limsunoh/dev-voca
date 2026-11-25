"""프로필 사진을 줄일 때 큰 그림이 메모리를 크게 쓰지 않는가(models.shrink_avatar_photo).

상한 끝의 그림 한 장이 서버 메모리를 수백 MB 씩 썼다. 한 번에 풀리는 JPEG 는 줄여서
펼치고(draft), 그러지 못하는 그림(PNG·WEBP, 긴 JPEG, 프로그레시브 등)은 상한을 낮췄고,
WebP 는 여는 순간 캔버스를 잡으므로 열기 전에 머리말로 크기를 본다. 메모리 자체는 테스트로 재기 어려워서, 그렇게 되는 길을
본다(열지 않았나, 줄여서 펼쳤나).

받는 형식(JPEG, PNG, WEBP 만)은 tests_security_basics 의 AvatarFormatTest 가 본다.
경계·색 모드·회전·깨진 파일은 tests_avatar_photo_dynamic, JPEG 표지 판정의 여러 조합과
퍼징은 tests_jpeg_one_pass_dynamic 이 본다.
"""

from __future__ import annotations

import io
from unittest import mock

from django.test import SimpleTestCase
from PIL import Image, ImageOps, WebPImagePlugin

from .models import (
    AVATAR_PHOTO_MAX_PIXELS,
    AVATAR_PHOTO_MAX_PIXELS_UNSCALED,
    AVATAR_PHOTO_SIZE,
    AvatarPhotoError,
    _jpeg_decodes_in_one_pass,
    shrink_avatar_photo,
)


def encode(image: Image.Image, fmt: str, **save) -> bytes:
    out = io.BytesIO()
    image.save(out, format=fmt, **save)
    return out.getvalue()


def fitted_size(raw: bytes) -> tuple[int, int]:
    """shrink 가 정사각형으로 자르기 직전 그림의 크기. 줄여서 펼쳤는지 본다."""
    with mock.patch.object(ImageOps, "fit", wraps=ImageOps.fit) as fit:
        shrink_avatar_photo(raw)
    return fit.call_args.args[0].size


# 상한을 조금 넘는 크기. 한 색이라 파일은 작다.
OVER_UNSCALED = (4100, 4000)
assert OVER_UNSCALED[0] * OVER_UNSCALED[1] > AVATAR_PHOTO_MAX_PIXELS_UNSCALED


class WebpCheckedBeforeOpenTest(SimpleTestCase):
    def test_큰_webp_는_캔버스를_잡기_전에_거절한다(self):
        raw = encode(Image.new("RGB", OVER_UNSCALED), "WEBP", lossless=True)

        with (
            mock.patch.object(
                WebPImagePlugin._webp, "WebPAnimDecoder", side_effect=AssertionError("열었다")
            ) as decoder,
            self.assertRaisesMessage(AvatarPhotoError, "너무 큽니다"),
        ):
            shrink_avatar_photo(raw)
        decoder.assert_not_called()

    def test_머리말로_크기를_못_읽는_webp_는_받지_않는다(self):
        raw = b"RIFF" + (200).to_bytes(4, "little") + b"WEBP" + b"ABCD" + bytes(200)

        with self.assertRaisesMessage(AvatarPhotoError, "읽을 수 없습니다"):
            shrink_avatar_photo(raw)

    def test_상한_안쪽_webp_는_받는다(self):
        for save in ({"lossless": True}, {"quality": 80}):
            with self.subTest(**save):
                raw = encode(Image.new("RGB", (640, 480), (1, 2, 3)), "WEBP", **save)
                self.assertTrue(shrink_avatar_photo(raw).startswith(b"RIFF"))


class PixelLimitByFormatTest(SimpleTestCase):
    def test_png_는_낮은_상한에_걸린다(self):
        raw = encode(Image.new("L", OVER_UNSCALED), "PNG")

        with self.assertRaisesMessage(AvatarPhotoError, "너무 큽니다"):
            shrink_avatar_photo(raw)

    def test_보통_jpeg_는_5천만까지_받고_줄여서_펼친다(self):
        size = (8000, 6000)
        self.assertLess(size[0] * size[1], AVATAR_PHOTO_MAX_PIXELS)
        self.assertGreater(size[0] * size[1], AVATAR_PHOTO_MAX_PIXELS_UNSCALED)
        raw = encode(Image.new("RGB", size, (40, 80, 120)), "JPEG", quality=30)

        width, height = fitted_size(raw)

        # 1/8 로 펼쳤다. 짧은 변은 여전히 저장 크기의 두 배 이상이라 화질은 그대로다.
        self.assertEqual((width, height), (1000, 750))
        self.assertGreaterEqual(min(width, height), AVATAR_PHOTO_SIZE * 2)

    def test_mpo_도_jpeg_처럼_5천만까지_받고_줄여서_펼친다(self):
        first = Image.new("RGB", (8000, 6000), (9, 9, 9))
        raw = encode(first, "MPO", save_all=True, append_images=[Image.new("RGB", (64, 64))])
        with Image.open(io.BytesIO(raw)) as opened:
            self.assertEqual(opened.format, "MPO")

        self.assertLess(max(fitted_size(raw)), 8000)

    def test_줄지_않는_아주_긴_jpeg_는_거절한다(self):
        """배율은 짧은 변으로 정해진다. 짧은 변이 1024 보다 작으면 원래 크기로 펼친다."""
        size = (20000, 900)
        self.assertLess(size[0] * size[1], AVATAR_PHOTO_MAX_PIXELS)
        self.assertGreater(size[0] * size[1], AVATAR_PHOTO_MAX_PIXELS_UNSCALED)
        raw = encode(Image.new("RGB", size, (40, 80, 120)), "JPEG", quality=30)

        with self.assertRaisesMessage(AvatarPhotoError, "너무 큽니다"):
            shrink_avatar_photo(raw)

    def test_줄어드는_파노라마는_받는다(self):
        raw = encode(Image.new("RGB", (16000, 3000), (40, 80, 120)), "JPEG", quality=30)

        self.assertEqual(fitted_size(raw), (4000, 750))

    def test_작은_사진은_줄이지_않고_그대로_펼친다(self):
        raw = encode(Image.new("RGB", (600, 600), (1, 2, 3)), "JPEG")

        self.assertEqual(fitted_size(raw), (600, 600))


class ExifRotationTest(SimpleTestCase):
    """회전 표시(EXIF Orientation)가 있는 폰 사진은 돌려서 저장한다. 제자리에서 돌린다."""

    def sample(self, fmt: str) -> bytes:
        # 왼쪽 절반 빨강, 오른쪽 절반 파랑인 가로 그림. 6 은 "시계 방향으로 90도 돌려 보라".
        image = Image.new("RGB", (400, 200), (220, 0, 0))
        image.paste((0, 0, 220), (200, 0, 400, 200))
        exif = Image.Exif()
        exif[0x0112] = 6
        return encode(image, fmt, exif=exif)

    def test_돌린_뒤에_자른다(self):
        for fmt in ("JPEG", "PNG", "WEBP"):
            with self.subTest(fmt=fmt):
                out = shrink_avatar_photo(self.sample(fmt))
                with Image.open(io.BytesIO(out)) as image:
                    image = image.convert("RGB")
                    top = image.getpixel((AVATAR_PHOTO_SIZE // 2, 10))
                    bottom = image.getpixel((AVATAR_PHOTO_SIZE // 2, AVATAR_PHOTO_SIZE - 10))
                # 돌리면 빨강이 위, 파랑이 아래로 간다. 안 돌렸으면 가운데 세로줄이 모두 파랑이다.
                self.assertGreater(top[0], 150)
                self.assertGreater(bottom[2], 150)

    def test_회전_표시가_없으면_원본을_복사하지_않는다(self):
        raw = encode(Image.new("RGB", (600, 600), (1, 2, 3)), "PNG")

        with mock.patch.object(Image.Image, "copy", side_effect=AssertionError("복사했다")):
            self.assertTrue(shrink_avatar_photo(raw).startswith(b"RIFF"))


class ProgressiveJpegTest(SimpleTestCase):
    """프로그레시브 JPEG 는 줄여서 펼쳐도 해석기가 원래 크기의 버퍼를 잡는다."""

    def test_프로그레시브는_원래_크기로_낮은_상한을_쓴다(self):
        raw = encode(Image.new("CMYK", OVER_UNSCALED), "JPEG", quality=5, progressive=True)
        with Image.open(io.BytesIO(raw)) as opened:
            self.assertTrue(opened.info.get("progressive"))

        with self.assertRaisesMessage(AvatarPhotoError, "너무 큽니다"):
            shrink_avatar_photo(raw)

    def test_같은_크기의_보통_jpeg_는_받는다(self):
        raw = encode(Image.new("CMYK", OVER_UNSCALED), "JPEG", quality=5)

        self.assertTrue(shrink_avatar_photo(raw).startswith(b"RIFF"))

    def test_상한_안쪽_프로그레시브는_받는다(self):
        raw = encode(Image.new("RGB", (2000, 1500), (1, 2, 3)), "JPEG", progressive=True)

        self.assertTrue(shrink_avatar_photo(raw).startswith(b"RIFF"))


def handmade_jpeg(width: int, height: int, *, sof: int, scan_components: int) -> bytes:
    """표지만 있는 CMYK JPEG. Pillow 로는 성분을 스캔마다 나눈 JPEG 를 쓸 수 없어 손으로 짠다.

    크기 검사는 펼치기 전에 끝나므로 표지만으로 충분하다. 검사를 지나면 펼치다가
    "읽을 수 없습니다" 로 끝난다.
    """
    frame = bytes([8]) + height.to_bytes(2, "big") + width.to_bytes(2, "big") + bytes([4])
    frame += b"".join(bytes([n, 0x11, 0]) for n in range(1, 5))
    scan = bytes([scan_components]) + b"".join(bytes([n, 0]) for n in range(1, scan_components + 1))
    scan += bytes([0, 63, 0])
    return (
        b"\xff\xd8"
        + bytes([0xFF, sof])
        + (2 + len(frame)).to_bytes(2, "big")
        + frame
        + b"\xff\xda"
        + (2 + len(scan)).to_bytes(2, "big")
        + scan
        + bytes(64)
        + b"\xff\xd9"
    )


class MultiScanJpegTest(SimpleTestCase):
    """한 번에 풀지 못하는 JPEG 는 원래 크기로 낮은 상한을 쓴다(models._jpeg_decodes_in_one_pass)."""

    def test_성분을_스캔마다_나눈_보통_jpeg_는_원래_크기로_본다(self):
        raw = handmade_jpeg(*OVER_UNSCALED, sof=0xC0, scan_components=1)
        with Image.open(io.BytesIO(raw)) as opened:
            self.assertEqual((opened.format, opened.mode), ("JPEG", "CMYK"))
            self.assertFalse(opened.info.get("progressive"))

        with self.assertRaisesMessage(AvatarPhotoError, "너무 큽니다"):
            shrink_avatar_photo(raw)

    def test_첫_스캔에_성분이_다_있으면_줄여서_본다(self):
        raw = handmade_jpeg(*OVER_UNSCALED, sof=0xC0, scan_components=4)

        # 크기 검사는 지나고, 표지만 있는 파일이라 펼치다가 끝난다.
        with self.assertRaisesMessage(AvatarPhotoError, "읽을 수 없습니다"):
            shrink_avatar_photo(raw)

    def test_sof0_sof1_이_아닌_방식은_원래_크기로_본다(self):
        for sof in (0xC2, 0xC3, 0xC9):  # 프로그레시브, 무손실, 산술 부호화 순차
            with self.subTest(sof=hex(sof)):
                raw = handmade_jpeg(*OVER_UNSCALED, sof=sof, scan_components=4)
                with self.assertRaisesMessage(AvatarPhotoError, "너무 큽니다"):
                    shrink_avatar_photo(raw)

    def test_exif_안의_작은_jpeg_에_속지_않는다(self):
        """폰 사진은 EXIF 안에 작은 JPEG 를 품는다. 그 안의 스캔 표지를 본문으로 읽으면 안 된다."""
        body = encode(Image.new("RGB", (640, 480), (1, 2, 3)), "JPEG")
        inner = b"Exif\x00\x00" + b"\xff\xd8\xff\xc2\x00\x11" + bytes(15) + b"\xff\xda\x00\x08\x01"
        app1 = b"\xff\xe1" + (2 + len(inner)).to_bytes(2, "big") + inner
        raw = body[:2] + app1 + body[2:]

        self.assertTrue(_jpeg_decodes_in_one_pass(raw))
        self.assertTrue(shrink_avatar_photo(raw).startswith(b"RIFF"))
