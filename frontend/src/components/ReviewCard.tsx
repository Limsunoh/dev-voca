import Link from "next/link";

import type { ReviewDue } from "@/lib/api/review";
import { routes } from "@/lib/routes";

/**
 * 홈에 놓는 복습 입구.
 *
 * 일일공부 카드 아래에 둔다. 일일공부는 오늘 안 하면 사라지지만 복습은
 * 안 해도 쌓여 있으므로, 하루 한 번뿐인 쪽이 먼저다.
 *
 * **다시 볼 것이 없으면 안 보인다.** 없는 상태로 띄우면 매일 "0" 이
 * 붙은 카드가 자리를 차지한다 - 홈은 오늘 할 일을 보는 곳이다.
 *
 * DailyCard 와 모양이 닮았지만 합치지 않는다. 저쪽은 상태가 셋(시작·
 * 이어서·완료)이고 이쪽은 개수 하나다. 하나로 묶으면 둘 중 한쪽만 쓰는
 * 분기가 컴포넌트 안에 남는다.
 */
export function ReviewCard({ due }: { due: ReviewDue }) {
  if (due.due === 0) return null;

  return (
    <Link
      href={routes.testReview}
      className="flex items-center justify-between gap-4 rounded-2xl border border-white/25 px-5 py-4 transition-[scale,border-color] duration-[120ms] ease-press hover:border-white/45 active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
    >
      <div className="min-w-0">
        <p className="text-sm font-semibold text-slate-100">다시 보기</p>
        <p className="mt-0.5 text-xs text-slate-400">
          틀린 것과 오래된 것을 다시 풉니다
        </p>
      </div>

      {/* 개수를 글자로도 알린다. 숫자만 두면 무엇의 개수인지 모른다. */}
      <span className="shrink-0 rounded-full bg-focus/15 px-3 py-1 text-xs font-medium text-focus ring-1 ring-focus/40">
        <span className="font-mono tabular-nums">{due.due}</span>개
      </span>
    </Link>
  );
}
