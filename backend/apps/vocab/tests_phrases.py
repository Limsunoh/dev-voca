"""일상 표현 데이터 검사.

**전 항목에 기계적으로 건다.** seed_phrases 가 is_reviewed=True 로 넣는
근거 중 형식 쪽이 이 파일이다. 내용 쪽은 seed_phrases 머리말에 누가 무엇을
읽었는지와 사용자 결정으로 적어 뒀다.

제일 중요한 것은 **낱말 수 일치**다. text·pronunciation·reading 셋의 낱말
수가 같아야 화면이 wrong_at 으로 받은 자리를 강조할 수 있고, 하나라도
어긋나면 그 항목은 강조 없이 통짜로 그려진다. 눈으로는 안 보이는 결함이라
여기서 막는다.
"""

from __future__ import annotations

import re

from django.core.management import call_command
from django.test import TestCase

from .management.commands.seed_phrases import PHRASES, SEED_SOURCE
from .models import DailyPhrase, PhraseScene
from .talk import is_speakable

# 낱말 경계. 하이픈도 낱말을 나눈다 - 화면이 같은 기준으로 쪼갠다.
_WORDS = re.compile(r"[\s\-]+")


def _text_words(text: str) -> int:
    return len(_WORDS.split(text))


def _ipa_words(pronunciation: str) -> int:
    # 바깥 슬래시를 떼고 센다.
    return len(pronunciation.strip().strip("/").split())


def _reading_words(reading: str) -> int:
    # 강세 표시를 걷어내고 센다. `**` 를 남기면 그것이 붙은 낱말이
    # 다르게 세어진다.
    return len(reading.replace("**", "").split())


# 사람이 Admin 에서 손으로 넣은 행을 흉내낼 때 쓰는 text.
#
# **씨드에 없는 값이어야 한다.** 전에는 "see you tomorrow" 를 썼는데, 나중에
# 그 표현이 실제로 씨드에 들어가면서 같은 text 가 둘이 되어 unique 제약에
# 걸렸다. 테스트가 깨진 것으로 드러나서 다행이었지 조용히 지나갈 수도 있는
# 모양이었다 - 그래서 값을 고르는 대신 **씨드에 없다는 것을 여기서 못 박는다.**
HAND_TYPED = "this row was typed by a person"
assert HAND_TYPED not in {row[0] for row in PHRASES}, (
    "손으로 넣은 행을 흉내내는 text 가 씨드에 들어갔다. 다른 값으로 바꿔라."
)


class PhraseDataTest(TestCase):
    """씨드 데이터 자체를 본다. DB 에 넣지 않고 목록만 검사한다."""

    def test_the_count_is_what_we_checked(self):
        """개수가 줄면 출제 풀이 줄고, 늘면 **검수 안 된 것이 섞인다.**

        하한이 아니라 정확한 수로 두는 이유가 그 둘째다. 이 목록은
        is_reviewed=True 로 들어가므로, 늘어난 만큼은 사람이 읽었거나 안
        읽었다는 사실을 알고 사용자가 넣기로 정한 것이어야 한다. 정확한 수면
        표현을 더할 때 이 줄을 반드시 건드리게 되고, 그 자리에서 "검수했나"
        를 한 번 묻게 된다.

        60 에서 207 로 늘린 147개는 후자다 - 사람이 안 읽었고, 사용자가 그것을
        안내받고 2026-09-15 에 넣기로 정했다(seed_phrases 머리말).
        """
        self.assertEqual(len(PHRASES), 207)

    def test_no_duplicates(self):
        """text 가 unique 라 중복이 있으면 씨드가 중간에 죽는다."""
        texts = [row[0] for row in PHRASES]
        self.assertEqual(len(texts), len(set(texts)))

    def test_word_counts_line_up(self):
        """셋의 낱말 수가 같아야 낱말 강조가 된다.

        이 테스트가 실제로 하나를 잡았다 - "do you take card" 의 한글
        발음이 `**카**r d` 로 띄어 써서 5조각이었다(text 는 4낱말).
        """
        for text, pronunciation, reading, _, _, _ in PHRASES:
            with self.subTest(text=text):
                self.assertEqual(
                    (_text_words(text), _ipa_words(pronunciation)),
                    (_text_words(text), _text_words(text)),
                    f"IPA 낱말 수가 다르다: {pronunciation}",
                )
                self.assertEqual(
                    _reading_words(reading),
                    _text_words(text),
                    f"한글 발음 낱말 수가 다르다: {reading}",
                )

    def test_ipa_is_wrapped_once(self):
        """바깥만 슬래시로 감싼다.

        낱말마다 두르면(/wɛr/ /ɪz/) 기호가 글자만큼 많아 읽기 나쁘고,
        화면이 쪼갤 때 슬래시가 낱말에 붙는다.
        """
        for text, pronunciation, *_ in PHRASES:
            with self.subTest(text=text):
                self.assertTrue(pronunciation.startswith("/"))
                self.assertTrue(pronunciation.endswith("/"))
                # 안쪽에는 슬래시가 없어야 한다.
                self.assertNotIn("/", pronunciation[1:-1])

    def test_stress_closes_inside_a_word(self):
        """강세 `**` 가 공백을 걸치면 안 된다.

        걸치면 공백으로 세는 낱말 수가 어긋난다. 개발 용어의
        `source map` 이 그 상태이고, 그래서 그 항목은 강조가 안 된다.
        """
        for text, _, reading, *_ in PHRASES:
            with self.subTest(text=text):
                for stressed in re.findall(r"\*\*(.+?)\*\*", reading):
                    self.assertNotIn(
                        " ", stressed, f"강세가 공백을 걸친다: {reading}"
                    )

    def test_every_phrase_is_speakable(self):
        """출제 필터를 통과해야 한다.

        약어·숫자·기호가 섞이면 소리로 채점할 수 없어 출제에서 조용히
        빠진다. 데이터를 넣었는데 안 나오는 상태가 제일 찾기 어렵다.

        이 테스트가 열 건을 잡았다 - 대명사 `I` 가 "낱말이 여러 개면
        1글자 대문자는 약어" 규칙에 걸려 "I am lost" 같은 것이 전부
        제외되고 있었다.
        """
        for text, *_ in PHRASES:
            with self.subTest(text=text):
                self.assertTrue(is_speakable(text))

    def test_scenes_are_valid(self):
        for text, _, _, _, scene, _ in PHRASES:
            with self.subTest(text=text):
                self.assertIn(scene, PhraseScene.values)

    def test_phrases_stay_within_six_words(self):
        """상한을 두는 이유는 화면이다.

        폰 390px 에서 여섯 낱말이 두 줄까지 간다. 그보다 길면 레이아웃을
        다시 봐야 한다.
        """
        for text, *_ in PHRASES:
            with self.subTest(text=text):
                self.assertLessEqual(_text_words(text), 6)


