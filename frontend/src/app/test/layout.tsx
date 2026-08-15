import { SurfaceLayer } from "@/components/SurfaceLayer";

/**
 * 문제풀이 영역의 배경.
 *
 * layout 에 두면 /test/words 와 /test/sentences 가 한 벌을 쓴다. 화면마다
 * 넣으면 문제 유형이 늘 때 빠뜨린다.
 */
export default function TestLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <SurfaceLayer variant="surface-quiz" />
      {children}
    </>
  );
}
