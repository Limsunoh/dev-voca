import type { Viewport } from "next";

import { SurfaceLayer } from "@/components/SurfaceLayer";

// 이 화면만 배경이 따뜻해서 루트의 themeColor(차가운 잉크)와 어긋난다.
// 이음매가 생기는 자리가 하필 화면 맨 위, 배경이 가장 따뜻한 지점 바로
// 위라서 모바일 주소창에 띠가 보인다.
export const viewport: Viewport = {
  themeColor: "#17140f",
};

/** 내정보 영역의 배경. */
export default function ProfileLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <SurfaceLayer variant="surface-profile" />
      {children}
    </>
  );
}
