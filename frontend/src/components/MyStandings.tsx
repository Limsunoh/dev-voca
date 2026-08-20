import Link from "next/link";

import type { BoardKind, BoardRow } from "@/lib/api/leaderboards";
import { BOARD_KINDS, BOARD_LABELS } from "@/lib/api/leaderboards";
import { routes } from "@/lib/routes";

/**
 * 내 순위 세 줄.
 *
 * 마이페이지에만 쓴다 - 남과 비교하러 오는 자리가 아니라 자기 상태를
 * 보러 오는 자리라, 20명 목록 대신 내 줄만 본다.
 *
 * **아직 못 오른 종류는 빈 줄로 둔다.** 0점 0위로 채우면 "0점을 냈다" 로
 * 읽혀서, 기능이 없는 것인지 내가 안 한 것인지 구분되지 않는다.
 */
export function MyStandings({
  standings,
}: {
  standings: Partial<Record<BoardKind, BoardRow>>;
}) {
  const empty = BOARD_KINDS.every((kind) => !standings[kind]);

  return (
    <div className="rounded-xl border border-white/10 bg-slate-950/35 px-4 py-4 sm:px-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium text-slate-300">내 순위</h3>
        <Link
          href={routes.board()}
          className="rounded-md px-1.5 py-1 text-xs text-slate-400 transition hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          순위표 전체
        </Link>
      </div>

      {empty ? (
        <p className="mt-3 text-sm text-slate-500">
          아직 오른 순위가 없습니다.{" "}
          <Link
            href={routes.testRound}
            className="font-medium text-teal-300 underline underline-offset-2 hover:text-teal-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          >
            한 판 풀어보기
          </Link>
        </p>
      ) : (
        <dl className="mt-3 grid grid-cols-3 gap-2">
          {BOARD_KINDS.map((kind) => (
            <StandingCell key={kind} kind={kind} row={standings[kind]} />
          ))}
        </dl>
      )}
    </div>
  );
}

function StandingCell({ kind, row }: { kind: BoardKind; row?: BoardRow }) {
  const labels = BOARD_LABELS[kind];

  return (
    <div className="rounded-lg border border-white/8 bg-slate-950/40 px-3 py-2.5 text-center">
      <dt className="text-[11px] text-slate-500">{labels.tab}</dt>
      {row ? (
        <dd className="mt-1">
          <span className="block font-mono text-lg font-semibold tabular-nums text-slate-100">
            {row.score.toLocaleString()}
          </span>
          <span className="mt-0.5 block font-mono text-xs tabular-nums text-violet-300/85">
            {row.rank}위
          </span>
        </dd>
      ) : (
        // 하이픈으로 둔다. 0 을 넣으면 "0점을 냈다" 로 읽힌다.
        <dd className="mt-1">
          <span className="block font-mono text-lg text-slate-600">-</span>
          <span className="mt-0.5 block text-xs text-slate-600">아직</span>
        </dd>
      )}
    </div>
  );
}
