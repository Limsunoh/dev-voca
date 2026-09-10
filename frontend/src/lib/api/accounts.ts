import { ApiError, apiBase, request } from "./client";

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
  /**
   * 비밀번호를 쓸 수 있는 계정인가. 구글로만 가입하면 false 다.
   *
   * google_picture 로 대신 판정하면 안 된다. 이메일로 가입한 뒤 구글로도
   * 로그인한 사람은 사진이 있으면서 비밀번호도 있다.
   */
  has_password: boolean;
  /**
   * 내가 올린 사진의 주소. 없으면 빈 문자열.
   *
   * google_picture 와 같은 이유로 따로 온다 - avatar_display 는 "지금
   * 무엇을 그릴지" 라서 아바타를 고르면 사진이 남아 있어도 preset 이 되고,
   * 그것만 보면 올린 사진으로 되돌아갈 길이 화면에서 사라진다.
   */
  uploaded_photo: string;
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

/**
 * 이메일 변경 신청. 새 주소로 확인 메일이 간다.
 *
 * 여기서는 주소가 바뀌지 않는다. 링크를 눌러야 끝난다 - 이메일은 로그인
 * 키라, 확인 없이 바꾸면 계정을 통째로 넘기는 통로가 된다.
 */
export function requestEmailChange(
  token: string,
  body: { new_email: string; current_password: string },
): Promise<{ sent_to: string }> {
  return request("/api/accounts/email-change/", {
    method: "POST",
    body,
    token,
  });
}

/**
 * 확인 링크를 눌렀을 때. 여기서 주소가 바뀐다.
 *
 * 로그인 토큰을 안 보낸다. 메일을 다른 기기에서 열 수 있어야 하고, 그
 * 기기에 우리 로그인이 없을 수 있다. 링크에 실린 토큰이 증거다.
 *
 * 응답으로 새 로그인 토큰이 온다. 주소가 바뀌면 서버가 옛 토큰을 전부
 * 끊기 때문에, 이것을 쿠키에 다시 넣어야 링크를 누른 기기가 이어서 쓴다.
 */
export function confirmEmailChange(
  changeToken: string,
): Promise<{ token: string; user: User }> {
  return request("/api/accounts/email-change/confirm/", {
    method: "POST",
    body: { token: changeToken },
  });
}

/** 비밀번호 변경 응답. 새 토큰이 함께 온다. */
export type PasswordChangeResult = AuthResult & {
  /**
   * 처음 설정한 것인가. 바꾼 것이면 false.
   *
   * 서버가 정해서 내려준다. 화면이 다시 판정할 수 없다 - 저장이 끝난
   * 뒤에는 양쪽 다 비밀번호가 있는 상태라 구분이 사라진다.
   */
  created: boolean;
};

/**
 * 비밀번호 변경. 처음 설정하는 것도 같은 경로다.
 *
 * **응답의 토큰으로 쿠키를 갱신해야 한다.** 서버가 이 계정의 토큰을 전부
 * 지우고 새로 발급하기 때문이다(다른 기기를 끊는 것이 목적이다). 옛 토큰이
 * 담긴 쿠키를 그대로 두면 지금 기기도 다음 요청에서 401 을 받는다.
 *
 * current_password 를 안 보내는 경우가 있다. 구글로만 가입한 사람은
 * 비밀번호가 없어서 확인할 값이 없다 - 그때 빈 값이라도 보내면 서버가
 * 400 으로 막는다.
 */
export function changePassword(
  token: string,
  body: { current_password?: string; new_password: string },
): Promise<PasswordChangeResult> {
  return request("/api/accounts/password/", {
    method: "POST",
    body,
    token,
  });
}

/**
 * 사진 경로만 쓰는 요청.
 *
 * 공용 request() 를 못 쓴다. 그쪽은 본문을 JSON.stringify 하고
 * Content-Type: application/json 을 붙이는데, multipart 는 경계
 * 문자열이 헤더에 들어가야 해서 fetch 가 직접 지어줘야 한다. 손으로
 * 붙이면 그 경계가 본문과 안 맞아 서버가 파일을 못 찾는다.
 *
 * client.ts 를 고치지 않고 여기 두는 이유: 지금 파일을 보내는 곳이
 * 이 한 군데다. 공용에 넣으면 쓰는 곳 하나짜리 분기가 그 파일에 남는다.
 */
async function photoRequest(
  method: "POST" | "DELETE",
  token: string,
  body?: FormData,
): Promise<User> {
  let res: Response;
  try {
    res = await fetch(`${apiBase()}/api/accounts/photo/`, {
      method,
      headers: {
        Accept: "application/json",
        Authorization: `Token ${token}`,
      },
      body,
      cache: "no-store",
    });
  } catch {
    throw new ApiError("서버에 연결할 수 없습니다.", 0);
  }

  if (!res.ok) {
    // 400 대의 본문만 안내로 쓴다. 이유는 client.ts 의 errorMessage 와
    // 같다 - 서버 오류 본문에는 사용자가 할 수 있는 일이 없다.
    let message = `사진을 저장하지 못했습니다. (${res.status})`;
    if (res.status < 500) {
      try {
        const data = await res.json();
        // 칸별 오류({"photo": ["..."]})와 전체 오류({"detail": "..."})
        // 둘 다 온다. 첫 줄만 보여준다.
        const first =
          typeof data?.detail === "string"
            ? data.detail
            : Object.values(data ?? {})
                .flat()
                .find((v) => typeof v === "string");
        if (typeof first === "string") message = first;
      } catch {
        // 본문이 JSON 이 아닌 경우. 위 기본 문구를 쓴다.
      }
    }
    throw new ApiError(message, res.status);
  }

  return res.json() as Promise<User>;
}

/**
 * 프로필 사진 올리기.
 *
 * 서버가 줄여서 저장하고, 무엇을 보여줄지도 사진으로 바꿔서 내려준다.
 * 여기서 avatar 를 따로 보낼 필요가 없다.
 */
export function uploadMyPhoto(token: string, file: File): Promise<User> {
  const body = new FormData();
  body.set("photo", file);
  return photoRequest("POST", token, body);
}

/** 올린 사진을 지우고 아바타로 되돌린다. */
export function deleteMyPhoto(token: string): Promise<User> {
  return photoRequest("DELETE", token);
}
