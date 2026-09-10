"use client"; // 에러 경계는 클라이언트 컴포넌트여야 한다.

import { useEffect } from "react";

/**
 * 예상 못 한 에러만 여기로 온다.
 *
 * 백엔드 연결 실패나 404 같은 "예상된 실패"는 page.tsx 안에서 처리한다.
 *
 * 주의: 두 번째 prop 이름은 Next 16 에서 reset 이 아니라 unstable_retry 다.
 */
export default function VocabError({
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
    <main className="mx-auto max-w-3xl px-4 py-10">
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
        단어를 불러오는 중 오류가 발생했습니다.
      </p>

      {/* 이 화면의 유일한 동작이라 코랄을 준다. */}
      <button
        type="button"
        onClick={() => unstable_retry()}
        className="dv-btn mt-6 inline-flex items-center rounded-full px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        style={
          {
            background: "var(--coral)",
            color: "var(--text-on-color)",
            border: 0,
            minHeight: "var(--hit-min)",
            fontWeight: "var(--weight-black)",
            letterSpacing: "var(--tracking-tight)",
            // 쉬는 두께는 --lift 로. 인라인 box-shadow 는 :active 를 이긴다.
            "--lift": "var(--lift-button)",
          } as React.CSSProperties
        }
      >
        다시 시도
      </button>
    </main>
  );
}
