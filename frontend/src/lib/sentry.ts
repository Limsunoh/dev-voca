/**
 * Sentry 설정. 폰 화면(instrumentation-client.ts)과 Next 서버(instrumentation.ts)가 같이 쓴다.
 *
 * NEXT_PUBLIC_SENTRY_DSN 은 Vercel 의 Production 에만 있다. 로컬과 미리보기 배포에서는
 * dsn 이 비어 아무것도 보내지 않는다. 성능 측정과 화면 녹화는 켜지 않는다(무료 한도를
 * 오류에만 쓴다).
 *
 * 보내지 않는 것:
 * - 주소의 토큰·번호. 이메일 변경 확인(/profile/email/<토큰>)처럼 경로에 토큰이 들어가는
 *   화면이 있고, 구글 로그인 콜백은 쿼리에 code 를 싣는다. 경로는 영어 소문자 이름 조각만
 *   남기고 나머지를 ":id" 로 바꾸며, 쿼리와 # 뒤는 버린다. 백엔드 error_mail.mask_path 와
 *   같은 규칙이다.
 * - 헤더는 User-Agent 만 남긴다. Next 서버에서 난 오류에는 로그인 쿠키(devvoca_token)와 사용자
 *   IP 헤더가 실리고, Referer 에는 토큰이 든 주소가 올 수 있다.
 * - 쿠키, 요청 본문, 사용자 정보, 지역 변수 값.
 *
 * 수집을 끄는 것(dataCollection)과 나가기 직전에 지우는 것(scrubEvent)을 둘 다 둔다. SDK 가
 * 판마다 기본값과 옵션 이름을 바꿔 왔고(sendDefaultPii -> dataCollection, 11 판의 기본값은
 * 전부 모으기), 그때 한쪽이 조용히 풀려도 다른 쪽이 막는다.
 */

const KEEP_SEGMENT = /^[a-z][a-z_-]{0,23}$/;

export function maskUrl(raw: string): string {
  let url: URL;
  try {
    url = new URL(raw, "http://relative.invalid");
  } catch {
    return ":url";
  }
  const path = url.pathname
    .split("/")
    .map((part) => (!part || KEEP_SEGMENT.test(part) ? part : ":id"))
    .join("/");
  return url.host === "relative.invalid" ? path : `${url.protocol}//${url.host}${path}`;
}

type RequestData = {
  url?: string;
  headers?: Record<string, string>;
  cookies?: unknown;
  data?: unknown;
  query_string?: unknown;
  env?: unknown;
};

type EventData = {
  request?: RequestData;
  user?: unknown;
  transaction?: string;
  contexts?: Record<string, Record<string, unknown> | undefined>;
};

export function scrubEvent<T extends EventData>(event: T): T {
  // Next 서버 오류는 주소를 request 말고도 두 곳에 더 싣는다: contexts.nextjs.request_path 와
  // 트랜잭션 이름("POST /profile/email/<토큰>").
  const nextjs = event.contexts?.nextjs;
  if (nextjs && typeof nextjs.request_path === "string") {
    nextjs.request_path = maskUrl(nextjs.request_path);
  }
  if (event.transaction) {
    const [method, path] = event.transaction.split(" ", 2);
    if (path?.startsWith("/")) event.transaction = `${method} ${maskUrl(path)}`;
    else if (method.startsWith("/")) event.transaction = maskUrl(method);
  }

  const request = event.request;
  if (request) {
    if (request.url) request.url = maskUrl(request.url);
    if (request.headers) {
      request.headers = Object.fromEntries(
        Object.entries(request.headers).filter(([key]) => key.toLowerCase() === "user-agent"),
      );
    }
    delete request.cookies;
    delete request.data;
    delete request.query_string;
    delete request.env;
  }
  delete event.user;
  return event;
}

// 화면 이동(from, to)과 fetch(url) 기록에 남는 주소도 같이 가린다.
const URL_KEYS = ["url", "from", "to"];

export function scrubBreadcrumb<T extends { data?: Record<string, unknown> }>(crumb: T): T {
  const data = crumb.data;
  if (data) {
    for (const key of URL_KEYS) {
      const value = data[key];
      if (typeof value === "string") data[key] = maskUrl(value);
    }
  }
  return crumb;
}

export const SENTRY_OPTIONS = {
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  dataCollection: {
    userInfo: false,
    cookies: false,
    httpHeaders: { request: { allow: ["user-agent"] }, response: false },
    httpBodies: [],
    urlQueryParams: false,
    stackFrameVariables: false,
  },
  beforeSend: scrubEvent,
  beforeBreadcrumb: scrubBreadcrumb,
};
