"use server";

import { redirect } from "next/navigation";

import { logIn, logOut, signUp } from "@/lib/api/accounts";
import { ApiError } from "@/lib/api/client";
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

/** 로그인 후 돌아갈 곳. 열린 리다이렉트를 막으려고 내부 경로만 허용한다. */
function safeNext(value: FormDataEntryValue | null): string {
  const raw = typeof value === "string" ? value : "";

  // 검사 전에 브라우저가 읽는 모양으로 맞춘다. 주소를 해석할 때 탭과
  // 줄바꿈은 지워지고 역슬래시는 슬래시로 취급되기 때문에, 원문 그대로
  // 보면 "/\evil.com" 이 내부 경로처럼 보이고 실제로는 밖으로 나간다.
  //
  // 그러면 사용자는 진짜 주소에서 제대로 로그인한 직후 남의 사이트로
  // 넘어간다. 방금 로그인에 성공했으니 거기서 다시 로그인을 요구해도
  // 의심하기 어렵다.
  const next = raw.replace(/[\t\r\n]/g, "").replace(/\\/g, "/");

  // 슬래시 하나로 시작하고 그다음이 슬래시가 아닌 경로만 통과시킨다.
  return /^\/(?!\/)/.test(next) ? next : "/";
}

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
