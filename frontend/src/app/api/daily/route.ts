import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { answerDaily, startDaily } from "@/lib/api/daily";
import { getToken } from "@/lib/session";

/**
 * 일일공부 중계.
 *
 * 이유는 /api/rounds/route.ts 첫머리와 같다 - 백엔드 주소는 서버 전용
 * 환경변수이고, 인증 토큰은 httpOnly 쿠키에 있어 브라우저 스크립트가
 * 읽을 수 없다. 그것을 꺼내 헤더에 붙이는 일은 여기서만 일어난다.
 *
 * 자유 문제풀이와 다른 점: **로그인이 없으면 아예 막는다.** 진행이
 * 서버에 남아야 하는 기능이라 게스트에게는 이어 볼 자리가 없다.
 */

type Body = {
  action?: "start" | "answer";
  length?: string;
  token?: string;
  choice_id?: number | null;
};

export async function POST(request: Request) {
  let body: Body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "잘못된 요청입니다." }, { status: 400 });
  }

  if (!body || typeof body !== "object") {
    return NextResponse.json({ detail: "잘못된 요청입니다." }, { status: 400 });
  }

  // **먼저 action 을 본다.** 뒤로 미루면 오타 난 action 이 아래 검사에
  // 걸려 원인과 무관한 문구를 받는다.
  if (!["start", "answer"].includes(body.action ?? "")) {
    return NextResponse.json({ detail: "잘못된 요청입니다." }, { status: 400 });
  }

  const auth = await getToken();
  if (!auth) {
    return NextResponse.json(
      { detail: "로그인이 필요합니다." },
      { status: 401 },
    );
  }

  try {
    if (body.action === "start") {
      if (typeof body.length !== "string" || !body.length) {
        return NextResponse.json(
          { detail: "길이를 골라주세요." },
          { status: 400 },
        );
      }
      return NextResponse.json(await startDaily(body.length, auth));
    }

    if (!body.token || typeof body.token !== "string") {
      return NextResponse.json(
        { detail: "판 정보가 없습니다." },
        { status: 400 },
      );
    }

    // bool 은 number 의 하위가 아니지만, 화면이 보낸 값이 정수가 아니면
    // 백엔드까지 갈 것도 없이 막는다.
    if (
      typeof body.choice_id !== "number" ||
      !Number.isInteger(body.choice_id)
    ) {
      return NextResponse.json(
        { detail: "보기를 골라주세요." },
        { status: 400 },
      );
    }

    return NextResponse.json(
      await answerDaily(body.token, body.choice_id, auth),
    );
  } catch (error) {
    return errorResponse(error);
  }
}

/**
 * 백엔드 오류를 그대로 흘려보낸다.
 *
 * 상태 코드를 200 으로 뭉개면 화면이 "문제 없음" 으로 착각한다.
 * 다만 백엔드 주소나 스택은 담지 않는다.
 */
function errorResponse(error: unknown) {
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
