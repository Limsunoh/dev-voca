/**
 * 공부 덱의 타입과 구성 규칙.
 *
 * **여기에는 네트워크가 없다.** 순수 타입과 순수 함수뿐이라 서버·화면
 * 어디서 불러도 된다.
 *
 * 카드를 실제로 가져오는 것은 `lib/api/study-deck.ts` 이고 그쪽은 서버
 * 전용이다. 나누는 이유: 화면이 길이에 맞춰 덱을 자르려면 planFor 가
 * 필요한데, 그 함수가 fetch 하는 모듈에 같이 있으면 값으로 import 하는
 * 순간 백엔드 주소를 아는 모듈(api/client.ts)까지 브라우저 번들로
 * 끌려온다. 트리셰이킹에 기대면 개발 모드에서 그대로 샌다.
 */

/** 공부 카드 한 장. 단어든 문장이든 화면에는 같은 모양으로 온다. */
export type StudyCard = {
  /** "w-12" / "s-34". 두 목록에서 온 id 가 겹치므로 접두사를 붙인다. */
  id: string;
  kind: "word" | "sentence";
  /** 앞면. 단어 자체이거나 영어 문장이다. */
  term: string;
  /** 발음기호. 문장에는 없어서 빈 문자열이 온다. */
  reading: string;
  /** 뒷면 첫 줄. 뜻이거나 번역이다. */
  meaning: string;
  /** 뒷면 둘째 줄. 예문이나 쓰이는 맥락. 없으면 빈 문자열. */
  note: string;
  /** 화면 오른쪽 위에 붙는 꼬리표. 분류명이나 종류명. */
  label: string;
  /** 더 보고 싶을 때 갈 곳. */
  href: string;
};

/** 길이 하나의 구성. */
export type DeckPlan = { words: number; sentences: number };

/**
 * 길이별 구성. 백엔드의 STUDY_PLANS 는 문제 수만 알아서 여기 둔다.
 *
 * 전용 API 가 생기면 이 표는 서버로 옮겨간다. 그때까지는 화면이 자른다.
 */
export const DECK_PLANS: Record<string, DeckPlan> = {
  "5m": { words: 4, sentences: 2 },
  "10m": { words: 7, sentences: 4 },
  "30m": { words: 12, sentences: 6 },
};

/**
 * 모르는 길이가 오면 쓸 구성. 화면을 막지 않는다.
 *
 * DECK_PLANS["5m"] 을 참조하지 않고 값을 적어두는 이유: Record 인덱스는
 * 타입이 undefined 를 포함하지 않아서, 나중에 누가 "5m" 키를 지우면
 * 컴파일은 통과하고 런타임에 undefined 가 된다.
 */
const FALLBACK_PLAN: DeckPlan = { words: 4, sentences: 2 };

/** 가장 긴 구성. 미리 받아둘 양을 정하는 데 쓴다. */
export function widestPlan(): DeckPlan {
  return Object.values(DECK_PLANS).reduce(
    (a, b) => ({
      words: Math.max(a.words, b.words),
      sentences: Math.max(a.sentences, b.sentences),
    }),
    FALLBACK_PLAN,
  );
}

/**
 * 미리 받아둔 덱에서 고른 길이만큼 잘라낸다.
 *
 * **자른 뒤에 다시 섞는다.** 섞인 것을 앞에서부터 잘라 쓰면 5분짜리에
 * 단어만 몰리거나 문장만 몰릴 수 있다 - 긴 구성 기준으로 갈마든 순서라
 * 그 앞부분이 짧은 구성에도 맞는다는 보장이 없다.
 */
export function planFor(deck: StudyCard[], length: string): StudyCard[] {
  const plan = DECK_PLANS[length] ?? FALLBACK_PLAN;
  const words = deck.filter((card) => card.kind === "word");
  const sentences = deck.filter((card) => card.kind === "sentence");
  return interleave(
    words.slice(0, plan.words),
    sentences.slice(0, plan.sentences),
  );
}

/**
 * 두 목록을 번갈아 섞는다. 짧은 쪽이 떨어지면 남은 쪽을 이어 붙인다.
 *
 * 단어를 먼저 다 보여주고 문장을 몰아 두면 뒤쪽이 갑자기 길어져서 지친다.
 * 무작위로 섞지 않는 이유는 단어 넷이 연달아 나오는 판이 생기기 때문이다 -
 * 규칙적으로 갈마드는 편이 훑기 좋다.
 *
 * 어느 쪽도 잃거나 중복하지 않는다. a 는 루프가 전부 밀어넣고, 간격
 * 계산에서 남은 b 는 마지막 while 이 붙인다.
 */
export function interleave(a: StudyCard[], b: StudyCard[]): StudyCard[] {
  // **긴 쪽을 기준으로 돌린다.** 한쪽만 기준으로 삼으면 반대로 기운
  // 조합에서 도로 몰린다 - a 기준으로만 세면 단어 1 + 문장 6 이
  // "wssssss" 가 되어, 막으려던 바로 그 모양이 나온다.
  //
  // 그런 조합은 실제로 생긴다. fetchStudyDeck 이 두 목록을 따로 부르고
  // 한쪽이 죽어도 다른 쪽은 쓰기 때문이다.
  const long = a.length >= b.length ? a : b;
  const short = long === a ? b : a;

  const out: StudyCard[] = [];
  // **첫 장은 a 쪽에서 시작한다.** b 가 더 길어 기준이 뒤바뀌어도
  // 마찬가지다 - 덱의 첫 장은 단어인 편이 낫다. 문장은 길어서 첫
  // 화면부터 나오면 훑기가 무겁게 시작한다.
  const leadWithShort = long !== a && a.length > 0;
  if (leadWithShort) out.push(short[0]);
  let si = leadWithShort ? 1 : 0;
  // 짧은 쪽 하나마다 긴 쪽 몇 개가 붙는지.
  const step =
    short.length > 0 ? Math.max(1, Math.round(long.length / short.length)) : 0;

  for (let li = 0; li < long.length; li++) {
    out.push(long[li]);
    if (step > 0 && (li + 1) % step === 0 && si < short.length) {
      out.push(short[si++]);
    }
  }
  // 간격 계산에서 남은 것은 뒤에 붙인다. 이 줄이 있어야 어느 쪽도
  // 잃지 않는다.
  while (si < short.length) out.push(short[si++]);
  return out;
}
