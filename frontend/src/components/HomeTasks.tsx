import Link from "next/link";

import type { StudyProgress } from "@/lib/api/daily";
import type { Board } from "@/lib/api/leaderboards";
import type { ReviewDue } from "@/lib/api/review";
import { routes } from "@/lib/routes";

/**
 * 홈 아래쪽 "오늘 할 일" 목록.
 *
 * **카드가 아니라 줄이다.** 앞서는 셋 다 테두리 있는 상자였는데, 그러면
 * 위의 오늘의 단어와 같은 무게로 읽혀서 화면이 무엇을 먼저 보라고 말하지
 * 않는다. 홈은 오늘의 단어를 읽고 어디로 갈지 고르는 자리라, 고르는
 * 쪽은 훑기 좋아야지 눈에 띌 필요가 없다.
 *
 * 상자를 없애면서 잃는 것은 "여기가 누를 수 있는 곳" 이라는 신호인데,
 * 그건 오른쪽 화살표와 누름 축소가 대신한다.
 *
 * 일일공부·복습은 로그인해야 쓴다. 게스트에게는 안 그린다 - 못 누르는
 * 줄을 띄워두면 눌러보고 로그인으로 튕기는 경험이 된다.
 */
export function HomeTasks({
  daily,
  due,
  board,
  signedIn,
}: {
  daily: StudyProgress | null;
  due: ReviewDue | null;
  board: Board | null;
  signedIn: boolean;
}) {
  // 내 순위. 상위권이면 board.rows 안에, 아니면 board.me 에 있다.
  const mine = board?.me ?? board?.rows.find((row) => row.is_me);

  const rows: TaskRow[] = [];

  if (signedIn) {
    const done = daily?.done ?? false;
    const started = daily !== null && !done;
    rows.push({
      href: routes.testDaily,
      mark: "공",
      title: "일일공부",
      hint: done
        ? "오늘 몫을 마쳤습니다"
        : started
          ? `${daily.answered}/${daily.total}문제까지 풀었습니다`
          : "하루 한 번, 길이를 골라 공부합니다",
      // 안 한 것에만 숫자를 붙인다. 끝낸 줄에 "완료" 를 달면 다 한 날
      // 화면이 배지로 뒤덮인다.
      badge: done ? null : started ? `${daily.answered}/${daily.total}` : null,
    });

    // 다시 볼 것이 없으면 줄 자체를 안 그린다. 매일 "0" 이 붙은 줄이
    // 자리를 차지하면 오늘 할 일이 아니라 목록이 된다.
    if (due && due.due > 0) {
      rows.push({
        href: routes.testReview,
        mark: "복",
        title: "복습",
        hint: "틀린 것과 오래된 것을 다시 봅니다",
        badge: `${due.due}개`,
      });
    }
  }

  if (board && mine) {
    rows.push({
      href: routes.board(),
      mark: "순",
      title: "이번 주 순위",
      hint: `${mine.entries}판 · ${mine.score}점`,
      badge: `${mine.rank}위`,
    });
  }

  if (rows.length === 0) return null;

  return (
    <nav aria-label="오늘 할 일" className="mt-auto pb-2">
      <ul className="flex flex-col">
        {rows.map((row) => (
          <li key={row.href}>
            <Link
              href={row.href}
              className="flex items-center gap-3 border-t border-white/10 py-3.5 transition-[scale] duration-[120ms] ease-press active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            >
              <span
                aria-hidden
                className="flex size-7 shrink-0 items-center justify-center rounded-lg border border-focus/30 bg-focus/10 text-xs font-bold text-focus"
              >
                {row.mark}
              </span>

              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-slate-100">
                  {row.title}
                </span>
                <span className="block truncate text-xs text-slate-400">
                  {row.hint}
                </span>
              </span>

              {row.badge && (
                <span className="shrink-0 font-mono text-xs font-semibold text-focus tabular-nums">
                  {row.badge}
                </span>
              )}
              <span aria-hidden className="shrink-0 text-sm text-slate-400">
                →
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

type TaskRow = {
  href: string;
  /** 한 글자 표식. 아이콘 대신 쓴다 - 의존성이 늘지 않는다. */
  mark: string;
  title: string;
  hint: string;
  /** 오른쪽 숫자. 없으면 안 그린다. */
  badge: string | null;
};
