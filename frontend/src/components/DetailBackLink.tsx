"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

type HistoryEntries = {
  currentEntry: { index: number } | null;
  entries(): { url: string | null }[];
};

/**
 * 바로 앞 방문 기록이 이 주소인지 본다. 알 수 없으면 false.
 *
 * Navigation API 가 없는 브라우저도 있다. 그때는 링크로 가서 목록 맨 위에서
 * 시작하는 지금까지의 동작이 된다.
 */
export function isPreviousEntry(
  href: string,
  navigation: HistoryEntries | undefined,
): boolean {
  const index = navigation?.currentEntry?.index ?? -1;
  if (index < 1) return false;

  const previous = navigation?.entries()[index - 1]?.url;
  // about:blank 같은 주소는 목록일 수 없고, 기준 주소로도 못 쓴다.
  if (!previous?.startsWith("http")) return false;

  // 쿼리 순서는 만드는 곳마다 달라서 정렬해 비교한다. 칩은 고른 값을 맨
  // 뒤에 붙이고, 카드의 돌아올 주소는 정해진 순서로 만든다.
  const before = new URL(previous);
  const target = new URL(href, before.origin);
  before.searchParams.sort();
  target.searchParams.sort();
  return (
    before.pathname + before.search === target.pathname + target.search
  );
}

/**
 * 상세에서 목록으로 돌아가는 링크.
 *
 * 바로 앞 기록이 그 목록이면 뒤로가기로 돌아간다. 링크로 이동하면 브라우저가
 * 스크롤을 복원하지 않아, 스무 장 중 아홉 번째 카드를 보고 돌아온 사람이 맨
 * 위에서 다시 찾아야 한다.
 *
 * 앞 기록을 확인하는 이유: 공유받은 상세 주소를 열었으면 뒤로가기는 앱 밖으로
 * 나간다. 그럴 때는 링크로 목록에 간다.
 */
export function DetailBackLink({
  href,
  className,
  style,
  children,
}: {
  href: string;
  className: string;
  style: React.CSSProperties;
  children: React.ReactNode;
}) {
  const router = useRouter();

  return (
    <Link
      href={href}
      className={className}
      style={style}
      onClick={(event) => {
        // 새 탭으로 여는 누름은 브라우저에 맡긴다.
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
          return;
        }
        const { navigation } = window as unknown as {
          navigation?: HistoryEntries;
        };
        if (isPreviousEntry(href, navigation)) {
          event.preventDefault();
          router.back();
        }
      }}
    >
      {children}
    </Link>
  );
}
