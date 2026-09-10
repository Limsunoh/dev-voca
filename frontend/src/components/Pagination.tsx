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

  // 흰 알약 + 두께. 목록 맨 아래에 홀로 놓이는 버튼이라 코랄을 쓰지 않는다 -
  // 한 화면에 코랄은 하나뿐이고, 그 자리는 검색 버튼이 갖는다.
  //
  // 최소 높이 44px(--hit-floor). 다크에서는 py-1.5(30px)라 터치 대상에
  // 못 미쳤는데, 목록 맨 아래에서 엄지로 누르는 자리라 이번에 맞춘다.
  const linkClass =
    "dv-btn inline-flex items-center px-4 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

  const linkStyle = {
    background: "var(--paper)",
    color: "var(--foreground)",
    borderRadius: "var(--radius-pill)",
    // 쉬는 두께는 --lift 로 넘긴다. box-shadow 를 인라인으로 적으면
    // globals.css 의 :active 가 두께를 0 으로 만드는 것을 이겨버린다.
    "--lift": "var(--lift-button-paper)",
    minHeight: "var(--hit-floor)",
    fontWeight: "var(--weight-black)",
  } as React.CSSProperties;

  return (
    <nav
      aria-label="페이지 이동"
      className="mt-8 flex items-center justify-between"
    >
      {hasPrevious ? (
        <Link
          href={hrefFor(currentPage - 1)}
          className={linkClass}
          style={linkStyle}
        >
          이전
        </Link>
      ) : (
        <span />
      )}

      {/* tabular-nums: 페이지를 넘길 때 숫자 폭이 달라지면 가운데 글자가
          좌우로 흔들린다(1 과 4 의 폭이 다르다). */}
      <span
        className="text-sm tabular-nums"
        style={{ color: "var(--text-muted)", fontWeight: "var(--weight-bold)" }}
      >
        {currentPage} 페이지
      </span>

      {hasNext ? (
        <Link
          href={hrefFor(currentPage + 1)}
          className={linkClass}
          style={linkStyle}
        >
          다음
        </Link>
      ) : (
        <span />
      )}
    </nav>
  );
}
