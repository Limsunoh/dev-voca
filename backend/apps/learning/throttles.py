"""판 요청 제한.

막으려는 것은 "판을 열고 닫기를 반복해 행만 쌓는 것" 이다. 점수는 하루에
가장 잘한 한 판만 세므로 아무리 많이 보내도 순위는 안 오른다. 남는 위험은
저장 공간과 쓰기 부하다.

로그인한 사람은 계정별로, 로그인하지 않은 사람은 접속 IP 별로 센다. 세는 규칙과
나누는 이유는 accounts.throttles.PerUserOrIpThrottle 에 있다.

IP 통은 계정 통보다 크게 잡는다(guest_multiplier). 학교·회사 와이파이처럼 IP 하나를
여럿이 쓴다. 답하기는 IP 하나에 동시 약 110명까지 받는다(계산은
RoundAnswerThrottle). "로그인 안 하면 429 가 난다" 는 신고가 들어오면 그
사람이 몇 명과 IP 를 같이 쓰는지부터 본다.

순위표에도 IP 통이 있다(순위표별로 하나씩, 각 1200/분). 판을 시작하기 전에
보는 화면이라 답하기보다 여기가 먼저 막힐 수도 있다.
"""

from __future__ import annotations

from apps.accounts.throttles import PerUserOrIpThrottle


class RoundStartThrottle(PerUserOrIpThrottle):
    scope = "round_start"


class RoundFinishThrottle(PerUserOrIpThrottle):
    scope = "round_finish"


class RoundAnswerThrottle(PerUserOrIpThrottle):
    """답하기.

    답하기도 센다. 되돌리기 방어 때문에 매 요청이 RoundStep 표에 쓰고,
    요청마다 다음 문제를 만드느라 단어·문장 표를 읽는다(무작위 고르기,
    vocab/sampling.py).

    한도가 다른 둘보다 훨씬 큰 이유: 한 판에 수십 번 오가는 것이 정상이다.
    90초에 30~40문제면 한 사람이 분당 27회쯤 부른다.

    로그인하지 않은 사람의 배수를 5 로 낮춰 잡았다. 여기가 IP 하나에서
    동시에 몇 명이 판을 할 수 있는지 정하는 자리다.

    그냥 두면(20배) IP 통 한도가 12,000 이 되는데, DRF 는 요청 시각을
    리스트 하나로 캐시 한 행에 넣고 그 길이 상한이 곧 한도다. 한 IP 에서
    몰아 보내면 매 요청이 타임스탬프 만 개짜리 값을 읽고 쓰게 되어 방어
    장치가 병목이 된다. 반대로 1 배로 끄면 600 / 27 = 22명이라, 와이파이를
    같이 쓰는 23번째 사람부터 429 를 본다.

    5 배(3,000)면 IP 하나에 동시 약 111명까지 받고 리스트도 3천 줄이다.
    보통은 IP 하나에 한두 명이라 행이 작다. IP 하나에 더 많이 몰리는
    곳이 생기면 배수를 올리는 대신 개수만 세는 방식으로 바꾼다. DRF
    기본형은 한도를 키우는 만큼 행이 커진다.
    """

    scope = "round_answer"
    guest_multiplier = 5


class LeaderboardThrottle(PerUserOrIpThrottle):
    """순위표 조회.

    쓰기가 없어 막을 것이 데이터가 아니라 비용이다. 세 순위표 모두
    전 사용자를 훑어 정렬하는 집계라 한 번이 가볍지 않다.

    통을 순위표별로 나눈다(아래 get_cache_key). 화면 하나가 셋을
    한꺼번에 부르므로, 통이 공용이면 새로고침 한 번에 3회가 닳아 분당
    60이 실제로는 20번이 된다. 나누면 각자 자기 몫을 쓴다.

    한도를 넉넉히 두는 이유: 순위표는 자꾸 보게 만드는 것이 목적이다.
    나눈 만큼 한 사람이 쓸 수 있는 총량은 분당 180이 되지만, 셋이 서로
    다른 집계라 한 통을 다 써도 나머지 둘은 멀쩡한 편이 낫다.
    """

    scope = "leaderboard"

    def get_cache_key(self, request, view) -> str | None:
        # 뷰마다 다른 통. board_kind 가 weekly / all_time / streak 다.
        #
        # getattr 로 기본값을 주지 않는다. 뷰가 board_kind 를 빠뜨리면
        # 거기서 터지는 것이 설계인데(views.py 참고), 여기서 빈 문자열로
        # 삼키면 그런 뷰들이 통 하나를 같이 쓰게 된다.
        # super() 보다 먼저 읽는다. 아래 None 길에서도 board_kind 를 빠뜨린 뷰가 터지게.
        kind = view.board_kind
        key = super().get_cache_key(request, view)
        # None(IP 를 못 실은 요청, 세지 않음)을 글자로 붙이면 "None:weekly" 한 통이 된다.
        if key is None:
            return None
        return f"{key}:{kind}"


class DailyStudyThrottle(PerUserOrIpThrottle):
    """일일공부 - 오늘 상태 보기와 시작.

    로그인해야 쓸 수 있어 IP 통이 안 돈다. 그래도 PerUserOrIpThrottle 을
    쓰는 이유는 계정별로 나누기 위해서다. 한 통이면 한 사람이 다 써서
    나머지가 막힌다.

    하루 한 번이라 시작은 하루 한 번만 성공한다. 낮아도 되는 자리다.
    """

    scope = "daily_study"


class DailyStudyAnswerThrottle(PerUserOrIpThrottle):
    """일일공부 답하기.

    시작과 통을 나눈다. 한 통이면 40문제짜리를 빠르게 푸는 사람이
    조회·시작 요청까지 같은 통에서 써서 판 중간에 429 로 갇힌다. 하루
    한 번이라 다시 시작할 수도 없다.

    "하루 40문제니 분당 30이면 넉넉하다" 는 틀린 계산이다. 한도는 하루
    총량이 아니라 슬라이딩 1분 창이다. 문제당 2.4초면 1분에 25문제가
    나가는데, 그건 4지선다에서 충분히 나오는 속도다.
    """

    scope = "daily_study_answer"


class ReviewThrottle(PerUserOrIpThrottle):
    """복습 - 시작과 남은 개수 보기."""

    scope = "review"


class ReviewAnswerThrottle(PerUserOrIpThrottle):
    """복습 답하기.

    시작과 통을 나눈다. 한 통이면 20문제를 빠르게 푸는 사람이 판 중간에
    막힌다(DailyStudyAnswerThrottle 과 같은 이유).
    """

    scope = "review_answer"
