import { NextResponse } from "next/server";

import { fetchTalkQuestion, gradeTalk } from "@/lib/api/talk";
import type { TalkKind } from "@/lib/routes";
import { ApiError } from "@/lib/api/client";
import { getToken } from "@/lib/session";

/**
 * 소리내어 읽기 중계.
 *
 * 이유는 /api/rounds/route.ts 첫머리와 같다 - 백엔드 주소는 서버 전용
 * 환경변수이고, 인증 토큰은 httpOnly 쿠키에 있어 브라우저 스크립트가
 * 읽을 수 없다. 그것을 꺼내 헤더에 붙이는 일은 여기서만 일어난다.
 *
 * **로그인을 요구하지 않는다.** 점수가 안 남는 연습이라 계정에 쌓일 것이
 * 없다. 게스트도 발음을 연습할 수 있어야 한다 - 이 기능은 처음 온 사람의
 * 두려움을 줄이려는 것이라 로그인 뒤로 숨기면 정작 필요한 사람이 못 만난다.
 * 토큰이 있으면 실어 보내고, 없으면 없는 대로 부른다.
 */

type Body = {
  action?: "start" | "grade";
  kind?: string;
  /** 최근에 낸 것. 같은 것이 연달아 나오지 않게 뺀다. */
  exclude?: unknown;
  token?: string;
  heard?: unknown;
};

/** 후보 상한. 서버도 5개까지만 보므로 여기서 잘라 보낸다. */
const MAX_HEARD = 5;

/**
 * 후보 하나의 글자 상한.
 *
 * 서버가 100자를 넘으면 400 을 주고 **자르지 않는다**. 인식기가 긴 문장을
 * 통째로 뱉는 경우가 있어서(사용자가 계속 말하면) 여기서 걸러야 원인 모를
 * 400 이 안 난다. 넘는 것은 자르지 말고 버린다 - 잘라 보내면 사용자가
 * 말하지 않은 것으로 채점된다.
 */
const MAX_HEARD_CHARS = 100;

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
  // 걸려 원인과 무관한 문구를 받는다(/api/daily 와 같은 판단).
  if (!["start", "grade"].includes(body.action ?? "")) {
    return NextResponse.json({ detail: "잘못된 요청입니다." }, { status: 400 });
  }

  const auth = (await getToken()) ?? undefined;

  try {
    if (body.action === "start") {
      const kind: TalkKind = body.kind === "dev" ? "dev" : "daily";
      // 정수만 통과시킨다. 그대로 이어 붙이면 쿼리에 아무 글자나 실린다.
      const exclude = Array.isArray(body.exclude)
        ? body.exclude.filter(
            (x): x is number => typeof x === "number" && Number.isInteger(x),
          )
        : [];
      return NextResponse.json(
        await fetchTalkQuestion(kind, { exclude, token: auth }),
      );
    }

    if (typeof body.token !== "string" || !body.token) {
      return NextResponse.json(
        { detail: "판 정보가 없습니다." },
        { status: 400 },
      );
    }

    // 배열이 아니거나 글자가 아닌 것이 섞여 오면 걸러낸다. 백엔드까지
    // 갈 것도 없고, 거기서 막히면 원인이 안 보이는 500 이 된다.
    const heard = Array.isArray(body.heard)
      ? body.heard
          .filter(
            (x): x is string =>
              typeof x === "string" &&
              x.trim() !== "" &&
              // 100자를 넘는 것은 버린다. 자르면 사용자가 말하지 않은
              // 것으로 채점되고, 그냥 보내면 서버가 400 을 준다.
              x.trim().length <= MAX_HEARD_CHARS,
          )
          .slice(0, MAX_HEARD)
      : [];

    return NextResponse.json(
      await gradeTalk({ token: body.token, heard }, auth),
    );
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json(
        { detail: error.message },
        { status: error.status || 502 },
      );
    }
    return NextResponse.json(
      { detail: "잠시 후 다시 시도해주세요." },
      { status: 502 },
    );
  }
}
