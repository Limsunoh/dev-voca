import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Noto_Sans_KR } from "next/font/google";

import { TabBar } from "@/components/TabBar";
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
  // 이게 없으면 iOS 가 safe-area env() 를 전부 0 으로 준다. 아래 탭바가
  // safe-area 만큼 띄우도록 짜여 있는데 그 방어가 통째로 무효가 되어,
  // 아이폰 홈 인디케이터가 탭 라벨 위에 겹친다.
  viewportFit: "cover",
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
      {/* 탭바가 가리는 만큼의 여백은 여기가 아니라 TabBar 자신이 만든다.
          여기에 두면 탭바가 없는 화면(문제풀이·로그인)에도 5rem 이 남아,
          게임 화면 아래에 아무것도 없는 띠가 생긴다. 탭바가 자기 자리를
          스스로 비우면 숨는 조건이 늘어도 여기를 같이 고칠 일이 없다. */}
      <body className="flex min-h-full flex-col bg-background font-sans text-foreground">
        {children}
        <TabBar />
      </body>
    </html>
  );
}
