"""로그인하지 않은 사람을 접속 IP 별로 세는 제한을 깨뜨려 보는 테스트(vocab 쪽).

대상: 낱개 연습 채점(단어·문장), 소리내어 읽기(출제·채점). 시나리오는
apps/learning/tests_guest_ip_throttle_dynamic.py 의 GuestIpThrottleCase 를 그대로 받고,
부를 곳과 비율을 좁힐 클래스만 바꾼다.

단어·문장 채점은 통(practice_grade)을 같이 쓴다. 그래서 "다른 자리는 안 막힌다" 에서 둘은
서로를 막는 것이 맞다(같은 scope 라 검사에서 빠진다). 아래에서 따로 못 박는다.
"""

from __future__ import annotations

from apps.accounts.tests_ip_throttle import relayed
from apps.accounts.throttles import PerUserOrIpThrottle
from apps.learning import tests_guest_ip_throttle_dynamic as base

from .throttles import PracticeGradeThrottle, TalkGradeThrottle, TalkQuestionThrottle

WORDS_GRADE = base.Endpoint("words-grade", "post", "/api/vocab/words/grade/", 20, "practice_grade")
SENTENCES_GRADE = base.Endpoint(
    "sentences-grade", "post", "/api/vocab/sentences/grade/", 20, "practice_grade"
)

VOCAB_ENDPOINTS = [
    WORDS_GRADE,
    SENTENCES_GRADE,
    base.Endpoint("talk-question", "get", "/api/vocab/talk/question/", 20, "talk_question"),
    base.Endpoint("talk-grade", "post", "/api/vocab/talk/grade/", 20, "talk_grade"),
]


class VocabGuestIpThrottleTest(base.GuestIpThrottleCase):
    ENDPOINTS = VOCAB_ENDPOINTS
    THROTTLE_BASES = (PerUserOrIpThrottle,)
    THROTTLE_CLASSES = (PracticeGradeThrottle, TalkQuestionThrottle, TalkGradeThrottle)

    def test_단어와_문장_채점은_같은_IP_통을_나눠_쓴다(self):
        """둘은 scope 가 같다. 단어로 다 쓰고 문장으로 옮겨 한도를 두 배로 늘릴 수 없다."""
        limit = self.guest_limit(WORDS_GRADE)
        for i in range(limit):
            ep = WORDS_GRADE if i % 2 else SENTENCES_GRADE
            self.assertNotEqual(self.call(ep, **relayed(base.IP_A)), 429)
        self.assertEqual(self.call(WORDS_GRADE, **relayed(base.IP_A)), 429)
        self.assertEqual(self.call(SENTENCES_GRADE, **relayed(base.IP_A)), 429)
        self.assertNotEqual(self.call(SENTENCES_GRADE, **relayed(base.IP_B)), 429)
