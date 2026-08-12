"use server";

import { redirect } from "next/navigation";

import { logIn, logOut, signUp } from "@/lib/api/accounts";
import { ApiError } from "@/lib/api/client";
import { safeNext } from "@/lib/routes";
import { clearToken, getToken, setToken } from "@/lib/session";

/**
 * 로그인·가입·로그아웃 처리.
 *
 * Server Action 으로 두는 이유: 폼 제출을 서버가 직접 받으면 토큰이
 * 브라우저를 거치지 않는다. 백엔드 응답의 토큰을 그 자리에서 httpOnly
 * 쿠키에 넣고, 브라우저에는 결과 화면만 돌려준다.
 *
 * 자바스크립트가 꺼져 있어도 동작한다는 부수 효과도 있다.
 */

/** 폼이 화면에 되돌려줄 값. 실패했을 때만 메시지가 있다. */
export type FormState = { error?: string };

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "잠시 후 다시 시도해주세요.";
}

export async function loginAction(
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const next = safeNext(formData.get("next"));

  if (!email || !password) {
    return { error: "이메일과 비밀번호를 입력해주세요." };
  }

  try {
    const { token } = await logIn({ email, password });
    await setToken(token);
  } catch (error) {
    return { error: messageOf(error) };
  }

  // redirect 는 내부적으로 예외를 던진다. try 안에서 부르면 위 catch 가
  // 그것을 삼켜 "잠시 후 다시 시도해주세요" 로 바뀐다.
  redirect(next);
}

export async function signUpAction(
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const displayName = String(formData.get("display_name") ?? "").trim();
  const next = safeNext(formData.get("next"));

  if (!email || !password) {
    return { error: "이메일과 비밀번호를 입력해주세요." };
  }

  try {
    const { token } = await signUp({
      email,
      password,
      ...(displayName ? { display_name: displayName } : {}),
    });
    await setToken(token);
  } catch (error) {
    return { error: messageOf(error) };
  }

  redirect(next);
}

export async function logoutAction(): Promise<void> {
  const token = await getToken();

  if (token) {
    try {
      // 서버의 토큰도 지운다. 쿠키만 지우면 그 사이 새어나간 토큰이
      // 계속 통한다.
      await logOut(token);
    } catch {
      // 서버가 응답하지 않아도 이쪽 쿠키는 지운다. 사용자 입장에서
      // 로그아웃이 안 되는 것보다는 낫다.
    }
  }

  await clearToken();
  redirect("/");
}
