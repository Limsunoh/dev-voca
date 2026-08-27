/**
 * lib/study-plan.ts 의 순수 로직 테스트.
 *
 * planFor 가 카드를 잃거나 중복하면 사용자는 "5분짜리인데 3장만 나왔다"
 * 로 겪는다. 여기 있는 것은 전부 네트워크를 안 타는 순수 함수라, 값만
 * 넣고 값만 본다.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  DECK_PLANS,
  interleave,
  planFor,
  widestPlan,
  type StudyCard,
} from "../src/lib/study-plan.ts";


/* ---- 헬퍼 ---- */

/** 단어 n 장, 문장 m 장짜리 덱. id 로 어느 장인지 알아볼 수 있게 만든다. */
function makeDeck(words: number, sentences: number): StudyCard[] {
  const card = (kind: "word" | "sentence", n: number): StudyCard => ({
    id: `${kind[0]}-${n}`,
    kind,
    term: `${kind}${n}`,
    reading: kind === "word" ? `[w${n}]` : "",
    meaning: `뜻${n}`,
    note: kind === "sentence" ? `맥락${n}` : "",
    label: "테스트",
    href: `/learn/${kind}s/${n}`,
  });
  return [
    ...Array.from({ length: words }, (_, i) => card("word", i + 1)),
    ...Array.from({ length: sentences }, (_, i) => card("sentence", i + 1)),
  ];
}

const kindsOf = (cards: StudyCard[]) => cards.map((c) => c.kind[0]).join("");
const count = (cards: StudyCard[], kind: string) =>
  cards.filter((c) => c.kind === kind).length;

/** 같은 종류가 연달아 나온 최대 길이. 몰림을 재는 자다. */
function maxRun(cards: StudyCard[]): number {
  let best = 0;
  let run = 0;
  let previous = "";
  for (const card of cards) {
    run = card.kind === previous ? run + 1 : 1;
    previous = card.kind;
    best = Math.max(best, run);
  }
  return best;
}

/* ---- planFor: 잃지도 늘지도 않는가 ---- */

test("planFor: 길이별로 정확히 계획한 장수를 준다", () => {
  const deck = makeDeck(12, 6);
  for (const [length, plan] of Object.entries(DECK_PLANS)) {
    const picked = planFor(deck, length);
    assert.equal(count(picked, "word"), plan.words, `${length} 단어 수`);
    assert.equal(count(picked, "sentence"), plan.sentences, `${length} 문장 수`);
    assert.equal(picked.length, plan.words + plan.sentences);
  }
});

test("planFor: 중복 카드를 만들지 않는다", () => {
  const deck = makeDeck(12, 6);
  for (const length of Object.keys(DECK_PLANS)) {
    const picked = planFor(deck, length);
    assert.equal(new Set(picked.map((c) => c.id)).size, picked.length);
  }
});

test("planFor: 원본 덱을 건드리지 않는다", () => {
  const deck = makeDeck(12, 6);
  const before = deck.map((c) => c.id).join(",");
  planFor(deck, "5m");
  planFor(deck, "30m");
  assert.equal(deck.map((c) => c.id).join(","), before);
});

test("planFor: 뽑힌 카드는 전부 원본 덱에 있던 것이다", () => {
  const deck = makeDeck(12, 6);
  const ids = new Set(deck.map((c) => c.id));
  for (const card of planFor(deck, "30m")) assert.ok(ids.has(card.id));
});

test("planFor: 같은 입력이면 같은 결과 - 순수 함수", () => {
  const deck = makeDeck(12, 6);
  assert.deepEqual(planFor(deck, "10m"), planFor(deck, "10m"));
});

/* ---- planFor: 모자란 덱 ---- */

test("planFor: 빈 덱이면 빈 배열 - 터지지 않는다", () => {
  for (const length of ["5m", "10m", "30m", "99m"]) {
    assert.deepEqual(planFor([], length), []);
  }
});

test("planFor: 요청보다 모자라면 있는 만큼만 준다", () => {
  // 30분(12/6)을 요청했는데 덱에 3/1 뿐이다. 없는 것을 지어내지 않는다.
  const picked = planFor(makeDeck(3, 1), "30m");
  assert.equal(count(picked, "word"), 3);
  assert.equal(count(picked, "sentence"), 1);
  assert.equal(picked.length, 4);
});

