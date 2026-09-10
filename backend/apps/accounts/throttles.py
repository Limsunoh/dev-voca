"""로그인·가입 시도 제한.

IP 로 세지 않는다. 이 프로젝트는 브라우저가 백엔드를 직접 부르지 않고
Next 서버가 대신 부르기 때문에, 백엔드가 보는 주소는 항상 하나다. IP 로
세면 접속자 전원이 한 통에 담겨 한 사람 때문에 나머지가 막힌다.

대신 요청에 실린 이메일로 센다. 막으려는 것이 "한 계정의 비밀번호를
반복해서 때리는 것" 과 "이메일 목록을 던져 가입 여부를 훑는 것" 이라,
세어야 할 단위가 애초에 이메일이다.
"""

from __future__ import annotations

import hashlib

from rest_framework.throttling import SimpleRateThrottle


class EmailRateThrottle(SimpleRateThrottle):
    """제출된 이메일 기준으로 시도 횟수를 센다."""

    scope = "auth_email"

    def get_cache_key(self, request, view) -> str | None:
        # 본문이 dict 가 아닐 수 있다. 그때는 어차피 400 이 되므로 세지 않는다.
        if not isinstance(request.data, dict):
            return None

        email = request.data.get("email")
        if not isinstance(email, str) or not email.strip():
            return None

        # 저장할 때와 같은 방식으로 낮춘다. 안 그러면 대소문자만 바꿔가며
        # 같은 계정을 계속 때릴 수 있다.
        #
        # 해시로 줄이는 이유: 이메일을 그대로 쓰면 키가 길어져 캐시 백엔드가
        # 거부한다(memcached 는 250자 제한). 길이가 고정되면 그 걱정이 없고,
        # 캐시에 이메일 원문이 남지도 않는다.
        ident = hashlib.sha256(email.strip().lower().encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": ident}


class GoogleRateThrottle(SimpleRateThrottle):
    """구글 로그인 시도 제한.

    이메일로 셀 수 없다. 구글 요청에는 코드만 들어 있고 이메일은 구글에
    물어봐야 나온다.

    요청자별로도 못 센다. 이 프로젝트는 모든 요청이 Next 서버 하나로
    보이고, 주소를 알려주는 헤더는 아무나 지어낼 수 있어 나누는 척하면
    오히려 헤더 하나로 갈라진다. 인증 여부로 나누는 것도 안 된다 -
    토큰만 붙이면 세지 않는 구현이 있어, 계정 하나 만들면 그대로 뚫린다.

    그래서 통을 하나만 둔다. 여기서 재는 것은 "누가 얼마나" 가 아니라
    "우리 서버가 구글을 얼마나 두드리는가" 다. 그 총량에 상한을 두면
    남이 우리를 통해 구글을 때리는 것도 함께 막힌다.

    대가로 한 사람이 한도를 다 쓰면 그동안 모두가 막힌다. 그래서 실제
    사용량보다 훨씬 넉넉하게 잡는다.
    """

    scope = "auth_google"

    def get_cache_key(self, request, view) -> str:
        return self.cache_format % {"scope": self.scope, "ident": "all"}


class EmailChangeThrottle(SimpleRateThrottle):
    """이메일 변경 신청 제한. 확인 메일이 나가는 자리다.

    막으려는 것은 남의 주소로 반복해서 신청을 걸어 우리 이름으로 메일
    폭탄을 만드는 것이다. 로그인이 필요하다는 것만으로는 못 막는다 -
    계정 하나면 무제한이 된다.

    계정으로 센다. 이 요청은 IsAuthenticated 라 익명이 도달하지 않는다.

    익명이면 세지 않고 통과시킨다(None). 통 하나에 담으면 안 된다 -
    401 로 끝날 요청들이 한 통을 채워, 아무나 그 통을 태우는 것만으로
    모두의 이메일 변경을 막을 수 있다. 어차피 인증에서 막힌다.
    """

    scope = "email_change"

    def get_cache_key(self, request, view) -> str | None:
        if not (request.user and request.user.is_authenticated):
            return None
        return self.cache_format % {"scope": self.scope, "ident": f"u{request.user.pk}"}


class EmailChangeConfirmThrottle(SimpleRateThrottle):
    """확인 링크를 쓰는 쪽의 제한. 서명을 무작위로 찔러보는 것을 막는다.

    **신청 쪽과 통을 나눈다.** 여기는 로그인이 없어서(메일을 다른 기기에서
    열 수 있어야 한다) 계정으로 셀 수 없고, 통 하나로 합쳐 센다.

    요청자별로 못 나눈다. 이 프로젝트는 브라우저가 백엔드를 직접 부르지
    않고 Next 서버가 대신 불러서, 백엔드가 보는 주소는 늘 하나다. 나누는
    척하면 접속자 전원이 한 통에 담기면서 나눴다는 착각만 남는다.

    **그래서 요율을 넉넉히 잡는다.** 한 통을 모두가 나눠 쓰므로 좁게 잡으면
    아무나 그 통을 태워 전원의 이메일 변경을 막는 스위치가 된다
    (apps/learning/throttles.py 가 같은 위험을 배수로 완화한다). 확인
    링크를 누르는 일은 계정당 몇 번 없어서, 넉넉해도 무차별 시도를 막는
    목적은 그대로 선다 - 서명을 맞히려면 그 정도로는 어림없다.
    """

    scope = "email_change_confirm"

    def get_cache_key(self, request, view) -> str:
        return self.cache_format % {"scope": self.scope, "ident": "all"}


class PasswordChangeThrottle(SimpleRateThrottle):
    """비밀번호 변경 시도 제한.

    막으려는 것은 **현재 비밀번호를 반복해서 찔러보는 것**이다. 이 통로는
    로그인과 성질이 같다 - 맞는지 틀리는지를 응답으로 알려주므로, 제한이
    없으면 로그인 화면 대신 여기로 추측을 던질 수 있다. 로그인에만 제한을
    걸고 여기를 비워두면 그쪽 제한이 무의미해진다.

    **계정으로 센다.** 이메일로 셀 수 없다 - 이 요청 본문에는 이메일이
    없고 토큰으로 들어온다. IP 로도 못 센다(위 EmailRateThrottle 참고).
    계정별로 나누면 한도를 다 쓴 사람만 기다린다. 통을 하나만 두면
    아무나 한도를 태워 전원의 비밀번호 변경을 막을 수 있다.

    인증이 없으면 세지 않는다. 이 뷰는 IsAuthenticated 라 그 경우 401 로
    끝나고, None 을 주면 DRF 가 제한을 건너뛴다. 인증 안 된 요청을 한
    통에 담으면 그것이 곧 전원을 막는 스위치가 된다.

    요율은 settings 의 DEFAULT_THROTTLE_RATES 에 둔다. 다른 통들과 한
    자리에 모여 있어야 조정할 때 흩어진 곳을 뒤지지 않는다.
    """

    scope = "password_change"

    def get_cache_key(self, request, view) -> str | None:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": f"u{user.pk}"}


class AvatarPhotoThrottle(SimpleRateThrottle):
    """사진 올리기 제한.

    여기가 이 앱에서 제일 비싼 자리다. 요청 하나가 최대 5MB 를 받아 Pillow
    로 열고 줄인 뒤 다시 인코딩한다. 제한이 없으면 계정 하나로 큰 사진을
    반복해서 던지는 것만으로 CPU 와 메모리를 밀 수 있다.

    IP 로 못 막는다 - 이 프로젝트는 Next 서버가 중계해서 백엔드가 보는
    주소가 늘 하나다(위 EmailRateThrottle 참고). 계정 단위가 유일한
    방어선이다.

    인증이 없으면 세지 않는다. 이 뷰는 IsAuthenticated 라 그 경우 401 로
    끝나고, 그런 요청을 한 통에 담으면 그것이 전원을 막는 스위치가 된다.
    """

    scope = "avatar_photo"

    def get_cache_key(self, request, view) -> str | None:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": f"u{user.pk}"}
