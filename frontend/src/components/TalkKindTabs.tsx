import Link from "next/link";

import { routes, type TalkKind } from "@/lib/routes";

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
export function TalkKindTabs({ current }: { current: TalkKind }) {
  return (
    <nav
      aria-label="읽을 갈래"
      className="inline-flex gap-1 p-1"
      style={{
        background: "var(--background-deep)",
        borderRadius: "var(--radius-pill)",
      }}
    >
      {KINDS.map((kind) => {
        const active = kind.slug === current;

        return (
          <Link
            key={kind.slug}
            href={routes.talk(kind.slug)}
            aria-current={active ? "page" : undefined}
            className="flex items-center px-4 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            style={{
              minHeight: "var(--hit-floor)",
              borderRadius: "var(--radius-pill)",
              // 켜진 쪽만 흰 알약이 된다. 두께(그림자)로 떠 보이게 해서
              // 눌린 것과 안 눌린 것을 색이 아니라 높이로 가른다.
              background: active ? "var(--paper)" : "transparent",
              boxShadow: active ? "var(--lift-card)" : "none",
              color: active ? "var(--foreground)" : "var(--text-muted)",
              fontWeight: active
                ? "var(--weight-black)"
                : "var(--weight-bold)",
            }}
          >
            {kind.label}
          </Link>
        );
      })}
    </nav>
  );
}

const KINDS: { slug: TalkKind; label: string }[] = [
  { slug: "daily", label: "일상 표현" },
  { slug: "dev", label: "개발 용어" },
];
