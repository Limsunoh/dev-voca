import Link from "next/link";

import type { StudyProgress } from "@/lib/api/daily";
import { routes } from "@/lib/routes";

/**
 * 홈에 놓는 일일공부 입구.
 *
 * 하루 한 번뿐이라 눈에 띄어야 한다. 순위 카드보다 위에 두는 이유:
 * 순위는 결과를 보는 곳이고 이건 오늘 할 일이다.
 *
 * 로그인해야 쓸 수 있는 기능이라 게스트에게는 안 보인다. 못 누르는
 * 버튼을 띄워두면 눌러보고 로그인 화면으로 튕기는 경험이 된다.
 */
export function DailyCard({ today }: { today: StudyProgress | null }) {
  const done = today?.done ?? false;
  const started = today !== null && !done;

  return (
    <Link
      href={routes.testDaily}
      className="flex items-center justify-between gap-4 rounded-2xl border border-white/25 px-5 py-4 transition-[scale,border-color] duration-[120ms] ease-press hover:border-white/45 active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
    >
      <div className="min-w-0">
        <p className="text-sm font-semibold text-slate-100">일일공부</p>
        <p className="mt-0.5 text-xs text-slate-400">
          {done
            ? "오늘 몫을 마쳤습니다"
            : started
              ? `${today.answered}/${today.total}문제까지 풀었습니다`
              : "하루 한 번, 길이를 골라 공부합니다"}
        </p>
      </div>

      {/* 상태를 글자로도 알린다. 색만으로 구분하면 색각 이상이 있는
          사람에게는 셋이 같은 카드다. */}
      <span
        className={[
          "shrink-0 rounded-full px-3 py-1 text-xs font-medium",
          done
            ? "bg-white/10 text-slate-300"
            : "bg-focus/15 text-focus ring-1 ring-focus/40",
        ].join(" ")}
      >
        {done ? "완료" : started ? "이어서" : "시작"}
      </span>
    </Link>
  );
}
