import { type NextRequest, NextResponse } from "next/server";

import { buildCsp, newNonce } from "@/lib/csp";

/**
 * 화면 응답마다 CSP 를 싣는다. 정책과 이유는 lib/csp.ts.
 *
 * 요청 머리에도 같은 값을 넣는다. Next 가 그것을 읽어 이번 화면의 스크립트에 nonce 를
 * 붙인다. 그래서 화면은 요청 때 그려야 한다(app/layout.tsx 의 connection()).
 */
export function proxy(request: NextRequest): NextResponse {
  const csp = buildCsp(newNonce(), {
    dev: process.env.NODE_ENV === "development",
    sentryDsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  });

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
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
      // 그 화면은 입력을 되비추지 않는다.
      source:
        "/((?!api/|_next/static/|_next/image$|icons/(?:icon-192|icon-512|maskable-512)\\.png$|\\.well-known/assetlinks\\.json$|sw\\.js$|offline\\.html$|manifest\\.webmanifest$|icon\\.png$|apple-icon\\.png$).*)",
      // Next 의 링크 미리 받기는 RSC 데이터라 nonce 가 필요 없다(Next 문서의 설정).
      missing: [{ type: "header", key: "next-router-prefetch" }],
    },
  ],
};
