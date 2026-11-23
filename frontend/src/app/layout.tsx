import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Noto_Sans_KR } from "next/font/google";
import { connection } from "next/server";

import { ServiceWorkerRegister } from "@/components/ServiceWorkerRegister";
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
// weight 를 명시한다. 안 적으면 가변 축이 있는 글꼴만 전 구간을 받고,
// Noto Sans KR 처럼 정적 웨이트로 배포되는 글꼴은 400 하나만 온다. 크림
// 디자인은 제목이 전부 900 이라 그것이 없으면 브라우저가 400 을 굵게
// 흉내내고(가짜 볼드), 한글에서 획이 뭉개진다.
const notoSansKr = Noto_Sans_KR({
  variable: "--font-noto-kr",
  subsets: ["latin"],
  weight: ["400", "500", "700", "900"],
  display: "swap",
});

const jetBrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "DeVoca",
  description: "개발할 때 마주치는 영어를 익히는 학습 서비스",
};

// themeColor: 모바일 브라우저가 주소창을 화면 색에 맞춰 칠하게 한다. 없으면
// 크림 화면 위에 회색 주소창이 남아 앱처럼 보이지 않는다.
//
// colorScheme: globals.css 에도 color-scheme: light 가 있지만 그건 스타일시트가
// 파싱된 뒤에야 적용된다. 여기 두면 head 의 meta 로 먼저 나가서 첫 페인트의
// 색 번쩍임이 없어진다.
export const viewport: Viewport = {
  themeColor: "#fff6e9",
  colorScheme: "light",
  // 이게 없으면 iOS 가 safe-area env() 를 전부 0 으로 준다. 아래 탭바가
  // safe-area 만큼 띄우도록 짜여 있는데 그 여백이 전부 0 이 되어,
  // 아이폰 홈 인디케이터가 탭 라벨 위에 겹친다.
  viewportFit: "cover",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // 모든 화면을 요청 때 그린다. CSP 의 nonce 는 요청마다 바뀌어서(proxy.ts) 빌드 때 미리
  // 만든 화면에는 붙지 않고, 그러면 그 화면의 스크립트가 전부 막힌다. 대부분의 화면은
  // 로그인 쿠키를 읽어 원래 요청 때 그렸고, 미리 만들던 것은 처리방침·약관·계정 삭제
  // 안내와 없는 주소 화면뿐이었다. Next 16 문서는 route segment config 의 dynamic 대신
  // 이것을 권한다(dynamic 은 cacheComponents 를 켜면 빌드 오류가 난다). 지우면 빌드와
  // 테스트는 초록인 채 그 화면들만 운영에서 죽는다. proxy.test.mts 가 이 줄을 지킨다.
  // 화면 파일에 dynamic = "force-static" 을 두면 그 화면에서는 이 줄이 아무 일도 안 한다.
  await connection();
  return (
    <html
      lang="ko"
      className={`${notoSansKr.variable} ${jetBrainsMono.variable} h-full antialiased`}
    >
      {/* 탭바가 가리는 만큼의 여백은 여기가 아니라 TabBar 자신이 만든다.
          여기에 두면 탭바가 없는 화면(문제풀이·로그인)에도 5.5rem 이 남아,
          게임 화면 아래에 아무것도 없는 띠가 생긴다. 탭바가 자기 자리를
          스스로 비우면 숨는 조건이 늘어도 여기를 같이 고칠 일이 없다. */}
      <body className="flex min-h-full flex-col bg-background font-sans text-foreground">
        {children}
        <TabBar />
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
