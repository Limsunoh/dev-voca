"""선택지 칸의 한글 이름(serializers.ChoiceLabelField)이 예전과 같은 JSON 을 내는가.

예전 main 은 라벨 칸을 `serializers.CharField(source="get_difficulty_display", read_only=True)` 로
두었다. 지금은 칸의 choices 로 만든 사전을 찾는다. 기준은 "예전 선언으로 만든 시리얼라이저와 같은
.data 를 내는가" 다. 그래서 여기서 예전 선언을 그대로 다시 써 둔 Old* 시리얼라이저와 견준다.

    선택지에 있는 값      모든 선택지에서 get_FOO_display() 와 같은 글자
    선택지에 없는 값      값을 그대로 글자로("zzz", 정수 칸의 99 -> "99")
    빈 문자열·None        "" 와 null (빈 과목, 저장 안 한 인스턴스)
    응답 전체             단어·문장 목록·상세, 문장 채점 응답이 예전 선언과 같은 JSON
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework import serializers
from rest_framework.test import APIClient

from . import serializers as vocab_serializers
from .models import LearningItem, Sentence, SentenceKind, Word

WORDS = "/api/vocab/words/"
SENTENCES = "/api/vocab/sentences/"

# 예전 main 의 라벨 선언. 칸 이름 -> get_FOO_display.
OLD_LABELS = {
    "difficulty_label": "get_difficulty_display",
    "category_label": "get_category_display",
    "exam_subject_label": "get_exam_subject_display",
    "kind_label": "get_kind_display",
}


def old_version(serializer_class: type[serializers.ModelSerializer]) -> type:
    """같은 시리얼라이저에서 라벨 칸만 예전 선언(CharField + get_FOO_display)으로 바꾼 것."""
    attrs = {
        name: serializers.CharField(source=method, read_only=True)
        for name, method in OLD_LABELS.items()
        if name in serializer_class._declared_fields
    }
    return type(f"Old{serializer_class.__name__}", (serializer_class,), attrs)


LABELLED = [
    vocab_serializers.WordListSerializer,
    vocab_serializers.WordDetailSerializer,
    vocab_serializers.SentenceListSerializer,
    vocab_serializers.SentenceDetailSerializer,
    vocab_serializers.QuizSentenceSerializer,
]

# 칸마다 시험할 값: 선택지 전부 + 선택지에 없는 값 + 빈 값.
ODD_VALUES = {
    "difficulty": [99, 0],
    "category": ["zzz", "", "GIT"],
    "exam_subject": ["", "nope"],
    "kind": ["", "other"],
}


def word(**extra) -> Word:
    fields = {"term": "cache", "meaning": "캐시", "description": "설명", "is_reviewed": True}
    return Word.objects.create(**{**fields, **extra})


def sentence(**extra) -> Sentence:
    fields = {"text": "Could you take a look?", "translation": "봐 주실래요?", "is_reviewed": True}
    return Sentence.objects.create(**{**fields, **extra})


class EveryValueMatchesTest(TestCase):
    """모든 라벨 칸, 모든 선택지와 이상한 값에서 예전 선언과 같은 .data 다."""

    def setUp(self):
        self.objects = {Word: word(), Sentence: sentence()}

    def values_for(self, model, field_name: str) -> list:
        field = model._meta.get_field(field_name)
        return [value for value, _label in field.flatchoices] + ODD_VALUES[field_name]

    def test_every_choice_and_odd_value_gives_the_same_data(self):
        checked = 0
        for serializer_class in LABELLED:
            model = serializer_class.Meta.model
            old_class = old_version(serializer_class)
            for label_name, method in OLD_LABELS.items():
                if label_name not in serializer_class._declared_fields:
                    continue
                field_name = method[len("get_"):-len("_display")]
                for value in self.values_for(model, field_name):
                    # 칸 하나만 바꾼 새 인스턴스. 앞 값이 다음 칸 검사에 남지 않게 한다.
                    obj = model.objects.get(pk=self.objects[model].pk)
                    setattr(obj, field_name, value)
                    with self.subTest(serializer=serializer_class.__name__, field=field_name, value=value):
                        new = serializer_class(obj).data
                        old = old_class(obj).data
                        self.assertEqual(new, old)
                        self.assertEqual(new[label_name], str(getattr(obj, method)()))
                        self.assertIsInstance(new[label_name], str)
                        checked += 1
        self.assertGreater(checked, 50)

    def test_integer_label_out_of_choices_is_text(self):
        """정수 칸에 선택지에 없는 값이면 숫자가 아니라 글자 "99" 다(CharField 가 그랬다)."""
        obj = self.objects[Word]
        obj.difficulty = 99
        data = vocab_serializers.WordListSerializer(obj).data
        self.assertEqual(data["difficulty_label"], "99")

    def test_none_value_is_null_like_before(self):
        obj = Word(term="x", meaning="y", difficulty=None, category=None)
        for serializer_class in (vocab_serializers.WordListSerializer, vocab_serializers.WordDetailSerializer):
            new = serializer_class(obj).data
            old = old_version(serializer_class)(obj).data
            self.assertEqual(new["difficulty_label"], old["difficulty_label"])
            self.assertEqual(new["category_label"], old["category_label"])

    def test_many_true_uses_the_child_model(self):
        """목록(many=True)에서도 칸을 찾는 모델이 맞다. 단어와 문장을 섞어 부르며 사전이 엉키지 않는다."""
        words = [word(term=f"w{i}", category=c) for i, c in enumerate(["git", "database", ""])]
        sentences = [sentence(text=f"s{i}", kind=k) for i, k in enumerate(SentenceKind.values)]
        new_w = vocab_serializers.WordListSerializer(words, many=True).data
        new_s = vocab_serializers.SentenceListSerializer(sentences, many=True).data
        self.assertEqual(new_w, old_version(vocab_serializers.WordListSerializer)(words, many=True).data)
        self.assertEqual(new_s, old_version(vocab_serializers.SentenceListSerializer)(sentences, many=True).data)

    def test_labels_are_the_model_choice_labels(self):
        """한 줄로 확인해 둔다. 사전이 칸을 잘못 고르면(예: 분류 칸에 과목 사전) 여기서 다르다."""
        obj = word(term="label-check", category=LearningItem.Category.GIT, difficulty=LearningItem.Difficulty.EASY)
        data = vocab_serializers.WordDetailSerializer(obj).data
        self.assertEqual(data["category_label"], "버전 관리(Git)")
        self.assertEqual(data["difficulty_label"], "쉬움")


class EndpointJsonMatchesOldTest(TestCase):
    """HTTP 응답 전체가 예전 선언과 같다(목록·상세·채점)."""

    def setUp(self):
        self.client = APIClient()
        categories = [value for value, _ in LearningItem.Category.choices] + [""]
        for i, category in enumerate(categories):
            word(term=f"term{i}", category=category, difficulty=(i % 3) + 1,
                 is_exam=bool(i % 2), exam_subject="database" if i % 2 else "")
        word(term="hidden", is_reviewed=False)
        for i, kind in enumerate(SentenceKind.values * 3):
            sentence(text=f"Sentence number {i} here", kind=kind, context=f"상황 {i}",
                     category=categories[i % len(categories)], is_exam=bool(i % 2),
                     exam_subject="design" if i % 2 else "")

    def old_json(self, serializer_class, objs, many: bool):
        return old_version(serializer_class)(objs, many=many).data

    def test_word_list_and_detail(self):
        body = self.client.get(WORDS, {"page_size": 50}).json()
        rows = body["results"]
        ids = [row["id"] for row in rows]
        objs = {w.pk: w for w in Word.objects.filter(pk__in=ids)}
        self.assertNotIn("hidden", [row["term"] for row in rows])
        for row in rows:
            old = self.old_json(vocab_serializers.WordListSerializer, objs[row["id"]], many=False)
            self.assertEqual(row, dict(old))

            detail = self.client.get(f"{WORDS}{row['id']}/").json()
            old_detail = self.old_json(vocab_serializers.WordDetailSerializer, objs[row["id"]], many=False)
            self.assertEqual(detail, dict(old_detail))

    def test_sentence_list_and_detail(self):
        rows = self.client.get(SENTENCES, {"page_size": 50}).json()["results"]
        self.assertTrue(rows)
        objs = {s.pk: s for s in Sentence.objects.filter(pk__in=[r["id"] for r in rows])}
        for row in rows:
            old = self.old_json(vocab_serializers.SentenceListSerializer, objs[row["id"]], many=False)
            self.assertEqual(row, dict(old))
            detail = self.client.get(f"{SENTENCES}{row['id']}/").json()
            old_detail = self.old_json(vocab_serializers.SentenceDetailSerializer, objs[row["id"]], many=False)
            self.assertEqual(detail, dict(old_detail))

    def test_sentence_grade_response(self):
        """상황 고르기를 채점하면 문장 설명이 붙는다. 그 부분이 예전 선언과 같다."""
        body = self.client.get(f"{SENTENCES}quiz/", {"kind": "situation"}).json()
        graded = None
        for choice in body["choices"]:
            res = self.client.post(f"{SENTENCES}grade/", {"token": body["token"], "picked": choice["id"]},
                                   format="json")
            self.assertEqual(res.status_code, 200, res.content[:200])
            if res.json()["correct"]:
                graded = res.json()
                break
        self.assertIsNotNone(graded)
        obj = Sentence.objects.get(pk=graded["sentence"]["id"])
        old = self.old_json(vocab_serializers.QuizSentenceSerializer, obj, many=False)
        self.assertEqual(graded["sentence"], dict(old))
        self.assertIn(graded["sentence"]["kind_label"], dict(SentenceKind.choices).values())
