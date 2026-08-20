import type { Metadata } from "next";
import Link from "next/link";

import { RoundBoard } from "@/components/RoundBoard";
import { routes } from "@/lib/routes";
import { getToken } from "@/lib/session";

export const metadata: Metadata = {
  title: "한 판 · devvoca",
  description: "90초 안에 몇 문제나 맞히는지. 점수가 순위표에 오릅니다.",
};

/**
 * 90초 한 판.
 *
 * 분류 필터가 없다. 판은 점수가 남는 승부라 낼 문제를 고를 수 있으면
 * 쉬운 분류만 골라 점수를 올릴 수 있다. 분류를 골라 연습하려면 옆의
 * 낱개 모드(/test/words)를 쓴다 - 그쪽은 점수가 안 남는다.
 */
export default async function RoundPage() {
  // 로그인 안 해도 풀 수 있다. 기록만 안 된다.
  const token = await getToken();

  return (
    // 세로 가운데. 시작 카드 하나뿐이라 위에 붙이면 데스크톱에서
    // 아래가 통째로 빈다. 판이 시작되면 내용이 길어져 자연히 위로 붙는다.
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center px-4 py-8">
      <div className="mb-5 flex items-center justify-between gap-3">
        <Link
          href={routes.testWords}
          className="min-h-11 rounded-lg px-2.5 py-2 text-sm text-slate-400 transition hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          연습 모드
        </Link>
        <Link
          href={routes.board()}
          className="min-h-11 rounded-lg px-2.5 py-2 text-sm text-slate-400 transition hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          순위표
        </Link>
      </div>

      <RoundBoard isGuest={!token} />
    </main>
  );
}
