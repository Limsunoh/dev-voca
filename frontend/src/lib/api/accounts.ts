import { request } from "./client";

/**
 * 계정 API 클라이언트.
 *
 * 브라우저가 아니라 서버에서만 부른다. 토큰이 오가는 경로라 더욱 그렇다 -
 * 브라우저가 직접 부르면 응답의 토큰이 자바스크립트에 노출되고, 그러면
 * httpOnly 쿠키에 넣는 의미가 사라진다.
 */

/** 프로필 그림으로 무엇을 그릴지. 서버가 정해서 내려준다. */
export type AvatarDisplay =
  | { type: "photo"; url: string }
  | { type: "preset"; key: string };

/** 로그인한 사용자. 백엔드 UserSerializer 와 짝. */
export type User = {
  id: number;
  email: string;
  /** 사용자가 정한 이름. 대소문자를 구분하지 않고 중복될 수 없다. */
  display_name: string;
  /** 화면에 쓸 이름. 비어 있는 경우가 없도록 서버가 채워 내려준다. */
  name: string;
  /** 고른 값. 비어 있으면 서버가 알아서 정한다. */
  avatar: string;
  avatar_display: AvatarDisplay;
  /**
   * 구글 계정 사진 주소. 없으면 빈 문자열.
   *
   * 읽기 전용이다. "구글 사진" 선택지를 그릴지 판단하는 데 쓴다 -
   * avatar_display 로 대신하면 안 된다. 그건 "지금 무엇을 그릴지" 라서
   * 아바타를 한 번 고르면 사진이 남아 있어도 preset 으로 온다.
   */
  google_picture: string;
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

/**
 * 구글 로그인.
 *
 * 구글이 준 코드를 넘기면 백엔드가 구글에 되물어 확인하고, 계정을 찾거나
 * 만든다. 사용자 정보를 직접 넘기지 않는 이유: 그러면 누구든 남의
 * 이메일을 적어 보내 그 계정으로 들어올 수 있다.
 */
export function logInWithGoogle(body: {
  code: string;
  redirect_uri: string;
}): Promise<AuthResult> {
  return request("/api/accounts/google/", { method: "POST", body });
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

/**
 * 내 프로필 수정.
 *
 * 이메일과 권한은 서버가 읽기 전용으로 막는다. 여기서 보낼 수 있는 것은
 * 이름과 아바타뿐이다.
 */
export function updateMe(
  token: string,
  body: { display_name?: string; avatar?: string },
): Promise<User> {
  return request("/api/accounts/me/", { method: "PATCH", body, token });
}
