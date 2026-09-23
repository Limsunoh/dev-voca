"""오답 노트와 학습 기록.

`views.py` 와 나눈 이유: 저쪽은 판을 열고 답을 받는 **쓰기** 경로이고,
여기는 이미 쌓인 것을 **읽기만** 한다. 한 파일에 두면 "답하면 무엇이
바뀌는가" 를 읽을 때 조회 코드가 사이에 끼어 흐름이 끊긴다.
"""

from __future__ import annotations

import sys

from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.vocab.models import Sentence, Word

# 대상 종류를 여기서 다시 적지 않는다. 저장할 때 quiz 의 값으로 넣으므로
# 두 벌이 되면 한쪽만 고쳐졌을 때 그 종류가 통째로 목록에서 사라진다.
from apps.vocab.quiz import TARGET_SENTENCE, TARGET_WORD

from .models import ReviewState


class MistakesThrottle(UserRateThrottle):
    """오답 노트 조회.

    쓰기가 없어 막을 것은 데이터가 아니라 **비용**이다(순위표와 같은
    이유). 한 번에 검수 하위 질의 둘이 든 COUNT 와 본문 조회 둘이 돈다.
    learning 의 다른 뷰 여덟 개가 전부 한도를 다는데 여기만 없었다.

    로그인해야 부르는 곳이라 게스트 통(`_PerUserOrShared`)이 필요 없다.
    DRF 의 계정별 통을 그대로 쓴다.

    **한도가 settings 가 아니라 여기 있다.** 다른 한도는 전부
    `DEFAULT_THROTTLE_RATES` 에 있는데 이것만 빠져 있다. 클래스에 `rate` 가
    있으면 DRF 는 settings 를 읽지 않으므로, 나중에 settings 에 "mistakes"
    를 더해도 이 줄이 조용히 이긴다 - 그쪽으로 옮길 때는 이 줄을 지운다.
    테스트에서 넉넉히 여는 모양은 settings 의 관용구를 그대로 따랐다.
    """

    scope = "mistakes"
    rate = "5000/min" if sys.argv[1:2] == ["test"] else "60/min"


