import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-4 py-10">
      <h1 className="text-4xl font-bold text-slate-900 dark:text-slate-100">
        devvoca
      </h1>
      <p className="mt-3 text-lg text-slate-600 dark:text-slate-400">
        개발하면서 마주치는 영어, 하나씩 익혀봅니다.
      </p>

      <div className="mt-8">
        <Link
          href="/vocab"
          className="inline-block rounded-md bg-slate-900 px-5 py-2.5 font-medium text-white transition hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
        >
          단어장 보기
        </Link>
      </div>
    </main>
  );
}
