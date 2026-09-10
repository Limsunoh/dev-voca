"""소리내어 읽기 채점·출제 필터 테스트.

**이 파일의 표본은 장식이 아니다.** 출제 필터가 세 번 고쳐졌고 두 번은
규칙을 읽어서가 아니라 통과 목록을 눈으로 봐서 잡혔다. 구현에 들어가면
눈으로 볼 기회가 사라지므로, 놓쳤던 것을 여기 박아둔다.

    1차에 놓친 것   API key · SQL injection · detached HEAD  (일부 낱말만 약어)
    2차에 놓친 것   I/O · big O                              (구분자로 쪼갠 1글자)

규칙을 고칠 일이 생기면 이 테스트를 먼저 보라. 셋 다 "제대로 읽었는데
인식 결과가 제각각이라 채점이 안 되는" 부류다.
"""

from django.core.cache import cache
from django.test import TestCase

from .models import Word
from .talk import (
    MAX_ALTERNATIVES,
    MAX_HEARD_LENGTH,
    clean_heard,
    grade_one,
    is_speakable,
    normalize,
)


class NormalizeTest(TestCase):
    """비교 전 다듬기."""

    def test_case_and_punctuation_are_dropped(self):
        """인식기가 대소문자·구두점을 제멋대로 준다.

        이것을 다르다고 판정하면 제대로 읽은 사람이 계속 실패한다.
        """
        self.assertEqual(normalize("Cache."), "cache")
        self.assertEqual(normalize("  CACHE  "), "cache")
        self.assertEqual(normalize("thank you!"), "thank you")

    def test_word_gaps_survive(self):
        """낱말 사이 공백은 남는다. 표현을 낱말 단위로 채점하는 근거다."""
        self.assertEqual(normalize("How was your weekend"), "how was your weekend")

    def test_hyphen_becomes_a_gap(self):
        """blue-green 은 "blue green" 으로 읽고 인식기도 그렇게 준다."""
        self.assertEqual(normalize("blue-green"), "blue green")


class GradeWordTest(TestCase):
    """낱말 하나 채점."""

    def test_exact_and_cosmetic_differences_pass(self):
        for said in ("cache", "Cache", "cache.", " cache "):
            with self.subTest(said=said):
                ok, wrong = grade_one(said, "cache")
                self.assertTrue(ok)
                self.assertEqual(wrong, [])

    def test_a_different_word_fails_and_points_at_it(self):
        ok, wrong = grade_one("cash", "cache")
        self.assertFalse(ok)
        self.assertEqual(wrong, [0])

    def test_a_tail_is_forgiven(self):
        """꼬리가 붙는 변형은 통과한다.

        인식기가 흔히 내는 것이고, 글자를 더하는 것은 바꾸는 것보다
        유사도를 덜 깎는다.
        """
        ok, _ = grade_one("deployed", "deploy")
        self.assertTrue(ok)

    def test_a_near_miss_still_fails(self):
        """employ 는 deploy 가 아니다.

        0.83 으로 문턱(0.85) 바로 아래다. 이 테스트가 임계값의 여유가
        얼마나 좁은지를 보여준다 - deployed 가 0.86 이라 0.03 차이다.
        """
        ok, _ = grade_one("employ", "deploy")
        self.assertFalse(ok)

    def test_short_words_are_effectively_exact(self):
        """짧은 낱말은 한 글자만 달라도 실패한다.

        유사도가 비율이라 3~6글자에서는 한 글자 차이가 0.85 를 못 넘는다.
        **의도한 것이다** - git/get, log/lag 처럼 짧을수록 한 글자가 다른
        낱말이 되므로 봐주면 틀린 발음이 통과한다.
        """
        self.assertFalse(grade_one("get", "git")[0])
        self.assertFalse(grade_one("lag", "log")[0])


