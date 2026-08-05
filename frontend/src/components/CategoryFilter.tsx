import Link from "next/link";

import type { CategoryOption } from "@/lib/api/vocab";

type Props = {
  options: CategoryOption[];
  /** 지금 선택된 분류. 없으면 "전체". */
  selected?: string;
  /** 분류를 바꿔도 유지할 검색어. */
  search?: string;
  /** 분류를 바꿔도 유지할 난이도. */
  difficulty?: string;
};

/**
 * 분류 필터 버튼 줄.
 *
 * 링크로 만든 이유: 서버 컴포넌트라 자바스크립트 없이 동작하고, 필터 상태가
 * URL 에 남아 뒤로가기와 공유가 그대로 된다.
 *
 * page 는 일부러 빼고 만든다. 3페이지를 보다 분류를 바꾸면 결과가 3페이지도
 * 안 되는 경우가 많아 빈 화면이 뜬다.
 */
export function CategoryFilter({
  options,
  selected,
  search,
  difficulty,
}: Props) {
  if (options.length === 0) return null;

  // 분류 외의 조건은 그대로 들고 간다. 여기서 빠뜨리면 분류를 바꾸는 순간
  // 다른 필터가 조용히 풀린다(Pagination 은 유지하므로 규칙도 어긋난다).
  const href = (category?: string) => {
    const query = new URLSearchParams();
    if (search) query.set("search", search);
    if (difficulty) query.set("difficulty", difficulty);
    if (category) query.set("category", category);
    const qs = query.toString();
    return qs ? `/vocab?${qs}` : "/vocab";
  };

  return (
    <nav aria-label="분류 필터" className="mt-4 flex flex-wrap gap-2">
      <Chip href={href()} active={!selected}>
        전체
      </Chip>
      {options.map((option) => (
        <Chip
          key={option.value}
          href={href(option.value)}
          active={selected === option.value}
        >
          {option.label}
        </Chip>
      ))}
    </nav>
  );
}

function Chip({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      // 선택된 항목은 색만으로 구분하지 않는다. 색각 이상이 있으면 구분이 안 된다.
      aria-current={active ? "page" : undefined}
      className={
        active
          ? "rounded-full bg-slate-900 px-3 py-1 text-sm text-white dark:bg-slate-100 dark:text-slate-900"
          : "rounded-full border border-slate-200 px-3 py-1 text-sm text-slate-600 hover:border-slate-400 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-500"
      }
    >
      {children}
    </Link>
  );
}
