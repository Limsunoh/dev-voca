/**
 * 로그인 쿠키(devvoca_token)의 이름·설정·값 꼴. lib/session.ts 와 proxy.ts 가 같이 쓴다.
 *
 * 값은 "토큰.발급시각(초)" 이다. 발급 시각을 같이 적는 것은 proxy 가 하루 지난 쿠키만
 * 백엔드에 로그인 이어 가기를 물으려는 것이다. 시각이 없으면 화면을 열 때마다 물어야 한다.
 *
 * 쿠키를 하나 더 두지 않은 이유: 처리방침 10절이 쿠키를 이름으로 적고 있어 이름을 늘리면
 * 개정(시행 7일 전 공지)이다. 발급 시각은 2절의 "로그인 토큰과 발급 시각" 에 이미 있다.
 *
 * 이 꼴 전에 넣은 쿠키는 토큰만 있다. 시각이 없는 것으로 보고 바로 이어 가기를 부른다.
 * 사용자가 시각을 고쳐도 언제 묻는지만 바뀐다. 토큰이 언제 끝나는지는 백엔드가 정한다.
 */

export const TOKEN_COOKIE = "devvoca_token";

// 30일. 학습 앱이라 자주 로그인시킬 이유가 없다. 백엔드 토큰도 발급 30일에 끝난다
// (accounts.LoginToken 의 LIFETIME). 쓰는 동안은 proxy 가 하루마다 새 토큰으로 바꿔
// 이 쿠키를 다시 붙이므로, 30일은 "30일 동안 안 쓰면" 이다. 처리방침 3절·10절의 30일과
// 같이 고친다.
export const TOKEN_MAX_AGE = 60 * 60 * 24 * 30;

// 이보다 오래된 쿠키면 이어 가기를 부른다. 백엔드 LoginToken.RENEW_AFTER 와 같다.
export const RENEW_AFTER_SECONDS = 60 * 60 * 24;

export function tokenCookieOptions() {
  return {
    httpOnly: true,
    // 운영은 https 다. 개발에서 켜면 http://localhost 에 쿠키가 안 붙는다.
    secure: process.env.NODE_ENV === "production",
    // lax 면 다른 사이트에서 넘어온 요청에는 쿠키가 안 실린다.
    // 로그인 상태로 남의 사이트 링크를 눌러도 그쪽 요청이 내 권한을
    // 빌려 쓰지 못한다.
    sameSite: "lax" as const,
    path: "/",
    maxAge: TOKEN_MAX_AGE,
  };
}

/**
 * 로그인 쿠키를 Set-Cookie 머리 한 줄로. 설정은 tokenCookieOptions 와 같다.
 *
 * proxy 가 새 토큰을 넣을 때 쓴다. NextResponse.cookies.set 은 같은 요청의 화면에도 값을
 * 넘겨서(proxy.ts 주석) 머리를 직접 쓴다. value 는 formatTokenCookie 의 결과(16진수·점·숫자)라
 * 따로 인코딩하지 않는다.
 */
export function serializeTokenCookie(value: string): string {
  const options = tokenCookieOptions();
  const sameSite = options.sameSite[0].toUpperCase() + options.sameSite.slice(1);
  return [
    `${TOKEN_COOKIE}=${value}`,
    `Path=${options.path}`,
    `Max-Age=${options.maxAge}`,
    ...(options.httpOnly ? ["HttpOnly"] : []),
    `SameSite=${sameSite}`,
    ...(options.secure ? ["Secure"] : []),
  ].join("; ");
}

export function formatTokenCookie(token: string, issuedAt: number): string {
  return `${token}.${Math.floor(issuedAt)}`;
}

export function parseTokenCookie(
  value: string | null | undefined,
): { token: string; issuedAt: number | null } | null {
  if (!value) return null;
  const dot = value.lastIndexOf(".");
  if (dot === -1) return { token: value, issuedAt: null };
  const token = value.slice(0, dot);
  if (!token) return null;
  // 숫자가 아니면 시각이 없는 것으로 본다. 토큰은 16진수라 점이 들지 않는다.
  const issuedAt = /^\d+$/.test(value.slice(dot + 1)) ? Number(value.slice(dot + 1)) : null;
  return { token, issuedAt };
}

/** 이어 가기를 부를 때가 됐나. 시각이 없거나 앞날이면(고친 쿠키) 부른다. */
export function isRenewalDue(issuedAt: number | null, nowSeconds: number): boolean {
  if (issuedAt === null || issuedAt > nowSeconds) return true;
  return nowSeconds - issuedAt >= RENEW_AFTER_SECONDS;
}
