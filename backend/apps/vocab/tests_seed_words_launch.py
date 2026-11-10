"""출시 전 보강 단어 명령(seed_words_launch)이 자기 목록을 실제로 넣는지 본다.

목록 형식은 tests.py 의 ALL_SEEDED 가 전 항목에 건다. 여기서는 명령이
seed_words_more 의 통로를 물려받으면서 목록과 출처를 제대로 넘기는지 본다.
연결이 끊기면 형식 검사는 그대로 초록이고, 운영에서만 "추가: 0개" 가 찍힌다.
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from .management.commands.seed_exam_words import EXAM_WORDS
from .management.commands.seed_words import WORDS as BASE_WORDS
from .management.commands.seed_words_launch import WORDS as LAUNCH_WORDS
from .management.commands.seed_words_more import WORDS as MORE_WORDS
from .models import Word

AI_SOURCE = "AI 생성(에이전트 검수)"


def run(*args: str) -> str:
    out = StringIO()
    call_command(*args, stdout=out, stderr=out)
    return out.getvalue()


class SeedWordsLaunchCommandTest(TestCase):
    def test_seeds_its_own_list_as_reviewed(self):
        run("seed_words_launch")

        self.assertEqual(
            set(Word.objects.values_list("term", flat=True)),
            {row[0] for row in LAUNCH_WORDS},
        )
        self.assertEqual(Word.objects.filter(is_reviewed=True).count(), len(LAUNCH_WORDS))

    def test_marks_ai_drafts_in_source(self):
        """사람이 줄별로 읽지 않은 묶음이라 출처로 골라낼 수 있어야 한다."""
        run("seed_words_launch")

        self.assertEqual(set(Word.objects.values_list("source", flat=True)), {AI_SOURCE})

    def test_previous_batch_keeps_its_list_and_source(self):
        run("seed_words_more")

        self.assertEqual(Word.objects.count(), len(MORE_WORDS))
        self.assertEqual(set(Word.objects.values_list("source", flat=True)), {"직접 작성"})

    def test_dry_run_saves_nothing(self):
        out = run("seed_words_launch", "--dry-run")

        self.assertEqual(Word.objects.count(), 0)
        self.assertIn(f"추가: {len(LAUNCH_WORDS)}개", out)

    def test_second_run_adds_nothing(self):
        run("seed_words_launch")

        out = run("seed_words_launch")

        self.assertEqual(Word.objects.count(), len(LAUNCH_WORDS))
        self.assertIn("추가: 0개", out)

    def test_existing_word_is_left_alone(self):
        """관리자가 고친 단어를 시드가 덮어쓰면 안 된다."""
        term = LAUNCH_WORDS[0][0]
        Word.objects.create(term=term, meaning="관리자가 고친 뜻", is_reviewed=True)

        run("seed_words_launch")

        self.assertEqual(Word.objects.get(term=term).meaning, "관리자가 고친 뜻")
        self.assertEqual(Word.objects.count(), len(LAUNCH_WORDS))


class LaunchWordsDataTest(TestCase):
    def test_terms_do_not_collide_with_earlier_batches_ignoring_case(self):
        """term 의 unique 는 대소문자를 구분한다. 같은 말이 대소문자만 달리 두 벌 들어가는 것을 막는다."""
        earlier = {row[0].lower() for row in (*BASE_WORDS, *MORE_WORDS, *EXAM_WORDS)}

        clashes = [row[0] for row in LAUNCH_WORDS if row[0].lower() in earlier]

        self.assertEqual(clashes, [])

    def test_terms_are_unique_within_the_batch_ignoring_case(self):
        terms = [row[0].lower() for row in LAUNCH_WORDS]

        self.assertEqual(len(terms), len(set(terms)))
