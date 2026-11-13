"use server";

import { createHash, randomBytes } from "node:crypto";

import { cookies } from "next/headers";
import { redirect, RedirectType } from "next/navigation";

import { logInWithGoogle } from "@/lib/api/accounts";
import { ApiError } from "@/lib/api/client";
import { safeNext } from "@/lib/routes";
import { carryGuestDailyLength, setToken } from "@/lib/session";

/**
 * 구글 버튼(GoogleButton)으로 로그인할 때의 서버 쪽.
 *
 * 화면 아래 계정 창(FedCM)으로 로그인하면 페이지를 떠나지 않는다. 구글이
 * 브라우저에 신분 토큰(credential)을 주고, 그것을 여기서 백엔드로 넘겨
 * 확인받는다. 구글 화면을 다녀오는 예전 길(app/api/auth/google)과 같은 일을
 * 하되, 기록에 구글 칸이 남지 않는다.
 */

/** 버튼 한 번의 로그인에만 쓰는 비밀값. 쿠키 이름. */
const NONCE_COOKIE = "devvoca_google_nonce";

// 1시간. 버튼을 띄워 둔 채 앱을 내려 두었다가 돌아와 눌러도 되게 넉넉히
// 둔다(구글 신분 토큰의 수명과 같다). 쓰면 바로 지운다.
//
// 쿠키는 하나라, 탭 두 개에서 로그인 화면을 열면 나중에 연 탭의 값이 앞 탭의
// 값을 덮는다. 앞 탭에서 누르면 한 번 실패하고(로그인 화면의 "구글 로그인을
// 마치지 못했습니다"), 화면을 새로 받아 버튼도 새 값으로 다시 그려지므로 다시
// 누르면 된다.
const MAX_AGE = 60 * 60;

/**
 * 버튼을 그릴 준비. 클라이언트 ID 와, 구글에 넘길 nonce 를 준다.
 *
 * 비밀값을 하나 만들어 httpOnly 쿠키에 두고, 구글에는 그 sha256 만 nonce 로
 * 넘긴다. 구글은 nonce 를 신분 토큰 안에 그대로 넣는데, 토큰은 서명만 돼 있고
 * 암호화돼 있지 않아 누구나 읽는다. 그래서 대조는 비밀값으로 한다. 토큰이
 * 오면 쿠키의 비밀값을 백엔드에 같이 보내고, 백엔드가 해시해 토큰의 nonce 와
 * 맞춰 본다. 새어 나간 토큰을 다른 곳에서 다시 보내도 비밀값을 몰라 통과하지
 * 못한다(OpenID Connect 가 권하는 방식).
 *
 * 클라이언트 ID 를 여기서 주는 이유: 서버 환경 변수(GOOGLE_CLIENT_ID)라 화면
 * 코드가 직접 읽지 못한다. 공개 값이지만(구글 버튼이 그대로 드러낸다) 화면용
 * 환경 변수를 따로 두면 배포 설정이 하나 늘어난다. 없으면 null 이고, 버튼은
 * 구글 화면으로 가는 예전 링크를 그대로 보인다.
 */
export async function prepareGoogleButton(): Promise<{
  clientId: string;
  nonce: string;
} | null> {
  const clientId = process.env.GOOGLE_CLIENT_ID;
  if (!clientId) return null;
  const secret = randomBytes(32).toString("hex");
  const store = await cookies();
  store.set(NONCE_COOKIE, secret, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: MAX_AGE,
  });
  return { clientId, nonce: createHash("sha256").update(secret).digest("hex") };
}

/**
 * 구글 버튼이 준 신분 토큰으로 로그인한다. 성공하면 돌아갈 곳으로, 새 계정인데
 * 동의가 없으면 가입 화면으로 보낸다. 그 밖의 실패는 { failed: true } 를 돌려주고
 * 화면(GoogleButton)이 로그인 화면을 문서째 새로 받는다. 여기서 같은 로그인
 * 화면으로 redirect 하면 Next 가 버튼을 다시 붙이지 않아, 다 쓴 nonce 와 "이미
 * 보냈다" 표시를 든 채 남아 다시 눌러도 반응하지 않을 수 있다.
 *
 * consent 는 가입 동의 세 항목을 켜고 누른 버튼에서만 true 다. 서버 액션은
 * 같은 사이트의 화면에서만 부를 수 있어(Next 가 Origin 을 대조한다), 남이
 * 만든 페이지에서 동의한 척 부를 수 없다.
 *
 * redirect 를 액션 안에 두고 바꿔치기(replace)로 보낸다. 값을 돌려주고 화면에서
 * 옮기면 Next 가 지금 화면을 새 쿠키로 다시 그려, 로그인 화면의 redirect 가
 * 먼저 돌아 돌아갈 주소(next)를 잃는다((auth)/actions.ts 의 loginAction 주석).
 */
export async function googleCredentialAction(input: {
  credential: unknown;
  next?: unknown;
  consent?: unknown;
}): Promise<{ failed: true } | void> {
  const store = await cookies();
  const secret = store.get(NONCE_COOKIE)?.value;
  // 한 번 쓰면 지운다. 남겨 두면 같은 값으로 다시 시도할 수 있다.
  store.delete(NONCE_COOKIE);

  // 서버 액션은 화면 밖에서도 아무 인자로나 부를 수 있다. 객체가 아니면 실패로.
  const args = input && typeof input === "object" ? input : { credential: null };
  const next = safeNext(typeof args.next === "string" ? args.next : null);
  const credential = args.credential;
  let outcome: "ok" | "consent" | "failed" = "failed";

  if (typeof credential === "string" && credential && secret) {
    try {
      const { token, user } = await logInWithGoogle({
        credential,
        nonce: secret,
        ...(args.consent === true
          ? { terms_agreed: true, disclosure_agreed: true, age_confirmed: true }
          : {}),
      });
      await setToken(token);
      await carryGuestDailyLength(token, user);
      outcome = "ok";
    } catch (error) {
      // 새 계정인데 동의 값이 없는 경우. 계정은 만들어지지 않았고, 가입
      // 화면에서 세 항목을 켜고 다시 누르게 한다.
      if (
        error instanceof ApiError &&
        error.field === "code" &&
        error.message === "consent_required"
      ) {
        outcome = "consent";
      } else {
        const detail = error instanceof ApiError ? error.message : String(error);
        console.error(`구글 로그인 실패: ${detail}`);
      }
    }
  } else {
    console.error("구글 로그인 실패: 신분 토큰이나 nonce 가 없습니다");
  }

  if (outcome === "consent") {
    const signup = new URLSearchParams({ error: "consent" });
    if (next !== "/") signup.set("next", next);
    redirect(`/signup?${signup}`, RedirectType.replace);
  }
  if (outcome === "failed") return { failed: true };
  redirect(next, RedirectType.replace);
}
