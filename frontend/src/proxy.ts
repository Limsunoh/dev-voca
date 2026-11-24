import { type NextRequest, NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { renewToken } from "@/lib/api/accounts";
import { buildCsp, newNonce } from "@/lib/csp";
import { isDailyLength } from "@/lib/daily-length";
import { GUEST_COOKIE, GUEST_LENGTH_COOKIE } from "@/lib/guest-cookie";
import { routes } from "@/lib/routes";
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
 *
 * 처음 온 사람을 홈 대신 첫 화면으로 보내는 것도 여기서 한다(firstScreen).
 */
export async function proxy(request: NextRequest): Promise<NextResponse> {
  const csp = buildCsp(newNonce(), {
    dev: process.env.NODE_ENV === "development",
    sentryDsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  });
  const login = await renewLogin(request);

  const first = firstScreen(request, login);
  if (first) {
    const response = NextResponse.redirect(new URL(first, request.url));
    if (login === null) response.cookies.delete(TOKEN_COOKIE);
    return response;
  }

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
 * 홈(/)을 여는데 쿠키만 보고도 다른 화면으로 보낼 사람이면 그 주소. 아니면 null.
 *
 * - 로그인 쿠키도 게스트 쿠키도 없다: 처음 온 사람이라 첫 화면(/start).
 * - 게스트인데 하루 공부량 쿠키가 없다: 공부량을 묻는 화면(/start/daily).
 *
 * 홈(app/page.tsx)도 같은 기준으로 보내지만 거기서는 늦다. 루트 loading.tsx 때문에 홈의
 * 껍데기가 200 으로 먼저 나가고, 브라우저는 그 안의 신호를 읽고서야 다시 넘어간다.
 * 처음 온 사람의 첫 화면이 /start 를 바로 열 때보다 1초쯤 늦게 떴다(운영 측정 LCP
 * 3.65초 대 2.56초). 여기서는 화면을 그리기 전이라 307 로 바로 보낸다.
 *
 * 로그인 쿠키가 있으면 보내지 않는다. 그 사람이 공부량을 골랐는지는 계정에 있어
 * 백엔드에 물어야 알고, 그건 홈이 한다. 방금 401 로 지우기로 한 쿠키(login 이 null)는
 * 없는 것으로 본다.
 *
 * 브라우저가 화면을 통째로 여는 요청(sec-fetch-dest: document)만 보낸다. 앱 안의
 * 이동과 서버 액션은 홈이 보내게 둔다. 서버 액션이 redirect("/") 하면 Next 가 서버
 * 안에서 "/" 를 다시 받아 오는데, 그 요청이 여기 307 을 따라가 /start/daily 화면을
 * 받아도 주소는 "/" 로 남는다. 그러면 "게스트로 둘러보기" 직후 공부량 고르는 화면에
 * 탭바가 뜨고, 로그아웃 직후 첫 화면에도 탭바가 뜬다(TabBar 는 주소로 숨길 화면을
 * 가른다). 그 요청은 empty 로 온다. RSC 머리(rsc)로 가를 수는 없다 - Next 가 proxy 를
 * 부르기 전에 지운다(next/dist/server/web/adapter.js 의 FLIGHT_HEADERS). 이 머리가
 * 없는 옛 브라우저는 홈이 보내던 대로 간다.
 */
function firstScreen(request: NextRequest, login: string | null | undefined): string | null {
  if (request.method !== "GET" || request.nextUrl.pathname !== "/") return null;
  if (request.headers.get("sec-fetch-dest") !== "document") return null;
  const token = parseTokenCookie(request.cookies.get(TOKEN_COOKIE)?.value);
  if (token && login !== null) return null;
  if (request.cookies.get(GUEST_COOKIE)?.value !== "1") return "/start";
  if (!isDailyLength(request.cookies.get(GUEST_LENGTH_COOKIE)?.value)) return routes.startDaily;
  return null;
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
