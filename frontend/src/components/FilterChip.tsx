import Link from "next/link";

/**
 * 필터 줄의 칩 하나.
 *
 * 분류 필터와 선택지 필터가 같은 것을 쓴다. 두 벌로 두면 한쪽만 고쳐지고
 * 같은 줄에 선 칩들이 서로 다르게 보인다.
 *
 * 버튼이 아니라 링크인 이유: 필터 상태가 URL 에 남아야 뒤로가기와 공유가
 * 그대로 되고, 자바스크립트 없이도 동작한다.
 */
export function FilterChip({
  href,
  active,
  ariaLabel,
  children,
}: {
  href: string;
  active: boolean;
  /** 스크린리더용 문구. 없으면 보이는 글자를 그대로 읽는다. */
  ariaLabel?: string;
  children: React.ReactNode;
}) {
  // 보이는 크기는 그대로 두고 누를 수 있는 영역만 넓힌다. 알약을 키우면
  // 필터 줄이 세 개인 화면(문장)에서 첫 카드가 화면 밖으로 밀린다.
  // 38px + 위아래 3px = 44px. 칩 사이 간격이 8px 이라 이웃과 겹치지 않는다.
  const hitArea =
    // -inset-y-1(4px)이면 36px 알약이 44px 로 잡힌다. 3px 이던 것을 올렸다 -
    // 42px 이라 한 칸이 모자랐고, 그 2px 은 재보기 전까지 안 보인다.
    "relative after:absolute after:inset-x-0 after:-inset-y-1 after:content-['']";

  // 테두리를 버렸다. 크림에서는 꺼진 칩도 흰 종이 + 두께로 서 있고, 켜지면
  // 잉크로 채워진다(번들 forms/FilterChip.jsx). 다크에서 켜짐·꺼짐을 채움
  // 유무로 갈랐던 것과 방향은 같고, 꺼진 쪽이 "테두리만" 이 아니라
  // "얇은 종이" 가 됐다.
  //
  // 켜진 칩에도 두께가 있어 높이가 어긋나지 않는다. 다크에서 투명 테두리를
  // 넣어 맞췄던 문제가 여기서는 저절로 사라진다 - 둘 다 padding 이 같고
  // 그림자는 자리를 안 먹는다.
  const shape = `dv-card dv-card-press ${hitArea} inline-flex items-center rounded-full px-3.5 py-2 text-sm font-[weight:var(--weight-bold)] whitespace-nowrap focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus`;

  return (
    <Link
      href={href}
      // 선택된 항목은 색만으로 구분하지 않는다. 색각 이상이 있으면 구분이 안 된다.
      // 크림에서는 채움이 반전되므로(흰 바탕 -> 잉크 바탕) 명도 차가 그 역할을
      // 한다 - 흑백으로 인쇄해도 켜진 칩이 보인다.
      //
      // "page" 가 아니라 "true" 인 이유: 토글이 되면서 켜진 칩의 링크가
      // "그 조건을 뺀 주소" 를 가리키게 됐다. "page" 는 "이 링크가 지금 보고
      // 있는 페이지" 라는 뜻이라, 스크린리더가 "선택 해제, 현재 페이지" 로
      // 앞뒤가 안 맞게 읽는다. "true" 는 묶음 안의 현재 항목이라는 뜻이다.
      aria-current={active ? "true" : undefined}
      aria-label={ariaLabel}
      className={shape}
      style={
        active
          ? ({
              background: "var(--foreground)",
              color: "var(--background)",
              // --lift-dark 를 안 쓴다. 그건 4px 이고 이 칩은 카드 규칙
              // (dv-card dv-card-press, 3px)으로 내려앉아서, 그대로 두면 눌렀을 때
              // 1px 이 남아 바닥에 안 닿는다. 진하기만 --lift-dark 에서
              // 가져오고 거리는 3px 로 맞춘다.
              // 쉬는 두께는 --lift 로 넘긴다. box-shadow 를 인라인으로 적으면
              // globals.css 의 :active 가 두께를 0 으로 만드는 것을 이겨버려서,
              // 칩이 두께를 단 채 3px 내려가 바닥을 뚫은 것처럼 보인다.
              "--lift": "var(--lift-dark-card)",
            } as React.CSSProperties)
          : ({
              background: "var(--paper)",
              color: "var(--text-muted)",
              "--lift": "var(--lift-card)",
            } as React.CSSProperties)
      }
    >
      {children}
    </Link>
  );
}
