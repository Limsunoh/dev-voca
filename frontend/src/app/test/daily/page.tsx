import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { DailyStudyBoard } from "@/components/DailyStudyBoard";
import { ApiError } from "@/lib/api/client";
import { fetchDailyStatus } from "@/lib/api/daily";
import { routes } from "@/lib/routes";
import { getToken } from "@/lib/session";

export const metadata: Metadata = {
  title: "일일공부 · devvoca",
  description: "하루 한 번, 길이를 골라 공부합니다.",
};

/**
 * 일일공부.
 *
 * **로그인이 필요하다.** 진행이 서버에 남아야 이어서 풀 수 있는 기능이라
 * 게스트에게는 이어 볼 자리가 없다. 90초 한 판이 게스트를 받는 것과 다르다.
 */
export default async function DailyPage() {
  const token = await getToken();
  if (!token) redirect(`/login?next=${routes.testDaily}`);

  let status;
  try {
    status = await fetchDailyStatus(token);
  } catch (error) {
    // 서버가 쿠키의 토큰을 거절했으면(다른 기기에서 로그아웃 등) 로그인
    // 화면으로 보낸다. 아래 실패 화면을 띄우면 "잠시 뒤 다시 시도해주세요"
    // 가 되는데, 다시 해도 안 풀리는 막다른 화면이었다(오답 노트도 401 이면
    // 로그인으로 보낸다). 로그인 확인을 먼저 하지 않는 이유: 로그인한 사람의
    // 화면 로딩에 백엔드 왕복이 하나 순서대로 늘어난다.
    //
    // catch 안에서 redirect 를 부른다. redirect 는 예외로 동작하니, 이
    // 블록을 다시 try 로 감싸면 그 catch 가 이것을 삼킨다.
    if (error instanceof ApiError && error.status === 401) {
      redirect(`/login?next=${routes.testDaily}`);
    }
    const offline = error instanceof ApiError && error.status === 0;
    return (
      <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-5 py-8 text-center">
        <p
          style={{
            fontWeight: "var(--weight-black)",
            letterSpacing: "var(--tracking-tight)",
            color: "var(--foreground)",
          }}
        >
          일일공부를 불러오지 못했습니다.
        </p>
        <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
          {offline
            ? "서버에 연결할 수 없습니다. 잠시 뒤 다시 시도해주세요."
            : "잠시 뒤 다시 시도해주세요."}
        </p>
        <div className="mt-6">
          {/* 여기서 갈 곳은 홈뿐이라 이 화면의 코랄 하나다. 되돌아가는
              동작이지만 다른 선택지가 없으면 그것이 주된 동작이다. */}
          <Link
            href={routes.home}
            className="dv-btn inline-flex items-center px-6 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            style={
              {
                minHeight: "var(--hit-min)",
                background: "var(--coral)",
                color: "var(--text-on-color)",
                borderRadius: "var(--radius-pill)",
                fontWeight: "var(--weight-black)",
                "--lift": "var(--lift-button)",
              } as React.CSSProperties
            }
          >
            홈으로
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col px-5 py-8">
      <DailyStudyBoard status={status} />
    </main>
  );
}
