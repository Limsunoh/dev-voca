/**
 * 앱의 뒤로 가기를 일반 앱처럼 만드는 이동 도우미(lib/history-nav.ts).
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - 뒤쪽 기록에 같은 경로가 있으면 가장 가까운 그 칸으로 돌아간다. 기록이
 *     늘지 않는다. 새로 받는 일은 탭바가 한다(여기서도 받으면 두 번 묻는다).
 *   - 없으면 지금 칸을 바꿔치기한다. Navigation API 가 없는 브라우저도 같다.
 *   - 경로만 본다(탭은 경로로 가리키는데 단어 목록은 들어가면 ?shuffle= 이 붙는다).
 *   - 다른 사이트의 기록(구글 로그인 등)과 앞쪽 기록은 보지 않는다.
 *   - 한 판의 나가기(goBackOrReplace)는 다른 문서의 칸으로 돌아가지
 *     않는다. 페이지를 통째로 다시 받으면 브라우저 경고가 한 번 더 뜬다.
 *   - 돌아가기가 막히면(ExitGuard 가 확인 창을 띄우려고 취소) 아무것도 안 한다.
 *     바꿔치기로 대신 가면 그 확인 창을 건너뛴다.
 *   - 바로 앞 칸이 지금과 같은 주소면 그 칸으로 돌아가 한 칸으로 줄인다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it } from "node:test";

import { earlierEntryKey, goBackOrReplace, stepOffRepeat, traverseBackTo } from "./history-nav";

const ORIGIN = "https://dev-voca.vercel.app";

type Entry = { key: string; url: string | null; index: number; sameDocument: boolean };

class FakeNavigation {
  traversals: string[] = [];
  outcome: "ok" | "blocked" = "ok";
  currentEntry: Entry | null;
  constructor(
    private list: Entry[],
    at: number,
  ) {
    this.currentEntry = list[at] ?? null;
  }
  entries() {
    return this.list;
  }
  traverseTo(key: string) {
    this.traversals.push(key);
    const finished =
      this.outcome === "ok" ? Promise.resolve() : Promise.reject(new Error("AbortError"));
    // 막힌 경우 finished 의 거절을 아무도 안 받으면 테스트 러너가 경고한다.
    finished.catch(() => {});
    return { committed: finished, finished };
  }
}

/** urls 의 at 번째가 지금 칸. otherDocument 에 든 번호는 다른 문서의 칸이다. */
function history(urls: (string | null)[], at = urls.length - 1, otherDocument: number[] = []): FakeNavigation {
  return new FakeNavigation(
    urls.map((url, index) => ({
      key: `k${index}`,
      url: url && (url.startsWith("http") ? url : ORIGIN + url),
      index,
      sameDocument: !otherDocument.includes(index),
    })),
    at,
  );
}

function makeRouter() {
  const calls: string[] = [];
  return {
    calls,
    replace: (to: string) => calls.push(`replace ${to}`),
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));
const realWindow = (globalThis as { window?: unknown }).window;
after(() => {
  (globalThis as { window?: unknown }).window = realWindow;
});

function install(nav: FakeNavigation | undefined) {
  (globalThis as { window?: unknown }).window = { navigation: nav, location: { origin: ORIGIN } };
}

beforeEach(() => install(undefined));

describe("earlierEntryKey", () => {
  it("뒤쪽 기록 중 같은 주소의 가장 가까운 칸을 고른다", () => {
    install(history(["/", "/learn/words", "/", "/talk"]));
    assert.equal(earlierEntryKey("/"), "k2");
    assert.equal(earlierEntryKey("/learn/words"), "k1");
  });

  it("경로만 본다(쿼리가 붙은 목록도 같은 화면)", () => {
    install(history(["/learn/words?shuffle=ab", "/learn/words/7"]));
    assert.equal(earlierEntryKey("/learn/words"), "k0");
    assert.equal(earlierEntryKey("/learn"), null);
  });

  it("sameDocument 를 주면 다른 문서의 칸은 건너뛴다", () => {
    install(history(["/test", "/", "/test", "/test/words"], 3, [0, 1]));
    assert.equal(earlierEntryKey("/test"), "k2");
    assert.equal(earlierEntryKey("/", false), "k1");
    assert.equal(earlierEntryKey("/", true), null);
  });

  it("지금 칸과 앞쪽 기록은 보지 않는다", () => {
    install(history(["/talk", "/", "/learn/words"], 0));
    assert.equal(earlierEntryKey("/"), null);
    assert.equal(earlierEntryKey("/talk"), null);
  });

  it("다른 사이트와 주소를 모르는 칸은 건너뛴다", () => {
    install(history(["https://accounts.google.com/", null, "/talk"]));
    assert.equal(earlierEntryKey("/"), null);
  });

  it("Navigation API 가 없으면 없다고 답한다", () => {
    install(undefined);
    assert.equal(earlierEntryKey("/"), null);
  });
});

describe("traverseBackTo", () => {
  it("뒤쪽에 있으면 돌아가고 true, 없으면 아무것도 안 하고 false", () => {
    const nav = history(["/", "/talk"]);
    install(nav);
    assert.equal(traverseBackTo("/"), true);
    assert.equal(traverseBackTo("/test"), false);
    assert.deepEqual(nav.traversals, ["k0"]);
  });

  it("탭과 홈 링크는 다른 문서의 칸으로도 돌아간다(홈이 첫 칸으로 남는다)", () => {
    const nav = history(["/", "/talk"], 1, [0]);
    install(nav);
    assert.equal(traverseBackTo("/"), true);
    assert.deepEqual(nav.traversals, ["k0"]);
  });
});

