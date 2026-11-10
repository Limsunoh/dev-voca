/**
 * lib/session.ts 의 게스트 하루 공부량 쿠키와 carryGuestDailyLength 를 실제
 * 코드로 돌린다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약.
 *   1. getGuestDailyLength 는 아는 값(5m·10m·30m)만 돌려주고, 그 밖의 쿠키
 *      값(조작·옛 값)은 null 이다.
 *   2. carryGuestDailyLength
 *      - 쿠키가 없거나 모르는 값이면 백엔드에 아무것도 안 보내고 쿠키도 안 건드린다.
 *      - 계정 값이 "" 이면 그 토큰으로 PATCH /me 를 보내고 쿠키를 지운다.
 *      - 계정에 값이 있으면 덮지 않는다(PATCH 없음). 쿠키는 지운다.
 *      - 계정에 칸이 없으면(옛 백엔드) PATCH 도 안 하고 쿠키도 남긴다.
 *      - PATCH 가 실패하면(401·500·연결 실패) 던지지 않고 쿠키를 남긴다.
 *        로그인을 막으면 안 되고, 남겨 두어야 다음 로그인 때 다시 옮긴다.
 *   3. clearToken(로그아웃)은 공부량 쿠키도 지우고, forgetToken(죽은 토큰
 *      정리)은 토큰만 지운다.
 *
 * 하네스는 session-stale-token.test.mts 와 같다(server-only 우회, 쿠키 대역,
 * 요청 하나 동안만 기억하는 cache).
 */
import assert from "node:assert/strict";
import Module from "node:module";
import { after, beforeEach, describe, it, mock } from "node:test";

const jar = new Map<string, string>();
let deleted: string[] = [];

mock.module("next/headers", {
  namedExports: {
    async cookies() {
      return {
        get: (name: string) => (jar.has(name) ? { name, value: jar.get(name) } : undefined),
        set: (name: string, value: string) => void jar.set(name, value),
        delete: (name: string) => {
          deleted.push(name);
          jar.delete(name);
        },
      };
    },
  },
});

mock.module("react", {
  namedExports: {
    cache<A extends unknown[], R>(fn: (...args: A) => R) {
      return fn;
    },
  },
});

const loader = Module as unknown as { _load: (request: string, ...rest: unknown[]) => unknown };
const realLoad = loader._load;
loader._load = function (this: unknown, request: string, ...rest: unknown[]) {
  if (request === "server-only") return {};
  return realLoad.call(this, request, ...rest);
};

// ---- 가짜 백엔드 ------------------------------------------------------------

type Reply = { status: number } | "down";
let reply: Reply = { status: 200 };
let calls: { method: string; url: string; auth: string | null; body: unknown }[] = [];

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
  calls.push({
    method: init?.method ?? "GET",
    url: String(input),
    auth: new Headers(init?.headers).get("Authorization"),
    body: init?.body ? JSON.parse(String(init.body)) : null,
  });
  if (reply === "down") throw new TypeError("fetch failed");
  const ok = reply.status === 200;
  return new Response(JSON.stringify(ok ? { daily_length: "10m" } : { detail: "실패" }), {
    status: reply.status,
    headers: { "Content-Type": "application/json" },
  });
}) as typeof fetch;

const realError = console.error;
let logged = 0;
console.error = () => {
  logged += 1;
};

after(() => {
  globalThis.fetch = realFetch;
  console.error = realError;
  loader._load = realLoad;
});

const session = await import("./session");

const TOKEN = "tok-carry";
const LENGTH_COOKIE = "devvoca_daily_length";

function user(daily_length?: string) {
  const base = { id: 1, email: "a@b.c", display_name: "a" };
  return (daily_length === undefined ? base : { ...base, daily_length }) as Parameters<
    typeof session.carryGuestDailyLength
  >[1];
}

beforeEach(() => {
  jar.clear();
  deleted = [];
  calls = [];
  reply = { status: 200 };
  logged = 0;
});

// ---------------------------------------------------------------------------

