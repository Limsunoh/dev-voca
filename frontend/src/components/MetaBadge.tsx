import Link from "next/link";

/**
 * 난이도·분류 같은 부가 정보 표시.
 *
 * 목록 카드와 상세 화면이 같은 것을 쓴다. 두 벌로 두면 한쪽만 고쳐지고
 * 같은 정보가 화면마다 다르게 보인다.
 */

/**
 * 알약 하나. 난이도·분류·정처기가 전부 이걸 쓴다.
 *
 * 셋이 각자 padding·radius·굵기를 들고 있으면 한 카드에 나란히 섰을 때
 * 높이가 어긋난다. 다크였을 때는 테두리가 그 차이를 가려줬지만, 크림은
 * 테두리를 안 쓰고 채움만으로 서 있어서 1px 차이도 그대로 보인다.
 *
 * 채움은 옅게, 글자는 진하게(디자인 가이드 color-difficulty). 채움을
 * 진하게 하면 목록이 알록달록해진다.
 */
const CHIP_TONES = {
  /** 분류. 회색. */
  sand: { background: "var(--sand)", color: "var(--text-muted)" },
  /** 난이도 1 쉬움. */
  green: { background: "var(--level-1-fill)", color: "var(--level-1-text)" },
  /** 난이도 2 보통. */
  amber: { background: "var(--level-2-fill)", color: "var(--level-2-text)" },
  /** 난이도 3 어려움. */
  coral: { background: "var(--level-3-fill)", color: "var(--level-3-text)" },
  /** 정처기 범위. */
  violet: { background: "var(--exam-fill)", color: "var(--exam-text)" },
} as const;

type ChipTone = keyof typeof CHIP_TONES;

/**
 * 알약의 공통 치수. 줄바꿈 규칙은 담지 않는다. 배지마다 다르다.
 *
 * whitespace-nowrap 을 여기 넣고 CategoryChip 에서 whitespace-normal 을 덧붙여
 * "떼던" 때가 있었다(850e995). 두 클래스가 같이 붙으면 어느 쪽이 이길지는
 * 클래스 순서가 아니라 생성된 CSS 순서로 정해지고, 거기서는 nowrap 이 뒤에
 * 있어 늘 이겼다. 그래서 분류가 한 번도 줄을 안 바꿨다. 이제 nowrap 이 필요한
 * 쪽(CHIP_SHAPE)만 따로 붙인다.
 */
const CHIP_BASE =
  "inline-flex items-center gap-1 px-3 py-1.5 text-xs font-[weight:var(--weight-bold)]";

/** 한 줄로 고정하는 배지(난이도, 정처기). 라벨이 짧게 닫혀 있다. */
const CHIP_SHAPE = `${CHIP_BASE} rounded-full whitespace-nowrap`;

/**
 * 난이도 배지.
 *
 * 셋을 같은 회색으로 두면 "쉬움" 인지 "어려움" 인지 글자를 읽어야 안다.
 * 목록에서는 훑어보는 게 목적이라 그 전에 눈에 들어와야 한다.
 *
 * 색만으로 구분하지는 않는다 - 라벨 글자가 그대로 남아 있어서 색각 이상이
 * 있어도 뜻이 전달된다. 색은 훑어볼 때를 돕는 보조 수단이다.
 *
 * 난이도 3 은 코랄 계열이다(강조색인 갈색과는 다르다). 채움이
 * --level-3-fill(옅은 장미)이라 오류 알림의 진한 코랄 글자와도 모양으로 갈린다.
 * 강조는 "누르는 것" 이고 이건 "읽는 것" 이라 모양(알약 vs 버튼 두께)이
 * 이미 다르다.
 */
export function DifficultyBadge({
  level,
  label,
}: {
  /** 백엔드 Difficulty 값. 1 쉬움 / 2 보통 / 3 어려움. */
  level: number;
  label: string;
}) {
  // 모르는 값이 와도 회색으로 뜬다. 화면이 비지 않는 쪽을 고른다.
  const tone: ChipTone =
    ({ 1: "green", 2: "amber", 3: "coral" } as const)[level as 1 | 2 | 3] ??
    "sand";

  return (
    // 여기는 shrink-0 을 유지한다. 라벨이 choices 로 닫혀 있어 "어려움" 3자가
    // 최대이고, 목록 카드에서는 제목 오른쪽에 놓여서 긴 제목에 눌리면 안 된다.
    <span className={`shrink-0 ${CHIP_SHAPE}`} style={CHIP_TONES[tone]}>
      {label}
    </span>
  );
}

/**
 * 분류 표시.
 *
 * 링크로 만들면 그 분류만 모아 볼 수 있다. 다만 상세에서는 눌러서 목록으로
 * 나가는 동작이라, 밑줄 없는 작은 회색 글자로 두면 눌리는 줄 모른다.
 * 칩 모양을 줘서 누를 수 있는 것으로 보이게 한다.
 */