test("planFor: 단어만 있으면 단어만 준다", () => {
  const picked = planFor(makeDeck(12, 0), "10m");
  assert.equal(picked.length, DECK_PLANS["10m"].words);
  assert.equal(count(picked, "sentence"), 0);
  assert.equal(kindsOf(picked), "w".repeat(7));
});

test("planFor: 문장만 있으면 문장만 준다", () => {
  const picked = planFor(makeDeck(0, 6), "10m");
  assert.equal(picked.length, DECK_PLANS["10m"].sentences);
  assert.equal(count(picked, "word"), 0);
});

test("planFor: 카드가 딱 한 장이어도 그 한 장이 나온다", () => {
  assert.equal(planFor(makeDeck(1, 0), "30m").length, 1);
  assert.equal(planFor(makeDeck(0, 1), "30m").length, 1);
});

/* ---- planFor: 모르는 길이 ---- */

test("planFor: 모르는 길이는 가장 짧은 구성(5m)으로 떨어진다", () => {
  const deck = makeDeck(12, 6);
  const expected = planFor(deck, "5m");
  for (const length of ["99m", "", "1h", "5M", " 5m", "5m ", "0m", "-5m"]) {
    assert.deepEqual(
      planFor(deck, length),
      expected,
      `length=${JSON.stringify(length)} 이 5m 로 안 떨어졌다`,
    );
  }
});

test("planFor: null/undefined 가 length 로 새어 들어와도 5m 로 떨어진다", () => {
  // 타입은 string 이지만 서버 응답이나 URL 파라미터에서 온 값은 런타임에
  // 무엇이든 될 수 있다. 화면이 안 막히는지만 본다.
  const deck = makeDeck(12, 6);
  const expected = planFor(deck, "5m");
  for (const bad of [null, undefined, 0, NaN, false]) {
    assert.deepEqual(planFor(deck, bad as unknown as string), expected);
  }
});

test("planFor: Object.prototype 의 이름이 길이로 와도 배열이 나온다", () => {
  // DECK_PLANS 는 그냥 객체 리터럴이라 "constructor"/"toString" 이
  // 상속 프로퍼티로 잡힌다. ?? 는 undefined 만 걸러서 함수가 통과한다.
  // 그 함수에는 .words 가 없어 slice(0, undefined) 가 되므로 자르기가
  // 통째로 풀린다 - 터지지는 않지만 계획 밖의 장수가 나온다.
  const deck = makeDeck(12, 6);
  for (const evil of ["constructor", "toString", "valueOf", "__proto__"]) {
    const picked = planFor(deck, evil);
    assert.ok(
      Array.isArray(picked),
      `length=${evil} 에서 배열이 아닌 것이 나왔다`,
    );
  }
});

/* ---- interleave: 몰리는가 ---- */

test("interleave: 균형 잡힌 구성에서는 단어가 셋 이상 안 붙는다", () => {
  for (const length of Object.keys(DECK_PLANS)) {
    const picked = planFor(makeDeck(12, 6), length);
    assert.ok(
      maxRun(picked) <= 3,
      `${length} 에서 같은 종류가 ${maxRun(picked)} 장 연달아 나왔다: ${kindsOf(picked)}`,
    );
  }
});

test("interleave: 문장이 하나뿐이면 단어가 앞에 통째로 몰린다", () => {
  // step = round(12/1) = 12 라 12장째 뒤에 문장 하나가 붙는다.
  // 훑는 사람 입장에서는 단어 열두 장을 연달아 본 뒤 문장이 나온다.
  const picked = planFor(makeDeck(12, 1), "30m");
  assert.equal(picked.length, 13);
  assert.equal(kindsOf(picked), "wwwwwwwwwwwws");
  assert.equal(maxRun(picked), 12);
});

test("interleave: 단어가 한 장뿐이면 더 나눌 수가 없다", () => {
  // 긴 쪽(문장 6)을 기준으로 돌려도 짧은 쪽이 한 장이라 끼울 자리가
  // 하나뿐이다. 이건 알고리즘이 아니라 입력의 한계다.
  const picked = planFor(makeDeck(1, 9), "30m");
  assert.equal(picked.length, 7); // 단어 1 + 문장 6(30m 상한)
  assert.equal(picked[0].kind, "word"); // 첫 장은 그래도 단어
  assert.equal(maxRun(picked), 6);
});

