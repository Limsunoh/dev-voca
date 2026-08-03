import Link from "next/link";

/**
 * 학습 콘텐츠 카드.
 *
 * 단어에 묶지 않는다 - 나중에 문장·에러 메시지가 같은 카드를 쓴다.
 * 그래서 props 가 term/meaning 이 아니라 title/subtitle 이다.
 */
export type LearningCardProps = {
  href: string;
  title: string;
  subtitle: string;
  /** 난이도 등 배지로 보일 짧은 문구. */
  badge?: string;
  /** 분류 같은 보조 라벨. */
  tag?: string;
};

export function LearningCard({
  href,
  title,
  subtitle,
  badge,
  tag,
}: LearningCardProps) {
  return (
    <Link
      href={href}
      className="group block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-slate-400 hover:shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-600"
    >
      <div className="flex items-start justify-between gap-3">
        <h2 className="font-mono text-lg font-semibold text-slate-900 group-hover:underline dark:text-slate-100">
          {title}
        </h2>
        {badge && (
          <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {badge}
          </span>
        )}
      </div>

      <p className="mt-1 text-slate-700 dark:text-slate-300">{subtitle}</p>

      {tag && (
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{tag}</p>
      )}
    </Link>
  );
}