describe("goBackOrReplace", () => {
  it("뒤쪽에 있으면 그리로 돌아가기만 한다(새로 받는 일은 탭바가 한다)", async () => {
    const nav = history(["/", "/learn/words", "/learn/words/7"]);
    install(nav);
    const router = makeRouter();
    goBackOrReplace(router, "/");
    await flush();
    assert.deepEqual(nav.traversals, ["k0"]);
    assert.deepEqual(router.calls, []);
  });

  it("다른 문서의 칸이면 돌아가지 않고 바꿔치기한다", async () => {
    const nav = history(["/", "/test", "/test/words"], 2, [0, 1]);
    install(nav);
    const router = makeRouter();
    goBackOrReplace(router, "/test");
    await flush();
    assert.deepEqual(nav.traversals, []);
    assert.deepEqual(router.calls, ["replace /test"]);
  });

  it("없으면 지금 칸을 바꿔치기한다", async () => {
    const nav = history(["/learn/words/7"]);
    install(nav);
    const router = makeRouter();
    goBackOrReplace(router, "/");
    await flush();
    assert.deepEqual(nav.traversals, []);
    assert.deepEqual(router.calls, ["replace /"]);
  });

  it("Navigation API 가 없는 브라우저는 바꿔치기한다", async () => {
    install(undefined);
    const router = makeRouter();
    goBackOrReplace(router, "/test");
    await flush();
    assert.deepEqual(router.calls, ["replace /test"]);
  });

  it("돌아가기가 막히면 아무것도 하지 않는다(확인 창을 건너뛰지 않는다)", async () => {
    const nav = history(["/test", "/test/daily"]);
    nav.outcome = "blocked";
    install(nav);
    const router = makeRouter();
    goBackOrReplace(router, "/test");
    await flush();
    assert.deepEqual(nav.traversals, ["k0"]);
    assert.deepEqual(router.calls, []);
  });
});

describe("stepOffRepeat", () => {
  it("바로 앞 칸이 같은 주소면 그 칸으로 돌아간다(홈에서 로그인한 뒤의 [홈, 홈])", () => {
    const nav = history(["/", "/"]);
    install(nav);
    assert.equal(stepOffRepeat(), true);
    assert.deepEqual(nav.traversals, ["k0"]);
  });

  it("쿼리까지 같아야 같은 주소다", () => {
    const nav = history(["/learn/words?shuffle=ab", "/learn/words?shuffle=cd"]);
    install(nav);
    assert.equal(stepOffRepeat(), false);
    assert.deepEqual(nav.traversals, []);
  });

  it("바로 앞이 아니면, 다른 문서의 칸이면, 첫 칸이면 그대로 둔다", () => {
    for (const nav of [
      history(["/", "/talk", "/"]),
      history(["/", "/"], 1, [0]),
      history(["/"]),
    ]) {
      install(nav);
      assert.equal(stepOffRepeat(), false);
      assert.deepEqual(nav.traversals, []);
    }
  });

  it("Navigation API 가 없으면 아무것도 안 한다", () => {
    install(undefined);
    assert.equal(stepOffRepeat(), false);
  });

  it("# 만 다른 칸(목차 이동)은 같은 주소가 아니다", () => {
    for (const urls of [
      ["/privacy", "/privacy#items"],
      ["/privacy#items", "/privacy"],
      ["/privacy#items", "/privacy#changes"],
    ]) {
      const nav = history(urls);
      install(nav);
      assert.equal(stepOffRepeat(), false, urls.join(" -> "));
      assert.deepEqual(nav.traversals, []);
    }
  });

  it("지금 칸이 기록 중간이어도 바로 앞 칸만 본다(앞쪽 기록은 안 본다)", () => {
    // 뒤로 가기로 [홈, 단어장, 홈] 의 단어장에 와 있다. 앞쪽의 홈은 상관없다.
    const nav = history(["/", "/learn/words", "/"], 1);
    install(nav);
    assert.equal(stepOffRepeat(), false);
    assert.deepEqual(nav.traversals, []);
  });

  it("돌아가기가 막혀도(확인 창) 거절이 새지 않는다", async () => {
    const nav = history(["/", "/"]);
    // 대역의 traverseTo 는 스스로 거절을 받아 두므로, 받지 않은 거절을 돌려주는 것으로 바꾼다.
    nav.traverseTo = (key: string) => {
      nav.traversals.push(key);
      return {
        committed: Promise.reject(new Error("AbortError")),
        finished: Promise.reject(new Error("AbortError")),
      };
    };
    install(nav);
    const leaked: unknown[] = [];
    const onUnhandled = (reason: unknown) => leaked.push(reason);
    process.on("unhandledRejection", onUnhandled);
    try {
      assert.equal(stepOffRepeat(), true);
      await flush();
      await flush();
      assert.deepEqual(leaked, []);
    } finally {
      process.off("unhandledRejection", onUnhandled);
    }
  });
});
