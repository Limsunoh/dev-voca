"use client"; // 에러 경계는 클라이언트 컴포넌트여야 한다.

import { useEffect } from "react";

import { HomeLink } from "@/components/HomeLink";

/**
 * 자기 error.tsx 가 없는 화면 전부의 마지막 방어선.
 *
 * 홈, 순위표, 일상영어, 내정보, 오답 노트처럼 가까운 error.tsx 가 없는 화면에서
 * 렌더가 실패하면 여기로 온다. 이 파일이 없으면 Next 기본 화면(영어로
 * "Application error")이 뜨고, 한국어 화면을 쓰던 사용자에게는 서비스가 죽은
 * 것으로 읽힌다. `learn/words`, `learn/sentences`, `test` 는 자기 것이 있어서
 * 그쪽이 이긴다.
 *
 * 루트 layout 은 감싸지 않는다(Next 문서 error.js). 그래서 탭바가 남고, 탭바가
 * 없는 문제 화면은 `test/error.tsx` 가 받는다. layout 자체가 깨진 경우는
 * `global-error.tsx` 가 받는다.
 *
 * 배치는 루트 `not-found.tsx` 를 따른다. 화면에 이것뿐이라 가운데에 둔다.
 * 버튼 둘은 `test/error.tsx` 와 같다 - 다시 시도가 갈색, 홈으로가 흰 알약.
 *
 * 주의: 두 번째 prop 이름은 Next 16 에서 reset 이 아니라 unstable_retry 다.
 */
export default function RootError({
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
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center px-4 py-10 text-center">
      <h1
        style={{
          fontSize: "var(--text-2xl)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
          color: "var(--foreground)",
        }}
      >
        문제가 생겼습니다
      </h1>
      <p className="mt-2" style={{ color: "var(--text-muted)" }}>
        화면을 불러오지 못했습니다. 잠시 뒤 다시 시도해주세요.
      </p>

      {/* flex-wrap: 글자를 200% 로 키우면 버튼 둘이 한 줄에 못 들어가는데,
          안 주면 줄바꿈 대신 화면 밖으로 밀린다. justify-center 는 위
          text-center 가 flex 자식에는 안 먹어서 따로 준다. */}
      <div className="mt-6 flex flex-wrap justify-center gap-2.5">
        <button
          type="button"
          onClick={() => unstable_retry()}
          className="dv-btn px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--brand)",
              color: "var(--text-on-color)",
              border: 0,
              borderRadius: "var(--radius-pill)",
              fontWeight: "var(--weight-black)",
              "--lift": "var(--lift-button)",
            } as React.CSSProperties
          }
        >
          다시 시도
        </button>
        <HomeLink
          className="dv-btn flex items-center justify-center px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--paper)",
              color: "var(--foreground)",
              borderRadius: "var(--radius-pill)",
              fontWeight: "var(--weight-black)",
              textDecoration: "none",
              "--lift": "var(--lift-button-paper)",
            } as React.CSSProperties
          }
        >
          홈으로
        </HomeLink>
      </div>
    </main>
  );
}
