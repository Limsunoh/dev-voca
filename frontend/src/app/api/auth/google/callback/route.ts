import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { logInWithGoogle } from "@/lib/api/accounts";
import { ApiError } from "@/lib/api/client";
import { callbackUrl } from "@/lib/google";
import { safeNext } from "@/lib/routes";
import { setToken } from "@/lib/session";
import { NEXT_COOKIE, STATE_COOKIE } from "../route";

/**
 * 구글에서 돌아오는 자리.
 *
 * 구글이 준 코드를 백엔드로 넘겨 확인받고, 받은 토큰을 쿠키에 넣는다.
 * 코드를 브라우저에 노출하지 않고 서버끼리 주고받는다.
 */

/** 실패했을 때. 이유는 감추고 로그인 화면으로 돌려보낸다. */
function backToLogin(request: Request, reason: string) {
  console.error(`구글 로그인 실패: ${reason}`);
  return NextResponse.redirect(new URL("/login?error=google", request.url));
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const store = await cookies();

  const state = store.get(STATE_COOKIE)?.value;
  const next = store.get(NEXT_COOKIE)?.value ?? "/";

  // 한 번 쓰면 지운다. 남겨두면 같은 값으로 다시 시도할 수 있다.
  store.delete(STATE_COOKIE);
  store.delete(NEXT_COOKIE);

  // 사용자가 동의 화면에서 취소한 경우. 오류가 아니므로 조용히 돌려보낸다.
  if (url.searchParams.get("error")) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // 우리가 보낸 요청이 맞는지 확인한다. 이게 없으면 남이 만든 링크를
  // 눌렀을 때 그 사람 계정으로 로그인된다.
  const returned = url.searchParams.get("state");
  if (!state || !returned || state !== returned) {
    return backToLogin(request, "state 가 맞지 않습니다");
  }

  const code = url.searchParams.get("code");
  if (!code) {
    return backToLogin(request, "코드가 없습니다");
  }

  try {
    const { token } = await logInWithGoogle({
      code,
      // 구글이 코드를 발급할 때 쓴 주소와 같아야 한다. 백엔드가 구글에
      // 확인을 요청할 때 이 값을 함께 보낸다.
      redirect_uri: callbackUrl(url.origin),
    });
    await setToken(token);
  } catch (error) {
    const detail = error instanceof ApiError ? error.message : String(error);
    return backToLogin(request, detail);
  }

  // 쿠키에 넣을 때 이미 걸렀지만 한 번 더 태운다. 옛 배포가 쓴 값이
  // 남아 있을 수 있고, 검사는 값을 쓰는 자리에 있어야 안 빠뜨린다.
  return NextResponse.redirect(new URL(safeNext(next), request.url));
}
