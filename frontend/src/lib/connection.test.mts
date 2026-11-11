/**
 * fetchOrExplain·connectionLostMessage 가 끊김을 사람이 읽을 말로 바꾸는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 판 화면(한 판·일일공부·복습·문제풀기)은 오류의 message 를 그대로 띄운다.
 * 여기서 놓치면 브라우저의 영어("Failed to fetch")가 화면에 뜬다. 반대로
 * 너무 많이 바꾸면 우리가 일부러 끊은 요청(AbortController)까지 "서버에
 * 연결하지 못했습니다" 가 되고, 서버의 거절(4xx·5xx)이 끊김으로 둔갑한다.
 */
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";

import {
  ConnectionLost,
  connectionLostMessage,
  fetchOrExplain,
  jsonOrExplain,
} from "./connection";

const OFFLINE = "인터넷에 연결되어 있지 않습니다. 연결되면 다시 눌러주세요.";
const SERVER = "서버에 연결하지 못했습니다. 잠시 뒤 다시 눌러주세요.";

const realFetch = globalThis.fetch;
const realNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");

/** navigator 를 바꾼다. undefined 면 아예 없는 환경(서버). */
function setNavigator(value: unknown) {
  Object.defineProperty(globalThis, "navigator", { value, configurable: true, writable: true });
}

beforeEach(() => setNavigator({ onLine: true }));
afterEach(() => {
  globalThis.fetch = realFetch;
  if (realNavigator) Object.defineProperty(globalThis, "navigator", realNavigator);
});

/** fetch 가 이 값을 던지게 한다. */
const fetchThrows = (error: unknown) => {
  globalThis.fetch = (async () => {
    throw error;
  }) as typeof fetch;
};

describe("connectionLostMessage", () => {
  it("오프라인이면 인터넷 연결을 말한다", () => {
    setNavigator({ onLine: false });
    assert.equal(connectionLostMessage(), OFFLINE);
  });

  it("온라인이면 서버 쪽이라고 말한다(인터넷을 확인하라고 하지 않는다)", () => {
    assert.equal(connectionLostMessage(), SERVER);
  });

  it("onLine 을 모르면(undefined) 오프라인으로 단정하지 않는다", () => {
    setNavigator({});
    assert.equal(connectionLostMessage(), SERVER);
  });

  it("navigator 가 없어도(서버 렌더) 터지지 않는다", () => {
    setNavigator(undefined);
    assert.equal(connectionLostMessage(), SERVER);
  });
});

describe("fetchOrExplain", () => {
  it("fetch 의 TypeError(끊김)를 ConnectionLost 로 바꾸고 영어를 싣지 않는다", async () => {
    fetchThrows(new TypeError("Failed to fetch"));
    await assert.rejects(fetchOrExplain("/api/rounds"), (error: unknown) => {
      assert.ok(error instanceof ConnectionLost);
      // 판 화면은 err instanceof Error ? err.message 로 읽는다.
      assert.ok(error instanceof Error);
      assert.equal(error.message, SERVER);
      assert.doesNotMatch(error.message, /[A-Za-z]/);
      return true;
    });
  });

  it("끊긴 순간 오프라인이면 그 문구다", async () => {
    setNavigator({ onLine: false });
    fetchThrows(new TypeError("Failed to fetch"));
    await assert.rejects(fetchOrExplain("/api/daily"), { message: OFFLINE });
  });

  it("Safari·Firefox 의 다른 영어 문구도 같은 한국어가 된다", async () => {
    for (const english of ["Load failed", "NetworkError when attempting to fetch resource."]) {
      fetchThrows(new TypeError(english));
      await assert.rejects(fetchOrExplain("/api/review"), { message: SERVER });
    }
  });

  it("우리가 끊은 요청(AbortError)은 바꾸지 않고 그 오류 그대로 올린다", async () => {
    const abort = new DOMException("The user aborted a request.", "AbortError");
    fetchThrows(abort);
    await assert.rejects(fetchOrExplain("/api/quiz"), (error: unknown) => {
      assert.equal(error, abort);
      assert.ok(!(error instanceof ConnectionLost));
      return true;
    });
  });

  it("진짜 AbortController 로 끊은 것도 그대로다", async () => {
    globalThis.fetch = realFetch;
    const controller = new AbortController();
    controller.abort();
    await assert.rejects(
      fetchOrExplain("http://127.0.0.1:9/never", { signal: controller.signal }),
      (error: unknown) => error instanceof DOMException && error.name === "AbortError",
    );
  });

  it("서버가 거절한 응답(4xx·5xx)은 던지지 않고 그대로 돌려준다", async () => {
    for (const status of [400, 404, 500, 503]) {
      const reply = { ok: false, status } as Response;
      globalThis.fetch = (async () => reply) as typeof fetch;
      assert.equal(await fetchOrExplain("/api/rounds"), reply);
    }
  });

  it("주소와 요청 옵션을 바꾸지 않고 넘긴다", async () => {
    const seen: [unknown, unknown][] = [];
    globalThis.fetch = (async (input: unknown, init: unknown) => {
      seen.push([input, init]);
      return { ok: true, status: 200 } as Response;
    }) as typeof fetch;
    const init = { method: "POST", body: "{}", cache: "no-store" } as RequestInit;
    await fetchOrExplain("/api/rounds", init);
    assert.equal(seen.length, 1);
    assert.equal(seen[0][0], "/api/rounds");
    assert.equal(seen[0][1], init);
  });
});

describe("jsonOrExplain", () => {
  it("본문을 읽으면 그 값을 그대로 돌려준다", async () => {
    const value = await jsonOrExplain<{ token: string }>(new Response('{"token":"t1"}'));
    assert.deepEqual(value, { token: "t1" });
  });

  it("본문이 잘려 오면(SyntaxError) 영어 대신 ConnectionLost 를 던진다", async () => {
    await assert.rejects(jsonOrExplain(new Response('{"result": {"corr')), (error) => {
      assert.ok(error instanceof ConnectionLost);
      assert.equal(error.message, connectionLostMessage());
      assert.doesNotMatch(error.message, /[A-Za-z]/);
      return true;
    });
  });

  it("본문을 받다 끊기면(TypeError) 영어 대신 ConnectionLost 를 던진다", async () => {
    const broken = { json: async () => { throw new TypeError("network error"); } } as unknown as Response;
    await assert.rejects(jsonOrExplain(broken), (error) => {
      assert.ok(error instanceof ConnectionLost);
      assert.equal(error.name, "ConnectionLost");
      return true;
    });
  });
});
