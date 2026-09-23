import { routes, type TalkKind, type TalkLevel } from "@/lib/routes";

import { TalkTabRow } from "./TalkKindTabs";

/**
 * 난이도를 고르는 탭.
 *
 * **두 갈래에서 뜻이 다르다.** 일상 표현의 난이도는 낱말 수가 아니라
 * 발음이 어려운 정도다(seed_phrases 의 같은 자리 주석) - comfortable 은 한
 * 낱말인데 가장 많이 틀리고 thank you 는 두 낱말이어도 누구나 안다. 개발
 * 용어는 Word.difficulty 를 그대로 쓰는데 그쪽은 **개념이 어려운 정도**다.
 * queue 는 개념이 쉬워서 1 이지만 발음은 이 앱 타겟이 가장 많이 틀린다.
 *
 * 같은 탭이 갈래마다 다른 축으로 거르는 셈이라, 언젠가 맞춰야 한다. 지금
 * 맞추려면 개발 용어 566개의 난이도를 발음 기준으로 다시 매겨야 하는데
 * 그것은 단어장·문제풀기의 난이도까지 통째로 바꾸는 일이라 이번 범위가
 * 아니다. 여기서는 그 사실을 적어만 둔다.
 *
 * 모양은 TalkKindTabs 의 TalkTabRow 를 같이 써서 맞춘다 - 바로 위아래에
 * 붙어 서는 두 줄이라 하나만 다르게 생기면 그때부터 규칙이 아니라 우연이 된다.
 *
 * ## 왜 색을 안 쓰나
 *
 * 카드 위의 DifficultyBadge 는 난이도별 색(초록·앰버·장미)을 쓰는데 여기는
 * 안 쓴다. 이 줄은 **고르는 곳**이고 색은 "지금 켜진 것" 을 말해야 하는데,
 * 난이도 색까지 같이 칠하면 무엇이 켜진 것인지가 흐려진다. 켜진 쪽만 흰
 * 알약으로 떠오르는 것이 그 신호다.
 */
export function TalkLevelTabs({
  kind,
  current,
}: {
  kind: TalkKind;
  /** 지금 고른 난이도. 0 이면 전체다. */
  current: TalkLevel;
}) {
  return (
    <TalkTabRow
      label="난이도"
      items={LEVELS.map((level) => ({
        key: level.value,
        href: routes.talk(kind, level.value),
        label: level.label,
        active: level.value === current,
      }))}
    />
  );
}

/**
 * 고를 수 있는 난이도.
 *
 * 이름을 서버의 Difficulty choices 와 맞춘다(쉬움·보통·어려움). 카드 위
 * 배지가 서버가 만든 이름을 그대로 그리므로, 여기서 다른 말을 쓰면 "보통"
 * 을 골랐는데 카드에는 "중간" 이 뜨는 꼴이 된다.
 */
const LEVELS: { value: TalkLevel; label: string }[] = [
  { value: 0, label: "전체" },
  { value: 1, label: "쉬움" },
  { value: 2, label: "보통" },
  { value: 3, label: "어려움" },
];
