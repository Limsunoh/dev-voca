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

/**
 * 가입 동의를 구글 왕복 동안 기억해두는 쿠키.
 *
 * 구글을 다녀오면 화면의 체크 상태가 사라진다. 값은 있다/없다 뿐이다.
 */
export const CONSENT_COOKIE = "devvoca_oauth_consent";

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

  // 체크박스가 없는 경로(로그인 화면)로 왔으면 전에 남은 동의도 지운다.
  // 남겨 두면 체크하지 않은 새 계정에 예전 동의가 적용된다.
  //
  // 우리 화면에서 누른 링크일 때만 동의로 친다. 남이 만든 링크나 주소창으로
  // 온 사람은 체크박스를 본 적이 없다. 이 값은 본인이 확인했다는 기록이다.
  // 헤더를 안 보내는 옛 브라우저는 지금처럼 통과시킨다.
  const site = request.headers.get("sec-fetch-site");
  const fromOurPage = site === "same-origin" || site === null;
  if (url.searchParams.get("consent") === "1" && fromOurPage) {
    store.set(CONSENT_COOKIE, "1", options);
  } else {
    store.delete(CONSENT_COOKIE);
  }

  return NextResponse.redirect(
    authUrl({ clientId, origin: url.origin, state }),
  );
}
