import Link from "next/link";

import { contentPath, contents } from "@/lib/routes";

/**
 * 한 모드 안에서 콘텐츠를 오가는 탭(단어 / 문장).
 *
 * 모드(익히기·문제풀기)는 아래 탭바가 맡고 이건 콘텐츠 축이다. 나중에 에러 메시지나
 * 아티클이 생기면 routes 의 contents 에 추가한다.
 *
 * 링크에 mode 를 반드시 넣는다. /learn 으로 고정하면 /test/words 에서
 * "문장" 을 눌렀을 때 익히기로 튕긴다.
 */
export function ContentTabs({
  mode,
  current,
}: {
  /** 지금 모드의 slug. 링크가 이 모드 안에 머문다. */
  mode: string;
  /** 지금 콘텐츠의 slug. */
  current: string;
}) {
  return (
    <nav
      aria-label="학습 콘텐츠"
      className="flex gap-1 border-b border-white/12"
    >
      {contents.map((content) => {
        const active = content.slug === current;

        return (
          <Link
            key={content.slug}
            href={contentPath(mode, content.slug)}
            aria-current={active ? "page" : undefined}
            className={
              active
                ? "-mb-px border-b-2 border-slate-100 px-4 py-2 text-sm font-medium text-slate-100"
                : "-mb-px border-b-2 border-transparent px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
            }
          >
            {content.label}
          </Link>
        );
      })}
    </nav>
  );
}
