/**
 * getDailyWords 의 페이지 계산 검증.
 *
 * 실행: cd frontend && npx tsx --test src/lib/api/daily-words.test.mts
 *
 * 러너를 새로 들이지 않으려고 node 내장 test 러너를 쓴다. tsx 는 확장자 없는
 * 임포트("./client")를 풀어주기 위해서만 필요하다.
 *
 * 가짜 백엔드는 DRF PageNumberPagination 을 그대로 흉내낸다. 범위 밖 페이지에
 * 404 를 주는 것이 핵심이다 - 실제 백엔드가 그렇고(page=30 -> 404), 그걸
 * 안 흉내내면 페이지 계산 실수가 조용히 묻힌다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it } from "node:test";

import { getDailyWords, HOME_WORDS, type WordListItem } from "./vocab";

const DAY_MS = 86_400_000;
const KST_OFFSET_MS = 9 * 60 * 60 * 1000;

const realFetch = globalThis.fetch;
const realNow = Date.now;
after(() => {
  globalThis.fetch = realFetch;
  Date.now = realNow;
});

/** 요청된 페이지 번호를 순서대로 기록한다. 요청 수·중복 요청을 보려면 필요하다. */
let requested: number[] = [];
beforeEach(() => {
  requested = [];
});

/**
 * DRF 목록 API 흉내. 단어 total 개, 페이지당 pageSize 개.
 *
 * 범위 밖 페이지는 실제 백엔드와 같이 404 를 준다.
 */
