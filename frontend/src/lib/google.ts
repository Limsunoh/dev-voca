/**
 * 구글 로그인 주소 만들기.
 *
 * 서버에서만 쓴다. 클라이언트 ID 는 감출 값이 아니지만(주소창에 그대로
 * 보인다) 여기서 만들어 넘기는 편이 화면 코드가 단순하다.
 */

const AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";

/**
 * 구글에서 돌아올 주소.
 *
 * 구글 콘솔에 등록한 것과 **글자 하나까지 같아야** 한다. 다르면
 * redirect_uri_mismatch 로 거절당한다.
 */
export function callbackUrl(origin: string): string {
  // APP_ORIGIN 이 있으면 그것을 쓴다. 요청에서 유추한 주소는 프록시
  // 뒤에서 어긋날 수 있는데(https 로 들어온 요청이 앱에는 http 로
  // 보이는 등), 그러면 구글이 등록된 주소와 다르다며 거절한다.
  // 사용자에게는 "구글 로그인을 마치지 못했습니다" 만 보여 원인을
  // 찾기 어렵다.
  return `${process.env.APP_ORIGIN || origin}/api/auth/google/callback`;
}

/**
 * 사용자를 보낼 구글 주소.
 *
 * state 는 돌아왔을 때 "우리가 보낸 요청이 맞는지" 확인하는 값이다.
 * 없으면 남이 만든 로그인 링크를 사용자가 눌렀을 때 그 사람 계정으로
 * 로그인되어 버린다.
 */
export function authUrl(options: {
  clientId: string;
  origin: string;
  state: string;
}): string {
  const params = new URLSearchParams({
    client_id: options.clientId,
    // 콜백에서 쓰는 값과 같아야 한다. 그래서 같은 함수를 부른다 -
    // 구글은 코드를 발급할 때와 확인할 때의 주소를 대조한다.
    redirect_uri: callbackUrl(options.origin),
    response_type: "code",
    // 이메일과 이름만 받는다. 더 달라고 하면 동의 화면이 길어지고
    // 사용자가 멈칫한다.
    scope: "openid email profile",
    state: options.state,
    // 이미 로그인된 계정이 하나면 묻지 않고 지나간다. 계정을 고르고
    // 싶은 사람이 있으니 선택 화면을 띄운다.
    prompt: "select_account",
  });

  return `${AUTH_URL}?${params}`;
}
