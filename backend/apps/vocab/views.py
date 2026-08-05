from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response

from .models import LearningItem, Sentence, Word
from .serializers import (
    SentenceDetailSerializer,
    SentenceListSerializer,
    WordDetailSerializer,
    WordListSerializer,
)


def can_review(user) -> bool:
    """검수 권한 판정.

    조회 범위(get_queryset)와 쓰기 권한(CanReview)이 이 함수 하나를 본다.
    판정이 두 곳으로 갈리면 한쪽만 바뀌었을 때 조용히 어긋난다 - 예를 들어
    쓰기만 superuser 로 좁히면 일반 staff 가 미검수 단어를 계속 조회하게 된다.
    """
    return user.is_authenticated and user.is_staff and user.is_active


class CanReview(BasePermission):
    """검수자만 통과. IsAdminUser 와 달리 is_active 까지 본다."""

    message = "검수 권한이 필요합니다."

    def has_permission(self, request, view) -> bool:
        return can_review(request.user)


class LearningItemViewSet(viewsets.ModelViewSet):
    """학습 콘텐츠(단어/문장) 공용 베이스.

    검수 게이트와 쓰기 권한은 콘텐츠 타입이 달라도 규칙이 같다. 도메인마다
    복사해두면 한쪽만 고쳤을 때 조용히 어긋나고, 그 어긋남이 곧 미검수
    노출이다. 규칙을 여기 한 곳에 둔다.

    상속하는 쪽이 정할 것:
        model             - 조회 대상
        list_serializer   - 목록용
        detail_serializer - 상세/생성/수정용
    """

    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["category", "difficulty"]

    model: type[LearningItem]
    list_serializer: type[serializers.ModelSerializer]
    detail_serializer: type[serializers.ModelSerializer]

    def get_queryset(self) -> QuerySet:
        """사용자에게는 검수된 항목만 보인다.

        관리자는 검수 전 항목까지 봐야 검수를 할 수 있으므로 전체를 준다.
        이 분기가 이 API 의 핵심 규칙이다 - 바꾸기 전에 CLAUDE.md 를 확인할 것.
        """
        if can_review(self.request.user):
            return self.model.objects.all()
        return self.model.objects.visible()

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        """검수자에게는 검수 대기를 앞에 모아 준다.

        get_queryset 에서 order_by 를 걸면 소용이 없다. OrderingFilter 가
        그 뒤에 돌면서 order_by 를 통째로 갈아끼우기 때문이다(ordering
        기본값이 항상 있어서 무조건 덮어쓴다).

        그래서 필터가 다 끝난 뒤에 정렬 키를 앞에 덧붙인다. 사용자가 고른
        정렬은 뒤에 남아 그대로 작동한다.
        """
        queryset = super().filter_queryset(queryset)
        if can_review(self.request.user):
            return queryset.order_by("is_reviewed", *queryset.query.order_by)
        return queryset

    def get_serializer_class(self) -> type[serializers.ModelSerializer]:
        if self.action == "list":
            return self.list_serializer
        return self.detail_serializer

    @action(detail=False)
    def categories(self, request: Request) -> Response:
        """분류 목록. 화면의 필터 버튼을 만들 때 쓴다.

        프론트에 목록을 복사해두면 분류를 추가할 때 두 곳을 고쳐야 하고,
        한쪽만 고치면 조용히 어긋난다. 라벨의 출처는 모델 하나로 둔다.
        """
        return Response(
            [
                {"value": value, "label": label}
                for value, label in self.model.Category.choices
            ]
        )

    def get_permissions(self) -> list[BasePermission]:
        """쓰기는 검수 권한이 있는 사용자만.

        IsAuthenticatedOrReadOnly 만으로는 로그인한 일반 사용자가 항목을
        지울 수 있다. 검수 대상 콘텐츠이므로 쓰기 권한을 좁힌다.
        조회 범위(can_review)와 같은 기준을 쓴다.
        """
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [CanReview()]
        return super().get_permissions()


class WordViewSet(LearningItemViewSet):
    """단어 조회/등록 API.

    조회는 누구나, 쓰기는 관리자만. 단어는 검수를 거쳐 나가는 콘텐츠라
    일반 사용자가 직접 추가하는 대상이 아니다(CLAUDE.md 의 검수 워크플로우).
    """

    model = Word
    list_serializer = WordListSerializer
    detail_serializer = WordDetailSerializer
    reviewer_ordering = ("is_reviewed", "term")

    search_fields = ["term", "meaning", "description"]
    ordering_fields = ["term", "created_at", "difficulty"]
    ordering = ["term"]


class SentenceViewSet(LearningItemViewSet):
    """문장 조회/등록 API. 규칙은 단어와 같다."""

    model = Sentence
    list_serializer = SentenceListSerializer
    detail_serializer = SentenceDetailSerializer

    # 문장은 본문·해석·나오는 상황까지 검색 대상이다. 에러 메시지를 찾을 때
    # 원문 일부를 그대로 붙여넣는 경우가 많아 text 검색이 특히 중요하다.
    search_fields = ["text", "translation", "context", "description"]
    filterset_fields = ["category", "difficulty", "kind"]
    ordering_fields = ["created_at", "difficulty", "id"]
    ordering = ["id"]

    @action(detail=False)
    def kinds(self, request: Request) -> Response:
        """종류 목록(실무 표현/에러 메시지). 분류와 같은 이유로 서버가 준다."""
        return Response(
            [
                {"value": value, "label": label}
                for value, label in Sentence.Kind.choices
            ]
        )
