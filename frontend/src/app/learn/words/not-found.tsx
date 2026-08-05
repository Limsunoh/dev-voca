import Link from "next/link";

import { routes } from "@/lib/routes";

// notFound() 가 호출되면 이 화면이 나온다. 없으면 Next 기본 영문 404 가 뜬다.
export default function VocabNotFound() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
        찾을 수 없습니다
      </h1>
      <p className="mt-2 text-slate-600 dark:text-slate-400">
        주소가 잘못되었거나, 아직 공개되지 않은 단어입니다.
      </p>

      <Link
        href={routes.words}
        className="mt-6 inline-block rounded-md bg-slate-900 px-4 py-2 font-medium text-white transition hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
      >
        단어장으로 돌아가기
      </Link>
    </main>
  );
}