export function CategoryChip({
  label,
  href,
}: {
  label: string;
  /** 없으면 누를 수 없는 표시로만 쓴다. */
  href?: string;
}) {
  // 빈 라벨이 오면 글자 없는 빈 알약이 그려진다. 호출부마다 막지 않고
  // 여기서 한 번 막는다.
  if (!label) return null;

  // shrink-0 도 whitespace-nowrap 도 쓰지 않는다. 분류 라벨은 "CS
  // 기초(Computer Science)" 처럼 길 수 있어서, 줄어들지도 꺾이지도 못하면
  // 칸보다 넓어졌을 때 그대로 화면 밖으로 나간다. 기본 글꼴에서는 안 드러나고
  // 폰 글자 크기를 200% 로 키운 사용자에게만 보인다(360폭 폰이 180px 폭처럼
  // 그려진다). 막혀 있을 때는 단어·문장 목록 카드가 "코드 리뷰(Code Review)"
  // 폭을 고집해 화면이 233px 로 넓어지고 아래 탭바가 밀렸다. 이제 칸이
  // 모자라면 칩 안에서 줄을 바꾸고, 꺾인 줄은 text-center 로 가운데에 모은다.
  //
  // 모서리는 알약(9999px)이 아니라 한 줄 높이의 절반이다. 위아래 py-1.5 와
  // text-xs 한 줄(1rem)이 1.75rem 이라 그 절반이 0.875rem 이고, 한 줄일 때는
  // 곧 알약이다. 두 줄이 된 알약은 양 끝이 반원으로 부풀어 글자 끝이 둥근
  // 벽에 닿는다(FilterChip 과 같은 판단).
  const shape = `min-w-0 rounded-[0.875rem] text-center ${CHIP_BASE}`;

  // 누를 수 있는 것과 없는 것을 모양으로 가른다. hover 로만 다르게 두면
  // 터치에서는 구분할 단서가 하나도 없다. 같은 줄에 두 종류가 나란히
  // 서는 화면(문장 상세)이 있다.
  //
  // 그 단서는 밑줄이 아니라 두께다. 이 시스템은 경계를 테두리가 아니라
  // 아래 그림자가 맡고(가이드 shape-lift), 누를 수 있는 것만 두께를
  // 갖는다. 밑줄까지 두면 같은 줄에서 표시가 둘(밑줄 + 두께)이 된다.
  if (!href) {
    return (
      <span className={shape} style={CHIP_TONES.sand}>
        {label}
      </span>
    );
  }

  return (
    <Link
      href={href}
      // dv-card dv-card-press: 누르면 두께가 0 이 되고 그만큼 내려앉는다.
      // :active 는 인라인 style 로 쓸 수 없어 globals.css 의 공통 클래스가 맡는다.
      className={`dv-card dv-card-press ${shape} focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus`}
      style={
        {
          background: "var(--paper)",
          color: "var(--text-body)",
          // 쉬는 두께는 --lift 로 넘긴다. box-shadow 를 인라인으로 적으면
          // globals.css 의 :active 가 두께를 0 으로 만드는 것을 이겨버린다.
          "--lift": "var(--lift-card)",
        } as React.CSSProperties
      }
    >
      {label}
    </Link>
  );
}

/**
 * 정처기 범위 표시.
 *
 * 분류 칩과 나란히 서지만 색이 다르다. 분류는 이 항목이 어느 갈래냐는
 * 사실이고, 이건 "시험에 나온다" 는 다른 축이라 같은 회색으로 두면
 * 분류가 하나 더 있는 것처럼 읽힌다.
 *
 * 앰버는 쓰지 않는다. 난이도 "보통" 이 앰버라 한 카드에 같은 색
 * 알약이 둘 뜬다. 새로 넣은 15개 중 8개가 난이도 2 라 흔한 조합이다.
 * 바이올렛은 난이도 세 단계 어디와도 안 겹치고 분류 칩의 회색과도 구분된다.
 *
 * shrink-0 을 쓰는 것은 CategoryChip 과 반대다. 거기는 분류 이름이
 * "CS 기초(Computer Science)" 처럼 길어 줄어들 수 있어야 하지만, 이쪽은
 * "정처기 N과목" 으로 최대 일곱 자라 줄어들 일이 없다. DifficultyBadge 가
 * 같은 이유로 shrink-0 을 유지한다.
 *
 * 과목까지 보여주는 이유: 정처기 준비생은 과목 단위로 공부한다. "정처기"
 * 만 있으면 목록을 훑다가 이게 몇 과목인지 상세로 들어가야 알 수 있다.
 * 라벨이 "3과목 데이터베이스 구축" 처럼 길어서 번호만 잘라 쓴다. 카드에
 * 전부 넣으면 한 줄을 혼자 먹는다.
 */
export function ExamBadge({
  subjectLabel,
}: {
  /** "3과목 데이터베이스 구축" 형태. 과목 미분류면 빈 문자열. */
  subjectLabel?: string;
}) {
  // 라벨 앞의 "N과목" 만 뗀다. 없으면(미분류) 그냥 "정처기".
  const short = subjectLabel?.match(/^\d+과목/)?.[0];

  return (
    <span className={`shrink-0 ${CHIP_SHAPE}`} style={CHIP_TONES.violet}>
      정처기
      {short && (
        // 과목 번호는 부가 정보라 한 단계 흐리게. 색까지 같으면 "정처기
        // 3과목" 이 한 덩어리 이름처럼 읽힌다.
        //
        // 알파를 낮추는 대신 --text-muted 를 쓴다. 크림 바탕에서 opacity 로
        // 흐리면 바탕(연보라 채움)이 비쳐 색이 탁해진다.
        <span style={{ color: "var(--text-muted)" }}>{short}</span>
      )}
    </span>
  );
}
