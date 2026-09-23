"""fixtures/readings_*.json 의 발음이 표기 규칙을 지키는지.

DB 없이 파일만 읽는다. 이 파일은 load_readings 로 DB 에 붓는 원본이라
(fixtures/README.md), 여기가 틀리면 화면에서 발음 줄이 이상해 보일 때까지
아무도 모른다.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# 주소를 한 글자씩 푼 흔적. 규칙 7(ai_pipeline/prompts/korean-reading.md)은
# 주소를 (주소) 로 적게 한다. 차례로 "://" 의 //, ".com", "localhost:",
# 0 이 낀 IP("127.0.0.1", "10.0.1.20" - 강세 있고 없고 둘 다), IPv6 ":::3000"
# 이다. 고치기 전 파일에서 이 표지가 걸린 줄과 이번에 고친 25줄이 정확히 같다 -
# 주소가 아닌 줄에는 안 나온다. 0 이 없는 IP("10.1.2.3")는 못 잡는다.
SPELLED_ADDRESS = (
    "슬래sh 슬래sh",
    "닷 캄",
    "닷 **캄**",
    "클호우s트 콜론",
    "닷 **z이**로우 닷",
    "닷 z이로우 닷",
    "콜론 콜론 콜론",
)


class ReadingFixtureTest(SimpleTestCase):
    def rows(self, name: str) -> list[dict]:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def test_rows_are_well_formed(self):
        """pk 가 겹치지 않고, 발음이 비지 않았고, 강세 별표 짝이 맞는다.

        pk 가 겹치면 load_readings 에서 뒤 줄이 앞 줄을 경고 없이 덮는다.
        별표 짝이 안 맞으면 화면에서 엉뚱한 곳이 굵어진다(korean-reading.md
        확인 목록 7). 건수는 보지 않는다 - 발음을 새로 적을 때마다 늘어나는
        값이라 못 박으면 멀쩡한 추가가 실패한다.
        """
        for name in ("readings_sentence.json", "readings_word.json"):
            rows = self.rows(name)
            with self.subTest(name):
                pks = [row["pk"] for row in rows]
                self.assertTrue(all(type(pk) is int for pk in pks), "pk 가 정수가 아니다")
                self.assertEqual(len(pks), len(set(pks)), "pk 가 겹친다")
                self.assertEqual([r["pk"] for r in rows if not r["reading"].strip()], [])
                self.assertEqual(
                    [r["pk"] for r in rows if r["reading"].count("**") % 2],
                    [],
                    "별표 짝이 안 맞는다",
                )

    def test_address_placeholder_is_written_exactly(self):
        """(주소) 는 괄호까지 한 덩어리다. 강세를 씌우거나 괄호를 빼면 다른 글자가 된다."""
        for name in ("readings_sentence.json", "readings_word.json"):
            for row in self.rows(name):
                reading = row["reading"]
                with self.subTest(name=name, pk=row["pk"]):
                    self.assertNotIn("**(주소)", reading)
                    self.assertNotIn("(**주소**)", reading)
                    self.assertEqual(reading.count("주소"), reading.count("(주소)"))

    def test_address_rule_reaches_the_generation_prompt(self):
        """규칙 7 이 AI 생성 프롬프트에 실제로 들어간다.

        규칙을 문서에만 적고 프롬프트가 다른 파일을 읽으면, 다음에 생성하는
        발음은 다시 주소를 한 글자씩 푼다.
        """
        from apps.ai_pipeline.prompts import reading

        system = reading.system()
        self.assertIn("### 7. 주소는 풀지 않고 `(주소)` 로 적는다", system)
        self.assertIn("투 (주소)", system)

    def test_addresses_are_not_spelled_out(self):
        for name in ("readings_sentence.json", "readings_word.json"):
            rows = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
            spelled = [
                row["pk"] for row in rows if any(mark in row["reading"] for mark in SPELLED_ADDRESS)
            ]
            with self.subTest(name):
                self.assertEqual(spelled, [], "주소를 한 글자씩 풀어 적었다 - (주소) 로 적는다")
