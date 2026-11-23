/**
 * proxy 의 로그인 이어 가기를 깨뜨려 본다. 백엔드는 가짜 fetch 다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약.
 *   1. GET 화면 요청에서 쿠키 값 "토큰.발급시각" 이 하루(86400초) 이상 지났거나 시각이 없거나
 *      앞날이면 백엔드 renew 를 부른다. 그보다 어리면 부르지 않는다. POST 는 부르지 않는다.
 *      백엔드에는 점 앞의 토큰만 싣는다.
 *   2. 새 토큰은 Set-Cookie 머리에 직접 붙는다(HttpOnly·SameSite=Lax·Path=/·30일). 이번 렌더에는
 *      넘기지 않는다. x-middleware-set-cookie 가 없고, 렌더가 읽는 요청 쿠키는 옛 값이다.
 *   3. 401 이면 쿠키를 지우고 이번 렌더도 지운 상태로 그린다.
 *   4. 그 밖의 실패(5xx·연결 실패·시간 초과·이상한 응답)는 아무것도 안 바꾼다. 응답의 토큰이
 *      16진수가 아니면 쿠키에 넣지 않는다(머리 주입).
 *   5. 어느 경우에도 CSP 는 그대로 실린다.
 *   6. getToken()(lib/session.ts)은 점 앞의 토큰만 돌려준다.
 *
 * 하네스: session.ts 의 `import "server-only"` 는 Next 밖에서 해석되지 않아 CJS 로더에서
 * 빈 객체로 돌려준다(session-stale-token.test.mts 와 같은 우회).
 */
import assert from "node:assert/strict";
import Module from "node:module";
import { after, beforeEach, describe, it, mock } from "node:test";

import { NextRequest } from "next/server";

// ---- 쿠키 대역(getToken 용) -------------------------------------------------

