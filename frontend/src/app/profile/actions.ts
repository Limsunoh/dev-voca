"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { updateMe } from "@/lib/api/accounts";
import { ApiError } from "@/lib/api/client";
import { getToken } from "@/lib/session";

/**
 * 프로필 수정.
 *
 * Server Action 인 이유는 로그인·가입과 같다 - 토큰이 httpOnly 쿠키에만
 * 있어서 브라우저 자바스크립트가 볼 수 없고, 그것을 헤더에 붙이는 일은
 * 서버에서만 일어난다.
 */

export type ProfileState = {
  error?: string;
  saved?: boolean;
  /** 서버가 다듬어 저장한 이름. 화면의 입력칸을 이 값에 맞춘다. */
  savedName?: string;
};

export async function updateProfileAction(
  _prev: ProfileState,
  formData: FormData,
): Promise<ProfileState> {
  const token = await getToken();
  if (!token) {
    // 폼을 열어둔 채 로그인이 풀린 경우. 저장에 실패했다고만 하면
    // 몇 번을 더 누르게 된다.
    redirect("/login?next=/profile");
  }

  const displayName = String(formData.get("display_name") ?? "").trim();
  const avatar = String(formData.get("avatar") ?? "");

  if (!displayName) {
    return { error: "이름을 입력해주세요." };
  }

  let saved;
  try {
    saved = await updateMe(token, { display_name: displayName, avatar });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "잠시 후 다시 시도해주세요." };
  }

  // 머리말이 이름과 사진을 함께 그린다. 이 페이지만 다시 그리면 위쪽이
  // 옛 이름인 채로 남는다.
  revalidatePath("/", "layout");

  return { saved: true, savedName: saved.display_name };
}
