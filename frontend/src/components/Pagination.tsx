import Link from "next/link";

import { listUrl } from "@/lib/routes";

/**
 * 처음/이전/다음/끝 링크.
 *
 * 백엔드가 준 next/previous 절대 URL 을 그대로 쓰지 않는다 - 그러면 API 주소가
 * 화면에 노출된다. 우리가 아는 필터만 유지한 채 page 만 바꿔 붙인다.
 * (searchParams 를 전부 넘기면 URL 에 낀 임의의 키까지 링크마다 따라다닌다.)
 */
export function Pagination({
  basePath,
  filters,
  currentPage,
  hasPrevious,
  hasNext,
  count,
  pageLength,
}: {
  /** 링크를 만들 기준 경로. 단어장·문장 등 쓰는 화면마다 다르다. */
  basePath: string;
  filters: Record<string, string | undefined>;
  currentPage: number;
  hasPrevious: boolean;
  hasNext: boolean;
  /** 조건에 맞는 전체 개수. 있어야 전체 쪽수와 "끝" 을 보여줄 수 있다. */
  count?: number;
  /** 이 쪽에 실린 개수. */
  pageLength?: number;
}) {
  if (!hasPrevious && !hasNext) return null;

  // 한 쪽 크기를 프론트에 따로 적지 않는다. 다음 쪽이 있으면 이 쪽은 꽉 찬
  // 쪽이라 실린 개수가 곧 한 쪽 크기다. 다음 쪽이 없으면 지금이 마지막이다.
  // 백엔드의 쪽 크기를 복사해 두면 한쪽만 바뀌었을 때 쪽수가 틀린다.
  // 개수를 안 넘기는 화면은 쪽마다 표시가 달라지지 않게 전체 쪽수를 안 쓴다.
  const totalPages =
    count && pageLength
      ? hasNext
        ? Math.ceil(count / pageLength)
        : currentPage
      : undefined;

  // 목록 주소는 routes 의 listUrl 하나로 만든다. 카드의 되돌아올 주소도
  // 같은 함수를 쓰므로, 상세에서 돌아오면 여기서 만든 주소와 같은 목록이다.
  const hrefFor = (page: number) => listUrl(basePath, filters, page);

  // 흰 알약 + 두께. 목록 맨 아래에 홀로 놓이는 버튼이라 갈색을 쓰지 않는다 -
  // 한 화면에 갈색은 하나뿐이고, 그 자리는 검색 버튼이 갖는다.
  //
  // 최소 높이 44px(--hit-floor). py-1.5(30px)면 터치 대상에 못 미친다.
  // 목록 맨 아래에서 엄지로 누르는 자리라 맞춘다.
  const linkClass =
    "dv-btn inline-flex items-center px-3.5 text-sm whitespace-nowrap focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

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

  const pageLink = (page: number, label: string) => (
    <Link href={hrefFor(page)} className={linkClass} style={linkStyle}>
      {label}
    </Link>
  );

  return (
    // 양옆을 같은 폭으로 두어 가운데 쪽수가 쪽을 넘겨도 움직이지 않게 한다.
    // 양옆이 flex-1(바탕 0 에서 같은 비율로 늘어남)이라 한 줄에 들어갈 때는
    // 3칸 격자(1fr auto 1fr)와 같은 자리다.
    //
    // 한 줄에 안 들어가면 다음 줄로 넘긴다. 폰 글자 크기 200% 면 360폭 폰이
    // 180px 폭처럼 그려지는데, 가운데 쪽(처음·이전·쪽수·다음·끝이 다 있을
    // 때)은 한 줄이 약 280px 이다. 격자는 줄을 못 바꿔 화면이 그만큼 넓어졌고
    // 아래 탭바도 밀렸다.
    <nav
      aria-label="페이지 이동"
      className="mt-8 flex flex-wrap items-center justify-center gap-1.5"
    >
      {/* 2쪽에서 "처음" 은 "이전" 과 같은 곳이라 뺀다. "끝" 도 같다. */}
      <div className="flex flex-1 justify-start gap-1.5">
        {currentPage > 2 && pageLink(1, "처음")}
        {hasPrevious && pageLink(currentPage - 1, "이전")}
      </div>

      {/* tabular-nums: 페이지를 넘길 때 숫자 폭이 달라지면 가운데 글자가
          좌우로 흔들린다(1 과 4 의 폭이 다르다).

          20rem(320px) 보다 좁으면 쪽수를 첫 줄에 혼자 가운데로 올린다. 줄이
          꺾일 때 그냥 두면 1쪽은 오른쪽, 가운데 쪽은 왼쪽 하는 식으로 쪽마다
          자리가 바뀐다. 글자를 키운 화면에서만 걸리고 보통 폰(360px 이상)은
          그대로 한 줄이다. */}
      <span
        className="text-sm whitespace-nowrap tabular-nums max-[20rem]:order-first max-[20rem]:basis-full max-[20rem]:text-center"
        style={{ color: "var(--text-muted)", fontWeight: "var(--weight-bold)" }}
      >
        {totalPages ? `${currentPage} / ${totalPages}` : `${currentPage} 페이지`}
      </span>

      <div className="flex flex-1 justify-end gap-1.5">
        {hasNext && pageLink(currentPage + 1, "다음")}
        {totalPages !== undefined &&
          totalPages - currentPage > 1 &&
          pageLink(totalPages, "끝")}
      </div>
    </nav>
  );
}
