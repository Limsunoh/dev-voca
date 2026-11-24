/**
 * 게스트 쿠키 이름. lib/session.ts 와 proxy.ts 가 같이 쓴다(로그인 쿠키는 token-cookie.ts).
 *
 * session.ts 에 두지 않는 이유: 그 파일은 "server-only" 라 proxy 가 가져오면 빌드가 깨진다.
 * 이름을 바꾸면 처리방침 10절(쿠키를 이름으로 적는다)도 같이 고친다.
 */

/** "게스트로 둘러보기" 를 고른 적이 있다. 값은 "1". */
export const GUEST_COOKIE = "devvoca_guest";

/** 게스트가 고른 하루 공부량. 로그인하면 계정으로 옮기고 지운다. */
export const GUEST_LENGTH_COOKIE = "devvoca_daily_length";