class MistakesView(APIView):
    """오답 노트. 마지막에 틀린 것만 모아 보여준다.

    **복습 대상과 다르다.** 복습(`review.py`)은 "지금 볼 것" 이라 틀린 것에
    더해 오래된 것(마지막 정답에서 7일)까지 낸다. 여기는 이름 그대로
    **틀린 것만**이다 - 틀린 적 없는데 오래된 단어는 오답이 아니다.

    그래서 두 화면의 개수가 다르다. 화면이 그 사실을 한 줄로 알린다.

    **로그인이 필요하다.** 무엇을 틀렸는지는 계정에 쌓이는 것이다.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [MistakesThrottle]

    def get(self, request: Request) -> Response:
        rows = (
            ReviewState.objects.filter(user=request.user, is_wrong=True)
            # **보여줄 수 있는 것만 남기고 세어야 한다.** 처음에는 페이지를
            # 자른 뒤에 본문 없는 줄을 뺐는데, 그러면 count 와 실제 줄 수가
            # 어긋난다 - 단어 둘을 미검수로 돌리니 "22개" 라고 적힌 화면에
            # 18줄만 떴다(실측). 마지막 페이지가 통째로 빌 수도 있다.
            #
            # 그래서 가려질 줄을 **질의에서** 뺀다. 그러면 count 도 페이지
            # 나눔도 실제로 보이는 것과 같아진다.
            .filter(_visible_targets())
            # 늦게 쌓인 것부터. **"최근에 틀린 것부터" 가 아니다** - 그렇게
            # 정렬할 수 있는 칸이 아직 없다.
            #
            # 처음에는 `-updated_at` 으로 두고 "마지막에 틀린 때" 라고 불렀다.
            # 틀렸다. `updated_at` 은 auto_now 인데, 자유 문제풀이와 일일공부는
            # bulk_update 로 줄을 고쳐서 auto_now 가 아예 안 돈다(실측: 30일
            # 전에 틀린 단어를 오늘 또 틀려도 시각이 그대로였다). 복습만
            # save 를 써서 움직인다. 세 경로 중 둘이 안 움직이는 값으로
            # "최근" 을 정하면 방금 틀린 것이 뒤로 밀린다.
            #
            # pk 는 그 항목을 **처음 푼** 순서다(맞혔을 때도 줄이 생긴다).
            # 그래서 1년 전에 맞혔다가 오늘 틀린 단어는 아래에 온다. 화면은
            # 순서를 약속하지 않으므로 그걸로 충분하다. 진짜 "마지막에 틀린
            # 때" 가 필요하면 ReviewState 에 그 칸을 만들어 세 경로가 다
            # 채워야 한다.
            .order_by("-pk")
        )

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(rows, request, view=self)

        return paginator.get_paginated_response(_serialize(page or []))


def _visible_targets() -> Q:
    """보여줄 수 있는 대상만 남기는 조건.

    **id 를 파이썬으로 끌어오지 않는다.** `values("pk")` 를 그대로 넘기면
    Django 가 하위 질의로 만들어 DB 안에서 끝낸다. 목록에 담아 넘기면
    단어·문장 전부(900개 남짓)를 매 요청마다 읽어 오게 된다.

    종류마다 조건이 다른 이유: `ReviewState` 는 대상을 FK 로 안 묶는다
    (단어일 수도 문장일 수도 있어 한 칸에 안 들어간다). 그래서 종류를 보고
    각자의 표에 묻는다.

    지워진 대상도 이 조건에서 함께 빠진다. 하위 질의에 그 id 가 없다.
    """
    return Q(
        target_type=TARGET_WORD,
        target_id__in=Word.objects.visible().values("pk"),
    ) | Q(
        target_type=TARGET_SENTENCE,
        target_id__in=Sentence.objects.visible().values("pk"),
    )


def _serialize(rows: list[ReviewState]) -> list[dict]:
    """줄들을 화면이 쓸 모양으로 바꾼다.

    **본문을 한 번에 가져온다.** 줄마다 Word/Sentence 를 조회하면 20줄에
    20번이 된다. 종류별로 id 를 모아 두 번만 묻는다.

    **본문을 가져올 때도 검수 게이트를 건다.** 주 게이트는 질의 안의
    `_visible_targets` 다. 여기서 한 번 더 거는 것은 그 질의와 이 조회
    사이에 검수가 취소되는 짧은 틈 때문이다 - 그때 게이트가 없으면 검수
    취소된 내용이 그대로 나간다(CLAUDE.md 의 검수 규칙). 비용은 거의 없다.
    """
    word_ids = [r.target_id for r in rows if r.target_type == TARGET_WORD]
    sentence_ids = [r.target_id for r in rows if r.target_type == TARGET_SENTENCE]

    words = {
        w.pk: w
        for w in Word.objects.visible().filter(pk__in=word_ids).only(
            "pk", "term", "meaning"
        )
    }
    sentences = {
        s.pk: s
        for s in Sentence.objects.visible().filter(pk__in=sentence_ids).only(
            "pk", "text", "translation"
        )
    }

    out: list[dict] = []
    for row in rows:
        if row.target_type == TARGET_WORD:
            target = words.get(row.target_id)
            text, meaning = (target.term, target.meaning) if target else (None, None)
        else:
            target = sentences.get(row.target_id)
            text, meaning = (
                (target.text, target.translation) if target else (None, None)
            )

        # 본문을 못 찾은 줄은 뺀다. 지워졌거나 미검수로 돌아간 항목이다.
        # 빈 줄을 내보내면 화면에 뜻 없는 칸이 생기고, 눌러도 갈 곳이 없다.
        if text is None:
            continue

        out.append(
            {
                "id": row.pk,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "text": text,
                "meaning": meaning,
                # **틀린 날짜는 안 보낸다.** 담을 칸이 없다.
                #
                # 한동안 updated_at 을 "마지막에 틀린 때" 로 내보냈는데
                # 거짓이었다. 자유 문제풀이와 일일공부는 bulk_update 로
                # 줄을 고치고, 그 경로는 auto_now 를 아예 안 돌린다.
                # 30일 전에 틀린 단어를 오늘 또 틀려도 화면에는 "8월 18일에
                # 틀림" 이라고 떴다(실측). 세 경로 중 복습만 맞는 값을 냈다.
                #
                # 틀린 날짜를 보여주려면 ReviewState 에 그 칸을 만들고 세
                # 경로가 다 채워야 한다. 모델 변경이라 이번 범위 밖이다.
                # 틀린 날짜를 보여주느니 안 보여주는 것이 낫다.
                #
                # "몇 번 더 맞히면 빠지나" 도 같은 이유로 안 넣는다. 틀린
                # 줄은 streak 이 0 이라 값이 늘 같아, 줄마다 보내면 화면이
                # 같은 문장을 되풀이한다. 그 약속은 tests_mistakes 가 지킨다.
            }
        )

    return out