class GradePhraseTest(TestCase):
    """표현(여러 낱말) 채점.

    **낱말 수를 먼저 본다.** 통째로 비교하면 낱말이 빠져도 통과한다 -
    "Hows your weekend" 가 0.94 다.
    """

    ANSWER = "how was your weekend"

    def test_the_same_phrase_passes(self):
        ok, wrong = grade_one("How was your weekend", self.ANSWER)
        self.assertTrue(ok)
        self.assertEqual(wrong, [])

    def test_one_misheard_word_is_forgiven(self):
        """your -> you 는 인식기 오차다. 낱말 하나가 0.86 으로 통과한다."""
        ok, _ = grade_one("How was you weekend", self.ANSWER)
        self.assertTrue(ok)

    def test_a_dropped_word_fails(self):
        """was 가 빠졌다. 전체 비교로는 0.94 로 통과해버리는 자리다."""
        ok, wrong = grade_one("Hows your weekend", self.ANSWER)
        self.assertFalse(ok)
        # 낱말 수가 어긋나 자리를 짚을 수 없다.
        self.assertIsNone(wrong)

    def test_a_wrong_word_is_pointed_at(self):
        """어느 낱말이 틀렸는지 알려준다.

        네 낱말짜리를 틀리면 어디를 고쳐야 할지 모른 채 전체를 다시
        말하게 된다. 이 자리 정보가 그것을 막는다.
        """
        ok, wrong = grade_one("How was the weekend", self.ANSWER)
        self.assertFalse(ok)
        self.assertEqual(wrong, [2])

    def test_a_truncated_phrase_fails(self):
        for said in ("How was your", "weekend"):
            with self.subTest(said=said):
                self.assertFalse(grade_one(said, self.ANSWER)[0])


class WordBoundaryTest(TestCase):
    """인식기가 낱말 경계를 다르게 잡은 경우.

    사용자 실수가 아니므로 살려야 한다. 다만 **완전 일치만** 인정한다 -
    유사도 문턱(0.95)을 두었더니 관사가 빠진 것이 통과했다.
    """

    def test_a_split_word_passes(self):
        """restroom 을 "rest room" 으로 적은 것은 사용자 탓이 아니다."""
        ok, wrong = grade_one("Where is the rest room", "where is the restroom")
        self.assertTrue(ok)
        self.assertIsNone(wrong)

    def test_a_joined_word_passes(self):
        self.assertTrue(grade_one("thankyou", "thank you")[0])
        self.assertTrue(grade_one("goodmorning", "good morning")[0])

    def test_a_dropped_article_fails(self):
        """관사가 빠지면 실패한다.

        **여기가 0.95 문턱을 버린 이유다.** 공백을 없앤 뒤에는 한 글자짜리
        낱말이 비율을 거의 안 깎아서, "can I get refill" 이 0.963,
        "have nice day" 가 0.957 로 통과했다. 완전 일치로 바꾸니 막힌다.
        """
        self.assertFalse(grade_one("can I get refill", "can I get a refill")[0])
        self.assertFalse(grade_one("have nice day", "have a nice day")[0])

    def test_a_truncated_phrase_still_fails(self):
        self.assertFalse(grade_one("see you", "see you later")[0])
        self.assertFalse(
            grade_one("could you say that", "could you say that again")[0]
        )

    def test_a_split_word_with_a_typo_is_not_rescued(self):
        """알려진 한계.

        낱말 경계가 어긋나면서 동시에 오인식이 난 경우는 어느 경로로도
        안 걸린다. **의도한 것이다** - 놓치는 편이 관사 빠진 것을
        통과시키는 것보다 낫다. 버그로 보고 고치려 들지 말 것.
        """
        ok, _ = grade_one("where is the rest rooms", "where is the restroom")
        self.assertFalse(ok)


