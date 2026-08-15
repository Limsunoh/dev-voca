"""판 요청 제한.

막으려는 것은 "판을 열고 닫기를 반복해 행만 쌓는 것" 이다. 점수는 하루에
가장 잘한 한 판만 세므로 아무리 많이 보내도 순위는 안 오른다. 남는 위험은
저장 공간과 쓰기 부하다.

IP 로 나눌 수 없다. accounts 쪽과 같은 사정이다 - 브라우저가 백엔드를
직접 부르지 않고 Next 서버가 대신 부르기 때문에, 백엔드가 보는 주소는
항상 하나다.

그래서 **로그인한 사람은 계정별로, 게스트는 다 함께** 센다.

계정별로 나누는 것이 중요한 이유: 통이 하나뿐이면 한 사람이 한도를 다 쓰는
동안 나머지 전원이 막힌다. 남을 막을 수 있는 스위치를 아무에게나 쥐여주는
셈이다. 계정으로 나누면 한도를 다 쓴 사람만 기다린다.

**게스트 통이 바로 그 스위치로 남아 있다.** 익명 스크립트가 게스트 한도를
태우면 로그인하지 않은 방문자 전원이 판을 시작할 수 없고, 공격자는 계정도
필요 없다. 게스트가 곧 신규 유입이라 피해 대상이 제일 나쁜 쪽이다.
없애지 못하는 이유는 위와 같다 - 게스트는 나눌 키가 없다.

대신 게스트 통을 계정 통보다 크게 잡는다(_GUEST_MULTIPLIER). 제대로
나누려면 Next 중계가 브라우저를 구분해 그쪽에서 제한해야 한다.

**게스트는 동시 약 110명이 상한이다.** 답하기가 판에서 요청이 가장 많이
오가는 곳이라 그 통이 수용 인원을 정한다(계산은 RoundAnswerThrottle 참고).
로그인한 사람은 계정별이라 이 상한과 무관하다. "로그인 안 하면 429 가
난다" 는 신고가 들어오면 여기가 원인이다.
"""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle

# 게스트 통은 이 배수만큼 넉넉하게. 한 명이 전원을 막는 데 필요한 양을
# 올려두는 것이지 없애는 것은 아니다.
_GUEST_MULTIPLIER = 20


class _PerUserOrShared(SimpleRateThrottle):
    """로그인했으면 계정별, 아니면 게스트끼리 한 통."""

    # 게스트 통을 이만큼 키운다. 통이 큰 곳에서는 1 로 되돌린다 -
    # 아래 RoundAnswerThrottle 참고.
    guest_multiplier = _GUEST_MULTIPLIER

    def get_cache_key(self, request, view) -> str:
        user = getattr(request, "user", None)
        ident = f"u{user.pk}" if user is not None and user.is_authenticated else "guest"
        return self.cache_format % {"scope": self.scope, "ident": ident}

    def allow_request(self, request, view) -> bool:
        # DRF 는 요청마다 새 인스턴스를 만든다. 여기서 값을 바꿔도
        # 다음 요청에 새지 않는다.
        user = getattr(request, "user", None)
        if self.num_requests and (user is None or not user.is_authenticated):
            self.num_requests *= self.guest_multiplier
        return super().allow_request(request, view)


class RoundStartThrottle(_PerUserOrShared):
    scope = "round_start"


class RoundFinishThrottle(_PerUserOrShared):
    scope = "round_finish"


class RoundAnswerThrottle(_PerUserOrShared):
    """답하기.

    예전에는 세지 않았다. 근거는 "답하기는 DB 에 쓰지 않는다" 였는데
    되돌리기 방어를 넣으면서 **매 요청이 RoundStep 표에 쓴다**. 게다가
    요청마다 다음 문제를 만드느라 order_by("?") 로 단어·문장을 통째로
    훑는다. 근거가 사라졌으니 통을 붙인다.

    한도가 다른 둘보다 훨씬 큰 이유: 한 판에 수십 번 오가는 것이 정상이다.
    90초에 30~40문제면 한 사람이 분당 27회쯤 부른다.

    **게스트 배수를 5 로 낮춰 잡았다. 여기가 게스트 동시 사용자 수를
    결정하는 자리다.**

    그냥 두면(20배) 게스트 통 한도가 12,000 이 되는데, DRF 는 요청 시각을
    **리스트 통째로** 캐시 한 행에 넣고 그 길이 상한이 곧 한도다. 게스트의
    답하기 매 요청이 타임스탬프 만 개짜리 값을 읽고 쓰게 되어 방어 장치가
    병목이 된다. 반대로 1 배로 끄면 600 / 27 = **동시 게스트 22명이 벽**이라,
    23번째 방문자부터 429 를 본다.

    5 배(3,000)면 동시 게스트 약 111명까지 받고 리스트도 3천 줄이다.
    지금 단계에서는 이걸로 충분하다. 더 필요해지면 배수를 올리는 대신
    **개수만 세는 방식**으로 바꿔야 한다 - DRF 기본형은 한도를 키우는 만큼
    행이 커져서, 올리는 순간 병목이 그대로 돌아온다.
    """

    scope = "round_answer"
    guest_multiplier = 5
