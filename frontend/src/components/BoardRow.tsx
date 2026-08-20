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
 * 1~3위 표시. 숫자 색과 테두리를 함께 바꾼다.
 *
 * **광채(zero-offset colored shadow)를 쓰지 않는다.** 어두운 배경에
 * 색 있는 후광을 두르는 것은 AI 가 만든 화면의 전형이고, 여기서는
 * 이미 색과 테두리로 상위 셋이 갈린다 - 광채는 덧칠이다.
 */
const MEDALS: Record<number, { ring: string; text: string }> = {
  1: { ring: "ring-amber-300/55", text: "text-amber-300" },
  2: { ring: "ring-slate-300/50", text: "text-slate-200" },
  3: { ring: "ring-orange-300/45", text: "text-orange-200" },
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
  /** 하단 고정 줄로 쓸 때. 순서 애니메이션을 끄고 테두리를 다르게 준다. */
  pinned?: boolean;
};

export function BoardRowItem({ row, kind, index = 0, pinned = false }: Props) {
  const medal = MEDALS[row.rank];
  const unit = BOARD_LABELS[kind].unit;

  return (
    <li
      className={[
        "rise flex items-center gap-3 rounded-xl border px-3 py-2.5 sm:gap-4 sm:px-4 sm:py-3",
        // 내 줄은 청록으로 띄운다. 배경이 자수정이라 보색에 가까워
        // 스무 줄 사이에서 눈이 바로 찾는다.
        row.is_me
          ? "border-teal-300/45 bg-teal-300/10"
          : "border-white/10 bg-slate-950/35",
        pinned ? "border-teal-300/55 bg-teal-300/12" : "",
        medal ? `ring-1 ${medal.ring}` : "",
      ].join(" ")}
      // 스무 줄이 동시에 뜨면 화면이 한 번 번쩍인다. 40ms 씩 밀어 위에서
      // 아래로 흐르게 한다. 마지막 줄이 0.8초라 기다린다는 느낌은 없다.
      style={pinned ? undefined : { animationDelay: `${index * 40}ms` }}
    >
      <span
        className={[
          "w-7 shrink-0 text-center font-mono text-sm tabular-nums sm:w-9 sm:text-base",
          medal ? `font-bold ${medal.text}` : "text-slate-400",
        ].join(" ")}
      >
        {row.rank}
      </span>

      <Avatar shown={row.avatar} size={34} className="shrink-0" />

      {/* min-w-0 이 없으면 긴 이름이 줄을 화면 밖으로 밀어낸다. */}
      <span className="min-w-0 flex-1 truncate text-sm text-slate-100 sm:text-base">
        {row.display_name}
        {row.is_me && (
          <span className="ml-1.5 text-xs font-medium text-teal-300">나</span>
        )}
      </span>

      <span className="shrink-0 text-right">
        <span className="block font-mono text-sm font-semibold tabular-nums text-slate-100 sm:text-base">
          {row.score.toLocaleString()}
        </span>
        <span className="block text-[11px] text-slate-400 sm:text-xs">
          {row.entries}
          {unit}
        </span>
      </span>
    </li>
  );
}