test("interleave: 단어가 0 이면 문장이 순서대로 다 나온다", () => {
  const picked = planFor(makeDeck(0, 6), "30m");
  assert.equal(kindsOf(picked), "ssssss");
  assert.deepEqual(
    picked.map((c) => c.id),
    ["s-1", "s-2", "s-3", "s-4", "s-5", "s-6"],
  );
});

test("interleave: 5분 구성(4/2)의 순서를 못으로 박는다", () => {
  // step = round(4/2) = 2. 단어 둘마다 문장 하나.
  assert.equal(kindsOf(planFor(makeDeck(12, 6), "5m")), "wwswws");
});

test("interleave: 10분 구성(7/4)의 순서를 못으로 박는다", () => {
  // step = max(1, round(7/4)) = 2. 마지막 문장 하나는 뒤에 붙는다.
  assert.equal(kindsOf(planFor(makeDeck(12, 6), "10m")), "wwswwswwsws");
});

test("interleave: 30분 구성(12/6)의 순서를 못으로 박는다", () => {
  assert.equal(kindsOf(planFor(makeDeck(12, 6), "30m")), "wwswwswwswwswwswws");
});

test("interleave: 어떤 조합에서도 카드 수가 보존되고 중복이 없다", () => {
  for (let words = 0; words <= 14; words++) {
    for (let sentences = 0; sentences <= 8; sentences++) {
      for (const length of ["5m", "10m", "30m"]) {
        const plan = DECK_PLANS[length];
        const picked = planFor(makeDeck(words, sentences), length);
        const expected =
          Math.min(words, plan.words) + Math.min(sentences, plan.sentences);
        assert.equal(
          picked.length,
          expected,
          `${words}/${sentences} ${length}: ${picked.length} != ${expected}`,
        );
        assert.equal(new Set(picked.map((c) => c.id)).size, picked.length);
      }
    }
  }
});

test("interleave: 각 종류 안에서는 원래 순서가 유지된다", () => {
  const picked = planFor(makeDeck(12, 6), "30m");
  const words = picked.filter((c) => c.kind === "word").map((c) => c.id);
  const sentences = picked.filter((c) => c.kind === "sentence").map((c) => c.id);
  assert.deepEqual(words, [
    "w-1", "w-2", "w-3", "w-4", "w-5", "w-6",
    "w-7", "w-8", "w-9", "w-10", "w-11", "w-12",
  ]);
  assert.deepEqual(sentences, ["s-1", "s-2", "s-3", "s-4", "s-5", "s-6"]);
});

/* ---- DECK_PLANS ---- */

test("DECK_PLANS: 길이가 길수록 카드가 늘어난다", () => {
  const total = (k: string) => DECK_PLANS[k].words + DECK_PLANS[k].sentences;
  assert.ok(total("5m") < total("10m"));
  assert.ok(total("10m") < total("30m"));
});

test("DECK_PLANS: 30m 가 모든 길이를 덮는다 - fetchStudyDeck 이 이만큼 받는다", () => {
  // 이게 깨지면 짧은 길이는 되는데 긴 길이만 카드가 모자라는, 눈에 잘
  // 안 띄는 형태로 나온다.
  for (const plan of Object.values(DECK_PLANS)) {
    assert.ok(plan.words <= DECK_PLANS["30m"].words);
    assert.ok(plan.sentences <= DECK_PLANS["30m"].sentences);
  }
});


/* ---- interleave 를 직접 부른다 ---- */

const W = (n: number) => makeDeck(n, 0);
const S = (n: number) => makeDeck(0, n).map((c) => c);

test("interleave: 어느 쪽도 잃거나 중복하지 않는다 (0..12 x 0..12)", () => {
  for (let a = 0; a <= 12; a++) {
    for (let b = 0; b <= 12; b++) {
      const out = interleave(W(a), S(b));
      assert.equal(out.length, a + b, `${a}+${b}`);
      assert.equal(new Set(out.map((c) => c.id)).size, a + b);
      assert.equal(count(out, "word"), a);
      assert.equal(count(out, "sentence"), b);
    }
  }
});

test("interleave: 양쪽이 다 비면 빈 배열", () => {
  assert.deepEqual(interleave([], []), []);
});

test("interleave: 한쪽이 비면 다른 쪽이 순서 그대로 나온다", () => {
  assert.deepEqual(interleave(W(3), []).map((c) => c.id), ["w-1", "w-2", "w-3"]);
  assert.deepEqual(interleave([], S(3)).map((c) => c.id), ["s-1", "s-2", "s-3"]);
});

