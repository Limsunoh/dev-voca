import Link from "next/link";

/**
 * 이전/다음 링크.
 *
 * 백엔드가 준 next/previous 절대 URL 을 그대로 쓰지 않는다 - 그러면 API 주소가
 * 화면에 노출된다. 우리가 아는 필터만 유지한 채 page 만 바꿔 붙인다.
 * (searchParams 를 통째로 넘기면 URL 에 낀 임의의 키까지 링크마다 따라다닌다.)
 */
export function Pagination({
  basePath,
  filters,
  currentPage,
  hasPrevious,
  hasNext,
}: {
  /** 링크를 만들 기준 경로. 단어장·문장 등 쓰는 화면마다 다르다. */
  basePath: string;
  filters: Record<string, string | undefined>;
  currentPage: number;
  hasPrevious: boolean;
  hasNext: boolean;
}) {
  if (!hasPrevious && !hasNext) return null;

  function hrefFor(page: number): string {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value) query.set(key, value);
    }
    if (page > 1) query.set("page", String(page));

    const qs = query.toString();
    return qs ? `${basePath}?${qs}` : basePath;
  }

  const linkClass =
    "rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:border-slate-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-500";

  return (
    <nav
      aria-label="페이지 이동"
      className="mt-8 flex items-center justify-between"
    >
      {hasPrevious ? (
        <Link href={hrefFor(currentPage - 1)} className={linkClass}>
          이전
        </Link>
      ) : (
        <span />
      )}

      <span className="text-sm text-slate-500 dark:text-slate-400">
        {currentPage} 페이지
      </span>

      {hasNext ? (
        <Link href={hrefFor(currentPage + 1)} className={linkClass}>
          다음
        </Link>
      ) : (
        <span />
      )}
    </nav>
  );
}
