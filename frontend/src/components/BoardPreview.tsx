import Link from "next/link";

import { BoardRowItem } from "@/components/BoardRow";
import type { Board } from "@/lib/api/leaderboards";
import { routes } from "@/lib/routes";

/**
 * 홈에 놓는 순위 카드.
 *
 * 상위 셋 + 내가 밖이면 내 줄. 전체 스무 줄을 홈에 펼치면 홈이 순위표
 * 화면이 되고, 그러면 순위표 화면이 있을 이유가 없어진다.
 *
 * 하단 탭에 순위표를 넣지 않고 여기 두는 이유: 탭 자리는 비싸고,
 * 순위표는 매일 여러 번 볼 화면이 아니다.
 */
export function BoardPreview({ board }: { board: Board }) {
  if (board.rows.length === 0) return null;

  const top = board.rows.slice(0, 3);
  // 내가 상위 셋 안에 있으면 아래에 또 그리지 않는다.
  const mine = board.me ?? board.rows.slice(3).find((row) => row.is_me);

  return (
    <section
      aria-labelledby="board-preview"
      className="rounded-2xl border border-white/10 bg-slate-950/35 px-4 py-4 sm:px-5"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 id="board-preview" className="text-sm font-medium text-slate-300">
          이번 주 순위
        </h2>
        <Link
          href={routes.board()}
          className="rounded-md px-1.5 py-1 text-xs text-slate-400 transition hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          전체 보기
        </Link>
      </div>

      <ol className="mt-3 flex flex-col gap-1.5">
        {top.map((row, index) => (
          <BoardRowItem
            key={row.rank}
            row={row}
            kind={board.kind}
            index={index}
          />
        ))}
      </ol>

      {mine && (
        <ol className="mt-1.5 flex flex-col gap-1.5">
          <BoardRowItem row={mine} kind={board.kind} pinned />
        </ol>
      )}
    </section>
  );
}
