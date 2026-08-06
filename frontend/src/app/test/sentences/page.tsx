import Link from "next/link";

import { LearnHeader } from "@/components/LearnHeader";
import { contentPath } from "@/lib/routes";

export const metadata = {
  title: "문장 문제풀기 | devvoca",
  description: "문장 문제는 준비 중입니다.",
};

/**
 * 아직 만들지 않은 화면.
 *
 * 콘텐츠 탭에서 "문장" 을 누르면 여기로 온다. 페이지 자체가 없으면
 * 404 가 뜨는데, 탭이 보이는데 눌렀더니 404 인 것은 고장으로 읽힌다.
 * 준비 중이라고 알려주고 갈 곳을 준다.
 */
export default function TestSentencesPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <LearnHeader
        mode="test"
        content="sentences"
        title="문장 문제풀기"
        description="준비 중입니다."
      />

      <p className="mt-8 rounded-md border border-slate-200 p-6 text-center text-slate-500 dark:border-slate-800 dark:text-slate-400">
        문장 문제는 아직 만들지 않았습니다. 단어 문제부터 풀어보세요.
      </p>

      <div className="mt-6 flex flex-wrap gap-3">
        <Link
          href={contentPath("test", "words")}
          className="rounded-md bg-slate-900 px-4 py-2 font-medium text-white transition hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
        >
          단어 문제풀기
        </Link>
        <Link
          href={contentPath("learn", "sentences")}
          className="rounded-md border border-slate-300 px-4 py-2 font-medium text-slate-900 transition hover:border-slate-500 dark:border-slate-700 dark:text-slate-100 dark:hover:border-slate-500"
        >
          문장 익히기
        </Link>
      </div>
    </main>
  );
}
