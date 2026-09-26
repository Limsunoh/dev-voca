/**
 * "로그인 없이 둘러보기"(continueAsGuestAction)가 남아 있는 토큰을 어떻게
 * 치우는지.
 *
 * 실행: cd frontend && npm test
 *
 * 계약.
 *   1. 쿠키에 토큰이 있으면 서버 토큰을 먼저 폐기하고(POST /api/accounts/logout/,
 *      그 토큰을 실어서) 토큰 쿠키만 지운다. 쿠키만 지우면 서버에는 만료 없는
 *      토큰이 남는다 - 백엔드가 잠깐 안 받아 살아 있는 토큰을 가진 사람에게도
 *      이 버튼이 보일 수 있다.
 *   2. 로그아웃 요청이 실패해도(죽은 토큰의 401, 연결 실패) 쿠키는 지우고
 *      끝까지 간다.
 *   3. 토큰이 없으면 로그아웃도 쿠키 지우기도 하지 않는다.
 *   4. 그다음 게스트 쿠키를 심고 / 로 보낸다. 게스트 쿠키까지 지우는
 *      clearToken 은 부르지 않는다.
 *
 * logOut 은 실제 코드(lib/api/accounts)를 돌리고 백엔드만 fetch 대역으로 둔다.
 * redirect 는 실제로도 던진다. 같은 방식으로 던지는 대역으로 잡는다.
 * 세션은 "server-only" 라 대역으로 바꾼다((auth)/actions.test.mts 와 같다).
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

class Redirect extends Error {
  constructor(readonly to: string) {
    super("NEXT_REDIRECT");
  }
}

mock.module("next/navigation", {
  namedExports: {
    redirect: (to: string) => {
      throw new Redirect(to);
    },
  },
});

const jar = new Map<string, string>();
let order: string[] = [];

mock.module("@/lib/session", {
  namedExports: {
    async getToken() {
      return jar.get("devvoca_token") ?? null;
    },
    async forgetToken() {
      order.push("forgetToken");
      jar.delete("devvoca_token");
    },
    async clearToken() {
      order.push("clearToken");
      jar.delete("devvoca_token");
      jar.delete("devvoca_guest");
    },
    async setGuest() {
      order.push("setGuest");
      jar.set("devvoca_guest", "1");
    },
  },
});

/** 로그아웃 요청에 백엔드가 어떻게 답하나. */
let logout: 204 | 401 | "down" = 204;

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
  const path = new URL(String(input)).pathname;
  const auth = new Headers(init?.headers).get("Authorization");
  // 응답이 한 박자 뒤에 온다고 치고, 그때 적는다. 기다리지 않고 쿠키부터
  // 지우면 순서가 뒤바뀌어 드러난다.
  await new Promise((resolve) => setTimeout(resolve, 0));
  order.push(`${init?.method ?? "GET"} ${path} ${auth}`);
  if (logout === "down") throw new TypeError("fetch failed");
  if (logout === 401) {
    return new Response(JSON.stringify({ detail: "토큰이 유효하지 않습니다." }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }
  return new Response(null, { status: 204 });
}) as typeof fetch;

after(() => {
  globalThis.fetch = realFetch;
});

const { continueAsGuestAction } = await import("./actions");

beforeEach(() => {
  jar.clear();
  order = [];
  logout = 204;
});

/** 액션을 돌려 / 로 보내는지까지 확인한다. */
async function run() {
  await assert.rejects(continueAsGuestAction(), (error) => {
    assert.ok(error instanceof Redirect, String(error));
    assert.equal(error.to, "/");
    return true;
  });
}

describe("쿠키에 토큰이 있으면", () => {
  for (const reply of [204, 401, "down"] as const) {
    it(`로그아웃(${reply})으로 서버 토큰을 폐기한 뒤 토큰 쿠키만 지우고 게스트로 / 에 보낸다`, async () => {
      jar.set("devvoca_token", "old");
      logout = reply;
      await run();
      assert.deepEqual(order, [
        "POST /api/accounts/logout/ Token old",
        "forgetToken",
        "setGuest",
      ]);
      assert.equal(jar.has("devvoca_token"), false);
      assert.equal(jar.get("devvoca_guest"), "1");
    });
  }
});

describe("쿠키에 토큰이 없으면", () => {
  it("로그아웃·쿠키 지우기 없이 게스트로 / 에 보낸다", async () => {
    await run();
    assert.deepEqual(order, ["setGuest"]);
    assert.equal(jar.get("devvoca_guest"), "1");
  });
});
