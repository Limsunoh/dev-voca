"use server";

import { redirect } from "next/navigation";

import { setGuest } from "@/lib/session";

/**
 * 게스트로 둘러보기.
 *
 * 계정을 만들지 않고 그냥 쓰겠다는 선택이다. 아무 권한도 주지 않고,
 * 첫 화면을 다시 띄우지 않기 위한 표시만 남긴다.
 *
 * 서버 액션인 이유: 쿠키는 서버에서만 쓸 수 있다. 링크로 두면 GET 이
 * 상태를 바꾸게 되어, 브라우저가 미리 불러오기만 해도 선택이 굳는다.
 */
export async function continueAsGuestAction(): Promise<void> {
  await setGuest();
  redirect("/");
}
