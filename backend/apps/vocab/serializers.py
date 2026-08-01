from rest_framework import serializers

from .models import Word


class WordListSerializer(serializers.ModelSerializer):
    """목록용 - 카드에 필요한 만큼만.

    설명·예문 같은 긴 텍스트는 빼서 목록 응답을 가볍게 유지한다.
    """

    difficulty_label = serializers.CharField(source="get_difficulty_display", read_only=True)

    class Meta:
        model = Word
        fields = ["id", "term", "meaning", "difficulty", "difficulty_label", "category"]


class WordDetailSerializer(serializers.ModelSerializer):
    """상세 조회 + 생성/수정 공용."""

    difficulty_label = serializers.CharField(source="get_difficulty_display", read_only=True)

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

    def update(self, instance: Word, validated_data: dict) -> Word:
        """내용을 고치면 검수 상태를 되돌린다.

        검수는 "사람이 이 내용을 확인했다"는 뜻이다. 뜻·예문을 갈아끼웠는데
        플래그가 True 로 남으면, 아무도 확인한 적 없는 문장이 검수 완료
        상태로 사용자에게 나간다. AI 파이프라인이 기존 단어를 갱신하게 되면
        그대로 노출 사고가 된다.
        """
        content_changed = any(
            field in validated_data and validated_data[field] != getattr(instance, field)
            for field in self.CONTENT_FIELDS
        )
        if content_changed:
            instance.is_reviewed = False
        return super().update(instance, validated_data)

    # 앞뒤 공백 제거와 빈 값 거부는 CharField 가 이미 한다
    # (trim_whitespace=True, allow_blank=False 가 기본값).
    # validate_<field> 에서 strip 을 다시 하면 유니크 검사가 도는 시점보다
    # 늦어서, "deploy " 처럼 공백만 다른 중복이 DB 까지 내려갈 수 있다.
    # 안내 문구만 한글로 바꿔 준다.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["term"].error_messages["blank"] = "단어를 입력해주세요."
        self.fields["meaning"].error_messages["blank"] = "뜻을 입력해주세요."