test("interleave: 각 입력의 상대 순서가 보존된다", () => {
  for (const [a, b] of [[12, 6], [1, 9], [9, 1], [5, 5], [7, 4]]) {
    const out = interleave(W(a), S(b));
    assert.deepEqual(
      out.filter((c) => c.kind === "word").map((c) => c.id),
      W(a).map((c) => c.id),
      `${a}/${b} 단어 순서`,
    );
    assert.deepEqual(
      out.filter((c) => c.kind === "sentence").map((c) => c.id),
      S(b).map((c) => c.id),
      `${a}/${b} 문장 순서`,
    );
  }
});

test("interleave: 첫 장은 항상 a 쪽에서 나온다(a 가 있으면)", () => {
  // 공부 화면의 첫 카드가 늘 단어라는 뜻이다. 문장으로 시작하면 첫인상이
  // 무거워진다.
  for (let b = 0; b <= 8; b++) {
    assert.equal(interleave(W(1), S(b))[0].kind, "word", `b=${b}`);
  }
});

test("interleave: b 가 a 보다 많아도 몰리지 않는다", () => {
  // 긴 쪽을 기준으로 돌린다. a 기준으로만 세면 a 를 다 쓴 뒤 남은 b 가
  // 줄줄이 붙어서(wswsssssssss, 9연속) 막으려던 모양이 그대로 나온다.
  //
  // 이 조합은 실제로 생긴다 - fetchStudyDeck 이 두 목록을 따로 부르고
  // 단어 쪽만 죽으면 문장이 훨씬 많아진다.
  const picked = interleave(W(2), S(10));
  assert.equal(kindsOf(picked), "wssssswsssss");
  assert.equal(picked[0].kind, "word");
  assert.ok(maxRun(picked) <= 5, `최대 연속이 ${maxRun(picked)} 장이다`);
  assert.equal(picked.length, 12); // 아무것도 안 잃는다
});

test("widestPlan: 모든 길이를 덮는다", () => {
  const widest = widestPlan();
  for (const plan of Object.values(DECK_PLANS)) {
    assert.ok(plan.words <= widest.words);
    assert.ok(plan.sentences <= widest.sentences);
  }
  assert.deepEqual(widest, { words: 12, sentences: 6 });
});

test("widestPlan: DECK_PLANS 가 비어도 기본 구성을 준다", () => {
  // reduce 에 초기값이 있어서 빈 표에서도 안 터진다. 초기값을 빼면
  // TypeError 가 나므로, 그 방어가 살아있는지 본다.
  assert.ok(widestPlan().words > 0);
});

/* ---- 서버 전용 모듈이 안 딸려오는지 ---- */

test("study-plan.ts 는 아무것도 import 하지 않는다 - 유출 회귀 방지", () => {
  // 이 브랜치에서 실제로 났던 사고를 못 박는다.
  //
  // 처음에는 planFor 가 lib/api/study-deck.ts 에 있었다. 화면(클라이언트
  // 컴포넌트)이 그걸 값으로 import 하자 같은 모듈의 최상단 import 를 타고
  // api/client.ts 까지 브라우저 번들로 끌려왔고, 백엔드 주소와 경로가
  // 클라이언트 청크에 실렸다. 빌드 산출물에서 확인된 사고다.
  //
  // 그래서 순수 로직을 이 파일로 뺐다. **여기에 import 가 하나라도
  // 생기면 그 사고가 되살아날 수 있다.** 타입만 가져오는 import 도
  // 막는다 - `import type` 이 아닌 형태로 바뀌는 순간 같은 일이 난다.
  //
  // ts-resolve.mjs 가 테스트에서 "server-only" 를 빈 모듈로 치환하므로,
  // 그 방어선은 여기서 확인할 수 없다. 이 검사가 그 대신이다.
  const source = readFileSync(
    new URL("../src/lib/study-plan.ts", import.meta.url),
    "utf8",
  );
  const imports = source
    .split("\n")
    .filter((line) => /^\s*import\s/.test(line))
    .map((line) => line.trim());

  assert.deepEqual(
    imports,
    [],
    `study-plan.ts 에 import 가 생겼다:\n${imports.join("\n")}`,
  );
});
