import { NextResponse } from "next/server";

import { relayError } from "@/lib/api/relay";
import { answerReview, startReview } from "@/lib/api/review";
import { getToken } from "@/lib/session";

/**
 * 복습 중계.
 *
 * 이유는 /api/rounds/route.ts 첫머리와 같다 - 백엔드 주소는 서버 전용
 * 환경변수이고, 인증 토큰은 httpOnly 쿠키에 있어 브라우저 스크립트가
 * 읽을 수 없다. 그것을 꺼내 헤더에 붙이는 일은 여기서만 일어난다.
 *
 * 일일공부와 달리 시작에 딸린 값이 없다. 무엇을 낼지는 서버가 정한다 -
 * 무엇을 틀렸는지가 서버에 있기 때문이다.
 */

type Body = {
  action?: "start" | "answer";
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
      return NextResponse.json(await startReview(auth));
    }

    if (!body.token || typeof body.token !== "string") {
      return NextResponse.json(
        { detail: "판 정보가 없습니다." },
        { status: 400 },
      );
    }

    // 화면이 보낸 값이 정수가 아니면 백엔드까지 갈 것도 없이 막는다.
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
      await answerReview(auth, body.token, body.choice_id),
    );
  } catch (error) {
    return relayError(error);
  }
}
