from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, serializers, viewsets
from rest_framework.permissions import BasePermission, IsAuthenticatedOrReadOnly

from .models import Word
from .serializers import WordDetailSerializer, WordListSerializer


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


class WordViewSet(viewsets.ModelViewSet):
    """단어 조회/등록 API.

    조회는 누구나, 쓰기는 관리자만. 단어는 검수를 거쳐 나가는 콘텐츠라
    일반 사용자가 직접 추가하는 대상이 아니다(CLAUDE.md 의 검수 워크플로우).
    """

    permission_classes = [IsAuthenticatedOrReadOnly]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["term", "meaning", "description"]
    filterset_fields = ["category", "difficulty"]
    ordering_fields = ["term", "created_at", "difficulty"]
    ordering = ["term"]

    def get_queryset(self) -> QuerySet[Word]:
        """사용자에게는 검수된 단어만 보인다.

        관리자는 검수 전 단어까지 봐야 검수를 할 수 있으므로 전체를 준다.
        이 분기가 이 API 의 핵심 규칙이다 - 바꾸기 전에 CLAUDE.md 를 확인할 것.
        """
        if can_review(self.request.user):
            # 검수 대기(is_reviewed=False)를 앞에 모아 준다. 섞여 나오면
            # 무엇이 아직 검수 전인지 목록에서 알아보기 어렵다.
            return Word.objects.all().order_by("is_reviewed", "term")
        return Word.objects.visible()

    def get_serializer_class(self) -> type[serializers.ModelSerializer]:
        if self.action == "list":
            return WordListSerializer
        return WordDetailSerializer

    def get_permissions(self) -> list[BasePermission]:
        """쓰기는 검수 권한이 있는 사용자만.

        IsAuthenticatedOrReadOnly 만으로는 로그인한 일반 사용자가 단어를
        지울 수 있다. 검수 대상 콘텐츠이므로 쓰기 권한을 좁힌다.
        조회 범위(_can_review)와 같은 기준을 쓴다.
        """
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [CanReview()]
        return super().get_permissions()
