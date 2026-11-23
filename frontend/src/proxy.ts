import { type NextRequest, NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { renewToken } from "@/lib/api/accounts";
import { buildCsp, newNonce } from "@/lib/csp";
import {
  formatTokenCookie,
  isRenewalDue,
  parseTokenCookie,
  serializeTokenCookie,
  TOKEN_COOKIE,
} from "@/lib/token-cookie";

/**
 * 화면 응답마다 CSP 를 싣는다. 정책과 이유는 lib/csp.ts.
 *
 * 요청 머리에도 같은 값을 넣는다. Next 가 그것을 읽어 이번 화면의 스크립트에 nonce 를
 * 붙인다. 그래서 화면은 요청 때 그려야 한다(app/layout.tsx 의 connection()).
 *
 * 로그인도 여기서 이어 간다(renewLogin). 화면을 여는 요청은 모두 여기를 지나고,
 * 화면을 그리는 도중에는 쿠키를 쓸 수 없어서(lib/session.ts 의 forgetToken 주석) 이곳이
 * 새 토큰을 쿠키에 넣을 수 있는 자리다.
 */
export async function proxy(request: NextRequest): Promise<NextResponse> {
  const csp = buildCsp(newNonce(), {
    dev: process.env.NODE_ENV === "development",
    sentryDsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  });
  const login = await renewLogin(request);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("Content-Security-Policy", csp);

  // 이번 화면은 옛 토큰으로 그린다. 새 토큰은 브라우저가 쿠키로 받아 다음 요청에 처음
  // 실어 와야 쓰기 시작한 것으로 친다(백엔드 LoginToken.mark_delivered). 이번 화면에
  // 넘기면 응답이 브라우저에 닿기 전에 새 토큰이 쓰인 것이 되어, 응답을 잃은 사람의
  // 옛 토큰이 한 시간 뒤 새어 나간 토큰으로 취급되고 그 로그인이 끊긴다.
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  // 지울 때는 이번 화면도 로그아웃 상태로 그린다. response.cookies 로 지우면 Next 가 같은
  // 요청의 cookies() 에도 반영한다(x-middleware-set-cookie).
  if (login === null) response.cookies.delete(TOKEN_COOKIE);
  // 새 쿠키는 Set-Cookie 머리에 직접 붙인다. response.cookies.set 을 쓰면 위와 같은 길로
  // 이번 화면에도 넘어가, 응답이 브라우저에 닿기 전에 새 토큰이 쓰인 것이 된다.
  // 이 아래에서 response.cookies 를 쓰지 않는다. 그것은 Set-Cookie 머리를 자기가 든 것으로
  // 통째로 다시 써서, 여기서 붙인 줄이 사라진다.
  else if (login !== undefined) response.headers.append("Set-Cookie", serializeTokenCookie(login));
  return response;
}

/**
 * 하루 지난 로그인 쿠키면 백엔드에서 새 토큰을 받아 온다.
 *
 * 돌려주는 값: 새 쿠키 값(바꾼다), null(토큰이 죽었으니 쿠키를 지운다), undefined(그대로).
 *
 * GET 만 본다. 서버 액션(POST)은 로그인·로그아웃·비밀번호 변경처럼 스스로 쿠키를 쓰는
 * 것이 있어, 여기서 같은 쿠키를 또 쓰면 어느 쪽이 남을지 정해지지 않는다.
 *
 * 백엔드가 늦거나 죽었으면 그대로 둔다. 토큰은 아직 살아 있고 다음 이동 때 다시 묻는다.
 * 401 이면 지운다. 남겨 두면 이동할 때마다 다시 묻느라 백엔드를 한 번씩 더 부른다.
 */
async function renewLogin(request: NextRequest): Promise<string | null | undefined> {
  if (request.method !== "GET") return undefined;
  const cookie = parseTokenCookie(request.cookies.get(TOKEN_COOKIE)?.value);
  if (!cookie || !isRenewalDue(cookie.issuedAt, Date.now() / 1000)) return undefined;

  try {
    const renewed = await renewToken(cookie.token);
    return formatTokenCookie(renewed.token, renewed.issued_at);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    console.error("로그인을 이어 가지 못했습니다.", error);
    return undefined;
  }
}

export const config = {
  matcher: [
    {
      // 빌드 파일과 실제 있는 정적 파일은 이름까지 적어 뺀다. 앞머리만 적으면 그 아래 없는
      // 주소(/icons/nope)의 404 화면이 CSP 없이 나간다. "점이 든 주소" 로 통째로 빼도 안
      // 된다. /learn/words/1.5 처럼 점 하나만 붙여 CSP 없는 화면을 받을 수 있다. sw.js 에
      // 정책이 붙으면 service worker 자신에게도 걸리고, offline.html 은 인라인 onclick 을 쓴다.
      // public/ 이나 app/ 의 아이콘·manifest 를 더하면 여기도 더한다.
      //
      // api 중계는 앞머리로 뺀다. 문제풀기 답하기처럼 자주 부르는 요청마다 proxy 를 한 번
      // 더 거치지 않게 하려는 것이다. 그래서 /api/없는주소 의 404 화면은 CSP 없이 나간다.
      // 그 화면은 입력을 되비추지 않는다. 로그인 이어 가기도 화면을 열 때만 한다.
      source:
        "/((?!api/|_next/static/|_next/image$|icons/(?:icon-192|icon-512|maskable-512)\\.png$|\\.well-known/assetlinks\\.json$|sw\\.js$|offline\\.html$|manifest\\.webmanifest$|icon\\.png$|apple-icon\\.png$).*)",
      // Next 의 링크 미리 받기는 RSC 데이터라 nonce 가 필요 없다(Next 문서의 설정).
      missing: [{ type: "header", key: "next-router-prefetch" }],
    },
  ],
};
