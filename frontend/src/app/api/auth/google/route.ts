import { randomBytes } from "node:crypto";

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { authUrl } from "@/lib/google";
import { safeNext } from "@/lib/routes";

/**
 * 구글 로그인 시작.
 *
 * "구글로 계속하기" 를 누르면 여기로 오고, 여기서 구글 동의 화면으로
 * 보낸다. 구글이 끝나면 /api/auth/google/callback 으로 돌아온다.
 */

/** 돌아왔을 때 대조할 값. 쿠키 이름. */
export const STATE_COOKIE = "devvoca_oauth_state";

/** 로그인 후 돌아갈 곳을 잠깐 기억해두는 쿠키. */
export const NEXT_COOKIE = "devvoca_oauth_next";

// 10분. 동의 화면에서 그보다 오래 머무르면 처음부터 다시 한다.
const MAX_AGE = 60 * 10;

export async function GET(request: Request) {
  const clientId = process.env.GOOGLE_CLIENT_ID;
  if (!clientId) {
    // 설정이 빠진 채 배포된 경우. 사용자에게는 이유를 감추고 로그인
    // 화면으로 돌려보낸다.
    console.error("GOOGLE_CLIENT_ID 가 설정되지 않았습니다.");
    return NextResponse.redirect(new URL("/login?error=google", request.url));
  }

  const url = new URL(request.url);

  // 남이 만든 로그인 링크를 눌렀을 때 그 사람 계정으로 로그인되는 것을
  // 막는 값이다. 여기서 만들어 쿠키에 넣고, 돌아왔을 때 대조한다.
  const state = randomBytes(16).toString("hex");

  const store = await cookies();
  const options = {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: MAX_AGE,
  };

  store.set(STATE_COOKIE, state, options);
  store.set(NEXT_COOKIE, safeNext(url.searchParams.get("next")), options);

  return NextResponse.redirect(
    authUrl({ clientId, origin: url.origin, state }),
  );
}
