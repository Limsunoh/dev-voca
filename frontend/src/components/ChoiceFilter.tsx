import Link from "next/link";

import type { ChoiceOption } from "@/lib/api/client";

type Props = {
  /** 필터 줄 앞에 붙는 이름. 스크린리더용 라벨로도 쓴다. */
  label: string;
  /** URL 쿼리 키. 예: kind */
  paramName: string;
  options: ChoiceOption[];
  /** 링크를 만들 기준 경로. */
  basePath: string;
  /** 지금 선택된 값. 없으면 "전체". */
  selected?: string;
  /** 이 필터를 바꿔도 유지할 다른 조건들. */
  keep?: Record<string, string | undefined>;
};

/**
 * 선택지 하나를 고르는 필터 칩 줄.
 *
 * 링크로 만든 이유: 서버 컴포넌트라 자바스크립트 없이 동작하고, 필터 상태가
 * URL 에 남아 뒤로가기와 공유가 그대로 된다.
 *
 * page 는 일부러 빼고 만든다. 3페이지를 보다 조건을 바꾸면 결과가 3페이지도
 * 안 되는 경우가 많아 빈 화면이 뜬다.
 */
export function ChoiceFilter({
  label,
  paramName,
  options,
  basePath,
  selected,
  keep,
}: Props) {
  if (options.length === 0) return null;

  const href = (value?: string) => {
    const query = new URLSearchParams();
    for (const [key, kept] of Object.entries(keep ?? {})) {
      if (kept) query.set(key, kept);
    }
    if (value) query.set(paramName, value);
    const qs = query.toString();
    return qs ? `${basePath}?${qs}` : basePath;
  };

  return (
    <nav
      aria-label={`${label} 필터`}
      className="mt-4 flex flex-wrap items-center gap-2"
    >
      <span className="text-sm text-slate-500 dark:text-slate-400">
        {label}
      </span>
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
