import Link from "next/link";

import { ContentTabs } from "@/components/ContentTabs";
import { ModeTabs } from "@/components/ModeTabs";

/**
 * 학습 화면 공통 머리말.
 *
 * 모드 탭(익히기/문제풀기/말하기)과 콘텐츠 탭(단어/문장)을 함께 둔다.
 * 화면마다 따로 만들면 탭이 하나 늘어날 때 모든 화면을 고쳐야 한다.
 */
export function LearnHeader({
  mode,
  content,
  title,
  description,
}: {
  /** 지금 모드의 slug. 예: learn */
  mode: string;
  /** 지금 콘텐츠의 slug. 예: words */
  content: string;
  title: string;
  description: string;
}) {
  return (
    <header>
      <Link
        href="/"
        className="text-sm text-slate-500 hover:underline dark:text-slate-400"
      >
        devvoca
      </Link>

      <div className="mt-3">
        <ModeTabs current={mode} content={content} />
      </div>

      <div className="mt-4">
        <ContentTabs mode={mode} current={content} />
      </div>

      <h1 className="mt-6 text-2xl font-bold text-slate-900 dark:text-slate-100">
        {title}
      </h1>
      <p className="mt-1 text-slate-600 dark:text-slate-400">{description}</p>
    </header>
  );
}
