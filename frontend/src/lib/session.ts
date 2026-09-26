import "server-only";

import { cookies } from "next/headers";
import { cache } from "react";

import { getMe, type User } from "./api/accounts";
import { ApiError } from "./api/client";

/**
 * 로그인 상태 보관. **서버에서만 쓴다.**
 *
 * 토큰을 httpOnly 쿠키에만 둔다. 자바스크립트가 읽을 수 없어야 스크립트
 * 하나가 끼어들었을 때 계정이 통째로 넘어가지 않는다.
 *
 * 맨 위의 "server-only" 가 그 방어선이다. 클라이언트 컴포넌트가 이 파일을
 * 가져다 쓰면 그 자리에서 에러가 난다. next 패키지 안에 들어 있는 것이라
 * 의존성이 늘지 않는다.
 */

const COOKIE_NAME = "devvoca_token";
const GUEST_COOKIE = "devvoca_guest";

// 30일. 학습 앱이라 자주 로그인시킬 이유가 없다. 백엔드 토큰 자체는
// 만료가 없고 로그아웃할 때 지워지므로, 이 값은 "이 브라우저에서
// 얼마나 오래 기억할까" 에 가깝다.
const MAX_AGE = 60 * 60 * 24 * 30;

export async function setToken(token: string): Promise<void> {
  const store = await cookies();
  store.set(COOKIE_NAME, token, {
    httpOnly: true,
    // 운영은 https 다. 개발에서 켜면 http://localhost 에 쿠키가 안 붙는다.
    secure: process.env.NODE_ENV === "production",
    // lax 면 다른 사이트에서 넘어온 요청에는 쿠키가 안 실린다.
    // 로그인 상태로 남의 사이트 링크를 눌러도 그쪽 요청이 내 권한을
    // 빌려 쓰지 못한다.
    sameSite: "lax",
    path: "/",
    maxAge: MAX_AGE,
  });
}

/**
 * 토큰 쿠키만 지운다. 서버가 거절한 토큰을 치울 때 쓴다.
 *
 * clearToken 과 달리 게스트 선택은 남긴다. 사용자가 로그아웃한 것이
 * 아니라 쿠키가 낡은 것이라, 첫 화면(/start)을 다시 띄울 이유가 없다.
 *
 * **쿠키를 쓸 수 있는 곳(route handler·서버 액션)에서만 부른다.** 화면을
 * 그리는 중에는 쿠키가 읽기 전용이라 예외가 난다(getCurrentUser 의 catch 주석).
 */
export async function forgetToken(): Promise<void> {
  const store = await cookies();
  store.delete(COOKIE_NAME);
}

export async function clearToken(): Promise<void> {
  await forgetToken();
  // 게스트 선택도 함께 지운다. 로그아웃했는데 첫 화면을 건너뛰면
  // 나가는 문만 있고 들어오는 문이 없는 상태가 된다.
  const store = await cookies();
  store.delete(GUEST_COOKIE);
}

/**
 * "게스트로 둘러보기" 를 고른 적이 있나.
 *
 * 첫 화면(/start)을 다시 띄울지 정하는 데만 쓴다. 로그인과 달리 아무
 * 권한도 주지 않으므로 httpOnly 가 아니어도 되지만, 다른 쿠키와 같은
 * 규칙으로 두는 편이 읽기 쉽다.
 *
 * 로그인과 같은 30일. 앱을 한 달 넘게 안 열었으면 처음 온 사람과
 * 다를 바 없어서 다시 물어보는 것이 자연스럽다.
 */
export async function setGuest(): Promise<void> {
  const store = await cookies();
  store.set(GUEST_COOKIE, "1", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: MAX_AGE,
  });
}

export async function isGuestChosen(): Promise<boolean> {
  const store = await cookies();
  return store.get(GUEST_COOKIE)?.value === "1";
}

export async function getToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(COOKIE_NAME)?.value ?? null;
}

