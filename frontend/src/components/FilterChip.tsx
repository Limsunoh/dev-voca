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
    "relative after:absolute after:inset-x-0 after:-inset-y-[3px] after:content-['']";

  // 켜진 쪽에도 투명 테두리를 준다. 없으면 켜진 칩만 2px 낮아서 켜고 끌
  // 때마다 줄 높이가 흔들린다(ChoiceFilter 의 nav 는 items-center 라
  // stretch 로 가려지지도 않는다).
  const shape = `${hitArea} rounded-full border px-3.5 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus`;

  return (
    <Link
      href={href}
      // 선택된 항목은 색만으로 구분하지 않는다. 색각 이상이 있으면 구분이 안 된다.
      //
      // "page" 가 아니라 "true" 인 이유: 토글이 되면서 켜진 칩의 링크가
      // "그 조건을 뺀 주소" 를 가리키게 됐다. "page" 는 "이 링크가 지금 보고
      // 있는 페이지" 라는 뜻이라, 스크린리더가 "선택 해제, 현재 페이지" 로
      // 앞뒤가 안 맞게 읽는다. "true" 는 묶음 안의 현재 항목이라는 뜻이다.
      aria-current={active ? "true" : undefined}
      aria-label={ariaLabel}
      className={
        active
          ? `${shape} border-transparent bg-slate-100 text-slate-900`
          : `${shape} border-white/40 text-slate-300 hover:border-white/60`
      }
    >
      {children}
    </Link>
  );
}
