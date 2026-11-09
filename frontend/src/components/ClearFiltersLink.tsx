import Link from "next/link";

/**
 * 목록의 조건을 모두 지우는 링크.
 *
 * 필터 상자가 접혀 있어도 보이는 자리에 둔다. 조건을 좁히다 결과가 없거나
 * 주소의 조건값이 틀렸을 때 바로 풀 수 있어야 한다.
 */
export function ClearFiltersLink({ href }: { href: string }) {
  return (
    <Link
      href={href}
      className="dv-btn mt-4 inline-flex min-h-11 items-center rounded-full px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      style={
        {
          background: "var(--paper)",
          color: "var(--foreground)",
          fontSize: "var(--text-sm)",
          fontWeight: "var(--weight-black)",
          // 쉬는 두께는 --lift 로. 인라인 box-shadow 는 :active 를 이긴다.
          "--lift": "var(--lift-button-paper)",
        } as React.CSSProperties
      }
    >
      조건 지우기
    </Link>
  );
}
