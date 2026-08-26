import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { ReviewBoard } from "@/components/ReviewBoard";
import { ApiError } from "@/lib/api/client";
import { fetchDue } from "@/lib/api/review";
import { routes } from "@/lib/routes";
import { getToken } from "@/lib/session";

export const metadata: Metadata = {
  title: "다시 보기 · devvoca",
  description: "틀린 것과 오래된 것을 다시 풉니다.",
};

/**
 * 복습.
 *
 * **로그인이 필요하다.** 무엇을 틀렸는지가 계정에 쌓여야 하는 기능이라
 * 게스트에게는 목록이 만들어질 자리가 없다.
 */
export default async function ReviewPage() {
  const token = await getToken();
  if (!token) redirect(`/login?next=${routes.testReview}`);

  let due;
  try {
    due = await fetchDue(token);
  } catch (error) {
    const offline = error instanceof ApiError && error.status === 0;
    return (
      <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-5 py-8 text-center">
        <p className="text-slate-200">복습을 불러오지 못했습니다.</p>
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
      <ReviewBoard due={due} />
    </main>
  );
}
