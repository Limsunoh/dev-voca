import Link from "next/link";

import { routes } from "@/lib/routes";

// notFound() 가 호출되면 이 화면이 나온다. 없으면 Next 기본 영문 404 가 뜬다.
export default function SentenceNotFound() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-2xl font-bold text-slate-100">
        찾을 수 없습니다
      </h1>
      <p className="mt-2 text-slate-300">
        주소가 잘못되었거나, 아직 공개되지 않은 문장입니다.
      </p>

      <Link
        href={routes.sentences}
        className="mt-6 inline-flex min-h-12 items-center rounded-full bg-focus px-5 font-semibold text-focus-on transition active:translate-y-px focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        문장으로 돌아가기
      </Link>
    </main>
  );
}
