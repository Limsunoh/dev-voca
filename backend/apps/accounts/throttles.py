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
