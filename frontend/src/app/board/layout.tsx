import { SurfaceLayer } from "@/components/SurfaceLayer";

/**
 * 순위표 영역의 배경.
 *
 * 학습 화면(청록)과 색을 달리 두는 이유는 globals.css 의 surface-board
 * 주석에 있다.
 */
export default function BoardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <SurfaceLayer variant="surface-board" />
      {children}
    </>
  );
}