class SeedPhrasesTest(TestCase):
    """명령이 실제로 넣는지."""

    def test_it_inserts_everything_as_reviewed(self):
        call_command("seed_phrases", verbosity=0)

        self.assertEqual(DailyPhrase.objects.count(), len(PHRASES))
        # 검수 안 된 것이 있으면 출제에서 빠진다.
        self.assertEqual(
            DailyPhrase.objects.filter(is_reviewed=True).count(), len(PHRASES)
        )
        # visible() 이 그 게이트를 쓴다.
        self.assertEqual(DailyPhrase.objects.visible().count(), len(PHRASES))

    def test_running_it_twice_adds_nothing(self):
        """씨드는 여러 번 돌 수 있어야 한다.

        text 가 unique 라 두 번째에 IntegrityError 가 나면 배포 스크립트가
        죽는다.
        """
        call_command("seed_phrases", verbosity=0)
        call_command("seed_phrases", verbosity=0)
        self.assertEqual(DailyPhrase.objects.count(), len(PHRASES))

    def test_reset_updates_in_place(self):
        call_command("seed_phrases", verbosity=0)
        phrase = DailyPhrase.objects.get(text="thank you")
        phrase.meaning = "엉뚱한 뜻"
        phrase.save(update_fields=["meaning"])

        call_command("seed_phrases", "--reset", verbosity=0)
        phrase.refresh_from_db()
        self.assertEqual(phrase.meaning, "고맙습니다")

    def test_reset_does_not_reopen_a_phrase_a_person_hid(self):
        """Admin 에서 검수를 끈 표현은 --reset 뒤에도 꺼져 있다.

        147개를 사람이 안 읽고 넣었으니 화면에서 이상한 것을 발견해 끄는
        일이 실제로 생긴다. 갱신이 is_reviewed 까지 덮으면 다음 배포의
        --reset 이 그것을 말없이 다시 보여준다.
        """
        call_command("seed_phrases", verbosity=0)
        phrase = DailyPhrase.objects.get(text="thank you")
        phrase.is_reviewed = False
        phrase.save(update_fields=["is_reviewed"])

        call_command("seed_phrases", "--reset", verbosity=0)
        phrase.refresh_from_db()
        self.assertFalse(phrase.is_reviewed)

    def test_none_of_them_are_exam_scope(self):
        """정처기와 무관한 표다. DB 제약도 같은 것을 막는다."""
        call_command("seed_phrases", verbosity=0)
        self.assertFalse(DailyPhrase.objects.filter(is_exam=True).exists())
        self.assertFalse(DailyPhrase.objects.exclude(exam_subject="").exists())


