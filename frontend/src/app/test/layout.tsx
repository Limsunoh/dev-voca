import { EnterVeil } from "@/components/EnterVeil";
import { SurfaceLayer } from "@/components/SurfaceLayer";

/**
 * 문제풀이 영역의 배경과 진입 연출.
 *
 * layout 에 두면 /test 아래 화면들이 한 벌을 쓴다. 화면마다 넣으면 문제
 * 유형이 늘 때 빠뜨리고, 그때 배경 없는 화면이나 연출 없는 화면이 하나만
 * 생겨도 앱이 아니라 웹 페이지로 돌아간다.
 *
 * layout 은 같은 세그먼트 안에서 이동할 때 다시 마운트되지 않는다. 그래서
 * 진입 장막이 이 화면에 처음 들어올 때 한 번만 돈다 - 판이 진행되는 동안
 * 다시 떨어지지 않는다(EnterVeil 주석 참고). 그게 이 자리에 두는 이유다.
 *
 * 그 대가로 /test/words 에서 /test/round 로 갈 때도 장막이 안 돈다(실측:
 * 같은 DOM 요소가 유지된다). 연습에서 판으로 넘어가는 것은 무게가 다른
 * 이동이라 연출이 있는 편이 나을 수 있는데 지금은 없다. 필요해지면
 * /test/template.tsx 로 옮긴다 - template 은 세그먼트가 바뀔 때마다
 * 다시 마운트되므로 그 이동에서만 장막이 돌고, 판 안에서 단계가 바뀌는
 * 위 문제는 돌아오지 않는다.
 */
export default function TestLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <SurfaceLayer variant="surface-quiz" />
      <EnterVeil />
      {children}
    </>
  );
}