/**
 * **토큰이 없어도 되는 요청**(순위표, 한 판 시작, 일상영어)을 쿠키의 토큰을
 * 실어 부르고, 서버가 그 토큰을 거절하면(401) 토큰 없이 한 번 더 부른다.
 *
 * 그냥 실으면 백엔드는 로그인 없이 쓰는 API 라도 무효 토큰에 401 을 내서,
 * 로그인이 풀린 사람(다른 기기에서 로그아웃, 다른 DB 에서 받은 쿠키)에게
 * 순위표가 "불러오지 못했습니다", 한 판 "시작" 이 "토큰이 유효하지
 * 않습니다" 가 됐다.
 *
 * 정상 경로에는 추가 왕복이 없다. 로그인 확인(/me)을 먼저 하지 않고,
 * 거절된 경우에만 한 번 더 부른다. 처음에는 로그인 확인을 먼저 하게
 * 짰는데, 로그인한 사람이 화면을 열 때마다 - 일상영어는 문장마다 - 왕복이
 * 하나씩 순서대로 늘었다.
 *
 * forget 이 true 면 거절된 쿠키를 지운다 - 쿠키를 쓸 수 있는 곳(route
 * handler·서버 액션)에서만 켠다. 화면을 그리는 중에 켜면 예외가 난다. 지워
 * 두어야 한 판을 게스트로 연 뒤 이어지는 답 요청에 죽은 토큰이 안 실린다.
 *
 * token 은 호출하는 쪽이 getToken() 으로 읽어 넘긴다. 여기서 쿠키를 읽으면
 * 호출부의 try 안에서 읽게 되는데, 그러면 빌드 때 Next 가 쿠키 접근으로
 * 던지는 신호(DynamicServerError)까지 호출부의 catch 에 잡힌다(홈의 "토큰은
 * catch 밖에서 읽는다" 주석과 같은 이유).
 *
 * 돌려주는 token 은 실제로 쓴 토큰이다. 게스트로 불렀으면 null.
 */
export async function withTokenOrGuest<T>(
  token: string | null,
  call: (token?: string) => Promise<T>,
  { forget }: { forget: boolean },
): Promise<{ value: T; token: string | null }> {
  if (!token) return { value: await call(undefined), token: null };

  try {
    return { value: await call(token), token };
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
    if (forget) await forgetToken();
    return { value: await call(undefined), token: null };
  }
}

/**
 * 지금 로그인한 사용자. 로그인 안 했으면 null.
 *
 * 쿠키에 토큰이 있어도 서버에 물어본다. 로그아웃을 다른 기기에서 했거나
 * 계정이 정지됐을 수 있어서, 쿠키만 믿으면 이미 못 쓰는 토큰으로 화면을
 * 로그인 상태로 그리게 된다.
 *
 * cache() 로 감싸는 이유: 한 요청 안에서 여러 번 불린다(머리말 + 페이지).
 * 감싸지 않으면 화면 하나를 그릴 때마다 백엔드에 두 번씩 물어본다.
 */
export const getCurrentUser = cache(async (): Promise<User | null> => {
  const token = await getToken();
  if (!token) return null;

  try {
    return await getMe(token);
  } catch (error) {
    // 여기서 쿠키를 지우면 안 된다. 이 함수는 화면을 그리는 도중에 불리는데,
    // 그 시점의 쿠키는 읽기 전용이라 지우려 하면 예외가 난다. 그 예외는
    // 루트 레이아웃까지 올라가 사이트 전체가 500 이 되고, 로그인 화면조차
    // 같은 레이아웃 아래라 사용자가 스스로 복구할 방법이 없어진다.
    //
    // 죽은 토큰은 쿠키를 쓸 수 있는 곳에서 지운다 - "로그인 없이 둘러보기",
    // 중계 라우트(withTokenOrGuest, relayError). 그때까지는 남아 있으므로,
    // 토큰이 없어도 되는 요청은 거절되면 토큰 없이 다시 부른다. 한때 "남아
    // 있어도 다른 요청을 막지 않는다" 고 여겼는데, 백엔드는 로그인 없이 보는
    // API 에도 무효 토큰이면 401 을 내서 순위표와 한 판을 막았다.

    // 401 이 아니면 토큰 문제가 아니다. 백엔드가 잠깐 죽었을 뿐인데
    // 로그아웃 상태로 그리면 멀쩡한 로그인이 날아간 것처럼 보인다.
    if (!(error instanceof ApiError) || error.status !== 401) {
      console.error("로그인 상태를 확인하지 못했습니다.", error);
    }
    return null;
  }
});
