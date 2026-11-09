"""시드 데이터에 시험 출제 빈도 주장이 없는지 본다.

출제 빈도를 뒷받침할 자료가 없다. '자주 출제된다' 같은 문장은 사용자에게
사실처럼 읽히므로 시드 값에 남아 있으면 안 된다. 범위만 말하는 표현
('정처기에서 다룬다')은 괜찮다.

소스 글자가 아니라 import 한 값을 본다. 파이썬이 이어 붙인 문자열이라
줄이 나뉜 '자주 ' + '출제된다' 를 글자 검색은 놓친다.

'자주 나온다'·'단골' 같은 말은 시험과 무관한 설명에도 쓴다
(예: 'ORM 을 쓸 때 특히 자주 나온다'). 그래서 같은 문장에 시험 맥락이
있을 때만 주장으로 본다.
"""

from __future__ import annotations

import re

from django.test import SimpleTestCase

from .management.commands.seed_exam_words import EXAM_WORDS
from .management.commands.seed_sentences import SENTENCES
from .management.commands.seed_words import WORDS

# 그 자체로 시험 이야기인 표현.
ALWAYS_A_CLAIM = ("자주 출제", "필수 암기")

# 일반 글에도 쓰는 표현. 같은 문장에 시험 맥락이 있어야 주장이다.
CLAIM_IN_EXAM_CONTEXT = ("자주 나온", "자주 나오", "단골", "필수 용어", "필수 개념", "필수 항목", "대개 이 문장")

EXAM_CONTEXT = re.compile(r"정처기|기출|출제|시험에|묻는 문제|문제로 자주|문제에 자주")

SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


def frequency_claims(text: str) -> list[str]:
    """글에서 출제 빈도를 주장하는 문장만 골라 돌려준다."""
    claims = []
    for sentence in SENTENCE_BREAK.split(text):
        if any(word in sentence for word in ALWAYS_A_CLAIM):
            claims.append(sentence)
        elif EXAM_CONTEXT.search(sentence) and any(
            word in sentence for word in CLAIM_IN_EXAM_CONTEXT
        ):
            claims.append(sentence)
    return claims


def claims_in(rows) -> list[tuple[str, str]]:
    """튜플의 글자 칸 전부를 본다. 칸 위치에 묶이면 칸이 늘 때 조용히 빠진다."""
    found = []
    for row in rows:
        for value in row:
            if isinstance(value, str):
                found.extend((str(row[0]), claim) for claim in frequency_claims(value))
    return found


class DetectorTest(SimpleTestCase):
    """판별 함수 자체. 여기가 틀리면 아래 데이터 검사가 전부 무의미하다."""

    def test_finds_the_kinds_of_claim_the_seed_used_to_make(self):
        for text in (
            "정처기에서 서브넷 계산 문제로 자주 출제된다.",
            "정처기에서 C 언어 문제로 자주 나온다.",
            "시험에서는 LIFO 라는 약자로 더 자주 나오고, 함수 호출이 쌓인다.",
            "값 호출과 함께 정처기 단골 문제다.",
            "redundancy 는 중복, integrity 는 무결성으로 정처기 필수 용어다.",
            "정규화의 목적을 묻는 문제의 답이 대개 이 문장 그대로다.",
            "말할 때 공통 언어가 된다. 정처기 필수 암기 항목이다.",
        ):
            with self.subTest(text=text):
                self.assertTrue(frequency_claims(text), "주장을 못 찾았다")

    def test_does_not_flag_ordinary_usage(self):
        for text in (
            "개발 환경에서는 멀쩡하다가 운영에서 터진다. ORM 을 쓸 때 특히 자주 나온다.",
            "파두는 설계에 대한 반론으로 자주 나온다.",
            "칸마다 맞추면 큰 칸에서 같은 것이 너무 자주 나온다.",
            "자주 나오는 문제의 정해진 풀이",
            "코드 리뷰에서 단골로 듣는 말이다.",
            "에러가 나면 대개 이 문장 뒤에 스택 트레이스가 이어진다.",
            "정처기에서 값 호출과 함께 다루는 개념이다.",
            "정처기에서 생성·구조·행위 세 갈래로 나눠 묻는다.",
            "LIFO 라는 약자로도 부르고, 함수 호출이 이 방식으로 쌓이고 풀린다.",
        ):
            with self.subTest(text=text):
                self.assertEqual(frequency_claims(text), [])

    def test_exam_context_must_share_the_sentence(self):
        """앞 문장이 정처기 이야기여도 뒷문장의 일반 표현은 주장이 아니다."""
        self.assertEqual(
            frequency_claims("정처기에서도 다룬다. 운영 로그에는 자주 나온다."), []
        )


class SeedDataHasNoFrequencyClaimTest(SimpleTestCase):
    """실제 시드 값."""

    def test_the_data_is_really_loaded(self):
        """목록이 비면 아래 검사는 아무것도 안 보고 통과한다."""
        self.assertGreater(len(EXAM_WORDS), 0)
        self.assertGreater(len(SENTENCES), 0)
        self.assertGreater(len(WORDS), 0)

    def test_exam_words_make_no_frequency_claim(self):
        self.assertEqual(claims_in(EXAM_WORDS), [])

    def test_words_make_no_frequency_claim(self):
        self.assertEqual(claims_in(WORDS), [])

    def test_sentences_make_no_frequency_claim(self):
        self.assertEqual(claims_in(SENTENCES), [])
