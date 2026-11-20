/**
 * getDailyWords 가 낡은 count 를 받았을 때.
 *
 * 실행: cd frontend && npx tsx --test src/lib/api/daily-words-stale-count.test.mts
 *
 * 백엔드는 목록 1페이지의 count 를 5분 동안 기억한다(backend/apps/vocab/
 * pagination.py). 그새 단어가 지워지면 1페이지는 실제보다 큰 count 를 주고,
 * 그 count 로 계산한 뒤쪽 페이지는 404 가 난다. 이때 묶음 전체를 버리면 홈의
 * 오늘의 단어가 통째로 빠진다. 받은 만큼은 보여야 한다.
 */
import assert from "node:assert/strict";
import { after, describe, it } from "node:test";

import { getDailyWords, HOME_WORDS, type WordListItem } from "./vocab";

const DAY_MS = 86_400_000;
const KST_OFFSET_MS = 9 * 60 * 60 * 1000;
const PAGE_SIZE = 20;

const realFetch = globalThis.fetch;
const realNow = Date.now;
const realWarn = console.warn;
after(() => {
  globalThis.fetch = realFetch;
  Date.now = realNow;
  console.warn = realWarn;
});

function makeWord(index: number): WordListItem {
  return {
    id: index,
    term: `w${index}`,
    pronunciation: "",
    reading: "",
    meaning: `뜻${index}`,
    difficulty: 1,
    difficulty_label: "쉬움",
    category: "",
    category_label: "",
  };
}

/**
 * 실제로는 actual 개인데 1페이지는 remembered 개라고 답하는 백엔드.
 * 뒤쪽 페이지는 실제 개수로 판단해 범위 밖이면 failStatus 를 준다.
 */
function installStaleBackend(remembered: number, actual: number, failStatus = 404): void {
  const lastPage = Math.ceil(actual / PAGE_SIZE);
  globalThis.fetch = (async (url: string | URL | Request) => {
    const href = typeof url === "string" ? url : url.toString();
    const page = Number(new URL(href).searchParams.get("page") ?? "1");
    if (page > lastPage) {
      return new Response(JSON.stringify({ detail: "잘못된 페이지입니다." }), {
        status: failStatus,
        headers: { "Content-Type": "application/json" },
      });
    }
    const start = (page - 1) * PAGE_SIZE;
    const results = Array.from(
      { length: Math.min(PAGE_SIZE, actual - start) },
      (_, i) => makeWord(start + i),
    );
    return new Response(
      JSON.stringify({ count: page === 1 ? remembered : actual, next: null, previous: null, results }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }) as typeof fetch;
}

/** 시작점(day % count)이 start 가 되는 날로 시계를 맞춘다. */
function setStart(start: number, count: number): void {
  const day = count * 40 + start;
  Date.now = () => day * DAY_MS - KST_OFFSET_MS + DAY_MS / 2;
}

describe("getDailyWords - 낡은 count", () => {
  it("count 로 계산한 쪽이 없으면(404) 받은 만큼만 돌려준다", async () => {
    // 566개를 기억한 뒤 10개가 지워졌다. 시작점 562 는 29쪽인데 실제로는 28쪽까지다.
    installStaleBackend(566, 556);
    setStart(562, 566);
    const warnings: unknown[] = [];
    console.warn = (...args: unknown[]) => warnings.push(args);

    const words = await getDailyWords(HOME_WORDS);

    // 562~565 는 없는 29쪽이라 빠지고, 끝을 돌아 0, 1, 2 는 1쪽에서 온다.
    assert.deepEqual(words.map((w) => w.id), [0, 1, 2]);
    assert.equal(warnings.length, 1);
  });

  it("404 가 아닌 실패는 그대로 던진다", async () => {
    installStaleBackend(566, 556, 500);
    setStart(562, 566);
    console.warn = () => {};

    await assert.rejects(getDailyWords(HOME_WORDS));
  });
});