class SpeakableFilterTest(TestCase):
    """출제 대상 판정.

    **아래 표본이 이 파일의 핵심이다.** 규칙이 세 번 고쳐지며 실제로
    놓쳤던 것들이다.
    """

    def test_plain_words_are_speakable(self):
        for term in ("cache", "deploy", "idempotent", "throughput"):
            with self.subTest(term=term):
                self.assertTrue(is_speakable(term))

    def test_multi_word_terms_are_speakable(self):
        for term in ("pull request", "merge conflict", "blue-green"):
            with self.subTest(term=term):
                self.assertTrue(is_speakable(term))

    def test_capitalised_words_read_as_words_are_kept(self):
        """대문자가 있어도 낱말로 읽는 것은 남긴다.

        "그래프큐엘"·"오오스" 처럼 철자를 하나씩 읽지 않는다.
        """
        for term in ("GraphQL", "OAuth", "NoSQL", "ETag", "gRPC", "IaC"):
            with self.subTest(term=term):
                self.assertTrue(is_speakable(term))

    def test_spelled_out_acronyms_are_excluded(self):
        for term in ("ACL", "APM", "BDD", "API", "ACID"):
            with self.subTest(term=term):
                self.assertFalse(is_speakable(term))

    def test_terms_with_an_acronym_inside_are_excluded(self):
        """1차 정정에서 놓쳤던 것들.

        낱말 전체가 대문자인지만 보면 이것들이 통과한다. "에이피아이 키" 로
        읽는데 인식 결과가 제각각이라 채점이 안 된다.
        """
        for term in (
            "API key",
            "SQL injection",
            "WIP limit",
            "detached HEAD",
            "semantic HTML",
            "virtual DOM",
            "SPA fallback",
        ):
            with self.subTest(term=term):
                self.assertFalse(is_speakable(term))

    def test_single_letter_acronyms_are_excluded(self):
        """2차 정정에서 놓쳤던 것들.

        구분자로 쪼개면 낱개 대문자 한 글자가 된다. "2글자 이상" 조건만
        두면 통과한다.
        """
        self.assertFalse(is_speakable("I/O"))
        self.assertFalse(is_speakable("big O"))

    def test_digits_and_symbols_are_excluded(self):
        for term in ("401", "502", "IPv4", "K8s", "TL;DR", "N+1", "UTF-8"):
            with self.subTest(term=term):
                self.assertFalse(is_speakable(term))

    def test_the_pronoun_i_is_not_an_acronym(self):
        """3차 정정에서 놓쳤던 것.

        "낱말이 여러 개면 1글자 대문자도 약어" 조건은 big O·I/O 를 잡으려고
        넣었는데, **대명사 I 가 같은 모양이라 함께 걸렸다** - 일상 표현
        60개 중 10개가 출제에서 조용히 빠졌다.

        I 는 철자가 아니라 낱말로 읽으므로 인식 결과가 흔들리지 않는다.
        """
        for text in (
            "I am lost",
            "I agree",
            "I need help",
            "I would like to order",
            "can I get a refill",
            "how do I get there",
        ):
            with self.subTest(text=text):
                self.assertTrue(is_speakable(text))

    def test_the_i_exception_does_not_revive_big_o(self):
        """예외가 잡아야 할 것을 되살리지 않는가.

        I·A 만 넘기므로 O 는 여전히 걸린다. 이 테스트가 없으면 예외를
        넓힐 때(예: 알파벳 한 글자 전부) big O 가 조용히 통과한다.
        """
        self.assertFalse(is_speakable("big O"))
        self.assertFalse(is_speakable("plan B"))


class ArticleAIsNotExemptTest(TestCase):
    """홀로 선 A 는 예외가 아니다.

    대명사 I 를 살리면서 관사 A 도 함께 넣을 뻔했다. 같은 모양이지만
    **지금 쓰는 표현 중에 홀로 선 A 가 하나도 없고**, 넣으면 plan A 나
    A record 처럼 plan B·big O 와 같은 부류가 통과한다.

    위쪽 test_the_i_exception_does_not_revive_big_o 는 목록에 **없는** 글자만
    보므로 이것을 못 잡는다.
    """

    def test_single_letter_terms_stay_out(self):
        for term in ("plan A", "grade A", "A record"):
            with self.subTest(term=term):
                self.assertFalse(is_speakable(term))

    def test_the_pronoun_still_passes(self):
        """A 를 빼면서 I 까지 막으면 표현 열 개가 사라진다."""
        for term in ("I am lost", "can I get a refill"):
            with self.subTest(term=term):
                self.assertTrue(is_speakable(term))


