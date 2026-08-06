import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { getQuestion, gradeAnswer } from "@/lib/api/quiz";

/**
 * 문제풀기 중계.
 *
 * 문제풀기 화면은 클라이언트 컴포넌트라 브라우저에서 API 를 부른다.
 * 그런데 백엔드 주소(API_URL)는 서버 전용 환경변수다 - 브라우저에
 * 노출하지 않는 것이 이 프로젝트의 규칙이고, 노출하면 CORS 설정도
 * 따로 열어야 한다.
 *
 * 그래서 브라우저는 여기(같은 출처)를 부르고, 실제 백엔드 호출은
 * Next 서버가 대신한다.
 */

/** 문제 받기. */
export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;

  try {
    const question = await getQuestion({
      category: params.get("category") ?? undefined,
      kind: params.get("kind") ?? undefined,
      exclude: params.get("exclude") ?? undefined,
    });
    return NextResponse.json(question);
  } catch (error) {
    return errorResponse(error);
  }
}

/** 채점. */
export async function POST(request: Request) {
  let body: { token?: string; picked?: number };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "잘못된 요청입니다." }, { status: 400 });
  }

  if (!body.token || typeof body.picked !== "number") {
    // 백엔드가 같은 상황에 쓰는 문구를 그대로 쓴다. 어느 쪽에서
    // 걸리든 사용자가 보는 말은 같아야 한다.
    return NextResponse.json(
      { detail: "문제 정보가 올바르지 않습니다. 새 문제를 받아주세요." },
      { status: 400 },
    );
  }

  try {
    const result = await gradeAnswer(body.token, body.picked);
    return NextResponse.json(result);
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
