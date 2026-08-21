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
    const offline = error instanceof ApiError && error.status === 0;
    return (
      <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-5 py-8 text-center">
        <p className="text-slate-200">일일공부를 불러오지 못했습니다.</p>
        <p className="mt-1 text-sm text-slate-500">
          {offline
            ? "서버에 연결할 수 없습니다. 잠시 뒤 다시 시도해주세요."
            : "잠시 뒤 다시 시도해주세요."}
        </p>
        <div className="mt-6">
          <Link
            href={routes.home}
            className="inline-flex min-h-11 items-center rounded-full border border-white/40 px-5 text-sm font-medium text-slate-100 transition-[scale,border-color] duration-[120ms] ease-press hover:border-white/60 active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
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
