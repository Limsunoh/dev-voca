/**
 * 선택지 목록(fetchChoices)만 Next 데이터 캐시에 한 시간 두고, 나머지 요청은 전부
 * 캐시하지 않는지 본다. fetch 에 넘긴 옵션을 그대로 읽는다.
 *
 * 실행: cd frontend && npm test
 *
 * 깨지면 생기는 일.
 *   - 일반 요청에 cache: "no-store" 가 빠지면 검수 취소된 단어(is_reviewed)가 옛 응답으로
 *     계속 보인다(client.ts request 주석).
 *   - fetchChoices 에 no-store 가 같이 붙으면 Next 는 no-store 를 따라 캐시가 꺼진다.
 *     둘을 같이 주면 Next 가 경고도 낸다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it } from "node:test";

let inits: { path: string; init: RequestInit & { next?: { revalidate?: number } } }[] = [];
let status = 200;

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
  inits.push({ path: new URL(String(input)).pathname, init: (init ?? {}) as never });
  return new Response(JSON.stringify(status === 200 ? [{ value: "a", label: "가" }] : { detail: "x" }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}) as typeof fetch;

const realError = console.error;
console.error = () => {};

after(() => {
  globalThis.fetch = realFetch;
  console.error = realError;
});

const { fetchChoices, fetchDetail, request } = await import("./client");
const { getCategories, getDifficulties, getExamSubjects } = await import("./vocab");
const { getSentenceCategories, getSentenceDifficulties, getSentenceKinds } = await import("./sentences");

beforeEach(() => {
  inits = [];
  status = 200;
});

function assertCachedHour(init: RequestInit & { next?: { revalidate?: number } }) {
  assert.deepEqual(init.next, { revalidate: 3600 });
  assert.equal(init.cache, undefined, "no-store 가 같이 붙어 캐시가 꺼진다");
  assert.ok(init.signal, "시간 제한이 빠졌다");
}

function assertNoStore(init: RequestInit & { next?: unknown }) {
  assert.equal(init.cache, "no-store");
  assert.equal(init.next, undefined);
}

describe("fetchChoices", () => {
  it("한 시간 캐시하고 no-store 를 붙이지 않는다", async () => {
    const choices = await fetchChoices("/api/vocab/words/categories/");
    assert.deepEqual(choices, [{ value: "a", label: "가" }]);
    assert.equal(inits.length, 1);
    assertCachedHour(inits[0].init);
  });

  it("단어·문장의 선택지 목록 함수가 전부 이 길로 간다", async () => {
    await Promise.all([
      getCategories(),
      getDifficulties(),
      getExamSubjects(),
      getSentenceCategories(),
      getSentenceDifficulties(),
      getSentenceKinds(),
    ]);
    assert.equal(inits.length, 6);
    for (const { path, init } of inits) {
      assert.match(path, /\/(categories|difficulties|exam_subjects|kinds)\/$/, path);
      assertCachedHour(init);
    }
  });

  it("실패하면 빈 배열이고 던지지 않는다", async () => {
    status = 500;
    assert.deepEqual(await fetchChoices("/api/vocab/words/categories/"), []);
  });
});

describe("그 밖의 요청은 캐시하지 않는다", () => {
  it("request GET·POST·토큰 실은 요청", async () => {
    await request("/api/vocab/words/");
    await request("/api/learning/daily/", { token: "t" });
    await request("/api/accounts/token/renew/", { method: "POST", token: "t" });
    assert.equal(inits.length, 3);
    for (const { init } of inits) assertNoStore(init);
  });

  it("fetchDetail(단어 상세)", async () => {
    await fetchDetail("/api/vocab/words/", "12");
    assertNoStore(inits[0].init);
  });

  it("revalidate 를 0 으로 줘도 no-store 로 새지 않고 그 값을 그대로 쓴다", async () => {
    await request("/x/", { revalidate: 0 });
    assert.deepEqual(inits[0].init.next, { revalidate: 0 });
  });
});
