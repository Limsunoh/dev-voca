/**
 * 화면 응답의 CSP(Content-Security-Policy). proxy.ts 가 요청마다 새 nonce 로 만든다.
 *
 * 스크립트는 이번 응답의 nonce 가 붙은 것과, 그 스크립트가 붙인 것('strict-dynamic')만
 * 돈다. Next 는 요청 머리의 CSP 에서 nonce 를 읽어 자기 스크립트에 붙인다(Next 문서
 * content-security-policy). 그래서 화면에 끼어든 <script> 나 onerror= 같은 것은 돌지
 * 않는다. 구글 로그인 스크립트는 next/script 가 실행 중에 붙여 strict-dynamic 으로 통과한다.
 * 뒤의 주소는 strict-dynamic 을 모르는 옛 브라우저용이다.
 *
 * 스타일은 nonce 로 막지 않는다. 화면 곳곳이 style={{...}} 를 써서 서버가 그린 HTML 에
 * style 속성이 들어가는데, 이것은 nonce 로 허락할 수 없다. style-src 에 nonce 를 넣으면
 * 'unsafe-inline' 이 무시돼 그 속성이 전부 막히므로 넣지 않는다.
 *
 * 구글 로그인(GIS)이 쓰는 주소는 구글 문서의 CSP 안내대로 /gsi/ 아래만 연다. 버튼은 그
 * 아래 iframe 이다. 계정 창(FedCM)은 브라우저가 띄우지만, 그 창이 받아 오는 설정
 * 파일(/gsi/fedcm.json)은 우리 쪽 connect-src 로 검사받는다. connect-src 의 /gsi/ 를
 * 지우면 계정 창이 안 뜬다.
 *
 * Sentry 는 폰 화면 오류를 DSN 의 주소로 보낸다. DSN 이 없는 로컬·미리보기에서는 뺀다.
 * 위반 보고(report-uri)는 Sentry 로 보내지 않는다. 브라우저가 만드는 보고에는 화면 주소가
 * 그대로 실리고(/profile/email/<토큰> 처럼 토큰이 든 주소), 우리가 오류에서 지우는 것을
 * 거치지 않는다(lib/sentry.ts).
 *
 * upgrade-insecure-requests 는 두지 않는다. 화면은 https 로만 나가고(Vercel, HSTS) 우리
 * 쪽 자원은 전부 같은 주소라 바꿀 것이 없다. 두면 http 로 띄우는 로컬 빌드만 깨진다.
 */

/** 요청마다 새로 만드는 nonce. 맞히면 스크립트를 넣을 수 있으니 예측할 수 없어야 한다. */
export function newNonce(): string {
  return btoa(crypto.randomUUID());
}

/**
 * DSN("https://키@o1.ingest.sentry.io/2")에서 보내는 곳의 주소만. 없거나 틀리면 null.
 *
 * 주소 꼴(https, 영문자·숫자·점·하이픈, 포트)만 받는다. URL 은 호스트에 ";" 를 허락해서,
 * DSN 을 잘못 넣으면 "https://a.com;sandbox" 처럼 정책에 다른 지시어가 끼어든다.
 */
export function sentryOrigin(dsn: string | undefined): string | null {
  if (!dsn) return null;
  try {
    const { origin } = new URL(dsn);
    return /^https:\/\/[a-z0-9.-]+(:\d+)?$/.test(origin) ? origin : null;
  } catch {
    return null;
  }
}

const GIS = "https://accounts.google.com/gsi/";

export function buildCsp(
  nonce: string,
  { dev = false, sentryDsn }: { dev?: boolean; sentryDsn?: string } = {},
): string {
  const sentry = sentryOrigin(sentryDsn);
  const directives = [
    "default-src 'self'",
    // 개발 서버만: React 가 서버 오류 스택을 브라우저에서 다시 세우려고 eval 을 쓴다.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' ${GIS}client${dev ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' 'unsafe-inline' ${GIS}style`,
    // 구글 프로필 사진은 구글이 준 주소(lh3.googleusercontent.com 등)를 그대로 그린다
    // (순위표, 내 정보). 올린 사진은 우리 주소(/api/accounts/photo/)로 중계한다.
    // data: 는 구글 로그인 스크립트가 버튼의 로고 그라데이션을 그릴 때 쓴다. 없으면 가끔
    // "Failed to load Google logo gradient. Add data: to ... img-src" 를 남긴다.
    // 글꼴은 default-src 를 따른다. 빌드 때 받아 우리 주소로 내보낸다(next/font).
    "img-src 'self' data: https://*.googleusercontent.com",
    `connect-src 'self' ${GIS}${sentry ? ` ${sentry}` : ""}`,
    `frame-src ${GIS}`,
    // strict-dynamic 이면 script-src 의 'self' 가 무시돼, 따로 적지 않으면 sw.js 등록이 막힌다.
    "worker-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];
  return directives.join("; ");
}
