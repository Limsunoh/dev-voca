"""vocab 화면의 요청 제한. 로그인했으면 계정별, 아니면 접속 IP 별.

소리내어 읽기(출제·채점)와 낱개 연습 채점이 쓴다. 세는 규칙은
accounts.throttles.PerUserOrIpThrottle 에 있고 learning 의 판·순위표와 같다.
"""

from __future__ import annotations

from apps.accounts.throttles import PerUserOrIpThrottle


class TalkQuestionThrottle(PerUserOrIpThrottle):
    """소리내어 읽기: 읽을 것을 받아오는 쪽. 조회만 하므로 넉넉하다."""

    scope = "talk_question"


class TalkGradeThrottle(PerUserOrIpThrottle):
    """소리내어 읽기: 채점하는 쪽.

    출제보다 넉넉해야 한다. 발음 연습은 한 항목을 받아 세 번쯤 읽어 보는
    것이 정상이라 채점이 출제보다 잦다. 같은 값으로 두면 정상 사용자가 막힌다.

    그래도 통을 두는 이유는 요청마다 후보 다섯 개를 문자열 비교하기 때문이다.

    수용 인원: 채점 180/min x 20 = 3600/min 이고 한 항목을 두세 번 읽어
    보는 것이 정상이라, IP 하나에서 로그인하지 않은 사람이 동시에 약 250명이면
    상한에 닿는다.
    """

    scope = "talk_grade"


class PracticeGradeThrottle(PerUserOrIpThrottle):
    """낱개 연습(단어·문장)의 채점.

    로그인 없이 부를 수 있고, 로그인했으면 틀릴 때마다 오답 노트 표에 쓴다. 제한이
    없을 때는 한 계정으로 그 표에 끝없이 쓸 수 있었다.
    """

    scope = "practice_grade"
