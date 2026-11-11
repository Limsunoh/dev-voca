/**
 * 판 화면(문제풀기·한 판·일일공부·복습)이 브라우저에서 중계(/api/...)를 부르다
 * 연결이 끊겼을 때 쓰는 것들.
 *
 * 연결이 끊기면 fetch 는 응답 없이 TypeError 를 던지고, 그 문구는 브라우저가
 * 정한 영어다(Chrome 은 "Failed to fetch"). 판 화면들은 오류의 message 를 그대로
 * 보여 주므로, 지하철에서 끊긴 채 답을 누르면 그 영어가 떴다. 여기서 사람이
 * 읽을 문구로 바꾼다.
 */

/** 연결이 끊겨 요청이나 응답이 실패했다. message 는 connectionLostMessage() 다. */
export class ConnectionLost extends Error {
  name = "ConnectionLost";
}

/**
 * fetch 와 같지만, 연결이 끊겨 실패하면 ConnectionLost 를 던진다.
 *
 * 대개는 요청이 서버에 닿기 전에 끊긴 것이라 판의 토큰이 아직 안 쓰였고,
 * 연결된 뒤 같은 보기를 다시 누르면 이어진다. 서버에 닿아 처리된 뒤 응답만
 * 끊긴 경우도 같은 TypeError 라 여기서는 가를 수 없다. 그때 다시 누르면 서버가
 * "이미 처리한 답입니다" 로 거절한다.
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
 * 답하기 요청이면 다시 눌러도 서버가 "이미 처리한 답입니다" 로 거절한다.
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
