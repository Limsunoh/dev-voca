"use server";

import { revalidatePath } from "next/cache";

import { confirmEmailChange, getMe, type User } from "@/lib/api/accounts";
import { ApiError } from "@/lib/api/client";
import { getToken, setToken } from "@/lib/session";

export type ConfirmState = {
  error?: string;
  /** 바뀐 주소. 화면이 "이 주소로 바뀌었습니다" 를 그린다. */
  changedTo?: string;
  /** 이 기기가 새 토큰으로 로그인을 이어 간다. 아니면 새 주소로 다시 로그인해야 한다. */
  signedIn?: boolean;
};

const RETRY = "잠시 후 다시 시도해주세요.";

/**
 * 주소에서 꺼낸 토큰을 원래 글자로 되돌린다.
 *
 * 토큰은 Django 서명(`값:시각:서명`)이라 쌍점이 들어 있는데, Next 는 경로
 * 값을 `%3A` 로 바꾼 채 넘긴다. 그대로 보내면 서명 검사가 실패해 모든
 * 링크가 "만료되었거나 올바르지 않습니다" 가 된다. 이미 풀린 값이 와도
 * 토큰에는 `%` 가 없어 그대로다. 깨진 값은 그대로 보내 서버가 거절하게 둔다.
 */
function tokenFromPath(raw: string): string {
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

/**
 * 확인 버튼을 눌렀을 때. 여기서 주소가 바뀐다.
 *
 * 서버가 옛 토큰을 전부 끊고 새것을 준다. 이 기기가 같은 계정으로 로그인해
 * 있었으면 그것을 쿠키에 다시 넣는다. 안 넣으면 방금 본인 확인을 마친 사람이
 * 튕겨나가 무엇이 잘못됐는지 모른 채 다시 로그인하게 된다.
 *
 * 그 밖의 기기(로그인이 없거나 다른 계정)에서는 쿠키를 건드리지 않는다. 링크만
 * 있으면 누구나 버튼을 누를 수 있어서, 남이 자기 계정의 확인 링크를 보내
 * 누르게 하면 누른 사람이 모르는 새 그 계정으로 로그인되고, 이후의 공부
 * 기록과 사진이 남의 계정에 쌓인다. 본인이 로그인 없는 브라우저에서 열었다면
 * 새 주소로 한 번 로그인하면 된다. 확인과 함께 다른 기기의 로그인이 모두
 * 끊기므로, 앱에서는 어차피 다시 로그인하게 된다.
 */
export async function confirmEmailChangeAction(
  _prev: ConfirmState,
  formData: FormData,
): Promise<ConfirmState> {
  const token = tokenFromPath(String(formData.get("token") ?? ""));
  if (!token) return { error: "확인 링크가 올바르지 않습니다." };

  // 확인 전에 묻는다. 확인이 끝나면 서버가 그 계정의 토큰을 모두 끊어서 같은
  // 사람이었는지 뒤에서는 알 수 없다. getCurrentUser 를 쓰지 않는 이유: 그것은
  // 백엔드가 잠깐 실패해도 null(로그인 없음)을 준다. 여기서 그렇게 읽으면 판단을
  // 못 한 채 넘어가게 되므로, 401 이 아닌 실패는 확인 전에 멈춘다. 링크는 그대로
  // 살아 있어 다시 누르면 된다.
  const loginToken = await getToken();
  let here: User | null = null;
  if (loginToken) {
    try {
      here = await getMe(loginToken);
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) {
        console.error("이메일 변경 확인 전에 로그인 상태를 확인하지 못했습니다.", error);
        return { error: RETRY };
      }
    }
  }

  let result: Awaited<ReturnType<typeof confirmEmailChange>>;
  try {
    result = await confirmEmailChange(token);
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    console.error("이메일 변경 확인에 실패했습니다.", error);
    return { error: RETRY };
  }

  if (here?.id !== result.user.id) return { changedTo: result.user.email };

  // 여기부터는 주소가 이미 바뀌었다. 쿠키를 못 넣어도 "다시 시도" 를 띄우면 안 된다 -
  // 링크는 이미 쓰여 다시 누르면 "만료" 가 나온다. 다시 로그인하라는 안내로 끝낸다.
  try {
    // 새 토큰으로 갈아 끼운다. 순서가 중요하다 - 이것을 먼저 해야
    // 아래 revalidate 가 그린 화면이 로그인된 상태로 나온다.
    await setToken(result.token);
  } catch (error) {
    console.error("바뀐 계정의 새 로그인 토큰을 쿠키에 넣지 못했습니다.", error);
    return { changedTo: result.user.email };
  }

  // 머리말이 이름과 사진을 그린다. 이 화면만 다시 그리면 위쪽이
  // 로그아웃 상태로 남는다.
  revalidatePath("/", "layout");

  return { changedTo: result.user.email, signedIn: true };
}
