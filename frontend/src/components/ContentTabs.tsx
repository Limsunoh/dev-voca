import Link from "next/link";

import { contentPath, contents } from "@/lib/routes";

/**
 * 한 모드 안에서 콘텐츠를 오가는 탭(단어 / 문장).
 *
 * 모드(익히기·문제풀기)는 아래 탭바가 맡고 이건 콘텐츠 축이다. 나중에 에러 메시지나
 * 아티클이 생기면 routes 의 contents 에 추가한다.
 *
 * 링크에 mode 를 반드시 넣는다. /learn 으로 고정하면 /test/words 에서
 * "문장" 을 눌렀을 때 익히기로 튕긴다.
 */
export function ContentTabs({
  mode,
  current,
}: {
  /** 지금 모드의 slug. 링크가 이 모드 안에 머문다. */
  mode: string;
  /** 지금 콘텐츠의 slug. */
  current: string;
}) {
  return (
    // 세그먼트. 옅은 띠 안에서 흰 알약이 켜진 쪽으로 옮겨간다.
    //
    // 밑줄 탭(border-b)에서 갈아탔다. 밑줄은 아래에 한 줄을 긋는 문법인데,
    // 크림에서 아래 방향은 두께(그림자)가 쓰는 자리라 둘이 같은 화면에
    // 있으면 무엇이 경계이고 무엇이 선택인지 흐려진다.
    //
    // inline-flex 라 내용만큼만 넓어진다. 탭이 둘(단어·문장)뿐이라 화면
    // 폭을 다 먹으면 알약 하나가 화면 절반이 되어 과하다. 나중에 에러
    // 메시지가 붙어도 셋까지는 이 폭으로 들어간다.
    <nav
      aria-label="학습 콘텐츠"
      className="inline-flex gap-1 p-1"
      style={{
        background: "var(--background-deep)",
        borderRadius: "var(--radius-pill)",
      }}
    >
      {contents.map((content) => {
        const active = content.slug === current;

        return (
          <Link
            key={content.slug}
            href={contentPath(mode, content.slug)}
            aria-current={active ? "page" : undefined}
            // after 로 히트영역을 44px 까지 넓힌다. 알약 자체를 키우면
            // 세그먼트가 두꺼워져 제목 줄과 균형이 깨지는데, 눌리는 넓이는
            // 보이는 넓이와 달라도 된다. FilterChip 이 같은 자리에서 같은
            // 방법을 쓴다.
            className="relative rounded-full px-4 py-2 text-sm after:absolute after:inset-x-0 after:-inset-y-1 after:content-[''] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            style={
              active
                ? {
                    background: "var(--paper)",
                    color: "var(--foreground)",
                    boxShadow: "var(--lift-card)",
                    fontWeight: "var(--weight-black)",
                  }
                : {
                    // 꺼진 탭은 띠 위에 글자만 앉는다. 여기에도 종이를 깔면
                    // 켜진 것과 구분이 안 된다.
                    color: "var(--text-muted)",
                    fontWeight: "var(--weight-bold)",
                  }
            }
          >
            {content.label}
          </Link>
        );
      })}
    </nav>
  );
}
