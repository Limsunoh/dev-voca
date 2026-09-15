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

/**
 * 폼이 화면에 되돌려줄 값. 실패했을 때만 메시지가 있다.
 *
 * 친 값을 같이 돌려주는 이유: Server Action 이 끝나면 React 가 폼을
 * **초기화한다**(브라우저가 폼을 제출했을 때와 같은 동작이다). 그래서
 * 비밀번호를 한 글자 틀렸을 뿐인데 이메일까지 다시 쳐야 했다. 가입은
 * 세 칸이라 더 나쁘다.
 *
 * 비밀번호는 안 돌려준다. 되돌려주려면 서버를 한 번 더 왕복시켜야 하고,
 * 그 값이 응답 본문과 브라우저 메모리에 남는다. 무엇보다 defaultValue 로
 * 넣으면 **DOM 의 value 속성에 평문이 박혀** 개발자 도구에 그대로 보인다.
 * 다시 치는 칸 하나와 바꿀 것이 아니다.
 *
 * **머무는 액션을 새로 붙이려면 values 를 반드시 같이 실어야 한다.** 지금은
 * 성공하면 redirect 로 나가서 values 가 필요 없는데, 값을 돌려주며 화면에
 * 남는 액션을 AuthForm 에 물리면 그 응답에서 values 가 빠진 순간 직전에
 * 되살린 값이 빈 칸이 된다 - React 가 폼을 초기화하며 defaultValue 를
 * 되돌리는데 그 자리가 undefined 가 되기 때문이다.
 */
export type FormState = {
  error?: string;
  /** 방금 친 값. 화면이 이걸로 칸을 되살린다. */
  values?: { email?: string; display_name?: string };
};

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
    return { error: "이메일과 비밀번호를 입력해주세요.", values: { email } };
  }

  try {
    const { token } = await logIn({ email, password });
    await setToken(token);
  } catch (error) {
    return { error: messageOf(error), values: { email } };
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

  // 친 값을 그대로 싣는다. 백엔드는 이보다 더 다듬지만(연속 공백 접기·숨은
  // 문자 제거·NFC) 그 결과를 돌려주지 않는다 - 실패한 폼에는 사용자가 친
  // 것이 그대로 있어야 무엇을 고칠지 안다. 다듬은 값으로 화면을 맞추는 것은
  // 저장에 성공한 뒤의 이야기다(ProfileForm 의 savedName).
  //
  // 이름은 비워도 되는 칸이라 빈 문자열이 실린다. 화면에서도 빈 칸이 되어
  // 되살릴 값이 없는 것과 결과가 같다.
  const kept = { email, display_name: displayName };

  if (!email || !password) {
    return { error: "이메일과 비밀번호를 입력해주세요.", values: kept };
  }

  try {
    const { token } = await signUp({
      email,
      password,
      ...(displayName ? { display_name: displayName } : {}),
    });
    await setToken(token);
  } catch (error) {
    return { error: messageOf(error), values: kept };
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
