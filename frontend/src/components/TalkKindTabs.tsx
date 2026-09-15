import Link from "next/link";

import { routes, type TalkKind, type TalkLevel } from "@/lib/routes";

/**
 * 일상 표현 / 개발 용어를 오가는 탭.
 *
 * **전역 콘텐츠 축(ContentTabs)을 안 쓴다.** 그쪽의 `contents` 는 모드와
 * 무관한 목록이라 거기에 한 줄 더하면 익히기·문제풀기에도 같은 탭이 생긴다.
 * `/learn/daily` 는 만든 적이 없으니 눌리는 순간 빈 화면이다. 이 축은 이
 * 모드 안에서만 돌아서 여기서 따로 그린다.
 *
 * 모양은 ContentTabs 와 같게 둔다 - 같은 자리에서 같은 일을 하는 탭이
 * 화면마다 다르게 생기면 그때부터 규칙이 아니라 우연이 된다.
 */
export function TalkKindTabs({
  current,
  level,
}: {
  current: TalkKind;
  /**
   * 지금 고른 난이도. 갈래를 바꿔도 들고 간다.
   *
   * 안 들고 가면 난이도 탭은 갈래를 기억하는데 갈래 탭은 난이도를 잊는다.
   * 두 줄이 나란히 서 있는데 한 줄만 상대 축을 기억하면, 사용자는 어느
   * 쪽을 누를 때 무엇이 풀리는지 외워야 한다.
   */
  level: TalkLevel;
}) {
  return (
    <TalkTabRow
      label="읽을 갈래"
      items={KINDS.map((kind) => ({
        key: kind.slug,
        href: routes.talk(kind.slug, level),
        label: kind.label,
        active: kind.slug === current,
      }))}
    />
  );
}

/**
 * 말하기 화면의 알약 탭 한 줄. 갈래(여기)와 난이도(TalkLevelTabs)가 같이 쓴다.
 *
 * 바로 위아래에 붙어 서는 두 줄이라 따로 그리면 한쪽만 고쳤을 때 모양이
 * 어긋난다. 그리는 곳을 하나로 두고 두 탭은 무엇을 늘어놓을지만 정한다.
 */
export function TalkTabRow({
  label,
  items,
}: {
  label: string;
  items: { key: string | number; href: string; label: string; active: boolean }[];
}) {
  return (
    <nav
      aria-label={label}
      className="inline-flex gap-1 p-1"
      style={{
        background: "var(--background-deep)",
        borderRadius: "var(--radius-pill)",
      }}
    >
      {items.map((item) => (
        <Link
          key={item.key}
          href={item.href}
          aria-current={item.active ? "page" : undefined}
          className="flex items-center px-4 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={{
            minHeight: "var(--hit-floor)",
            borderRadius: "var(--radius-pill)",
            // 켜진 쪽만 흰 알약이 된다. 두께(그림자)로 떠 보이게 해서
            // 눌린 것과 안 눌린 것을 색이 아니라 높이로 가른다.
            background: item.active ? "var(--paper)" : "transparent",
            boxShadow: item.active ? "var(--lift-card)" : "none",
            color: item.active ? "var(--foreground)" : "var(--text-muted)",
            fontWeight: item.active
              ? "var(--weight-black)"
              : "var(--weight-bold)",
          }}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}

const KINDS: { slug: TalkKind; label: string }[] = [
  { slug: "daily", label: "일상 표현" },
  { slug: "dev", label: "개발 용어" },
];
