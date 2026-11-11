"use client"; // 에러 경계는 클라이언트 컴포넌트여야 한다.

import { useEffect } from "react";

/**
 * 루트 layout 까지 깨졌을 때 뜨는 화면.
 *
 * `error.tsx` 는 루트 layout 을 감싸지 못한다. 탭바나 글꼴 설정처럼 layout 에
 * 있는 것이 실패하면 여기로 온다. 이 파일이 없으면 Next 기본 화면이 영어로
 * 뜬다.
 *
 * layout 을 대신하므로 html·body 를 직접 그리고, globals.css 와 글꼴도 오지
 * 않는다(Next 문서 error.js 의 global-error). 그래서 색을 토큰이 아니라 값으로
 * 적는다. 값은 globals.css 의 --background, --foreground, --text-muted, --paper,
 * --brand, --brand-deep, --text-on-color, --lift-button-paper 와 같다. 그쪽을 바꾸면 여기도 같이 고친다.
 *
 * 탭바가 없으므로 나가는 길을 둘 둔다. "다시 시도" 는 그 자리에서 다시
 * 그리고, "홈으로" 는 Link 가 아니라 a 라서 페이지를 통째로 새로 받는다.
 * 배포 직후 옛 파일이 남아 깨진 경우처럼 다시 그려도 같은 오류가 나는 때는
 * 새로 받는 쪽이 살린다. layout 에서 실패할 만한 것(TabBar 처럼 경로에 따라
 * 갈리는 것)은 특정 경로에서만 깨질 수 있어서 홈은 열릴 수 있다.
 *
 * viewport meta 를 직접 둔다. 루트 layout 의 viewport 설정으로 만든 meta 는
 * layout 과 함께 사라지고, 없으면 폰이 980px 폭으로 그려 글자가 아주 작아진다.
 *
 * 주의: 두 번째 prop 이름은 Next 16 에서 reset 이 아니라 unstable_retry 다.
 */
export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="ko">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "40px 16px",
          boxSizing: "border-box",
          background: "#fff6e9",
          color: "#191512",
          fontFamily: "system-ui, sans-serif",
          textAlign: "center",
          // 한글이 낱말 가운데서 끊기지 않게(globals.css 의 keep-all 이 여기 안 온다).
          wordBreak: "keep-all",
        }}
      >
        {/* metadata 를 못 쓰는 파일이라 title 을 직접 둔다. 서비스 이름은
            넣지 않는다 - JSX 글자로 이름을 적지 않는 규칙(brand-name 테스트)이
            있고, BrandName 은 title 안에 못 들어간다(title 은 글자만 받는다). */}
        <title>문제가 생겼습니다</title>
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, viewport-fit=cover"
        />
        <h1 style={{ margin: 0, fontSize: "1.5rem", fontWeight: 900 }}>
          문제가 생겼습니다
        </h1>
        <p style={{ margin: "8px 0 0", color: "#706557" }}>
          화면을 불러오지 못했습니다. 잠시 뒤 다시 시도해주세요.
        </p>
        <button
          type="button"
          onClick={() => unstable_retry()}
          style={{
            marginTop: 24,
            minHeight: 52,
            padding: "0 20px",
            border: 0,
            borderRadius: 9999,
            background: "#683a24",
            color: "#ffffff",
            // 아래 두께와 글자 크기는 error.tsx 의 갈색 버튼과 같게.
            // --lift-button 과 globals.css 의 강조 버튼 19px 규칙이 여기 안 온다.
            boxShadow: "0 4px 0 #4a2817",
            font: "inherit",
            fontSize: 19,
            fontWeight: 900,
            cursor: "pointer",
          }}
        >
          다시 시도
        </button>
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- 일부러
            페이지를 통째로 새로 받는다. 위 머리 주석. */}
        <a
          href="/"
          style={{
            marginTop: 12,
            minHeight: 52,
            display: "inline-flex",
            alignItems: "center",
            padding: "0 20px",
            borderRadius: 9999,
            background: "#ffffff",
            color: "#191512",
            // 흰 알약은 크림 바탕과 거의 같아(1.07:1) 아래 두께가 "버튼" 을
            // 말한다. error.tsx 의 --lift-button-paper 와 같은 값.
            boxShadow: "0 4px 0 rgb(25 21 18 / 0.14)",
            fontWeight: 900,
            textDecoration: "none",
          }}
        >
          홈으로
        </a>
      </body>
    </html>
  );
}