class PhraseAdminTest(TestCase):
    """검수 화면에 필드가 다 나오는가.

    **fieldsets 가 명시적이라 여기 없는 필드는 폼에 아예 안 나온다.**
    칸을 만들어놓고 목록에서 빠뜨리면 관리자가 그 값을 고칠 방법이 없고,
    화면을 열어보지 않으면 모른다 - 이 저장소가 실제로 당한 적이 있다.
    """

    # 물려받았지만 이 표에서 안 쓰는 것. DB 제약이 값을 막으므로 폼에
    # 두면 채울 수 있는 것처럼 보이는데 저장하면 거절당한다.
    DELIBERATELY_HIDDEN = {"category", "is_exam", "exam_subject"}

    def test_every_editable_field_is_on_the_form(self):
        from django.contrib import admin as django_admin

        model_admin = django_admin.site._registry[DailyPhrase]
        shown: set[str] = set()
        for _, options in model_admin.fieldsets:
            shown.update(options["fields"])

        editable = {
            field.name
            for field in DailyPhrase._meta.get_fields()
            if getattr(field, "editable", False) and field.name != "id"
        }
        missing = editable - shown - self.DELIBERATELY_HIDDEN
        self.assertEqual(
            missing,
            set(),
            f"폼에서 빠진 필드가 있다: {sorted(missing)}. "
            "fieldsets 에 넣지 않으면 Admin 에서 고칠 수 없다.",
        )

    def test_the_hidden_ones_are_blocked_by_the_database(self):
        """폼에서 뺀 것이 실제로 막혀 있는가.

        제약이 없으면 폼에서 뺀 것이 "저장은 되는데 화면에 안 보이는"
        상태가 된다 - 그게 더 나쁘다.
        """
        constraints = {c.name for c in DailyPhrase._meta.constraints}
        self.assertIn("vocab_dailyphrase_not_exam", constraints)


class SeedRemovesStaleRowsTest(TestCase):
    """소스에서 사라진 표현을 지우는가.

    **이것이 없어서 실제로 사고가 났다.** 축약형으로 넷을 바꿨더니
    (`I do not understand` -> `I don't understand`) 옛 형태가 DB 에 남아
    총 64개가 되었고, **한 뜻에 두 표현이 동시에 출제됐다** - 그중 하나는
    우리가 부자연스럽다고 판단해 뺀 것이다.

    같은 함정이 2026-08-10 에 문장 데이터에서 이미 한 번 났다. 그때
    결론이 "지우는 변경을 했으면 배포 후 별도로 확인한다" 였는데,
    **사람이 기억해야 하는 절차는 잊힌다**는 것이 이번에 드러났다.
    """

    def test_reset_deletes_rows_that_left_the_source(self):
        call_command("seed_phrases", verbosity=0)
        DailyPhrase.objects.create(
            text="I do not understand",
            pronunciation="/x/",
            reading="엑s",
            meaning="옛 표현",
            is_reviewed=True,
            source=SEED_SOURCE,
        )
        self.assertEqual(DailyPhrase.objects.count(), len(PHRASES) + 1)

        call_command("seed_phrases", "--reset", verbosity=0)

        self.assertEqual(DailyPhrase.objects.count(), len(PHRASES))
        self.assertFalse(
            DailyPhrase.objects.filter(text="I do not understand").exists()
        )

    def test_reset_keeps_rows_even_when_a_person_types_a_natural_source(self):
        """사람이 출처에 흔한 말을 적어도 지워지지 않아야 한다.

        **이 검사가 진짜 위험을 본다.** 위 테스트는 출처가 다를 때만 보므로
        "구분이 된다" 는 것만 증명한다. 정작 데이터를 잃는 경우는 사람이
        고른 말이 씨드 표시와 겹칠 때다.

        출처는 자유 입력이고 Admin 폼에 열려 있다. 표현을 손으로 넣는
        사람이 "직접 작성" 이라고 적는 것은 아주 자연스럽다 - 다른 씨드
        명령 여섯 곳이 그 말을 쓰고 있기도 하다. 그래서 씨드 표시를 사람이
        칠 일 없는 값으로 두었고, 이 검사가 그것을 지킨다.
        """
        call_command("seed_phrases", verbosity=0)
        DailyPhrase.objects.create(
            text=HAND_TYPED,
            pronunciation="/si ju təˈmɑroʊ/",
            reading="씨 유 터**마**로우",
            meaning="내일 봐요",
            is_reviewed=True,
            source="직접 작성",
        )

        call_command("seed_phrases", "--reset", verbosity=0)

        self.assertTrue(
            DailyPhrase.objects.filter(text=HAND_TYPED).exists(),
            "사람이 넣은 행이 지워졌다. 씨드 표시가 사람이 칠 만한 말이면 "
            "안 된다(seed_phrases.SEED_SOURCE 주석 참고).",
        )

    def test_reset_keeps_rows_a_person_added(self):
        """Admin 에서 사람이 넣은 것은 지우지 않는다.

        `DailyPhraseAdmin` 이 등록돼 있어 실제로 생길 수 있는 행이고,
        그것까지 지우면 남의 작업을 말없이 없애는 것이 된다. source 로
        가른다.
        """
        call_command("seed_phrases", verbosity=0)
        DailyPhrase.objects.create(
            text=HAND_TYPED,
            pronunciation="/si ju təˈmɑroʊ/",
            reading="씨 유 터**마**로우",
            meaning="내일 봐요",
            is_reviewed=True,
            source="관리자 추가",
        )

        call_command("seed_phrases", "--reset", verbosity=0)

        self.assertTrue(
            DailyPhrase.objects.filter(text=HAND_TYPED).exists()
        )
        self.assertEqual(DailyPhrase.objects.count(), len(PHRASES) + 1)

    def test_without_reset_nothing_is_deleted(self):
        """`--reset` 없이는 지우지 않는다.

        기본 실행이 데이터를 없애면 배포 스크립트가 무심코 지운다.
        """
        call_command("seed_phrases", verbosity=0)
        DailyPhrase.objects.create(
            text="I do not understand",
            pronunciation="/x/",
            reading="엑s",
            meaning="옛 표현",
            is_reviewed=True,
            source=SEED_SOURCE,
        )

        call_command("seed_phrases", verbosity=0)

        self.assertTrue(
            DailyPhrase.objects.filter(text="I do not understand").exists()
        )


