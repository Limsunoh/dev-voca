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

export async function clearToken(): Promise<void> {
  const store = await cookies();
  store.delete(COOKIE_NAME);
  // 게스트 선택도 함께 지운다. 로그아웃했는데 첫 화면을 건너뛰면
  // 나가는 문만 있고 들어오는 문이 없는 상태가 된다.
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
    // 죽은 토큰은 다시 로그인할 때 덮어써진다. 그때까지는 남아 있지만,
    // 화면은 로그아웃 상태로 그려지고 그 토큰이 다른 요청을 막지도 않는다.

    // 401 이 아니면 토큰 문제가 아니다. 백엔드가 잠깐 죽었을 뿐인데
    // 로그아웃 상태로 그리면 멀쩡한 로그인이 날아간 것처럼 보인다.
    if (!(error instanceof ApiError) || error.status !== 401) {
      console.error("로그인 상태를 확인하지 못했습니다.", error);
    }
    return null;
  }
});
