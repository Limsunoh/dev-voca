import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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

export default nextConfig;