function installFakeBackend(total: number, pageSize = 20): void {
  const lastPage = Math.max(1, Math.ceil(total / pageSize));

  globalThis.fetch = (async (url: string | URL | Request) => {
    const href = typeof url === "string" ? url : url.toString();
    const page = Number(new URL(href).searchParams.get("page") ?? "1");
    requested.push(page);

    if (!Number.isInteger(page) || page < 1 || (total > 0 && page > lastPage)) {
      return new Response(JSON.stringify({ detail: "잘못된 페이지입니다." }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }

    const startIdx = (page - 1) * pageSize;
    const results = Array.from(
      { length: Math.max(0, Math.min(pageSize, total - startIdx)) },
      (_, i) => makeWord(startIdx + i),
    );
    return new Response(
      JSON.stringify({
        count: total,
        next: page < lastPage ? `?page=${page + 1}` : null,
        previous: page > 1 ? `?page=${page - 1}` : null,
        results,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }) as typeof fetch;
}

/** 전역 인덱스가 곧 id 다. 어느 자리 단어가 나왔는지 바로 알 수 있다. */
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

/** day 번째 날의 정오(KST)로 시계를 고정한다. day 가 곧 코드의 day 값이 된다. */
function setDay(day: number): void {
  Date.now = () => day * DAY_MS - KST_OFFSET_MS + DAY_MS / 2;
}

describe("getDailyWords - 날짜 전수 스윕", () => {
  it("566개·20개씩에서 566일 전부 5개를 채우고 중복이 없다", async () => {
    const total = 566;
    installFakeBackend(total);

    const failures: string[] = [];
    for (let day = 0; day < total; day += 1) {
      setDay(day);
      const words = await getDailyWords(5);

      if (words.length !== 5) {
        failures.push(`day=${day} start=${day % total} 개수=${words.length}`);
        continue;
      }
      const ids = words.map((w) => w.id);
      if (new Set(ids).size !== ids.length) {
        failures.push(`day=${day} start=${day % total} 중복 ids=${ids}`);
      }
      // 목록 순서대로 연속이어야 한다. 끝에 닿으면 앞으로 돈다.
      const expected = Array.from({ length: 5 }, (_, i) => (day + i) % total);
      if (ids.join() !== expected.join()) {
        failures.push(`day=${day} 순서 어긋남 ids=${ids} 기대=${expected}`);
      }
    }

    assert.equal(
      failures.length,
      0,
      `566일 중 ${failures.length}일 실패:\n${failures.slice(0, 20).join("\n")}`,
    );
  });

  it("566일 전부 404 를 내지 않는다 (29페이지가 마지막)", async () => {
    const total = 566;
    installFakeBackend(total);

    const bad: string[] = [];
    for (let day = 0; day < total; day += 1) {
      setDay(day);
      requested = [];
      await getDailyWords(5).catch((e: unknown) => {
        bad.push(`day=${day} 예외=${(e as Error).message} 요청=${requested}`);
        return [];
      });
      const over = requested.filter((p) => p > 29);
      if (over.length > 0) bad.push(`day=${day} 범위 밖 페이지 요청=${over}`);
    }

    assert.equal(bad.length, 0, `실패:\n${bad.slice(0, 20).join("\n")}`);
  });

  it("566일 전부 요청이 3장 이하이고 같은 페이지를 두 번 받지 않는다", async () => {
    const total = 566;
    installFakeBackend(total);

    const bad: string[] = [];
    for (let day = 0; day < total; day += 1) {
      setDay(day);
      requested = [];
      await getDailyWords(5);
      if (requested.length > 3) {
        bad.push(`day=${day} 요청 ${requested.length}장 ${requested}`);
      }
      if (new Set(requested).size !== requested.length) {
        bad.push(`day=${day} 같은 페이지 중복 요청 ${requested}`);
      }
    }

    assert.equal(bad.length, 0, `실패:\n${bad.slice(0, 20).join("\n")}`);
  });
});

describe("getDailyWords - 홈이 실제로 쓰는 값", () => {
  // 위 스윕은 5로 돈다. 홈은 HOME_WORDS 로 부르는데, 묶음이 걸치는 페이지
  // 수가 그 값에 따라 달라지므로 실제 값으로도 한 바퀴 돌려야 한다.
  // 이 테스트가 없으면 HOME_WORDS 를 25 로 올려도 초록불이 나온다.
  it(`HOME_WORDS(${HOME_WORDS}) 로 566일 전부 채우고 중복·404 가 없다`, async () => {
    const total = 566;
    installFakeBackend(total);
    const lastPage = Math.ceil(total / 20);

    const bad: string[] = [];
    for (let day = 0; day < total; day += 1) {
      setDay(day);
      requested = [];
      let words: WordListItem[] = [];
      try {
        words = await getDailyWords(HOME_WORDS);
      } catch (e) {
        bad.push(`day=${day} 예외=${(e as Error).message} 요청=${requested}`);
        continue;
      }
      if (words.length !== HOME_WORDS) {
        bad.push(`day=${day} 개수=${words.length} 기대=${HOME_WORDS}`);
      }
      const ids = words.map((w) => w.id);
      if (new Set(ids).size !== ids.length) bad.push(`day=${day} 중복=${ids}`);
      const expected = Array.from(
        { length: HOME_WORDS },
        (_, i) => (day + i) % total,
      );
      if (ids.join() !== expected.join()) {
        bad.push(`day=${day} 순서 어긋남 ids=${ids}`);
      }
      const over = requested.filter((p) => p > lastPage);
      if (over.length > 0) bad.push(`day=${day} 범위 밖=${over}`);
    }

    assert.equal(
      bad.length,
      0,
      `실패 ${bad.length}건:\n${bad.slice(0, 10).join("\n")}`,
    );
  });

  // 요청 수는 곧 비용이다. 값을 올릴 때 여기가 같이 빨개져야 "몇 장 더
  // 나가는지" 를 보고 결정하게 된다.
  //
  // 세 장인 이유: count 를 알려면 1페이지를 먼저 받아야 하는데, 묶음이
  // 그 페이지를 안 지나가면 그것은 버려지고 필요한 두 장을 새로 받는다.
  // 566개 기준으로 그런 날이 174일이다.
  it(`HOME_WORDS(${HOME_WORDS}) 는 하루 세 장 안에 끝난다`, async () => {
    const total = 566;
    installFakeBackend(total);

    let worst = 0;
    const dist = new Map<number, number>();
    for (let day = 0; day < total; day += 1) {
      setDay(day);
      requested = [];
      await getDailyWords(HOME_WORDS);
      worst = Math.max(worst, requested.length);
      dist.set(requested.length, (dist.get(requested.length) ?? 0) + 1);
    }

    const summary = [...dist]
      .sort((a, b) => a[0] - b[0])
      .map(([n, days]) => `${n}장 ${days}일`)
      .join(" / ");
    assert.ok(worst <= 3, `최대 ${worst}장을 받았다 (${summary})`);
  });
});

describe("getDailyWords - 단어 수 경계", () => {
  // 41개는 마지막 페이지에 1개만 남는 조건. 시작점이 뒤쪽이면 2·3·1 세 장을 탄다.
  for (const total of [1, 2, 3, 5, 19, 20, 21, 40, 41, 42, 60, 566]) {
    it(`단어 ${total}개일 때 모든 날 min(5, ${total})개를 채운다`, async () => {
      installFakeBackend(total);
      const wanted = Math.min(5, total);
      const lastPage = Math.max(1, Math.ceil(total / 20));

      const bad: string[] = [];
      // 한 바퀴 전부. total 일이면 start 가 모든 값을 한 번씩 지난다.
      for (let day = 0; day < total; day += 1) {
        setDay(day);
        requested = [];
        let words: WordListItem[] = [];
        try {
          words = await getDailyWords(5);
        } catch (e) {
          bad.push(`day=${day} 예외=${(e as Error).message} 요청=${requested}`);
          continue;
        }
        if (words.length !== wanted) {
          bad.push(
            `day=${day} start=${day % total} 개수=${words.length} 기대=${wanted} 요청=${requested}`,
          );
        }
        const ids = words.map((w) => w.id);
        if (new Set(ids).size !== ids.length) {
          bad.push(`day=${day} 중복 ids=${ids}`);
        }
        const over = requested.filter((p) => p > lastPage);
        if (over.length > 0) bad.push(`day=${day} 범위 밖 페이지=${over}`);
      }

      assert.equal(
        bad.length,
        0,
        `실패 ${bad.length}건:\n${bad.slice(0, 10).join("\n")}`,
      );
    });
  }

  // 페이지 크기를 20 으로 하드코딩해도 위 테스트는 전부 통과한다 - 가짜
  // 백엔드가 20 으로만 답하기 때문이다. 백엔드가 PAGE_SIZE 를 바꾸면
  // 인덱스가 엉뚱한 페이지를 가리켜 중복·누락이 나는데, 그것을 여기서 막는다.
  for (const [total, pageSize] of [
    [41, 7],
    [566, 50],
    [30, 3],
  ] as const) {
    it(`페이지가 ${pageSize}개씩이어도 동작한다 (단어 ${total}개)`, async () => {
      installFakeBackend(total, pageSize);
      const wanted = Math.min(5, total);
      const lastPage = Math.max(1, Math.ceil(total / pageSize));

      const bad: string[] = [];
      for (let day = 0; day < total; day += 1) {
        setDay(day);
        requested = [];
        let words: WordListItem[] = [];
        try {
          words = await getDailyWords(5);
        } catch (e) {
          bad.push(`day=${day} 예외=${(e as Error).message} 요청=${requested}`);
          continue;
        }
        if (words.length !== wanted) {
          bad.push(`day=${day} 개수=${words.length} 기대=${wanted}`);
        }
        const ids = words.map((w) => w.id);
        if (new Set(ids).size !== ids.length) bad.push(`day=${day} 중복=${ids}`);
        const over = requested.filter((p) => p > lastPage);
        if (over.length > 0) bad.push(`day=${day} 범위 밖=${over}`);
      }

      assert.equal(
        bad.length,
        0,
        `실패 ${bad.length}건:\n${bad.slice(0, 10).join("\n")}`,
      );
    });
  }
});

describe("getDailyWords - 인자 경계", () => {
  it("size 가 0 이하면 빈 배열이고 요청을 아예 안 한다", async () => {
    installFakeBackend(566);
    for (const size of [0, -1, -100]) {
      requested = [];
      assert.deepEqual(await getDailyWords(size), []);
      assert.equal(requested.length, 0, `size=${size} 인데 요청이 나갔다`);
    }
  });

  it("단어가 하나도 없으면 빈 배열이다", async () => {
    installFakeBackend(0);
    setDay(1);
    assert.deepEqual(await getDailyWords(5), []);
  });

  it("size 가 전체 개수보다 크면 전체 개수만큼만 준다", async () => {
    installFakeBackend(3);
    setDay(0);
    const words = await getDailyWords(10);
    assert.equal(words.length, 3);
    assert.equal(new Set(words.map((w) => w.id)).size, 3);
  });

  it("size 가 한 페이지보다 커도 개수를 채우고 중복이 없다", async () => {
    installFakeBackend(566);
    setDay(100);
    const words = await getDailyWords(45);
    assert.equal(words.length, 45);
    assert.equal(new Set(words.map((w) => w.id)).size, 45);
  });
});

describe("getDailyWords - 하루 고정", () => {
  it("같은 날에 두 번 부르면 같은 묶음이다", async () => {
    installFakeBackend(566);
    setDay(20250);
    const a = await getDailyWords(5);
    const b = await getDailyWords(5);
    assert.deepEqual(
      a.map((w) => w.id),
      b.map((w) => w.id),
    );
  });

  it("KST 로 센다 - UTC 15:00 (KST 자정) 에 날짜가 바뀐다", async () => {
    installFakeBackend(566);
    // UTC 14:59 와 15:00 은 KST 로 다른 날이다.
    Date.now = () => Date.UTC(2026, 8, 6, 14, 59);
    const before = await getDailyWords(5);
    Date.now = () => Date.UTC(2026, 8, 6, 15, 0);
    const afterMidnight = await getDailyWords(5);
    assert.notDeepEqual(
      before.map((w) => w.id),
      afterMidnight.map((w) => w.id),
      "KST 자정에 묶음이 바뀌어야 한다",
    );
  });
});
