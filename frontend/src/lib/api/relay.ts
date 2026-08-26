import { NextResponse } from "next/server";

import { ApiError } from "./client";

/**
 * 중계 라우트가 백엔드 오류를 화면으로 흘려보내는 방식.
 *
 * 상태 코드를 200 으로 뭉개면 화면이 "문제 없음" 으로 착각한다. 다만
 * 백엔드 주소나 스택은 담지 않는다 - 중계를 두는 이유 자체가 그것들을
 * 브라우저에 보이지 않게 하려는 것이다.
 *
 * 셋(rounds/daily/review)이 같은 처리를 하므로 한 곳에 둔다. 복사해두면
 * 한쪽만 고쳐져, 어떤 화면은 503 을 받고 어떤 화면은 500 을 받는다.
 */
export function relayError(error: unknown) {
  if (error instanceof ApiError) {
    // 0 은 연결 자체가 안 된 경우다. 그대로 쓰면 fetch 가 깨진다.
    const status = error.status === 0 ? 503 : error.status;
    return NextResponse.json({ detail: error.message }, { status });
  }
  return NextResponse.json(
    { detail: "알 수 없는 오류가 발생했습니다." },
    { status: 500 },
  );
}
