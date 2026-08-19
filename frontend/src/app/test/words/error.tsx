"use client"; // 에러 경계는 클라이언트 컴포넌트여야 한다.

import { useEffect } from "react";

/**
 * 예상 못 한 에러만 여기로 온다.
 *
 * 문제를 못 받거나 채점이 실패하는 "예상된 실패"는 QuizBoard 안에서
 * 문구와 버튼으로 처리한다.
 *
 * 주의: 두 번째 prop 이름은 Next 16 에서 reset 이 아니라 unstable_retry 다.
 */
export default function QuizError({
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
      <h1 className="text-2xl font-bold text-slate-100">문제가 생겼습니다</h1>
      <p className="mt-2 text-slate-300">
        문제풀기를 여는 중 오류가 발생했습니다.
      </p>

      <button
        type="button"
        onClick={() => unstable_retry()}
        className="mt-6 min-h-12 rounded-full bg-focus px-5 font-semibold text-focus-on transition-[scale] duration-[120ms] ease-press active:scale-[0.97] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        다시 시도
      </button>
    </main>
  );
}
