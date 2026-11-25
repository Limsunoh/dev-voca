"""JPEG 를 한 번에 풀 수 있는지 가르는 판정을 깨뜨려 본다(models._jpeg_decodes_in_one_pass).

판정이 True 면 shrink_avatar_photo 는 줄여 펼친(draft) 크기로 1,600만 상한을 보고, False 면
원래 크기로 본다. True 를 잘못 내면 프로그레시브·성분별 스캔 JPEG 가 원래 크기의 버퍼를 잡은
채 상한을 지나가고, False 를 잘못 내면 평범한 고화소 폰 사진이 거절된다. 그래서 두 쪽을 다 본다.

판정 함수 자체는 여기서 본다. 모드·저장 옵션 조합, 손으로 짠 표지(길이 없는 표지 뒤에 숨긴 가짜
스캔 포함), 무작위로 흔든 머리말이다. shrink_avatar_photo 가 판정에 따라 상한을 실제로 거는지는
tests_avatar_photo_memory 가 본다.
"""

from __future__ import annotations

import io
import random
import struct
import warnings

from django.test import SimpleTestCase
from PIL import ExifTags, Image

from . import models
from .models import AVATAR_PHOTO_MAX_PIXELS_UNSCALED, AvatarPhotoError, shrink_avatar_photo


# 모듈 속성으로 부른다. 판정을 mock.patch.object(models, ...) 로 바꿔 끼워 이 테스트가 무는지
# 볼 때 이 파일의 호출과 shrink 안의 호출이 함께 바뀐다.
def one_pass(raw: bytes) -> bool:
    return models._jpeg_decodes_in_one_pass(raw)


def encode(image: Image.Image, fmt: str = "JPEG", **save) -> bytes:
    out = io.BytesIO()
    image.save(out, format=fmt, **save)
    return out.getvalue()


def seg(marker: int, payload: bytes) -> bytes:
    """길이를 가진 표지 하나. 길이는 길이 칸 두 바이트를 포함한다."""
    return bytes([0xFF, marker]) + (2 + len(payload)).to_bytes(2, "big") + payload


def sof(marker: int = 0xC0, nf: int = 3, width: int = 64, height: int = 64) -> bytes:
    body = bytes([8]) + height.to_bytes(2, "big") + width.to_bytes(2, "big") + bytes([nf])
    body += b"".join(bytes([n, 0x11, 0]) for n in range(1, nf + 1))
    return seg(marker, body)


def sos(ns: int) -> bytes:
    return seg(
        0xDA, bytes([ns]) + b"".join(bytes([n, 0]) for n in range(1, ns + 1)) + b"\x00\x3f\x00"
    )


SOI = b"\xff\xd8"
TAIL = bytes(64) + b"\xff\xd9"


def exif_with_thumbnail(thumb: bytes) -> bytes:
    """IFD1 에 JPEG 썸네일을 담은 Exif. Pillow 가 IFD1 로 읽어 내는 꼴이다."""
    ifd0 = struct.pack("<H", 1) + struct.pack("<HHII", 0x0112, 3, 1, 1) + struct.pack("<I", 26)
    ifd1 = (
        struct.pack("<H", 2)
        + struct.pack("<HHII", 0x0201, 4, 1, 56)
        + struct.pack("<HHII", 0x0202, 4, 1, len(thumb))
        + struct.pack("<I", 0)
    )
    return b"Exif\x00\x00" + b"II*\x00" + struct.pack("<I", 8) + ifd0 + ifd1 + thumb


def pillow_first_scan(raw: bytes) -> tuple[int, int, bool] | None:
    """Pillow 가 연 파일의 (첫 스캔 성분 수, 프레임 성분 수, 프로그레시브 여부).

    Pillow 의 JPEG _open 은 첫 스캔 표지(SOS)를 길이대로 읽은 자리에서 멈춘다. 그 자리
    (fp.tell())에서 끝나는 SOS 를 거꾸로 찾아 성분 수를 읽는다. 못 열면 None.
    """
    try:
        with warnings.catch_warnings(), Image.open(io.BytesIO(raw), formats=("JPEG",)) as image:
            warnings.simplefilter("ignore")
            if image.format != "JPEG":
                return None
            end = image.fp.tell()
            layers = image.layers
            progressive = bool(image.info.get("progressive"))
    except Exception:
        return None
    start = end
    while True:
        start = raw.rfind(b"\xff\xda", 0, start)
        if start < 0:
            return None
        if start + 2 + int.from_bytes(raw[start + 2 : start + 4], "big") == end:
            return raw[start + 4], layers, progressive