describe("getGuestDailyLength", () => {
  it("아는 값만 돌려준다", async () => {
    for (const ok of ["5m", "10m", "30m"]) {
      jar.set(LENGTH_COOKIE, ok);
      assert.equal(await session.getGuestDailyLength(), ok);
    }
  });

  it("조작한 쿠키 값은 null 이다", async () => {
    for (const bad of ["", "99m", "10M", "10m ", "%31%30m", "5m;30m"]) {
      jar.set(LENGTH_COOKIE, bad);
      assert.equal(await session.getGuestDailyLength(), null, JSON.stringify(bad));
    }
  });

  it("setGuestDailyLength 로 넣은 값을 그대로 읽는다", async () => {
    await session.setGuestDailyLength("30m");
    assert.equal(await session.getGuestDailyLength(), "30m");
  });
});

describe("carryGuestDailyLength - 옮길 것이 없으면", () => {
  it("쿠키가 없으면 백엔드에 안 묻는다", async () => {
    await session.carryGuestDailyLength(TOKEN, user(""));
    assert.equal(calls.length, 0);
    assert.deepEqual(deleted, []);
  });

  it("조작한 쿠키 값은 계정에 보내지 않는다", async () => {
    jar.set(LENGTH_COOKIE, "999m");
    await session.carryGuestDailyLength(TOKEN, user(""));
    assert.equal(calls.length, 0);
  });
});

describe("carryGuestDailyLength - 계정이 비어 있으면", () => {
  it("그 토큰으로 PATCH /me 를 보내고 쿠키를 지운다", async () => {
    jar.set(LENGTH_COOKIE, "10m");
    await session.carryGuestDailyLength(TOKEN, user(""));

    assert.equal(calls.length, 1);
    assert.equal(calls[0].method, "PATCH");
    assert.match(calls[0].url, /\/api\/accounts\/me\/$/);
    assert.equal(calls[0].auth, `Token ${TOKEN}`);
    assert.deepEqual(calls[0].body, { daily_length: "10m" });
    assert.equal(jar.has(LENGTH_COOKIE), false);
  });
});

describe("carryGuestDailyLength - 계정에 값이 있으면", () => {
  for (const saved of ["5m", "30m"]) {
    it(`${saved} 를 덮지 않고 쿠키만 지운다`, async () => {
      jar.set(LENGTH_COOKIE, "10m");
      await session.carryGuestDailyLength(TOKEN, user(saved));

      assert.equal(calls.length, 0, "다른 기기에서 정한 값을 게스트 선택이 덮었다");
      assert.equal(jar.has(LENGTH_COOKIE), false);
    });
  }
});

describe("carryGuestDailyLength - 칸이 없는 옛 백엔드면", () => {
  it("보내지도 지우지도 않는다", async () => {
    jar.set(LENGTH_COOKIE, "10m");
    await session.carryGuestDailyLength(TOKEN, user(undefined));

    assert.equal(calls.length, 0);
    assert.deepEqual(deleted, []);
    assert.equal(jar.get(LENGTH_COOKIE), "10m");
  });
});

for (const [label, r] of [
  ["401", { status: 401 }],
  ["400", { status: 400 }],
  ["500", { status: 500 }],
  ["연결 실패", "down"],
] as [string, Reply][]) {
  describe(`carryGuestDailyLength - PATCH 가 ${label} 이면`, () => {
    it("던지지 않고 쿠키를 남긴다", async () => {
      jar.set(LENGTH_COOKIE, "10m");
      reply = r;

      await session.carryGuestDailyLength(TOKEN, user(""));

      assert.equal(calls.length, 1);
      assert.equal(jar.get(LENGTH_COOKIE), "10m", "실패했는데 게스트가 고른 값이 사라졌다");
      assert.equal(logged, 1);
    });
  });
}

describe("쿠키 지우기와 공부량", () => {
  it("clearToken(로그아웃)은 공부량 쿠키를 지운다", async () => {
    jar.set("devvoca_token", TOKEN);
    jar.set(LENGTH_COOKIE, "10m");
    await session.clearToken();
    assert.equal(jar.has(LENGTH_COOKIE), false);
  });

  it("forgetToken(죽은 토큰 정리)은 공부량 쿠키를 남긴다", async () => {
    jar.set("devvoca_token", TOKEN);
    jar.set(LENGTH_COOKIE, "10m");
    await session.forgetToken();
    assert.equal(jar.get(LENGTH_COOKIE), "10m");
  });
});
