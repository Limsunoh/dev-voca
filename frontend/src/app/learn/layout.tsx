import { SurfaceLayer } from "@/components/SurfaceLayer";

/**
 * 단어·문장 영역의 배경.
 *
 * 배경을 루트가 아니라 영역 layout 에 두는 이유: 화면마다 배경이 다르다.
 * 문제풀이와 내정보는 각자 다른 배경을 갖는다. 루트에 하나만 두면 영역을
 * 구분할 수 없다.
 *
 * 레이어가 fixed 인 이유와 주의점은 SurfaceLayer 에 적어뒀다.
 */
export default function LearnLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <SurfaceLayer variant="surface-learn" />
      {children}
    </>
  );
}
