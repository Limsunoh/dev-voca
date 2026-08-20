/**
 * 쓸 수 있는 배경. 유니온으로 두면 오타(surface-lern)가 컴파일에서 걸린다.
 * string 으로 두면 배경만 조용히 사라지고 아무도 모른다.
 */
export type Surface =
  | "surface-learn"
  | "surface-detail"
  | "surface-quiz"
  | "surface-profile";

/**
 * 화면 뒤에 깔리는 배경 레이어.
 *
 * 영역마다 다른 배경을 쓴다(단어·문장 / 문제풀이 / 내정보). 클래스 이름만
 * 바꿔 부르면 되도록 이 컴포넌트로 묶었다.
 *
 * fixed 인 이유가 둘이다.
 *
 * 1. 스크롤해도 배경이 제자리에 있다. 목록이 길어도 그라디언트가 같이
 *    밀려 올라가지 않는다.
 * 2. 아래 탭바가 루트 layout 소속이라 화면 안쪽 요소로는 그 자리를 못 덮는다.
 *    화면 전체를 덮어야 탭바까지 같은 배경 위에 앉는다.
 *
 * 주의: 이 레이어가 보이는 것은 <html> 에 배경이 없어서 <body> 의
 * bg-background 가 캔버스로 전파되기 때문이다. <html> 에 배경 클래스를
 * 붙이는 순간 body 배경이 이 레이어를 덮어 배경이 통째로 사라진다.
 */
export function SurfaceLayer({ variant }: { variant: Surface }) {
  return (
    // 장식이라 스크린리더에서 숨기고, 클릭도 통과시킨다.
    // surface-grain 을 같이 붙인다. 그라디언트만 있으면 다크 배경에서
    // 계단(밴딩)이 보이는데, 아주 옅은 노이즈가 그것을 흩는다.
    // 결을 이 레이어에 얹는 이유: 화면 요소마다 걸면 글자 위에도 노이즈가
    // 앉아 읽기가 나빠진다. 배경에만 둔다.
    <div
      aria-hidden
      className={`${variant} surface-grain pointer-events-none fixed inset-0 -z-10`}
    />
  );
}
