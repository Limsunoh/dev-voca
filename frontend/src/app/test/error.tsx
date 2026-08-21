"use client"; // 에러 경계는 클라이언트 컴포넌트여야 한다.

import Link from "next/link";
import { useEffect } from "react";

import { routes } from "@/lib/routes";

/**
 * 문제풀이 영역 전체의 마지막 방어선.
 *
 * **여기 있는 이유가 나가는 길 때문이다.** /test 아래 화면들은 탭바를
 * 숨기므로(routes 의 immersiveRoutes 참고) 나가는 문이 각 화면의
 * ExitGuard 하나뿐인데, 에러 경계는 그 화면을 통째로 갈아치운다. 그러면
 * 나가기 버튼도 같이 사라진다.
 *
 * 이게 없으면 /test/round 에서 렌더가 실패했을 때 Next 기본 에러 화면이
 * 뜨는데, 거기엔 홈 링크가 없고 탭바도 없다. 홈 화면에서 띄운 앱이면
 * 브라우저 뒤로가기 버튼조차 없어서 완전히 갇힌다.
 *
 * 세그먼트마다 두지 않고 여기 하나로 둔다. /test/words 처럼 더 가까운
 * error.tsx 가 있으면 그쪽이 이기고, 없는 화면은 이게 받는다. 문제 유형이
 * 늘어도 빠뜨릴 자리가 없다.
 *
 * 주의: 두 번째 prop 이름은 Next 16 에서 reset 이 아니라 unstable_retry 다.
 */
export default function TestError({
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

      {/* flex-wrap: 글자를 200% 로 키우면 버튼 둘이 한 줄에 못 들어가는데,
          안 주면 줄바꿈 대신 화면 밖으로 밀린다. */}
      <div className="mt-6 flex flex-wrap gap-2.5">
        <button
          type="button"
          onClick={() => unstable_retry()}
          className="min-h-12 flex-1 rounded-full bg-focus px-5 font-semibold text-focus-on transition-[scale] duration-[120ms] ease-press active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          다시 시도
        </button>
        {/* 테두리가 유일한 "여기가 버튼" 신호라 white/40 아래로 내리지
            않는다. WCAG 1.4.11 이 컨트롤 경계에 3:1 을 요구한다. */}
        <Link
          href={routes.home}
          className="flex min-h-12 flex-1 items-center justify-center rounded-full border border-white/40 px-5 font-semibold text-slate-100 transition-[scale,border-color] duration-[120ms] ease-press hover:border-white/60 active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          홈으로
        </Link>
      </div>
    </main>
  );
}
