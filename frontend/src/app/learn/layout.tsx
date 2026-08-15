/**
 * 단어·문장 영역의 배경.
 *
 * 배경을 여기(영역 layout)에 두는 이유는 두 가지다.
 *
 * 1. 화면마다 배경이 다르다. 문제풀이와 내정보는 각자 다른 배경을 갖는다.
 *    루트 layout 에 하나만 두면 영역을 구분할 수 없다.
 * 2. 머리말(SiteHeader)은 루트 layout 이 그리므로 이 layout 바깥에 있다.
 *    화면 안쪽에만 배경을 깔면 머리말 자리만 다른 색으로 남는다.
 *    fixed 레이어로 화면 전체를 덮어야 머리말까지 같은 배경 위에 앉는다.
 *
 * fixed 라서 스크롤해도 배경은 제자리에 있다. 목록이 길어도 그라디언트가
 * 같이 밀려 올라가지 않는다.
 *
 * 주의: 이 레이어가 보이는 것은 <html> 에 배경이 없기 때문이다. 그래서
 * <body> 의 bg-background 가 캔버스로 전파되어 음수 z-index 자식보다 먼저
 * 칠해진다. <html> 에 배경 클래스를 붙이는 순간 body 배경이 이 레이어를
 * 덮어 배경이 통째로 사라진다.
 */
export default function LearnLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      {/* 장식이라 스크린리더에서 숨기고, 클릭도 통과시킨다. */}
      <div
        aria-hidden
        className="surface-learn pointer-events-none fixed inset-0 -z-10"
      />
      {children}
    </>
  );
}
