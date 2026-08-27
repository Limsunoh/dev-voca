/**
 * lib/api/study-deck.ts 의 가져오기 경로 테스트.
 *
 * global fetch 를 갈아끼워 실제 경로(getWords/getSentences -> request ->
 * fetch)를 그대로 태운다. 목록 응답을 카드로 옮기는 과정에서 필드가
 * 어긋나면 화면에는 빈 카드로 나오는데, 화면을 열어봐야만 보이는 종류라
 * 여기서 값으로 못을 박는다.
 *
 * 이 파일은 --experimental-transform-types 가 필요하다. api/client.ts 의
 * ApiError 가 parameter property(`readonly status: number`)를 써서
 * strip-only 모드로는 못 읽는다. 실행 명령은 tests/README.md 참고.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { fetchStudyDeck } from "../src/lib/api/study-deck.ts";
import { DECK_PLANS, planFor, type StudyCard } from "../src/lib/study-plan.ts";

const count = (cards: StudyCard[], kind: string) =>
  cards.filter((c) => c.kind === kind).length;

/** fetch 를 가로채 준비한 목록을 돌려준다. 되돌리는 함수를 준다. */
function stubFetch(handler: (url: string) => unknown) {
  const original = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = (async (input: string | URL | Request) => {
    const url = String(input);
    calls.push(url);
    const body = handler(url);
    if (body instanceof Error) throw body;
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;
  return {
    calls,
    restore: () => {
      globalThis.fetch = original;
    },
  };
}

const page = (results: unknown[]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});

const rawWords = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    id: i + 1,
    term: `term${i + 1}`,
    pronunciation: `[t${i + 1}]`,
    meaning: `뜻${i + 1}`,
    difficulty: 1,
    difficulty_label: "쉬움",
    category: "devops",
    category_label: "데브옵스",
  }));

const rawSentences = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    id: i + 1,
    text: `sentence ${i + 1}`,
    translation: `번역${i + 1}`,
    kind: "phrase",
    kind_label: "실무 표현",
    context: `맥락${i + 1}`,
    difficulty: 1,
    difficulty_label: "쉬움",
    category: "devops",
    category_label: "데브옵스",
  }));

test("fetchStudyDeck: 가장 긴 구성(12/6)만큼만 잘라 온다", async () => {
  // 백엔드 페이지 크기가 커서 50장이 와도 18장만 쓴다.
  const stub = stubFetch((url) =>
    page(url.includes("sentences") ? rawSentences(50) : rawWords(50)),
  );
  try {
    const deck = await fetchStudyDeck();
    assert.equal(count(deck, "word"), 12);
    assert.equal(count(deck, "sentence"), 6);
  } finally {
    stub.restore();
  }
});

test("fetchStudyDeck: id 에 접두사를 붙여 단어·문장 충돌을 막는다", async () => {
  // 두 목록의 id 는 둘 다 1 부터 시작한다. 접두사가 없으면 React key 가
  // 겹쳐서 카드가 사라지거나 엉뚱한 것이 다시 그려진다.
  const stub = stubFetch((url) =>
    page(url.includes("sentences") ? rawSentences(6) : rawWords(12)),
  );
  try {
    const deck = await fetchStudyDeck();
    assert.equal(new Set(deck.map((c) => c.id)).size, deck.length);
    assert.ok(deck.every((c) => /^[ws]-\d+$/.test(c.id)));
  } finally {
    stub.restore();
  }
});

test("fetchStudyDeck: 필드가 종류별로 제대로 옮겨진다", async () => {
  const stub = stubFetch((url) =>
    page(url.includes("sentences") ? rawSentences(1) : rawWords(1)),
  );
  try {
    const deck = await fetchStudyDeck();
    const word = deck.find((c) => c.kind === "word");
    const sentence = deck.find((c) => c.kind === "sentence");
    assert.ok(word && sentence);

    assert.equal(word.term, "term1");
    assert.equal(word.reading, "[t1]");
    assert.equal(word.meaning, "뜻1");
    assert.equal(word.note, ""); // 목록 API 는 예문을 안 준다
    assert.equal(word.href, "/learn/words/1");

    assert.equal(sentence.term, "sentence 1");
    assert.equal(sentence.reading, ""); // 문장에는 발음기호가 없다
    assert.equal(sentence.meaning, "번역1");
    assert.equal(sentence.note, "맥락1");
    assert.equal(sentence.href, "/learn/sentences/1");
  } finally {
    stub.restore();
  }
});

