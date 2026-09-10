"""소리내어 읽기 요청 제한.

IP 로 세지 않는 이유는 accounts·learning 쪽과 같다 - Next 서버가 백엔드를
대신 부르기 때문에 백엔드가 보는 주소는 항상 하나다.
"""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle


class _TalkThrottle(SimpleRateThrottle):
    """소리내어 읽기 요청 제한. 로그인했으면 계정별, 아니면 게스트끼리 한 통.

    IP 로 셀 수 없다. accounts·learning 과 같은 사정이다 - 브라우저가
    백엔드를 직접 부르지 않고 Next 서버가 대신 부르기 때문에 백엔드가
    보는 주소는 항상 하나다. IP 로 세면 접속자 전원이 한 통에 담긴다.

    **계정별로 나누는 것이 중요하다.** 통이 하나뿐이면 한 사람이 한도를
    다 쓰는 동안 나머지 전원이 막힌다 - 남을 막는 스위치를 아무에게나
    쥐여주는 셈이다.

    **게스트 통은 그 스위치로 남아 있다.** 이 화면은 로그인 없이 쓸 수
    있어서(점수가 안 남으므로 막을 이유가 없다) 게스트를 나눌 키가 없다.
    learning 쪽과 같은 한계이고, 같은 방식으로 게스트 통을 크게 잡는다.
    제대로 나누려면 실제 클라이언트를 아는 Next 중계가 제한해야 한다.

    **수용 인원**: 채점 180/min x 20 = 3600/min 이고 한 항목을 두세 번
    읽어보는 것이 정상이라, 게스트가 동시에 약 250명이면 상한에 닿는다.
    "429 가 뜬다" 는 신고가 오면 여기가 원인이다.

    **learning.throttles._PerUserOrShared 와 같은 구현이다.** 앱 간 의존을
    만들지 않으려고 복제했다. 게스트를 식별하는 방식을 바꾸는 날에는 두
    곳을 함께 고쳐야 한다 - 공통으로 뺄 자리는 core 앱이 생길 때다.
    """

    # 게스트 통을 이만큼 키운다. learning.throttles 의 값과 같게 둔다 -
    # 두 곳이 다르면 어느 쪽이 먼저 막히는지 예측이 안 된다.
    guest_multiplier = 20

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


class TalkQuestionThrottle(_TalkThrottle):
    """읽을 것을 받아오는 쪽. 조회만 하므로 넉넉하다."""

    scope = "talk_question"


class TalkGradeThrottle(_TalkThrottle):
    """채점하는 쪽.

    출제보다 넉넉해야 한다. **발음 연습은 한 항목을 여러 번 시도하는 것이
    정상 사용이다** - 한 번 받아 세 번 읽어보는 흐름이라 채점이 출제보다
    잦다. 같은 값으로 두면 정상 사용자가 막힌다.

    그래도 통을 두는 이유: 요청마다 후보 다섯 개를 문자열 비교한다.
    """

    scope = "talk_grade"