# 상한을 조금 넘는 크기. 한 색이라 파일은 작다.
OVER_UNSCALED = (4100, 4000)
assert OVER_UNSCALED[0] * OVER_UNSCALED[1] > AVATAR_PHOTO_MAX_PIXELS_UNSCALED


class PillowWrittenJpegTest(SimpleTestCase):
    """Pillow 가 쓰는 보통 JPEG 는 저장 옵션이 무엇이든 한 번에 풀리는 것으로 본다."""

    def assert_one_pass_and_shrinks(self, raw: bytes) -> None:
        self.assertTrue(one_pass(raw))
        self.assertTrue(shrink_avatar_photo(raw).startswith(b"RIFF"))

    def test_모드와_서브샘플링과_화질을_바꿔도_한_번에_풀린다(self):
        for mode in ("RGB", "L", "CMYK", "YCbCr"):
            for subsampling in (0, 1, 2):  # 4:4:4, 4:2:2, 4:2:0
                for quality in (1, 50, 95):
                    for optimize in (False, True):
                        with self.subTest(mode=mode, ss=subsampling, q=quality, opt=optimize):
                            raw = encode(
                                Image.new(mode, (64, 48)),
                                subsampling=subsampling,
                                quality=quality,
                                optimize=optimize,
                            )
                            self.assert_one_pass_and_shrinks(raw)

    def test_16비트_양자화표의_sof1_도_한_번에_풀린다(self):
        raw = encode(Image.new("RGB", (64, 48)), qtables=[[300] * 64])
        self.assertIn(b"\xff\xc1", raw)
        self.assertNotIn(b"\xff\xc0", raw)
        self.assert_one_pass_and_shrinks(raw)

    def test_restart_표지를_쓴_jpeg_도_한_번에_풀린다(self):
        for save in ({"restart_marker_blocks": 1}, {"restart_marker_rows": 1}):
            with self.subTest(**save):
                raw = encode(Image.new("RGB", (64, 48), (1, 2, 3)), **save)
                self.assertIn(b"\xff\xdd", raw)
                self.assert_one_pass_and_shrinks(raw)

    def test_여러_app2_로_나뉜_큰_icc_프로파일도_건너뛴다(self):
        icc = random.Random(1).randbytes(200_000)
        raw = encode(Image.new("RGB", (64, 48)), icc_profile=icc)
        self.assertGreaterEqual(raw.count(b"\xff\xe2"), 4)
        self.assert_one_pass_and_shrinks(raw)

    def test_주석과_xmp_가_있어도_한_번에_풀린다(self):
        raw = encode(Image.new("RGB", (64, 48)), comment=b"\xff\xda\x00\x08\x01", xmp=b"<x/>" * 100)
        self.assert_one_pass_and_shrinks(raw)

    def test_mpo_도_첫_장으로_판정한다(self):
        raw = encode(
            Image.new("RGB", (64, 48)),
            "MPO",
            save_all=True,
            append_images=[Image.new("L", (32, 32))],
        )
        with Image.open(io.BytesIO(raw)) as opened:
            self.assertEqual(opened.format, "MPO")
        self.assert_one_pass_and_shrinks(raw)

    def test_exif_썸네일이_프로그레시브여도_본문으로_판정한다(self):
        """EXIF 속 썸네일의 SOF2·SOS 를 본문으로 읽으면 False 가 나와 고화소 사진이 거절된다."""
        thumb = encode(Image.new("L", (16, 16)), progressive=True)
        raw = encode(Image.new("RGB", (64, 48)), exif=exif_with_thumbnail(thumb))
        with Image.open(io.BytesIO(raw)) as opened:
            self.assertEqual(dict(opened.getexif().get_ifd(ExifTags.IFD.IFD1))[0x0202], len(thumb))
        self.assertLess(raw.find(b"\xff\xc2"), raw.find(b"\xff\xc0"))
        self.assert_one_pass_and_shrinks(raw)

    def test_상한을_넘는_보통_jpeg_는_옵션이_있어도_줄여서_받는다(self):
        """True 가 실제로 쓰이는지. False 로 떨어지면 이 크기는 거절된다."""
        thumb = encode(Image.new("L", (16, 16)), progressive=True)
        cases = {
            "exif썸네일": ("JPEG", {"exif": exif_with_thumbnail(thumb)}),
            "icc": ("JPEG", {"icc_profile": random.Random(2).randbytes(100_000)}),
            "dri": ("JPEG", {"restart_marker_rows": 4}),
            "sof1": ("JPEG", {"qtables": [[300] * 64]}),
            "mpo": ("MPO", {"save_all": True, "append_images": [Image.new("L", (8, 8))]}),
        }
        for name, (fmt, save) in cases.items():
            with self.subTest(name):
                raw = encode(Image.new("L", OVER_UNSCALED), fmt, quality=5, **save)
                self.assert_one_pass_and_shrinks(raw)