class HeardLimitTest(TestCase):
    """후보 길이 상한.

    계산량 때문이 아니다 - difflib 비용은 짧은 쪽에 지배돼 거의 선형이다.
    낱말 하나가 올 자리에 10만자가 오는 것 자체가 정상이 아니라서 막는다.
    """

    def test_the_limit_leaves_room_for_the_longest_answer(self):
        """최장 정답(22글자)보다 넉넉해야 한다.

        상한을 정답보다 짧게 줄이면 긴 표현을 제대로 읽은 사람이 막힌다.
        """
        self.assertGreaterEqual(MAX_HEARD_LENGTH, 100)


class CleanHeardTest(TestCase):
    """화면이 보낸 후보를 다듬는 단계."""

    def test_empty_strings_do_not_push_out_real_candidates(self):
        """**빈 값을 먼저 걷어내고 상한을 적용한다.**

        순서가 뒤바뀌면 앞에 온 빈 값이 실제 후보를 밀어낸다. 인식기가
        빈 결과를 배열에 담는 경우가 있어서 실재하는 입력이고, 그때
        사용자는 정확히 읽었는데 "소리가 안 들렸어요" 를 받는다.
        """
        self.assertEqual(clean_heard(["", "", "", "", "", "cache"]), ["cache"])
        self.assertEqual(clean_heard(["", "cache"]), ["cache"])

    def test_the_cap_still_applies(self):
        """상한은 걷어낸 뒤에 적용한다."""
        many = [f"word{n}" for n in range(10)]
        self.assertEqual(len(clean_heard(many)), MAX_ALTERNATIVES)

    def test_a_long_candidate_is_refused_even_past_the_cap(self):
        """길이 검사는 상한 뒤로 밀린 것까지 본다.

        슬라이스 뒤에만 검사하면 여섯 번째에 긴 문자열을 넣어 검사를
        건너뛸 수 있다.
        """
        raw = ["a", "b", "c", "d", "e", "x" * (MAX_HEARD_LENGTH + 1)]
        self.assertIsNone(clean_heard(raw))

    def test_an_empty_list_is_allowed(self):
        """빈 목록은 정상이다 - 아무 소리도 안 난 경우다."""
        self.assertEqual(clean_heard([]), [])
        self.assertEqual(clean_heard(None), [])

    def test_a_non_list_is_refused(self):
        self.assertIsNone(clean_heard("cache"))
        self.assertIsNone(clean_heard([1, 2]))


class ContractionTest(TestCase):
    """축약형(what's up).

    일상 영어의 큰 몫이라 막으면 안 된다. 막으면 관리자가 넣고 검수해도
    출제가 안 되는데 이유를 알 방법이 없다.
    """

    def test_contractions_are_speakable(self):
        for text in ("what's up", "how's it going", "I'm fine", "don't worry"):
            with self.subTest(text=text):
                self.assertTrue(is_speakable(text))

    def test_an_apostrophe_does_not_split_a_word(self):
        """아포스트로피는 공백이 아니라 삭제다.

        공백으로 바꾸면 "what's" 가 두 조각이 되어 낱말 수가 어긋나고,
        wrong_at 이 자리를 못 짚는다.
        """
        self.assertEqual(normalize("what's up"), "whats up")
        self.assertEqual(len(normalize("how's it going").split()), 3)

    def test_a_missing_apostrophe_still_points_at_the_word(self):
        """인식기가 아포스트로피를 빼고 적어도 자리가 나온다."""
        ok, wrong = grade_one("whats up", "what's up")
        self.assertTrue(ok)
        self.assertEqual(wrong, [])

    def test_expanding_the_contraction_fails(self):
        """"what is up" 은 "what's up" 이 아니다.

        읽은 것이 다르므로 통과시키면 안 된다.
        """
        self.assertFalse(grade_one("what is up", "what's up")[0])


