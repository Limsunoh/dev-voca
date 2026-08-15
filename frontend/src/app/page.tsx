import Link from "next/link";

import { routes } from "@/lib/routes";

export default function Home() {
  // flex-1 로 남은 높이를 채운다. min-h-screen 을 쓰면 위에 놓인
  // 머리말 높이만큼 화면을 넘어가 스크롤이 생긴다.
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-4 py-10">
      <h1 className="text-4xl font-bold text-slate-900 dark:text-slate-100">
        devvoca
      </h1>
      <p className="mt-3 text-lg text-slate-600 dark:text-slate-400">
        개발하면서 마주치는 영어, 하나씩 익혀봅니다.
      </p>

      <div className="mt-8 flex flex-wrap gap-3">
        <Link
          href={routes.words}
          className="inline-block rounded-md bg-slate-900 px-5 py-2.5 font-medium text-white transition hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
        >
          단어장 보기
        </Link>
        <Link
          href={routes.sentences}
          className="inline-block rounded-md border border-slate-300 px-5 py-2.5 font-medium text-slate-900 transition hover:border-slate-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus dark:border-slate-700 dark:text-slate-100 dark:hover:border-slate-500"
        >
          문장 보기
        </Link>
      </div>
    </main>
  );
}
