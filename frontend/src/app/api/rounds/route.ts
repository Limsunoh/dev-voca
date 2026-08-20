import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { answerRound, finishRound, startRound } from "@/lib/api/rounds";
import { getToken } from "@/lib/session";

/**
 * 문제풀이 한 판 중계.
 *
 * 이유는 /api/quiz/route.ts 첫머리와 같다 - 백엔드 주소는 서버 전용
 * 환경변수라 브라우저에 노출하지 않는다.
 *
 * 여기서 한 가지가 더 있다. **인증 토큰도 서버에서만 붙인다.** 토큰은
 * httpOnly 쿠키에 있어 브라우저 스크립트가 읽을 수 없고, 그것을 꺼내
 * Authorization 헤더에 넣는 일은 이 라우트에서만 일어난다.
 *
 * 동작 세 가지를 한 라우트에서 처리한다(action 으로 갈림). 파일을 셋으로
 * 나누면 토큰 꺼내기와 오류 변환이 세 번 복사된다.
 */

type Body = {
  action?: "start" | "answer" | "finish";
  token?: string;
  choice_id?: number | null;
  skip?: boolean;
};

export async function POST(request: Request) {
  let body: Body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "잘못된 요청입니다." }, { status: 400 });
  }

  // 본문이 객체가 아니면 아래 접근이 원시값에 붙는다. JSON 문자열
  // 하나만 보내도 여기까지 온다.
  if (!body || typeof body !== "object") {
    return NextResponse.json({ detail: "잘못된 요청입니다." }, { status: 400 });
  }

  // **먼저 action 을 본다.** 뒤로 미루면 오타 난 action 이 아래 토큰
  // 검사에 먼저 걸려 "판 정보가 없습니다" 라는 엉뚱한 문구를 받는다.
  if (!["start", "answer", "finish"].includes(body.action ?? "")) {
    return NextResponse.json({ detail: "잘못된 요청입니다." }, { status: 400 });
  }

  // 로그인 안 해도 풀 수 있다. 없으면 기록만 안 된다.
  const auth = (await getToken()) ?? undefined;

  try {
    if (body.action === "start") {
      return NextResponse.json(await startRound(auth));
    }

    // 아래 둘은 판 토큰이 있어야 한다. 없으면 백엔드까지 갈 것도 없다.
    if (!body.token || typeof body.token !== "string") {
      return NextResponse.json(
        { detail: "판 정보가 없습니다." },
        { status: 400 },
      );
    }

    if (body.action === "answer") {
      const skip = body.skip === true;
      // bool 은 number 가 아니지만, 화면이 보낸 값이 숫자가 아닐 때
      // null 로 눌러두면 백엔드가 "보기를 고르거나 넘겨주세요" 로 받는다.
      const choice =
        typeof body.choice_id === "number" && Number.isInteger(body.choice_id)
          ? body.choice_id
          : null;

      if (!skip && choice === null) {
        return NextResponse.json(
          { detail: "보기를 고르거나 넘겨주세요." },
          { status: 400 },
        );
      }
      return NextResponse.json(
        await answerRound(body.token, choice, skip, auth),
      );
    }

    if (body.action === "finish") {
      return NextResponse.json(await finishRound(body.token, auth));
    }
  } catch (error) {
    return errorResponse(error);
  }

  return NextResponse.json({ detail: "잘못된 요청입니다." }, { status: 400 });
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