const jar = new Map<string, string>();
mock.module("next/headers", {
  namedExports: {
    async cookies() {
      return {
        get: (name: string) => (jar.has(name) ? { name, value: jar.get(name) } : undefined),
        set: (name: string, value: string) => void jar.set(name, value),
        delete: (name: string) => void jar.delete(name),
      };
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

type Reply = { status: number; body?: unknown } | "down" | "timeout";
let reply: Reply = { status: 200 };
let calls: { url: string; method: string; auth: string | null }[] = [];

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
  const headers = new Headers(init?.headers);
  calls.push({ url: String(input), method: init?.method ?? "GET", auth: headers.get("Authorization") });
  if (reply === "down") throw new TypeError("fetch failed");
  if (reply === "timeout") throw new DOMException("The operation was aborted due to timeout", "TimeoutError");
  return new Response(JSON.stringify(reply.body ?? {}), {
    status: reply.status,
    headers: { "Content-Type": "application/json" },
  });
}) as typeof fetch;

const realError = console.error;
console.error = () => {};

after(() => {
  globalThis.fetch = realFetch;
  console.error = realError;
  loader._load = realLoad;
});

const { proxy } = await import("./proxy");
const { getToken } = await import("./lib/session");

// ---- 도구 -------------------------------------------------------------------

const ORIGIN = "https://dev-voca.vercel.app";
const OLD = "a".repeat(40);
const NEW = "b".repeat(40);
const DAY = 86_400;
// 시각을 고정한다. 하루 경계를 Date.now 의 흐름에 맡기면 초가 넘어가는 순간 갈린다.
const NOW_MS = 1_800_000_000_500;
const NOW_S = Math.floor(NOW_MS / 1000);

function page(cookie?: string, method = "GET"): NextRequest {
  const headers: Record<string, string> = {};
  if (cookie !== undefined) headers.cookie = `devvoca_token=${cookie}`;
  return new NextRequest(`${ORIGIN}/learn/words`, { method, headers });
}

function tokenSetCookies(res: Response): string[] {
  return res.headers.getSetCookie().filter((line) => line.startsWith("devvoca_token="));
}

/** proxy 가 넘긴 요청 쿠키 머리. 바꾸지 않았으면 원래 요청 머리 그대로다. */
function renderCookie(res: Response, original: NextRequest): string {
  return res.headers.get("x-middleware-request-cookie") ?? original.headers.get("cookie") ?? "";
}

/**
 * 렌더의 cookies().get("devvoca_token") 이 돌려줄 값. Next 는 요청 쿠키 머리 위에
 * x-middleware-set-cookie 를 덮어 쓴다(next/dist/server/async-storage/request-store.js 의
 * mergeMiddlewareCookies). 지운 쿠키는 빈 값으로 덮인다.
 */
function renderToken(res: Response, original: NextRequest): string | undefined {
  const overlay = res.headers.get("x-middleware-set-cookie")?.match(/(?:^|, )devvoca_token=([^;]*)/);
  if (overlay) return overlay[1];
  return renderCookie(res, original).match(/(?:^|; )devvoca_token=([^;]*)/)?.[1];
}

function assertUntouched(res: Response, req: NextRequest) {
  assert.deepEqual(tokenSetCookies(res), []);
  assert.equal(res.headers.get("x-middleware-set-cookie"), null);
  assert.equal(renderCookie(res, req), req.headers.get("cookie") ?? "");
  assert.ok(res.headers.get("content-security-policy"));
}

beforeEach(() => {
  reply = { status: 200, body: { token: NEW, issued_at: NOW_S } };
  calls = [];
  jar.clear();
  mock.restoreAll();
  mock.method(Date, "now", () => NOW_MS);
});

// ---- 언제 부르나 ------------------------------------------------------------

describe("proxy 이어 가기 - 언제 부르나", () => {
  it("정확히 하루면 부르고, 1초 모자라면 안 부른다", async () => {
    await proxy(page(`${OLD}.${NOW_S - DAY + 1}`));
    assert.equal(calls.length, 0);

    await proxy(page(`${OLD}.${NOW_S - DAY}`));
    assert.equal(calls.length, 1);
  });

  it("시각이 없거나 숫자가 아니거나 앞날이면 부른다", async () => {
    for (const cookie of [OLD, `${OLD}.`, `${OLD}.abc`, `${OLD}.-5`, `${OLD}.${NOW_S + DAY * 365}`]) {
      calls = [];
      await proxy(page(cookie));
      assert.equal(calls.length, 1, cookie);
    }
  });

  it("백엔드에는 점 앞의 토큰만 POST 로 싣는다", async () => {
    await proxy(page(`${OLD}.${NOW_S - DAY * 2}`));

    assert.equal(calls.length, 1);
    assert.equal(calls[0].method, "POST");
    assert.match(calls[0].url, /\/api\/accounts\/token\/renew\/$/);
    assert.equal(calls[0].auth, `Token ${OLD}`);
  });

  it("POST·HEAD 요청은 하루가 지났어도 부르지 않고 쿠키를 안 건드린다", async () => {
    for (const method of ["POST", "HEAD", "PUT", "DELETE"]) {
      const req = page(`${OLD}.${NOW_S - DAY * 2}`, method);
      const res = await proxy(req);
      assertUntouched(res, req);
    }
    assert.equal(calls.length, 0);
  });

  it("쿠키가 없거나 비었거나 토큰이 빈 값이면 부르지 않는다", async () => {
    for (const cookie of [undefined, "", ".", `.${NOW_S - DAY * 2}`]) {
      const req = page(cookie);
      const res = await proxy(req);
      assertUntouched(res, req);
    }
    assert.equal(calls.length, 0);
  });
});

// ---- 새 토큰을 받으면 -------------------------------------------------------

describe("proxy 이어 가기 - 새 토큰", () => {
  it("Set-Cookie 에 새 값과 쿠키 설정을 싣고, 이번 렌더에는 넘기지 않는다", async () => {
    const req = page(`${OLD}.${NOW_S - DAY * 2}`);
    const res = await proxy(req);

    const lines = tokenSetCookies(res);
    assert.equal(lines.length, 1, lines.join(" | "));
    const parts = lines[0].split("; ");
    assert.equal(parts[0], `devvoca_token=${NEW}.${NOW_S}`);
    assert.ok(parts.includes("HttpOnly"));
    assert.ok(parts.includes("SameSite=Lax"));
    assert.ok(parts.includes("Path=/"));
    assert.ok(parts.includes(`Max-Age=${DAY * 30}`));
    assert.ok(!parts.some((p) => /^Domain=/i.test(p)));

    assert.equal(res.headers.get("x-middleware-set-cookie"), null);
    assert.equal(renderToken(res, req), `${OLD}.${NOW_S - DAY * 2}`);
    assert.ok(res.headers.get("content-security-policy"));
    assert.equal(
      res.headers.get("content-security-policy"),
      res.headers.get("x-middleware-request-content-security-policy"),
    );
  });

  it("백엔드가 같은 토큰을 돌려줘도(하루 안 됨) 받은 발급 시각으로 다시 붙인다", async () => {
    const issued = NOW_S - DAY * 2;
    reply = { status: 200, body: { token: OLD, issued_at: issued } };

    const res = await proxy(page(`${OLD}.${NOW_S - DAY * 3}`));

    assert.equal(tokenSetCookies(res)[0].split("; ")[0], `devvoca_token=${OLD}.${issued}`);
  });

  it("다른 쿠키(게스트 등)는 건드리지 않는다", async () => {
    const req = new NextRequest(`${ORIGIN}/learn/words`, {
      headers: { cookie: `devvoca_guest=g1; devvoca_token=${OLD}.${NOW_S - DAY * 2}` },
    });
    const res = await proxy(req);

    const all = res.headers.getSetCookie();
    assert.equal(all.length, 1, all.join(" | "));
    assert.ok(renderCookie(res, req).includes("devvoca_guest=g1"));
  });
});

// ---- 401 ---------------------------------------------------------------------

describe("proxy 이어 가기 - 401", () => {
  it("쿠키를 지우고 이번 렌더도 토큰 없이 그린다", async () => {
    reply = { status: 401, body: { detail: "x" } };
    const req = page(`${OLD}.${NOW_S - DAY * 2}`);

    const res = await proxy(req);

    const lines = tokenSetCookies(res);
    assert.equal(lines.length, 1, lines.join(" | "));
    assert.match(lines[0], /^devvoca_token=;/);
    assert.match(lines[0], /Max-Age=0|Expires=Thu, 01 Jan 1970/);
    assert.equal(renderToken(res, req), "");
    assert.ok(res.headers.get("content-security-policy"));
  });
});

// ---- 그 밖의 실패 -----------------------------------------------------------

describe("proxy 이어 가기 - 그 밖의 실패는 아무것도 안 바꾼다", () => {
  const cases: [string, Reply][] = [
    ["400", { status: 400, body: { detail: "x" } }],
    ["403", { status: 403, body: { detail: "x" } }],
    ["500", { status: 500, body: { detail: "x" } }],
    ["503", { status: 503 }],
    ["연결 실패", "down"],
    ["시간 초과", "timeout"],
    ["토큰 없음", { status: 200, body: { issued_at: NOW_S } }],
    ["토큰에 쿠키 속성 주입", { status: 200, body: { token: `${NEW}; Domain=evil.example`, issued_at: NOW_S } }],
    ["토큰에 줄바꿈", { status: 200, body: { token: `${NEW}\r\nSet-Cookie: x=1`, issued_at: NOW_S } }],
    ["토큰에 점", { status: 200, body: { token: `${NEW}.1`, issued_at: NOW_S } }],
    ["빈 토큰", { status: 200, body: { token: "", issued_at: NOW_S } }],
    ["토큰이 숫자", { status: 200, body: { token: 123, issued_at: NOW_S } }],
    ["시각이 문자열", { status: 200, body: { token: NEW, issued_at: String(NOW_S) } }],
    ["시각이 소수", { status: 200, body: { token: NEW, issued_at: NOW_S + 0.5 } }],
    ["시각 없음", { status: 200, body: { token: NEW } }],
    ["본문이 배열", { status: 200, body: [] }],
    ["본문이 null", { status: 200, body: null }],
  ];

  for (const [name, r] of cases) {
    it(name, async () => {
      reply = r;
      const req = page(`${OLD}.${NOW_S - DAY * 2}`);

      const res = await proxy(req);

      assert.equal(calls.length, 1);
      assertUntouched(res, req);
    });
  }
});

// ---- getToken -----------------------------------------------------------------

describe("getToken", () => {
  it("점 앞의 토큰만 돌려준다", async () => {
    const cases: [string | undefined, string | null][] = [
      [undefined, null],
      ["", null],
      [`${OLD}.${NOW_S}`, OLD],
      [OLD, OLD],
      [`${OLD}.`, OLD],
      [`${OLD}.abc`, OLD],
      [`.${NOW_S}`, null],
    ];
    for (const [value, expected] of cases) {
      jar.clear();
      if (value !== undefined) jar.set("devvoca_token", value);
      assert.equal(await getToken(), expected, String(value));
    }
  });
});
