"use server";

import { revalidatePath } from "next/cache";
import { redirect, RedirectType } from "next/navigation";

import { updateMe } from "@/lib/api/accounts";
import { ApiError } from "@/lib/api/client";
import { isDailyLength } from "@/lib/daily-length";
import { forgetToken, getToken, setGuestDailyLength } from "@/lib/session";

export type DailyLengthState = { error?: string; saved?: boolean };

/**
 * 하루 공부량 저장. 처음 묻는 화면(/start/daily)과 내정보가 같이 쓴다.
 *
 * 로그인했으면 계정에, 게스트면 이 기기 쿠키에 둔다. 처음 묻는 화면에서는
 * 저장한 뒤 홈으로 가고, 내정보에서는 그 자리에 남아 고른 것이 바뀐다.
 *
 * 쿠키의 토큰을 서버가 거절하면(다른 기기에서 로그아웃 등) 그 토큰을 지우고
 * 게스트로 저장한다. 그대로 실패로 돌려주면 홈은 로그인 안 한 사람으로 보고
 * 다시 이 화면으로 보내서, 고르고 실패하기를 반복하는 화면에 갇힌다.
 */
export async function saveDailyLengthAction(
  _prev: DailyLengthState,
  formData: FormData,
): Promise<DailyLengthState> {
  const length = formData.get("length");
  if (!isDailyLength(length)) return { error: "길이를 골라주세요." };
  const fromProfile = formData.get("from") === "profile";

  const token = await getToken();
  let stored = false;
  if (token) {
    try {
      await updateMe(token, { daily_length: length });
      stored = true;
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) {
        return {
          error: error instanceof ApiError ? error.message : "잠시 후 다시 시도해주세요.",
        };
      }
      await forgetToken();
    }
  }
  if (!stored) {
    // 내정보는 로그인해야 열리는 화면이다. 거기서 토큰이 거절됐으면 게스트로
    // 저장할 일이 아니라 다시 로그인할 일이다.
    if (fromProfile) redirect("/login?next=/profile", RedirectType.replace);
    await setGuestDailyLength(length);
  }

  revalidatePath("/", "layout");
  if (fromProfile) return { saved: true };
  // 바꿔치기다. 공부량을 묻는 화면이 기록에 남으면 홈에서 뒤로 가기가 거기로
  // 간다(lib/history-nav.ts).
  redirect("/", RedirectType.replace);
}
