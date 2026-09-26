"use server";

import { redirect } from "next/navigation";

import { logOut } from "@/lib/api/accounts";
import { forgetToken, getToken, setGuest } from "@/lib/session";

/**
 * 게스트로 둘러보기.
 *
 * 계정을 만들지 않고 그냥 쓰겠다는 선택이다. 아무 권한도 주지 않고,
 * 첫 화면을 다시 띄우지 않기 위한 표시만 남긴다.
 *
 * 서버 액션인 이유: 쿠키는 서버에서만 쓸 수 있다. 링크로 두면 GET 이
 * 상태를 바꾸게 되어, 브라우저가 미리 불러오기만 해도 선택이 굳는다.
 *
 * **남아 있는 로그인 쿠키도 지운다.** 이 버튼이 보이는 곳(로그인·가입·첫
 * 화면)은 로그인한 사람을 들여보내지 않으니, 남은 토큰은 대개 서버가 거절한
 * 죽은 토큰이다. 지우지 않으면 "로그인 없이" 를 골라도 그 토큰이 계속
 * 실려, 한 판 "시작" 이 "토큰이 유효하지 않습니다" 로 막힌 채 빠져나올
 * 길이 없었다.
 *
 * "대개" 인 이유: 백엔드가 잠깐 안 받아 로그인 확인이 실패하면 살아 있는
 * 토큰을 가진 사람에게도 이 버튼이 보인다. 그래서 지우기 전에 로그아웃처럼
 * 서버 토큰도 폐기한다 - 쿠키만 지우면 서버에는 만료 없는 토큰이 남는다.
 * 죽은 토큰이면 서버가 401 을 주고, 그 실패는 무시한다(logoutAction 과 같다).
 */
export async function continueAsGuestAction(): Promise<void> {
  const token = await getToken();
  if (token) {
    try {
      await logOut(token);
    } catch {
      // 죽은 토큰이거나 서버가 응답하지 않는 경우. 어느 쪽이든 쿠키는 지운다.
    }
    await forgetToken();
  }
  await setGuest();
  redirect("/");
}
