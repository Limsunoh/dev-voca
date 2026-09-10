import { Avatar } from "@/components/Avatar";
import type { BoardKind, BoardRow as Row } from "@/lib/api/leaderboards";
import { BOARD_LABELS } from "@/lib/api/leaderboards";

/**
 * 순위표 한 줄.
 *
 * 순위표 화면과 홈 카드가 같은 줄을 쓴다. 두 곳에 따로 만들면 등수 색이나
 * 내 줄 강조가 한쪽만 바뀌어 어긋난다.
 *
 * 등수 색(금·은·동)은 1~3위에만 준다. 넷째부터 색을 이어 붙이면 무지개가
 * 되고, 그러면 상위 셋이 특별해 보이지 않는다.
 */

/**
 * 1~3위 표시. 등수 숫자의 색과 크기를 함께 바꾼다.
 *
 * 크림에서 링(ring)을 버렸다. 다크에서는 색 있는 테두리로 상위 셋을 갈랐지만
 * 이 시스템은 경계를 테두리가 아니라 아래 두께가 맡는다(가이드 shape-lift).
 * 줄마다 색 링을 두르면 두께가 만든 층 위에 다른 층이 하나 더 생긴다.
 *
 * 대신 숫자를 한 단계 키운다(--text-md vs --text-sm). 번들 원본
 * (identity/BoardRow.jsx)이 17px / 14px 로 가른 것과 같은 방식이고, 색을
 * 못 보는 사람에게도 상위 셋이 크기로 남는다.
 */
const MEDALS: Record<number, string> = {
  1: "var(--medal-1)",
  2: "var(--medal-2)",
  3: "var(--medal-3)",
};

type Props = {
  row: Row;
  kind: BoardKind;
  /**
   * 등장 순서. 목록이 위에서 아래로 차례로 떠오르게 한다.
   *
   * 지연을 인라인 스타일로 주는 이유: 줄 수가 가변(최대 TOP_SIZE)이라
   * 다른 화면처럼 [animation-delay:NNms] 클래스를 못 쓴다. 스무 개를
   * 나열해두면 TOP_SIZE 가 바뀔 때 조용히 어긋난다.
   */
  index?: number;
  /** 하단 고정 줄로 쓸 때. 순서 애니메이션을 끈다. */
  pinned?: boolean;
};

export function BoardRowItem({ row, kind, index = 0, pinned = false }: Props) {
  const medal = MEDALS[row.rank];
  const unit = BOARD_LABELS[kind].unit;

  // 내 줄은 옅은 코랄로 채운다(번들 identity/BoardRow.jsx). 스무 줄이 전부
  // 흰 종이라 채움 하나만 달라도 눈이 바로 찾는다.
  //
  // 두께도 코랄 계열로 같이 바꾼다. 흰 줄과 같은 잉크 두께를 두면 채움만
  // 뜨고 판은 그대로라 색을 덧칠한 것처럼 보인다.
  const mine = row.is_me;

  return (
    <li
      // rise 는 고정 줄에도 건다. 지연만 빼서 목록과 함께 한 번에 올라온다 -
      // 목록 끝에 40ms 씩 이어 붙이면 스무 줄 뒤에 혼자 늦게 뜬다.
      className="rise flex items-center gap-3 px-3.5 py-3 dv-card sm:gap-4 sm:px-4"
      style={
        {
          background: mine ? "var(--coral-soft)" : "var(--paper)",
          borderRadius: "var(--radius-xl)",
          // 누를 수 없는 줄이라 dv-card-press 를 안 건다. 그래도 두께는
          // --lift 로 넘긴다 - .dv-card 가 box-shadow: var(--lift) 를
          // 그리므로 변수를 안 주면 그림자가 통째로 사라진다.
          "--lift": mine ? "0 3px 0 rgb(193 62 34 / 0.25)" : "var(--lift-card)",
          // 스무 줄이 동시에 뜨면 화면이 한 번 번쩍인다. 40ms 씩 밀어 위에서
          // 아래로 흐르게 한다. 마지막 줄이 0.8초라 기다린다는 느낌은 없다.
          animationDelay: pinned ? undefined : `${index * 40}ms`,
        } as React.CSSProperties
      }
    >
      <span
        className="w-7 shrink-0 text-center tabular-nums sm:w-9"
        style={{
          fontFamily: "var(--font-mono)",
          fontWeight: "var(--weight-bold)",
          // 상위 셋은 한 단계 크다. 색만으로 가르지 않는다.
          fontSize: medal ? "var(--text-md)" : "var(--text-sm)",
          color: medal ?? "var(--text-muted)",
          letterSpacing: "var(--tracking-tighter)",
        }}
      >
        {row.rank}
      </span>

      <Avatar shown={row.avatar} size={34} className="shrink-0" />

      {/* min-w-0 이 없으면 긴 이름이 줄을 화면 밖으로 밀어낸다. */}
      <span
        className="min-w-0 flex-1 truncate text-sm sm:text-base"
        style={{
          color: "var(--foreground)",
          fontWeight: "var(--weight-bold)",
        }}
      >
        {row.display_name}
        {mine && (
          <span
            className="ml-1.5 text-xs"
            style={{
              color: "var(--coral-deep)",
              fontWeight: "var(--weight-black)",
            }}
          >
            나
          </span>
        )}
      </span>

      <span className="shrink-0 text-right">
        {/* tabular-nums: 점수가 920 에서 1,040 으로 갈 때 자릿수가 바뀌는데,
            폭이 흔들리면 오른쪽 끝이 줄마다 다른 자리에서 끝난다. */}
        <span
          className="block text-sm tabular-nums sm:text-base"
          style={{
            fontFamily: "var(--font-mono)",
            fontWeight: "var(--weight-bold)",
            color: "var(--foreground)",
            letterSpacing: "var(--tracking-tighter)",
          }}
        >
          {row.score.toLocaleString()}
        </span>
        <span
          className="block text-[length:var(--text-11)] sm:text-xs"
          style={{
            color: "var(--text-dim)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          {row.entries}
          {unit}
        </span>
      </span>
    </li>
  );
}