class TalkEndpointTest(TestCase):
    """엔드포인트를 실제로 불러본다.

    **이 클래스가 없어서 구멍이 하나 새고 있었다.** 위쪽 테스트가 전부
    순수 함수를 직접 부르는 것이라, 뷰가 응답 dict 를 손으로 만들면서
    검수 게이트를 빠뜨린 것을 아무도 못 봤다. 함수 단위로 아무리 촘촘해도
    뷰의 결함은 구조적으로 안 보인다.
    """

    QUESTION_URL = "/api/vocab/talk/question/"
    GRADE_URL = "/api/vocab/talk/grade/"

    def setUp(self):
        cache.clear()

    def _word(self, **kw):
        defaults = {
            "term": "cache",
            "meaning": "자주 쓰는 것을 가까이 두는 것",
            "pronunciation": "/kæʃ/",
            "reading": "캐시",
            "reading_reviewed": True,
            "is_reviewed": True,
        }
        defaults.update(kw)
        return Word.objects.create(**defaults)

    def test_미검수_발음은_안_나간다(self):
        """검수된 단어라도 발음만 미검수일 수 있다.

        이 화면은 그 표기를 **본보기로 제시하고 따라 읽으라고 시킨다.**
        아무도 확인 안 한 표기를 그렇게 쓰면 잘못 외우고, 영어가 약한
        사람일수록 되돌리기 어렵다.
        """
        Word.objects.all().delete()
        self._word(reading="아무도-확인-안-함", reading_reviewed=False)

        res = self.client.get(self.QUESTION_URL, {"kind": "dev"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["reading"], "")

    def test_검수된_발음은_나간다(self):
        """게이트가 멀쩡한 것까지 지우면 본보기가 통째로 사라진다."""
        Word.objects.all().delete()
        self._word(reading="캐시", reading_reviewed=True)

        res = self.client.get(self.QUESTION_URL, {"kind": "dev"})

        self.assertEqual(res.json()["reading"], "캐시")

    def test_검수_안_된_항목은_출제되지_않는다(self):
        Word.objects.all().delete()
        self._word(is_reviewed=False)

        res = self.client.get(self.QUESTION_URL, {"kind": "dev"})

        self.assertEqual(res.status_code, 404)

    def test_정답은_응답에_없다(self):
        """화면이 미리 알면 채점이 의미가 없다."""
        Word.objects.all().delete()
        self._word()

        body = self.client.get(self.QUESTION_URL, {"kind": "dev"}).json()

        self.assertIn("token", body)
        self.assertNotIn("answer", body)

    def test_방금_낸_것을_뺄_수_있다(self):
        """화면이 exclude 로 되돌려주려면 응답에 번호가 있어야 한다.

        없으면 뺄 값을 몰라 같은 것이 계속 나온다.
        """
        Word.objects.all().delete()
        first = self._word(term="cache")
        self._word(term="deploy", meaning="내보내기", pronunciation="/dɪˈplɔɪ/")

        body = self.client.get(
            self.QUESTION_URL, {"kind": "dev", "exclude": str(first.pk)}
        ).json()

        self.assertIn("id", body)
        self.assertNotEqual(body["id"], first.pk)

    def test_손댄_토큰은_거절된다(self):
        Word.objects.all().delete()
        self._word()
        token = self.client.get(self.QUESTION_URL, {"kind": "dev"}).json()["token"]

        res = self.client.post(
            self.GRADE_URL,
            {"token": token + "x", "heard": ["cache"]},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 400)

    def test_후보가_너무_길면_거절한다(self):
        """단어 하나 올 자리에 긴 문자열이 오는 것은 정상 요청이 아니다."""
        Word.objects.all().delete()
        self._word()
        token = self.client.get(self.QUESTION_URL, {"kind": "dev"}).json()["token"]

        res = self.client.post(
            self.GRADE_URL,
            {"token": token, "heard": ["x" * (MAX_HEARD_LENGTH + 1)]},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 400)
