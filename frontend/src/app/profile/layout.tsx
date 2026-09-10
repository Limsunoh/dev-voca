import type { Viewport } from "next";

// 크림 한 겹이라 화면마다 다른 themeColor 를 둘 이유가 없어졌다. 이 파일이
// 남은 것은 루트(#fff6e9)와 같은 값을 다시 적기 위해서가 아니라, 다크였을
// 때 여기서 덮어쓰던 값(#17140f)을 확실히 지우기 위해서다 - 안 지우면 이
// 화면에서만 모바일 주소창이 검게 남는다.
//
// 루트와 같아지는 순간 이 파일은 필요 없다. 지워도 부모 값이 그대로 온다.
export const viewport: Viewport = {
  themeColor: "#fff6e9",
};

export default function ProfileLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
