import Link from "next/link";

import { routes } from "@/lib/routes";

/**
 * 없는 순위표 종류.
 *
 * 이 파일이 없으면 Next 기본 영문 404 가 뜬다 - 한글 화면 한가운데
 * 영어 문구가 나온다. learn/words 와 learn/sentences 가 같은 이유로
 * 각자 두고 있다.
 */
export default function BoardNotFound() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center px-4 py-10 text-center">
      <p className="text-slate-300">그런 순위표는 없습니다.</p>
      <p className="mt-1 text-sm text-slate-500">
        이번 주, 전체, 꾸준함 세 가지가 있습니다.
      </p>
      <div className="mt-6">
        <Link
          href={routes.board()}
          className="inline-flex min-h-11 items-center rounded-lg border border-white/12 px-5 text-sm font-medium text-slate-200 transition hover:border-white/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          순위표로
        </Link>
      </div>
    </main>
  );
}
