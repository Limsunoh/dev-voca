import { withSentryConfig } from "@sentry/nextjs/config";
import type { NextConfig } from "next";

// CSP 는 여기 없다. 요청마다 nonce 가 바뀌어 proxy.ts 가 화면 응답에만 싣는다(lib/csp.ts).
// 여기에 고정 정책을 더하면 응답에 정책이 둘이 되고, 브라우저는 둘 다 지켜서 nonce 가 없는
// 쪽이 화면 스크립트를 전부 막는다.
const SECURITY_HEADERS = [
  // 다른 사이트의 iframe 안에 로그인·문제풀기를 띄우지 못하게 한다. CSP 의
  // frame-ancestors 와 같은 일이지만, 그것을 모르는 브라우저와 CSP 가 안 붙는 경로(api 등)를 덮는다.
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // 말하기 연습(MicCheck, TalkBoard)이 마이크를 쓴다. 비우면 그 화면이 죽는다.
  { key: "Permissions-Policy", value: "microphone=(self)" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  experimental: {
    serverActions: {
      // 프로필 사진은 서버 액션으로 올린다. 기본 한도 1MB 를 넘으면 화면이
      // 통째로 죽는데 폰 사진은 대부분 그보다 크다. 화면이 4MB 에서 먼저
      // 막으므로(ProfileForm) multipart 경계만큼만 여유를 뒀다.
      bodySizeLimit: "5mb",
    },
  },
  async redirects() {
    return [
      // 단어장 경로를 두 번 옮겼다. /vocab -> /learn/vocab -> /learn/words.
      //
      // 마지막 이름이 words 인 이유는 모드가 늘어나기 때문이다. /test/words,
      // /talk/words 가 생겼을 때 콘텐츠 이름이 모드마다 다르면(vocab vs words)
      // 경로만 보고 무엇을 다루는지 알 수 없다.
      //
      // permanent: true 는 308 이다. 브라우저와 검색엔진이 새 주소를
      // 기억하므로, 나중에 이 규칙을 지우면 그때 캐시된 사용자만 깨진다.
      // 경로를 다시 옮길 일이 없다고 확신할 때까지 두는 편이 안전하다.
      {
        source: "/vocab",
        destination: "/learn/words",
        permanent: true,
      },
      {
        source: "/vocab/:id",
        destination: "/learn/words/:id",
        permanent: true,
      },
      // 배포된 적은 없지만 이 브랜치를 보던 사람이 열어둔 탭이 있을 수 있다.
      {
        source: "/learn/vocab",
        destination: "/learn/words",
        permanent: true,
      },
      {
        source: "/learn/vocab/:id",
        destination: "/learn/words/:id",
        permanent: true,
      },
    ];
  },
};

// 빌드할 때 소스맵을 Sentry 에 올려 폰 화면 오류를 원래 코드 줄로 본다. 올린 뒤에는
// 배포물에서 지운다(deleteSourcemapsAfterUpload 기본값). SENTRY_AUTH_TOKEN 은 Vercel 의
// Production 에만 있어서, 로컬과 CI 빌드는 올리지 않고 그대로 끝난다.
export default withSentryConfig(nextConfig, {
  org: "lim-sun-oh",
  project: "devvoca-frontend",
  authToken: process.env.SENTRY_AUTH_TOKEN,
  widenClientFileUpload: true,
  // 서버 라이브러리를 빌드 때 자동 계측하는 기능(성능 측정용)이다. 우리는 오류만 받는다.
  // 켜 두면 .next 안에 패키지 바로가기(junction)를 만드는데, 이 저장소가 있는 D: 는
  // exFAT 이라 바로가기를 못 만들어 로컬 next build 가 Turbopack 오류로 멈춘다.
  buildTimeInstrumentation: false,
  telemetry: false,
  silent: !process.env.CI,
});
