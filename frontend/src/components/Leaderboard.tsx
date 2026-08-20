import Link from "next/link";

import { BoardRowItem } from "@/components/BoardRow";
import type { Board, BoardKind } from "@/lib/api/leaderboards";
import { BOARD_KINDS, BOARD_LABELS } from "@/lib/api/leaderboards";
import { routes } from "@/lib/routes";

/**
 * 순위표 한 판.
 *
 * 탭은 링크다 - 클라이언트 상태로 두면 세 종류를 미리 다 받아와야 하고,
 * 탭을 눌러도 주소가 안 바뀌어 "이번 주 순위" 를 남에게 보낼 수 없다.
 */

/** "8월 18일 ~ 8월 24일". 연도는 뺀다 - 이번 주 얘기라 굳이 필요 없다. */
function periodText(start: string, end: string): string {
  const fmt = (value: string) => {
    const [, month, day] = value.split("-");
    return `${Number(month)}월 ${Number(day)}일`;
  };
  return `${fmt(start)} ~ ${fmt(end)}`;
}

type Props = {
  board: Board;
  /** 로그인 안 했으면 하단에 안내를 붙인다. */
  isGuest: boolean;
};

export function Leaderboard({ board, isGuest }: Props) {
  const labels = BOARD_LABELS[board.kind];
  const empty = board.rows.length === 0;

  return (
    <div className="rise">
      {/* 제목이 먼저다. 탭을 위에 두면 "이번 주" 라는 탭 이름과 "이번 주
          최고점" 이라는 제목이 겹쳐 읽혀 위계가 뒤집힌다. */}
      <header>
        <h1 className="text-2xl font-bold text-slate-100 sm:text-3xl">
          {labels.title}
        </h1>
        <p className="mt-1.5 text-sm text-slate-400">{labels.note}</p>
        {board.period && (
          <p className="mt-1 font-mono text-xs text-violet-300/80 tabular-nums">
            {periodText(board.period.start, board.period.end)}
          </p>
        )}
      </header>

      <nav aria-label="순위표 종류" className="mt-5 flex gap-1.5">
        {BOARD_KINDS.map((kind) => (
          <TabLink key={kind} kind={kind} current={board.kind} />
        ))}
      </nav>

      {empty ? (
        <EmptyBoard />
      ) : (
        <ol className="mt-5 flex flex-col gap-1.5">
          {board.rows.map((row, index) => (
            <BoardRowItem
              key={row.rank}
              row={row}
              kind={board.kind}
              index={index}
            />
          ))}
        </ol>
      )}

      {/* 내가 상위 밖이면 하단에 따로 붙인다. 목록 안에 끼워 넣으면
          등수가 건너뛰어 보여서 표가 깨진 것처럼 읽힌다. */}
      {board.me && (
        <div className="mt-4">
          <p className="mb-1.5 text-xs text-slate-500">내 순위</p>
          <ol className="flex flex-col gap-1.5">
            <BoardRowItem row={board.me} kind={board.kind} pinned />
          </ol>
        </div>
      )}

      {isGuest && !empty && (
        <p className="mt-5 rounded-lg border border-white/10 bg-slate-950/40 px-4 py-3 text-sm text-slate-400">
          로그인하면 내 순위도 함께 보입니다.{" "}
          <Link
            href="/login?next=/board"
            className="font-medium text-teal-300 underline underline-offset-2 hover:text-teal-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          >
            로그인
          </Link>
        </p>
      )}
    </div>
  );
}

function TabLink({ kind, current }: { kind: BoardKind; current: BoardKind }) {
  const active = kind === current;
  return (
    <Link
      href={routes.board(kind)}
      aria-current={active ? "page" : undefined}
      // 44px 이상. 앱으로 옮겼을 때 그대로 쓰는 치수다.
      className={[
        "min-h-11 rounded-lg px-3.5 py-2.5 text-sm font-medium transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
        active
          ? "bg-violet-300/15 text-violet-100 ring-1 ring-violet-300/35"
          : "text-slate-400 hover:bg-white/5 hover:text-slate-200",
      ].join(" ")}
    >
      {BOARD_LABELS[kind].tab}
    </Link>
  );
}

/**
 * 아직 아무도 없을 때.
 *
 * 0 을 채운 가짜 줄을 두지 않는다 - 0 은 "아직 아무도 안 함" 이 아니라
 * "누군가 0점을 냈다" 로 읽힌다.
 */
function EmptyBoard() {
  return (
    <div className="mt-6 rounded-xl border border-dashed border-white/12 bg-slate-950/30 px-5 py-10 text-center">
      <p className="text-slate-300">아직 아무도 오르지 않았습니다.</p>
      <p className="mt-1 text-sm text-slate-500">
        한 판만 풀어도 이 자리에 이름이 올라갑니다.
      </p>
      <Link
        href={routes.testRound}
        className="mt-5 inline-flex min-h-11 items-center rounded-lg bg-violet-300/15 px-5 text-sm font-medium text-violet-100 ring-1 ring-violet-300/35 transition hover:bg-violet-300/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        문제 풀러 가기
      </Link>
    </div>
  );
}
