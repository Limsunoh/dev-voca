from rest_framework import serializers

from .models import LearningItem, Sentence, Word


class UnreviewOnContentChangeMixin:
    """내용을 고치면 검수 상태를 되돌린다.

    검수는 "사람이 이 내용을 확인했다"는 뜻이다. 뜻·예문을 갈아끼웠는데
    플래그가 True 로 남으면, 아무도 확인한 적 없는 내용이 검수 완료
    상태로 사용자에게 나간다. AI 파이프라인이 기존 항목을 갱신하게 되면
    그대로 노출 사고가 된다.

    쓰는 쪽에서 CONTENT_FIELDS 를 정의한다. 난이도·분류·출처처럼 분류
    정보에 해당하는 필드는 빼둔다 - 바뀌어도 "확인한 내용" 이 달라지지 않는다.
    """

    # 기본값을 주지 않는다. 빈 튜플을 기본으로 두면 정의를 빠뜨렸을 때
    # any() 가 항상 False 라 검수 되돌리기가 조용히 꺼진다 - 에러 없이,
    # 아무도 확인 안 한 내용이 검수 완료 상태로 나간다.
    # 선언만 남겨 미정의 시 AttributeError 로 즉시 터지게 한다.
    CONTENT_FIELDS: tuple[str, ...]

    def __init_subclass__(cls, **kwargs) -> None:
        """정의 누락을 앱 로드 시점에 잡는다.

        런타임 AttributeError 는 그 엔드포인트를 실제로 호출해야 드러난다.
        여기서 막으면 배포 전에 걸린다.
        """
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "CONTENT_FIELDS", None):
            raise TypeError(
                f"{cls.__name__} 이 CONTENT_FIELDS 를 정의하지 않았습니다. "
                "내용이 바뀌었을 때 검수를 되돌릴 필드를 지정해야 합니다."
            )

    def update(self, instance: LearningItem, validated_data: dict) -> LearningItem:
        content_changed = any(
            field in validated_data and validated_data[field] != getattr(instance, field)
            for field in self.CONTENT_FIELDS
        )
        if content_changed:
            instance.is_reviewed = False
        return super().update(instance, validated_data)


class WordListSerializer(serializers.ModelSerializer):
    """목록용 - 카드에 필요한 만큼만.

    설명·예문 같은 긴 텍스트는 빼서 목록 응답을 가볍게 유지한다.
    """

    difficulty_label = serializers.CharField(source="get_difficulty_display", read_only=True)
    # 화면은 이 라벨만 쓴다. category(영어 코드)는 필터 링크를 만들 때 필요해서 함께 준다.
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Word
        fields = [
            "id",
            "term",
            "meaning",
            "difficulty",
            "difficulty_label",
            "category",
            "category_label",
        ]


class WordDetailSerializer(
    UnreviewOnContentChangeMixin, serializers.ModelSerializer
):
    """상세 조회 + 생성/수정 공용."""

    difficulty_label = serializers.CharField(source="get_difficulty_display", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Word
        fields = [
            "id",
            "term",
            "meaning",
            "description",
            "example",
            "example_translation",
            "difficulty",
            "difficulty_label",
            "category",
            "category_label",
            "source",
            "is_reviewed",
            "created_at",
            "updated_at",
        ]
        # is_reviewed 는 API 로 못 바꾼다. 검수는 Admin 에서만 한다
        # (API 로 열면 검수 게이트를 클라이언트가 스스로 통과시킬 수 있다).
        read_only_fields = ["is_reviewed", "created_at", "updated_at"]

    # 내용이 바뀌면 다시 검수받아야 하는 필드. 난이도·분류·출처는 분류 정보라
    # 바뀌어도 "사람이 확인한 내용"이 달라지지 않으므로 제외한다.
    CONTENT_FIELDS = ("term", "meaning", "description", "example", "example_translation")

    # 앞뒤 공백 제거와 빈 값 거부는 CharField 가 이미 한다
    # (trim_whitespace=True, allow_blank=False 가 기본값).
    # validate_<field> 에서 strip 을 다시 하면 유니크 검사가 도는 시점보다
    # 늦어서, "deploy " 처럼 공백만 다른 중복이 DB 까지 내려갈 수 있다.
    # 안내 문구만 한글로 바꿔 준다.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["term"].error_messages["blank"] = "단어를 입력해주세요."
        self.fields["meaning"].error_messages["blank"] = "뜻을 입력해주세요."


class SentenceListSerializer(serializers.ModelSerializer):
    """목록용.

    문장은 단어와 달리 본문(text)이 곧 제목이라 목록에서도 통째로 보여준다.
    대신 설명은 뺀다.
    """

    difficulty_label = serializers.CharField(source="get_difficulty_display", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Sentence
        fields = [
            "id",
            "text",
            "translation",
            "kind",
            "kind_label",
            "context",
            "difficulty",
            "difficulty_label",
            "category",
            "category_label",
        ]


class SentenceDetailSerializer(
    UnreviewOnContentChangeMixin, serializers.ModelSerializer
):
    """상세 조회 + 생성/수정 공용."""

    difficulty_label = serializers.CharField(source="get_difficulty_display", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Sentence
        fields = [
            "id",
            "text",
            "translation",
            "kind",
            "kind_label",
            "context",
            "description",
            "difficulty",
            "difficulty_label",
            "category",
            "category_label",
            "source",
            "is_reviewed",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["is_reviewed", "created_at", "updated_at"]

    # kind 는 어디서 마주치는 문장인지를 나타내는 분류라, 바뀌어도 문장
    # 내용 자체가 달라지지 않는다. context 는 뜻을 좌우하므로 포함한다.
    CONTENT_FIELDS = ("text", "translation", "context", "description")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["text"].error_messages["blank"] = "문장을 입력해주세요."
        self.fields["translation"].error_messages["blank"] = "해석을 입력해주세요."
