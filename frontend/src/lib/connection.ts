/**
 * 판 화면(문제풀기·한 판·일일공부·복습)이 브라우저에서 중계(/api/...)를 부르다
 * 연결이 끊겼을 때 쓰는 것들.
 *
 * 연결이 끊기면 fetch 는 응답 없이 TypeError 를 던지고, 그 문구는 브라우저가
 * 정한 영어다(Chrome 은 "Failed to fetch"). 판 화면들은 오류의 message 를 그대로
 * 보여 주므로, 지하철에서 끊긴 채 답을 누르면 그 영어가 떴다. 여기서 사람이
 * 읽을 문구로 바꾼다.
 */

import { routes } from "./routes";

/**
 * 연결이 끊겨 요청이나 응답이 실패했다. message 는 connectionLostMessage() 다.
 *
 * 한 판 화면(RoundBoard)은 5xx 도 이 클래스로 올리고, 그때 message 는 서버가 보낸
 * 문구다. message 로 끊김인지 가르지 말고 클래스로 가른다.
 */
export class ConnectionLost extends Error {
  name = "ConnectionLost";
}

/**
 * fetch 와 같지만, 연결이 끊겨 실패하면 ConnectionLost 를 던진다.
 *
 * 대개는 요청이 서버에 닿기 전에 끊긴 것이라 판의 토큰이 아직 안 쓰였고,
 * 연결된 뒤 같은 보기를 다시 누르면 이어진다. 서버에 닿아 처리된 뒤 응답만
 * 끊긴 경우도 같은 TypeError 라 여기서는 가를 수 없다. 그때 다시 누르면 서버가
 * "이미 처리한 답입니다" 로 거절한다. 한 판만 예외다. 같은 답을 다시 보내면
 * 서버가 처음 응답을 돌려주고(backend session._take_step), 화면(RoundBoard)이
 * 보기를 잠그고 그 답만 다시 보낸다.
 */
export async function fetchOrExplain(
  input: string,
  init?: RequestInit,
): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch (error) {
    // 일부러 끊은 것(AbortController)은 그대로 올린다.
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ConnectionLost(connectionLostMessage());
  }
}

/**
 * 성공 응답의 본문을 JSON 으로 읽는다. 받는 도중 끊기거나(TypeError) JSON 이
 * 아닌 본문이 오면(SyntaxError) ConnectionLost 를 던진다.
 *
 * 응답 머리는 받았는데 본문을 받다 끊기는 일이 있다. 그대로 두면 "Unterminated
 * string in JSON at position 17" 같은 영어가 화면에 뜬다. 공용 와이파이의 로그인
 * 화면(HTML)이 200 으로 오는 것도 같은 길이다.
 *
 * fetchOrExplain 과 달리 이때는 서버가 이미 처리를 마쳤다(응답 머리가 왔다).
 * 답하기 요청이면 다시 눌러도 서버가 "이미 처리한 답입니다" 로 거절한다. 한
 * 판은 예외다(위 fetchOrExplain 주석).
 *
 * 중계를 잘못 고쳐 JSON 이 아닌 200 을 돌려주는 프로그램 오류도 같은 문구가
 * 되므로, 원래 오류를 콘솔에 남긴다.
 */
export async function jsonOrExplain<T>(res: Response): Promise<T> {
  try {
    return (await res.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    console.error(error);
    throw new ConnectionLost(connectionLostMessage());
  }
}

/**
 * 연결이 끊겼을 때 보일 문구.
 *
 * 폰이 오프라인이면 그렇다고 말한다. 온라인인데 실패했으면 서버 쪽이라 "인터넷
 * 연결을 확인하라" 고 하면 사실과 다르다. navigator.onLine 은 오프라인일 때만
 * 믿을 수 있다(온라인이라고 해도 실제로는 안 닿을 수 있다).
 */
export function connectionLostMessage(): string {
  return typeof navigator !== "undefined" && navigator.onLine === false
    ? "인터넷에 연결되어 있지 않습니다. 연결되면 다시 눌러주세요."
    : "서버에 연결하지 못했습니다. 잠시 뒤 다시 눌러주세요.";
}

/**
 * 중계가 401 을 주면(로그인이 풀렸다) 로그인 화면으로 보내고, 돌아올 곳은 지금 주소다.
 *
 * 로그인이 있어야 하는 판 화면(일일공부, 복습)이 쓴다. 다른 기기에서 비밀번호를 바꿨거나
 * 로그인이 끝나면, 이 화면에 그대로 두는 동안 보기를 누를 때마다 "토큰이 유효하지
 * 않습니다." 만 뜬다. 복습은 보기 말고 누를 것이 없어 막다른 길이었다. 중계가 이미 죽은
 * 쿠키를 지웠으므로 로그인 화면이 "이미 로그인됨" 으로 되돌려 보내지 않는다.
 *
 * 쿼리까지 넘긴다. 일일공부의 "오늘만 다른 길이로"(?choose=1) 같은 상태가 로그인 뒤에도
 * 남는다. 한 판·문제풀기는 로그인 없이도 되는 화면이라 게스트로 다시 부르므로 쓰지 않는다.
 */
export function leaveIfSignedOut(res: Response): void {
  if (res.status !== 401) return;
  const here = window.location.pathname + window.location.search;
  window.location.replace(`${routes.login}?next=${encodeURIComponent(here)}`);
  throw new Error("로그인이 풀렸습니다. 로그인 화면으로 갑니다.");
}
