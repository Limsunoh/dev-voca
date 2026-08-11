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