class PhraseMeaningTest(TestCase):
    """기계 검사가 못 보던 두 축.

    기존 검사는 낱말 수·슬래시·강세 위치·약어 혼입 넷이다. **meaning 은
    아무도 안 봤고, 한글 표기가 항목마다 갈리는 것도 안 봤다.** 둘 다
    "형식은 맞는데 내용이 틀린" 자리라 눈으로만 걸렸다.

    실제로 걸렸다 - 147개를 더했을 때 뜻이 글자까지 같은 쌍이 다섯,
    같은 영어 낱말을 두 가지 한글로 적은 것이 하나 나왔다.
    """

    def test_meanings_do_not_repeat(self):
        """한 뜻에 두 표현을 두지 않는다.

        이 표의 `--reset` 이 생긴 계기가 그것이다(SeedRemovesStaleRowsTest
        머리말) - 한 뜻에 두 표현이 동시에 출제되면 사용자는 무엇이 다른지
        모른 채 둘 다 외운다. 같은 상태를 소스 안에 만들지 않는다.

        비슷한 뜻은 괜찮다. 여기서 막는 것은 **글자까지 같은 것**이다 -
        그건 뜻을 갈라 적지 않았다는 신호다.
        """
        meanings = [row[3] for row in PHRASES]
        repeated = {m for m in meanings if meanings.count(m) > 1}
        self.assertEqual(
            repeated,
            set(),
            f"같은 뜻이 둘 이상이다: {sorted(repeated)}. "
            "뜻을 갈라 적거나 한쪽을 빼라.",
        )

    def test_one_english_word_has_one_korean_spelling(self):
        """같은 영어 낱말은 어디서나 같은 한글로 적는다.

        이 칸의 존재 이유가 "한글만 읽어도 통한다" 인데, 같은 낱말이
        항목마다 다르게 적혀 있으면 어느 쪽이 맞는지 데이터가 스스로
        모른다는 뜻이다. 화면은 이 표기를 **본보기로 제시하고 따라 읽으라고
        시키므로**, 흔들리면 그대로 잘못된 학습이 된다.

        실제로 `speak` 가 `스핔` 과 `s핔` 로 갈려 있었다. 어두 자음군에
        모음을 넣느냐 마느냐가 항목마다 달랐던 것이고, 낱말 수는 어느
        쪽이든 맞아서 기존 검사가 전부 통과했다.
        """
        spellings: dict[str, set[str]] = {}
        for text, _, reading, *_ in PHRASES:
            english = text.split()
            korean = reading.replace("**", "").split()
            # 낱말 수는 위 테스트가 이미 본다. 여기서는 짝이 맞는 것만 센다.
            if len(english) != len(korean):
                continue
            for word, spelled in zip(english, korean):
                spellings.setdefault(word.lower(), set()).add(spelled)

        split = {w: sorted(s) for w, s in spellings.items() if len(s) > 1}
        self.assertEqual(
            split,
            {},
            f"같은 낱말을 다르게 적었다: {split}. 한쪽으로 맞춰라.",
        )
