import { SurfaceLayer } from "@/components/SurfaceLayer";

/**
 * 상세 화면의 배경.
 *
 * 목록(surface-learn)과 다른 배경을 쓴다. 목록은 층을 흩어 훑어보기 좋게
 * 하고, 상세는 단색으로 두어 하나에 집중하게 한다.
 *
 * 부모(learn/layout.tsx)도 배경을 깔지만 이 레이어가 뒤에 그려져 위에
 * 얹힌다. 아래 것이 가려지는 만큼은 낭비지만, 배경을 각 화면이 직접
 * 선언하게 만들면 error·not-found 처럼 나중에 생기는 화면에서 빠뜨린다
 * (실제로 한 번 그렇게 네 화면이 배경을 잃었다). layout 에 두면 그
 * 세그먼트 아래 모든 화면이 자동으로 받는다.
 */
export default function DetailLayoutRoute({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <SurfaceLayer variant="surface-detail" />
      {children}
    </>
  );
}