class ProgressiveAllModesTest(SimpleTestCase):
    def test_프로그레시브는_모드와_무관하게_원래_크기로_본다(self):
        for mode in ("RGB", "L", "CMYK", "YCbCr"):
            with self.subTest(mode=mode):
                small = encode(Image.new(mode, (64, 48)), progressive=True)
                self.assertFalse(one_pass(small))

                raw = encode(Image.new(mode, OVER_UNSCALED), quality=5, progressive=True)
                with self.assertRaisesMessage(AvatarPhotoError, "너무 큽니다"):
                    shrink_avatar_photo(raw)

    def test_프로그레시브_mpo_도_원래_크기로_본다(self):
        raw = encode(
            Image.new("L", OVER_UNSCALED),
            "MPO",
            quality=5,
            progressive=True,
            save_all=True,
            append_images=[Image.new("L", (8, 8))],
        )
        self.assertFalse(one_pass(raw))
        with self.assertRaisesMessage(AvatarPhotoError, "너무 큽니다"):
            shrink_avatar_photo(raw)


class HandmadeMarkerTest(SimpleTestCase):
    """손으로 짠 표지. 모두 예외 없이 bool 을 돌려줘야 한다."""

    def check(self, raw: bytes, expected: bool) -> None:
        result = one_pass(raw)
        self.assertIs(result, expected)

    def test_기준_첫_스캔에_성분이_다_있으면_true(self):
        for marker in (0xC0, 0xC1):
            for nf in (1, 3, 4):
                with self.subTest(sof=hex(marker), nf=nf):
                    self.check(SOI + sof(marker, nf) + sos(nf) + TAIL, True)

    def test_성분을_나눈_첫_스캔은_false(self):
        for nf, ns in ((3, 1), (3, 2), (4, 1), (4, 3), (1, 2), (3, 4)):
            with self.subTest(nf=nf, ns=ns):
                self.check(SOI + sof(0xC0, nf) + sos(ns) + TAIL, False)

    def test_sof0_sof1_이_아닌_sof_는_모두_false(self):
        for marker in (0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            with self.subTest(sof=hex(marker)):
                self.check(SOI + sof(marker, 3) + sos(3) + TAIL, False)

    def test_sof_보다_스캔이_먼저면_false(self):
        self.check(SOI + sos(3) + sof(0xC0, 3) + sos(3) + TAIL, False)
        self.check(SOI + seg(0xDB, bytes(65)) + sos(1) + TAIL, False)

    def test_sof_가_둘이면_뒤가_프로그레시브일_때_false(self):
        self.check(SOI + sof(0xC0, 3) + sof(0xC2, 3) + sos(3) + TAIL, False)
        self.check(SOI + sof(0xC2, 3) + sof(0xC0, 3) + sos(3) + TAIL, False)

    def test_sof_가_둘인_실제_파일은_해석기가_거절한다(self):
        """판정은 뒤 SOF 로 True 를 낼 수 있지만, libjpeg 가 SOF 중복을 펼치기 전에 거절한다."""
        raw = encode(Image.new("RGB", (64, 48), (1, 2, 3)))
        at = raw.index(b"\xff\xc0")
        frame = raw[at : at + 2 + int.from_bytes(raw[at + 2 : at + 4], "big")]
        dup = raw[:at] + frame + raw[at:]
        with self.assertRaisesMessage(AvatarPhotoError, "읽을 수 없습니다"):
            shrink_avatar_photo(dup)

    def test_길이가_0_1_거대값인_세그먼트는_false(self):
        for length in (b"\x00\x00", b"\x00\x01", b"\xff\xff", b"\x7f\xff"):
            for marker in (0xE0, 0xFE, 0xDB, 0xC4, 0xDD):
                with self.subTest(length=length.hex(), marker=hex(marker)):
                    bad = bytes([0xFF, marker]) + length
                    self.check(SOI + bad + sof(0xC0, 3) + sos(3) + TAIL, False)
                    self.check(SOI + sof(0xC0, 3) + bad + sos(3) + TAIL, False)

    def test_길이_없는_표지와_모르는_표지가_스캔_앞에_오면_false(self):
        lengthless = [bytes([0xFF, m]) for m in range(0xD0, 0xD8)]  # RST0~7
        lengthless += [b"\xff\x00", b"\xff\x01", b"\xff\xd8", b"\xff\xd9", b"\xff\xc8"]
        with_length = [seg(m, bytes(4)) for m in (0xDC, 0xDE, 0xDF, 0x02, 0xBF, 0xF0, 0xFD)]
        for bad in lengthless + with_length:
            for where in ("앞", "사이"):
                with self.subTest(marker=bad[:2].hex(), where=where):
                    if where == "앞":
                        raw = SOI + bad + sof(0xC0, 3) + sos(3) + TAIL
                    else:
                        raw = SOI + sof(0xC0, 3) + bad + sos(3) + TAIL
                    self.check(raw, False)

    def test_길이_없는_표지_뒤_주석_속_가짜_스캔에_속지_않는다(self):
        # 실제 해석기: RST(또는 FF00)를 넘기고 00 0A 를 쓰레기로 버리고 주석을 건너뛰어
        # 진짜 스캔(성분 1)을 만난다. 길이 없는 표지를 길이대로 읽으면 00 0A 를 길이로 보고
        # 주석 속 가짜 스캔(성분 3)으로 뛴다.
        comment = b"\xff\xfe\x00\x0e" + bytes(4) + sos(3)[:8]
        for lengthless in (b"\xff\xd0", b"\xff\xd3", b"\xff\x00", b"\xff\x01"):
            with self.subTest(marker=lengthless.hex()):
                raw = SOI + sof(0xC0, 3) + lengthless + b"\x00\x0a" + comment + sos(1) + TAIL
                self.check(raw, False)

    def test_주석_안의_가짜_스캔은_건너뛴다(self):
        fake_full, fake_split = sos(3), sos(1)
        self.check(SOI + sof(0xC0, 3) + seg(0xFE, fake_full) + sos(1) + TAIL, False)
        self.check(SOI + sof(0xC0, 3) + seg(0xFE, fake_split) + sos(3) + TAIL, True)
        self.check(SOI + seg(0xE1, sof(0xC2, 3)) + sof(0xC0, 3) + sos(3) + TAIL, True)
        self.check(SOI + seg(0xE1, sof(0xC0, 3) + sos(3)) + sof(0xC2, 3) + sos(3) + TAIL, False)

    def test_채움_바이트는_건너뛰고_쓰레기_바이트는_false(self):
        self.check(SOI + b"\xff\xff\xff" + sof(0xC0, 3) + b"\xff\xff" + sos(3) + TAIL, True)
        self.check(SOI + b"\x00" + sof(0xC0, 3) + sos(3) + TAIL, False)
        self.check(SOI + sof(0xC0, 3) + b"\x00\x00" + sos(3) + TAIL, False)

    def test_아주_짧거나_잘린_입력은_false(self):
        raw = SOI + seg(0xE0, b"JFIF\x00" + bytes(9)) + sof(0xC0, 3) + sos(3) + TAIL
        ns_at = raw.index(b"\xff\xda") + 4
        for cut in range(0, ns_at + 1):
            with self.subTest(cut=cut):
                self.check(raw[:cut], False)
        self.check(b"", False)
        self.check(b"\xff", False)
        self.check(SOI + b"\xff" * 1000, False)

    def test_길이_2인_세그먼트가_수없이_이어져도_끝난다(self):
        raw = SOI + b"\xff\xfe\x00\x02" * 250_000 + sof(0xC0, 3) + sos(3) + TAIL
        self.check(raw, True)


class FuzzedHeaderTest(SimpleTestCase):
    """정상 JPEG 머리말 앞 200바이트를 흔든다. 시드를 고정해 늘 같은 입력을 본다."""

    INTERESTING = (
        0x00,
        0x01,
        0x02,
        0x03,
        0x04,
        0xFF,
        0xDA,
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC4,
        0xC8,
        0xC9,
        0xCC,
        0xD0,
        0xD7,
        0xD8,
        0xD9,
        0xDB,
        0xDC,
        0xDD,
        0xDE,
        0xE0,
        0xE1,
        0xE2,
        0xEE,
        0xFE,
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        thumb = encode(Image.new("L", (8, 8)), progressive=True)
        cls.base = encode(
            Image.new("RGB", (32, 24), (10, 20, 30)),
            exif=exif_with_thumbnail(thumb),
            comment=b"hi",
            restart_marker_blocks=2,
        )
        cls.base_l = encode(Image.new("L", (32, 24)), comment=b"hello", qtables=[[300] * 64])

    def mutate(self, rng: random.Random, raw: bytes) -> bytes:
        data = bytearray(raw)
        for _ in range(rng.randint(1, 4)):
            at = rng.randrange(2, min(200, len(data)))
            data[at] = rng.choice(self.INTERESTING) if rng.random() < 0.7 else rng.randrange(256)
        if rng.random() < 0.1:  # 가끔 바이트를 끼우거나 뺀다
            at = rng.randrange(2, 200)
            if rng.random() < 0.5:
                data[at:at] = bytes([rng.choice(self.INTERESTING)])
            else:
                del data[at]
        return bytes(data)

    def test_흔든_머리말에서_예외가_새지_않고_true_면_pillow_와_성분_수가_같다(self):
        rng = random.Random(20261125)
        agreed = 0
        for n in range(4000):
            raw = self.mutate(rng, self.base if n % 2 else self.base_l)
            result = one_pass(raw)
            self.assertIsInstance(result, bool)
            if not result:
                continue
            seen = pillow_first_scan(raw)
            if seen is None:
                continue  # Pillow 가 못 여는 파일은 shrink 가 크기 검사 전에 거절한다.
            scan_ns, layers, progressive = seen
            self.assertEqual((scan_ns, progressive), (layers, False), raw[:200].hex())
            agreed += 1
        # 흔든 것 중 상당수는 판정이 True 이고 Pillow 도 연다. 0 이면 대조가 공회전한 것이다.
        self.assertGreater(agreed, 500)

    def test_구조를_무작위로_짜도_true_면_pillow_와_성분_수가_같다(self):
        """세그먼트를 무작위 순서·개수로 이어 붙인다. 판정이 True 인데 Pillow 가 다른 스캔을 보면 실패."""
        rng = random.Random(7)
        pieces = [
            lambda: sof(0xC0, rng.choice((1, 3, 4)), 16, 16),
            lambda: sof(rng.choice((0xC1, 0xC2, 0xC3, 0xC9, 0xCA)), rng.choice((1, 3)), 16, 16),
            lambda: sos(rng.choice((1, 2, 3, 4))),
            lambda: seg(
                rng.choice((0xE0, 0xE1, 0xE2, 0xEE, 0xFE)), rng.randbytes(rng.randrange(0, 30))
            ),
            lambda: seg(0xFE, sos(rng.choice((1, 3, 4)))),
            lambda: seg(0xDB, bytes(65)),
            lambda: seg(0xDD, b"\x00\x04"),
            lambda: bytes([0xFF, rng.choice((0xD0, 0xD5, 0x00, 0x01, 0xFF))]),
            lambda: bytes([0xFF, rng.choice((0xE0, 0xFE)), 0x00, rng.choice((0, 1))]),
            lambda: bytes([rng.randrange(256)]),
        ]
        true_seen = 0
        for _ in range(3000):
            parts = [rng.choice(pieces)() for _ in range(rng.randint(0, 5))]
            if rng.random() < 0.8:  # 대개는 짝이 맞는 SOF0·SOS 를 사이사이에 끼운다
                nf = rng.choice((1, 3, 4))
                at = rng.randint(0, len(parts))
                parts[at:at] = [sof(0xC0, nf, 16, 16)]
                parts.insert(rng.randint(at + 1, len(parts)), sos(nf))
            raw = SOI + b"".join(parts) + TAIL
            result = one_pass(raw)
            self.assertIsInstance(result, bool)
            if result:
                true_seen += 1
                seen = pillow_first_scan(raw)
                if seen is not None:
                    self.assertEqual((seen[0], seen[2]), (seen[1], False), raw.hex())
        self.assertGreater(true_seen, 300)
