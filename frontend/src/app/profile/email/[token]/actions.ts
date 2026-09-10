"use server";

import { revalidatePath } from "next/cache";

import { confirmEmailChange } from "@/lib/api/accounts";
import { ApiError } from "@/lib/api/client";
import { setToken } from "@/lib/session";

export type ConfirmState = {
  error?: string;
  /** 바뀐 주소. 화면이 "이 주소로 바뀌었습니다" 를 그린다. */
  changedTo?: string;
};

/**
 * 확인 버튼을 눌렀을 때. 여기서 주소가 바뀐다.
 *
 * 서버가 옛 토큰을 전부 끊고 새것을 준다. 그것을 쿠키에 다시 넣지 않으면
 * **이 기기도 함께 로그아웃된다** - 방금 본인 확인을 마친 사람이 튕겨나가
 * 무엇이 잘못됐는지 모른 채 다시 로그인하게 된다.
 */
export async function confirmEmailChangeAction(
  _prev: ConfirmState,
  formData: FormData,
): Promise<ConfirmState> {
  const token = String(formData.get("token") ?? "");
  if (!token) return { error: "확인 링크가 올바르지 않습니다." };

  try {
    const result = await confirmEmailChange(token);

    // 새 토큰으로 갈아 끼운다. 순서가 중요하다 - 이것을 먼저 해야
    // 아래 revalidate 가 그린 화면이 로그인된 상태로 나온다.
    await setToken(result.token);

    // 머리말이 이름과 사진을 그린다. 이 화면만 다시 그리면 위쪽이
    // 로그아웃 상태로 남는다.
    revalidatePath("/", "layout");

    return { changedTo: result.user.email };
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "잠시 후 다시 시도해주세요." };
  }
}
