import Link from "next/link";

import type { BoardKind, BoardRow } from "@/lib/api/leaderboards";
import { BOARD_KINDS, BOARD_LABELS } from "@/lib/api/leaderboards";
import { routes } from "@/lib/routes";

/**
 * 내 순위 세 칸.
 *
 * 마이페이지에만 쓴다 - 남과 비교하러 오는 자리가 아니라 자기 상태를
 * 보러 오는 자리라, 20명 목록 대신 내 줄만 본다.
 *
 * **아직 못 오른 종류는 빈 칸으로 둔다.** 0점 0위로 채우면 "0점을 냈다" 로
 * 읽혀서, 기능이 없는 것인지 내가 안 한 것인지 구분되지 않는다.
 *
 * 프로토타입(identity/MyStandings.jsx)은 두 칸이지만 우리는 세 칸이다 -
 * 꾸준함이 별도 순위로 있어서, 그것만 빼면 프로필에서 볼 수 없게 된다.
 */
export function MyStandings({
  standings,
}: {
  standings: Partial<Record<BoardKind, BoardRow>>;
}) {
  const empty = BOARD_KINDS.every((kind) => !standings[kind]);

  return (
    // 흰 카드 + 아래 3px 두께. 누를 수 없으므로 dv-card-press 는 안 건다.
    <div
      className="px-4 py-4 dv-card sm:px-5"
      style={
        {
          background: "var(--paper)",
          borderRadius: "var(--radius-2xl)",
          "--lift": "var(--lift-card)",
        } as React.CSSProperties
      }
    >
      <div className="flex items-center justify-between gap-3">
        <h3
          className="text-xs tracking-[var(--tracking-wide)]"
          style={{
            color: "var(--text-dim)",
            fontWeight: "var(--weight-black)",
          }}
        >
          내 순위
        </h3>
        <Link
          href={routes.board()}
          className="rounded-md px-1.5 py-1 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={{
            color: "var(--text-muted)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          순위표 전체
        </Link>
      </div>

      {empty ? (
        <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
          아직 오른 순위가 없습니다.{" "}
          <Link
            href={routes.testRound}
            className="underline underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            style={{
              color: "var(--coral-deep)",
              fontWeight: "var(--weight-bold)",
            }}
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
    // 칸 안에 두께를 또 얹지 않는다. 카드 안의 카드가 되어 층이 둘이 된다.
    // 옅은 모래색 채움으로만 가른다(번들 identity/MyStandings.jsx 의 sand).
    <div
      className="px-2 py-2.5 text-center"
      style={{
        background: "var(--background-deep)",
        borderRadius: "var(--radius-lg)",
      }}
    >
      <dt
        className="text-[length:var(--text-11)]"
        style={{
          color: "var(--text-dim)",
          fontWeight: "var(--weight-bold)",
        }}
      >
        {labels.tab}
      </dt>
      {row ? (
        <dd className="mt-1">
          {/* tabular-nums: 세 칸이 나란히 서는데 자릿수가 제각각이라
              (12 / 340 / 1,208) 폭이 흔들리면 가운데 정렬이 어긋나 보인다. */}
          <span
            className="block text-lg tabular-nums"
            style={{
              fontFamily: "var(--font-mono)",
              fontWeight: "var(--weight-bold)",
              color: "var(--foreground)",
              letterSpacing: "var(--tracking-tighter)",
            }}
          >
            {row.score.toLocaleString()}
          </span>
          {/* 순위는 코랄. 점수와 같은 색이면 두 줄이 한 덩어리로 읽혀
              무엇이 점수고 무엇이 등수인지 헷갈린다. */}
          <span
            className="mt-0.5 block text-xs tabular-nums"
            style={{
              color: "var(--coral-deep)",
              fontWeight: "var(--weight-bold)",
            }}
          >
            {row.rank}위
          </span>
        </dd>
      ) : (
        // 하이픈으로 둔다. 0 을 넣으면 "0점을 냈다" 로 읽힌다.
        //
        // --text-faint(크림 위 2.51:1)를 안 쓴다. 이 자리는 "아직 순위가
        // 없다" 는 **정보**이지 장식이 아니고, 이 저장소가 0 을 안 채우기로
        // 한 판단이 여기 이 두 글자로만 드러난다. 안 보이면 그 판단이
        // 통째로 사라진다.
        <dd className="mt-1">
          <span
            className="block text-lg"
            style={{
              fontFamily: "var(--font-mono)",
              color: "var(--text-dim)",
            }}
          >
            -
          </span>
          <span
            className="mt-0.5 block text-xs"
            style={{ color: "var(--text-muted)" }}
          >
            아직
          </span>
        </dd>
      )}
    </div>
  );
}
