import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Noto_Sans_KR } from "next/font/google";

import { SiteHeader } from "@/components/SiteHeader";
import "./globals.css";

// 화면에 한글(뜻·설명)과 라틴(용어·코드)이 항상 같이 나온다. 라틴 전용 글꼴만
// 물리면 한글이 OS 기본 글꼴로 떨어져 두 글자체가 따로 논다. 그래서 한글을
// 포함하는 본문 글꼴과 코드용 고정폭 글꼴을 나눠 지정한다.
//
// 둘 다 가변 글꼴(variable)이라 굵기마다 파일을 따로 받지 않는다. 한글은
// 유니코드 구간별로 잘게 쪼개져 있어서, 굵기별 정적 글꼴을 쓰면 받아야 할
// 파일이 몇 배로 늘어난다.
//
// subsets 는 "받을 글리프"가 아니라 "preload 로 미리 당길 구간"을 정한다.
// 한글 글리프는 subsets 에 없어도 함께 자체 호스팅되며, 브라우저가
// unicode-range 를 보고 필요한 구간만 내려받는다. 한글 구간을 전부 preload
// 하면 첫 화면에 쓰지도 않을 파일을 수백 개 당기게 되므로 latin 만 둔다.
const notoSansKr = Noto_Sans_KR({
  variable: "--font-noto-kr",
  subsets: ["latin"],
  display: "swap",
});

const jetBrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "devvoca",
  description: "개발할 때 마주치는 영어를 익히는 학습 서비스",
};

// themeColor: 모바일 브라우저가 주소창을 화면 색에 맞춰 칠하게 한다. 없으면
// 어두운 화면 위에 흰 주소창이 남아 앱처럼 보이지 않는다.
//
// colorScheme: globals.css 에도 color-scheme: dark 가 있지만 그건 스타일시트가
// 파싱된 뒤에야 적용된다. 여기 두면 head 의 meta 로 먼저 나가서 첫 페인트의
// 흰 번쩍임이 없어진다.
export const viewport: Viewport = {
  themeColor: "#0b1017",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ko"
      // dark 는 고정이다. globals.css 의 @custom-variant 설명 참고.
      className={`dark ${notoSansKr.variable} ${jetBrainsMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-background font-sans text-foreground">
        <SiteHeader />
        {children}
      </body>
    </html>
  );
}
