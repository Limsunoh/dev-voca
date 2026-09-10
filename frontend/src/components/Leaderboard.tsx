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
 *
 * 프로토타입(ui_kits/devvoca-web/BoardScreen.jsx)은 순위표를 프로필 하위
 * 화면으로 두고 내 줄을 목록 안에 끼웠다. 우리는 탭 셋으로 나눈 독립 화면을
 * 유지한다 - 세 종류가 성격이 다른 순위(주간·누적·꾸준함)라 한 목록으로는
 * 못 담고, 기간 표시도 주간에만 붙는다.
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
        <h1
          className="text-[length:var(--text-2xl)] tracking-[var(--tracking-tight)]"
          style={{
            color: "var(--foreground)",
            fontWeight: "var(--weight-black)",
          }}
        >
          {labels.title}
        </h1>
        <p className="mt-1.5 text-sm" style={{ color: "var(--text-muted)" }}>
          {labels.note}
        </p>
        {board.period && (
          // 기간은 사실 하나뿐이라 색으로 세우지 않는다. 고정폭 + tabular-nums
          // 로 두면 날짜가 바뀌어도 글자 폭이 흔들리지 않는다.
          <p
            className="mt-1 text-xs tabular-nums"
            style={{
              fontFamily: "var(--font-mono)",
              color: "var(--text-dim)",
              fontWeight: "var(--weight-bold)",
              letterSpacing: "var(--tracking-tighter)",
            }}
          >
            {periodText(board.period.start, board.period.end)}
          </p>
        )}
      </header>

      <nav aria-label="순위표 종류" className="mt-5 flex gap-2">
        {BOARD_KINDS.map((kind) => (
          <TabLink key={kind} kind={kind} current={board.kind} />
        ))}
      </nav>

      {empty ? (
        <EmptyBoard />
      ) : (
        <ol className="mt-5 flex flex-col gap-2">
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
        <div className="mt-5">
          <p
            className="mb-2 text-xs tracking-[var(--tracking-wide)]"
            style={{
              color: "var(--text-dim)",
              fontWeight: "var(--weight-black)",
            }}
          >
            내 순위
          </p>
          <ol className="flex flex-col gap-2">
            <BoardRowItem row={board.me} kind={board.kind} pinned />
          </ol>
        </div>
      )}

      {isGuest && !empty && (
        // 안내 줄은 눌리지 않으므로 흰 종이에 두께만 얹는다. 크림 바탕
        // 위에서 카드 하나가 놓인 것으로 읽히고, 안의 "로그인" 만 누른다.
        <p
          className="mt-5 px-4 py-3.5 text-sm dv-card"
          style={
            {
              background: "var(--paper)",
              borderRadius: "var(--radius-2xl)",
              color: "var(--text-body)",
              "--lift": "var(--lift-card)",
            } as React.CSSProperties
          }
        >
          로그인하면 내 순위도 함께 보입니다.{" "}
          <Link
            href="/login?next=/board"
            className="underline underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            style={{
              color: "var(--coral-deep)",
              fontWeight: "var(--weight-bold)",
            }}
          >
            로그인
          </Link>
        </p>
      )}
    </div>
  );
}

/**
 * 종류 탭 하나.
 *
 * FilterChip 과 같은 문법이다(꺼짐 흰 알약 + 두께, 켜짐 잉크 채움). 따로
 * 만들지 않고 모양을 맞춘 이유: 같은 앱 안에서 "여럿 중 하나를 고르는 알약"
 * 이 화면마다 다르게 생기면 같은 동작인 줄 모른다. 컴포넌트를 그대로 쓰지는
 * 못한다 - FilterChip 은 토글이라 aria-current="true" 를 쓰는데, 이 탭은
 * 진짜 페이지 이동이라 "page" 가 맞다.
 */
function TabLink({ kind, current }: { kind: BoardKind; current: BoardKind }) {
  const active = kind === current;

  return (
    <Link
      href={routes.board(kind)}
      aria-current={active ? "page" : undefined}
      // 44px 이상(--hit-floor). 앱으로 옮겼을 때 그대로 쓰는 치수다.
      className="dv-card dv-card-press inline-flex min-h-11 items-center rounded-full px-4 text-sm whitespace-nowrap focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      style={
        active
          ? ({
              background: "var(--foreground)",
              color: "var(--background)",
              fontWeight: "var(--weight-black)",
              // --lift-dark 는 4px 인데 이 알약은 카드 규칙(3px)으로
              // 내려앉는다. 그대로 두면 눌렀을 때 1px 이 남아 바닥에 안 닿는다.
              // 진하기만 가져오고 거리는 3px 로 맞춘다(FilterChip 과 같은 판단).
              "--lift": "var(--lift-dark-card)",
            } as React.CSSProperties)
          : ({
              background: "var(--paper)",
              color: "var(--text-muted)",
              fontWeight: "var(--weight-bold)",
              "--lift": "var(--lift-card)",
            } as React.CSSProperties)
      }
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
    <div
      className="mt-6 px-5 py-10 text-center dv-card"
      style={
        {
          background: "var(--paper)",
          borderRadius: "var(--radius-2xl)",
          "--lift": "var(--lift-card)",
        } as React.CSSProperties
      }
    >
      <p
        style={{
          color: "var(--foreground)",
          fontWeight: "var(--weight-bold)",
        }}
      >
        아직 아무도 오르지 않았습니다.
      </p>
      <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
        한 판만 풀어도 이 자리에 이름이 올라갑니다.
      </p>

      {/* 이 화면에서 코랄 버튼은 여기 하나뿐이다 - 빈 순위표에서 할 일은
          문제를 푸는 것 하나라, 그것이 주된 동작이다. */}
      <Link
        href={routes.testRound}
        className="dv-btn mt-6 inline-flex items-center rounded-[var(--radius-pill)] px-6 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        style={
          {
            minHeight: "var(--hit-floor)",
            background: "var(--coral)",
            color: "var(--text-on-color)",
            fontWeight: "var(--weight-black)",
            "--lift": "var(--lift-button)",
          } as React.CSSProperties
        }
      >
        문제 풀러 가기
      </Link>
    </div>
  );
}
