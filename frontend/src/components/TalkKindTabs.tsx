import Link from "next/link";

import {
  routes,
  type TalkKind,
  type TalkLevel,
  type TalkScene,
} from "@/lib/routes";

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
  scene,
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
  /**
   * 지금 고른 상황. 난이도와 같이 넘기지만 개발 용어로 가는 링크에서는
   * routes.talk 가 뺀다 - 개발 용어에는 상황이 없다.
   */
  scene: TalkScene;
}) {
  return (
    <TalkTabRow
      label="읽을 갈래"
      items={KINDS.map((kind) => ({
        key: kind.slug,
        href: routes.talk(kind.slug, level, scene),
        label: kind.label,
        active: kind.slug === current,
      }))}
    />
  );
}

/**
 * 말하기 화면의 알약 탭 한 줄. 갈래(여기)·난이도(TalkLevelTabs)·
 * 상황(TalkSceneTabs)이 같이 쓴다.
 *
 * 바로 위아래에 붙어 서는 세 줄이라 따로 그리면 한쪽만 고쳤을 때 모양이
 * 어긋난다. 그리는 곳을 하나로 두고 각 탭은 무엇을 늘어놓을지만 정한다.
 */
export function TalkTabRow({
  label,
  items,
  wrap = false,
}: {
  label: string;
  items: { key: string | number; href: string; label: string; active: boolean }[];
  /**
   * 폭이 모자라면 줄을 바꾼다. 상황 탭(여섯 개)이 쓴다.
   *
   * 모서리를 알약(9999px)이 아니라 "한 줄 높이의 절반" 으로 둔다. 두 줄이
   * 된 바탕에 알약 모서리를 주면 양 끝이 반원으로 부풀어 첫 칸과 끝 칸이
   * 둥근 벽에 눌려 보인다. 한 줄 높이는 칸(--hit-floor) + 위아래 p-1 이라
   * 그 절반이면 한 줄일 때 곧 알약이어서 다른 두 줄과 모양이 같다. 26px
   * 같은 고정값으로 두면 글자 크기를 키운 브라우저에서 칸만 커지고
   * 모서리는 그대로라 한 줄인데도 알약이 아니게 된다.
   */
  wrap?: boolean;
}) {
  return (
    <nav
      aria-label={label}
      className={`${wrap ? "flex flex-wrap" : "inline-flex"} gap-1 p-1`}
      style={{
        background: "var(--background-deep)",
        borderRadius: wrap
          ? "calc(var(--hit-floor) / 2 + 0.25rem)"
          : "var(--radius-pill)",
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