test("fetchStudyDeck: 빈 문자열 필드가 와도 그대로 통과한다", async () => {
  // 발음기호·맥락은 백엔드에서 빈 문자열로 온다. StudyCard 가 optional 이
  // 아니라 필수 필드라, 여기서 undefined 가 새면 화면이 "undefined" 를
  // 글자로 그린다.
  const stub = stubFetch((url) =>
    page(
      url.includes("sentences")
        ? [{ ...rawSentences(1)[0], context: "", kind_label: "" }]
        : [{ ...rawWords(1)[0], pronunciation: "", category_label: "" }],
    ),
  );
  try {
    const deck = await fetchStudyDeck();
    for (const card of deck) {
      assert.equal(typeof card.reading, "string");
      assert.equal(typeof card.note, "string");
      assert.equal(typeof card.label, "string");
    }
  } finally {
    stub.restore();
  }
});

test("fetchStudyDeck: 한쪽이 죽어도 다른 쪽은 온다", async () => {
  const stub = stubFetch((url) =>
    url.includes("sentences") ? new Error("문장 API 죽음") : page(rawWords(12)),
  );
  try {
    const deck = await fetchStudyDeck();
    assert.equal(count(deck, "word"), 12);
    assert.equal(count(deck, "sentence"), 0);
  } finally {
    stub.restore();
  }
});

test("fetchStudyDeck: 둘 다 죽으면 빈 배열 - 공부 단계만 건너뛴다", async () => {
  const stub = stubFetch(() => new Error("백엔드 죽음"));
  try {
    assert.deepEqual(await fetchStudyDeck(), []);
  } finally {
    stub.restore();
  }
});

test("fetchStudyDeck: results 가 없는 응답에도 안 터진다", async () => {
  const stub = stubFetch(() => ({ count: 0, next: null, previous: null }));
  try {
    assert.deepEqual(await fetchStudyDeck(), []);
  } finally {
    stub.restore();
  }
});

test("fetchStudyDeck: 두 요청이 같은 shuffle 시드를 쓴다", async () => {
  // 시드가 다르면 단어와 문장이 서로 다른 무작위 순서로 와서, 같은 판을
  // 두 번 열었을 때 겹치는 정도가 들쭉날쭉해진다.
  const stub = stubFetch(() => page([]));
  try {
    await fetchStudyDeck();
    assert.equal(stub.calls.length, 2);
    const seeds = stub.calls.map((url) =>
      new URL(url).searchParams.get("shuffle"),
    );
    assert.ok(seeds[0], "shuffle 시드가 안 붙었다");
    assert.equal(seeds[0], seeds[1]);
  } finally {
    stub.restore();
  }
});

test("fetchStudyDeck 결과를 planFor 로 다시 잘라도 계획대로다", async () => {
  // 실제 흐름: 서버가 fetchStudyDeck 으로 18장을 받아 내려보내고,
  // 화면이 고른 길이로 planFor 를 부른다. 이미 갈마든 것을 다시 자른다.
  const stub = stubFetch((url) =>
    page(url.includes("sentences") ? rawSentences(6) : rawWords(12)),
  );
  try {
    const deck = await fetchStudyDeck();
    for (const [length, plan] of Object.entries(DECK_PLANS)) {
      const picked = planFor(deck, length);
      assert.equal(count(picked, "word"), plan.words, `${length} 단어`);
      assert.equal(count(picked, "sentence"), plan.sentences, `${length} 문장`);
      assert.equal(new Set(picked.map((c) => c.id)).size, picked.length);
    }
  } finally {
    stub.restore();
  }
});
