import { request } from "./client";

/**
 * 계정 API 클라이언트.
 *
 * 브라우저가 아니라 서버에서만 부른다. 토큰이 오가는 경로라 더욱 그렇다 -
 * 브라우저가 직접 부르면 응답의 토큰이 자바스크립트에 노출되고, 그러면
 * httpOnly 쿠키에 넣는 의미가 사라진다.
 */

/** 로그인한 사용자. 백엔드 UserSerializer 와 짝. */
export type User = {
  id: number;
  email: string;
  display_name: string;
  /** 화면에 쓸 이름. 표시 이름이 없으면 이메일 앞부분이 온다. */
  name: string;
  is_staff: boolean;
};

/** 가입·로그인 응답. 토큰과 사용자 정보가 함께 온다. */
export type AuthResult = {
  token: string;
  user: User;
};

export function signUp(body: {
  email: string;
  password: string;
  display_name?: string;
}): Promise<AuthResult> {
  return request("/api/accounts/signup/", { method: "POST", body });
}

export function logIn(body: {
  email: string;
  password: string;
}): Promise<AuthResult> {
  return request("/api/accounts/login/", { method: "POST", body });
}

/** 토큰을 서버에서도 무효로 만든다. */
export function logOut(token: string): Promise<void> {
  return request("/api/accounts/logout/", { method: "POST", token });
}

/**
 * 내 정보. 쿠키의 토큰이 아직 쓸 수 있는지 확인하는 데도 쓴다.
 *
 * 토큰이 없거나 만료면 401 이 오고, 화면은 로그아웃 상태로 그린다.
 */
export function getMe(token: string): Promise<User> {
  return request("/api/accounts/me/", { token });
}
