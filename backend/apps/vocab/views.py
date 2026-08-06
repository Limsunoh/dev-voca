from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import (
    AllowAny,
    BasePermission,
    IsAuthenticatedOrReadOnly,
)
from rest_framework.request import Request
from rest_framework.response import Response

from .models import LearningItem, Sentence, Word
from .quiz import grade_answer, make_question, sign_question
from .serializers import (
    QuizWordSerializer,
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

    # POST 지만 데이터를 바꾸지 않아 익명도 허용하는 액션. 채점처럼
    # "제출" 의미 때문에 POST 를 쓰지만 실제로는 조회에 가깝다.
    #
    # 여기 이름을 추가하려면 그 액션이 DB 에 아무것도 쓰지 않는지
    # 먼저 확인할 것. 이 목록에 올리는 순간 로그인 없이 열린다.
    SAFE_POST_ACTIONS: tuple[str, ...] = ()

    def get_permissions(self) -> list[BasePermission]:
        """쓰기는 검수 권한이 있는 사용자만.

        IsAuthenticatedOrReadOnly 만으로는 로그인한 일반 사용자가 항목을
        지울 수 있다. 검수 대상 콘텐츠이므로 쓰기 권한을 좁힌다.
        조회 범위(can_review)와 같은 기준을 쓴다.
        """
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [CanReview()]
        if self.action in self.SAFE_POST_ACTIONS:
            return [AllowAny()]
        return super().get_permissions()


class WordViewSet(LearningItemViewSet):
    """단어 조회/등록 API.

    조회는 누구나, 쓰기는 관리자만. 단어는 검수를 거쳐 나가는 콘텐츠라
    일반 사용자가 직접 추가하는 대상이 아니다(CLAUDE.md 의 검수 워크플로우).
    """

    model = Word
    list_serializer = WordListSerializer
    detail_serializer = WordDetailSerializer

    search_fields = ["term", "meaning", "description"]
    ordering_fields = ["term", "created_at", "difficulty"]
    ordering = ["term"]

    # 채점은 POST 지만 아무것도 저장하지 않는다. 로그인을 요구하면
    # 문제풀기를 아예 못 쓴다.
    SAFE_POST_ACTIONS = ("grade",)

    @action(detail=False)
    def quiz(self, request: Request) -> Response:
        """문제 하나를 낸다.

        출제를 서버에서 하는 이유는 두 가지다. 오답을 프론트에서 뽑으려면
        566개를 통째로 받아야 하고, 정답을 응답에 담으면 개발자도구로
        미리 보인다. 채점은 grade 엔드포인트로 따로 받는다.

        검수자에게도 검수된 단어만 낸다. 목록에서 미검수를 보여주는 건
        검수하라고 주는 것이지 학습하라고 주는 게 아니다. 아직 아무도
        확인하지 않은 뜻을 정답이라고 채점하면 그대로 잘못 외운다.

        ?category=git   분류를 좁힌다
        ?kind=meaning   유형을 고정한다. 없으면 매번 무작위
        ?exclude=1,2,3  방금 낸 문제를 다시 내지 않는다
        """
        # 목록과 달리 filter_queryset 을 쓰지 않는다. SearchFilter 가
        # 붙어 있어서 ?search=commit 으로 풀을 좁혀 정답 후보를 추릴 수
        # 있다. 출제에 필요한 건 분류 하나뿐이다.
        pool = self.model.objects.visible()

        category = request.query_params.get("category")
        if category:
            if category not in self.model.Category.values:
                return Response(
                    {"detail": "그런 분류는 없습니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            pool = pool.filter(category=category)

        exclude = _parse_ids(request.query_params.get("exclude", ""))
        question = make_question(
            pool, kind=request.query_params.get("kind"), exclude_ids=exclude
        )

        if question is None:
            # 보기 4개를 채울 만큼 단어가 없다. 분류를 너무 좁혔거나
            # 이미 다 푼 경우다. 사용자가 조건을 바꿀 수 있게 알려준다.
            return Response(
                {"detail": "문제를 낼 단어가 모자랍니다. 분류를 넓혀보세요."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "kind": question.kind,
                "kind_label": question.kind_label,
                "question": question.question,
                "prompt": question.prompt,
                "category": question.category,
                "category_label": question.category_label,
                "choices": [{"id": c.id, "text": c.text} for c in question.choices],
                # 채점 정보를 토큰으로 만들어 내려준다. 정답 id 를 그냥
                # 담으면 개발자도구로 보이고, 안 담으면 채점할 방법이 없다.
                # 무엇을 담고 왜 그런지는 quiz.sign_question 에 적어뒀다.
                "token": sign_question(
                    question.answer_id, [c.id for c in question.choices]
                ),
            }
        )

    @action(detail=False, methods=["post"])
    def grade(self, request: Request) -> Response:
        """고른 보기가 정답인지 알려주고 해설을 준다.

        틀렸을 때만 해설을 주면 맞힌 사람은 왜 맞았는지 모르고 넘어간다.
        어차피 한 문제가 끝난 시점이라 감출 이유가 없다.

        POST 인 이유: 토큰을 URL 에 실으면 브라우저 기록과 서버 로그에
        남는다. 채점은 조회가 아니라 제출이라 의미상으로도 POST 가 맞다.
        """
        # 본문 전체가 사용자 입력이다. JSON 은 배열이나 문자열도 될 수
        # 있어서 dict 라고 가정하고 .get 을 부르면 500 이 난다.
        if not isinstance(request.data, dict):
            return Response(
                {"detail": "요청 형식이 올바르지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token = request.data.get("token")
        picked = request.data.get("picked")

        if not isinstance(token, str):
            return Response(
                {"detail": "문제 정보가 올바르지 않습니다. 새 문제를 받아주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # picked 도 무엇이든 들어온다. 정수가 아니면 어느 보기와도 맞지
        # 않으므로 오답으로 친다. id 는 항상 양수라 -1 은 겹치지 않는다.
        #
        # bool 을 빼는 이유: 파이썬에서 True 는 int 라 1 번 보기를 고른
        # 것으로 처리된다.
        if isinstance(picked, bool) or not isinstance(picked, int):
            picked = -1

        graded = grade_answer(token, picked)
        if graded is None:
            return Response(
                {"detail": "문제 정보가 올바르지 않습니다. 새 문제를 받아주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        correct, answer_id = graded

        # 정답 단어는 항상 내려준다. 틀렸을 때 무엇이 답이었는지 봐야
        # 학습이 된다.
        #
        # visible() 로 좁히는 이유: 문제를 낸 뒤 검수가 취소됐을 수 있다.
        # 그때는 정답을 보여주지 않고 404 를 준다 - 아무도 확인하지 않은
        # 내용을 정답이라고 알려주면 그대로 잘못 외운다.
        word = self.model.objects.visible().filter(pk=answer_id).first()
        if word is None:
            # 문제를 낸 뒤 그 단어가 지워졌거나 검수가 취소된 경우.
            return Response(
                {"detail": "이 문제는 지금 풀 수 없습니다. 다음 문제로 넘어가주세요."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "correct": correct,
                "answer_id": answer_id,
                "word": QuizWordSerializer(word).data,
            }
        )


# exclude 로 받을 id 개수 상한. 방금 푼 문제를 거르는 용도라 이 정도면
# 충분하고, 없으면 긴 문자열을 보내 pk__in 을 무겁게 만들 수 있다.
MAX_EXCLUDE_IDS = 100

# id 는 bigint 다. 이 범위를 넘으면 DB 가 쿼리를 거절한다.
_MAX_PK = 2**63 - 1
_MAX_PK_DIGITS = len(str(_MAX_PK))


def _parse_ids(raw: str) -> list[int]:
    """"1,2,3" 을 [1, 2, 3] 으로. 숫자가 아닌 것은 버린다.

    사용자가 보내는 값이라 무엇이든 들어올 수 있다. 검증 없이 넘기면
    pk__in 에서 터진다.

    isascii() 를 같이 보는 이유: isdigit() 은 "²" 나 아랍-인도 숫자에도
    True 를 주는데 int() 는 그중 일부에서 터진다.

    자릿수도 본다. id 는 bigint 라 범위를 넘는 값을 pk__in 에 넣으면
    DB 가 거절해서 500 이 난다.

    쪼갠 조각 수부터 자르는 이유: 유효한 id 만 세면 "a,a,a,..." 처럼
    쓰레기만 보내 상한을 피해가며 순회를 길게 끌 수 있다.
    """
    ids = []
    for part in raw.split(",")[: MAX_EXCLUDE_IDS * 10]:
        part = part.strip()
        if part.isascii() and part.isdigit() and len(part) <= _MAX_PK_DIGITS:
            value = int(part)
            if 0 < value <= _MAX_PK:
                ids.append(value)
                if len(ids) >= MAX_EXCLUDE_IDS:
                    break
    return ids


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
