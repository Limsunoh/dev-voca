import type { MetadataRoute } from "next";

/**
 * 앱 설치 정보. Next 가 /manifest.webmanifest 로 내보내고 모든 화면에 링크를 단다.
 *
 * Google Play 의 Android 앱은 이 웹을 Chrome 이 감싼 것(TWA)이다. 껍데기를 만드는
 * Bubblewrap 이 이 파일에서 이름·색·아이콘을 읽어 간다. 여기를 바꾸면 껍데기를
 * 다시 만들어야 앱의 홈 화면 아이콘과 첫 화면이 바뀐다.
 *
 * 아이콘 셋은 public/icons 에 있다. 글자 없는 "dv" 앱 아이콘(512px)에서 만들었다.
 * 그 그림을 바꾸면 이 셋도 다시 만든다. maskable 은 런처가 원이나 둥근 사각형으로
 * 잘라도 되게 정사각형 전체를 크림으로 채우고, 마크만 떼어 가운데 80% 안에 둔 것이다.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "DeVoca",
    short_name: "DeVoca",
    description: "개발할 때 마주치는 영어를 익히는 학습 앱",
    lang: "ko",
    start_url: "/",
    scope: "/",
    display: "standalone",
    // 앱이 뜨는 순간의 바탕과 위쪽 상태 표시줄 색. layout.tsx 의 themeColor,
    // globals.css 의 --background 와 같은 값이다.
    background_color: "#fff6e9",
    theme_color: "#fff6e9",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
