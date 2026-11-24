/**
 * proxy 의 첫 화면 보내기(firstScreen)를 깨뜨려 본다. 백엔드는 가짜 fetch 다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약.
 *   1. GET "/" 에서 로그인 쿠키도 게스트 쿠키(devvoca_guest=1)도 없으면 307 /start.
 *   2. 게스트인데 하루 공부량 쿠키가 5m·10m·30m 이 아니면 307 /start/daily.
 *   3. 로그인 쿠키가 있으면 보내지 않는다(공부량은 계정에 있어 홈이 묻는다). 값이 깨져
 *      토큰을 못 꺼내는 쿠키("", ".123", ".")는 없는 것으로 본다.
 *   4. 이어 가기가 401 을 받아 쿠키를 지우기로 했으면 토큰이 없는 것으로 보고, 보낼 때도
 *      Set-Cookie 로 토큰을 지운다. 5xx·연결 실패·시간 초과면 토큰을 그대로 믿는다.
 *   5. "/" 가 아닌 경로, GET 이 아닌 요청, 문서 요청이 아닌 것(sec-fetch-dest 가 document 가
 *      아니거나 없음 - 앱 안 이동, 서버 액션의 redirect)은 보내지 않는다.
 *   6. 보내지 않을 때는 예전과 같다(CSP 가 실린다).
 *
 * 하네스는 proxy-renew-dynamic.test.mts 와 같다.
 */
import assert from "node:assert/strict";
import Module from "node:module";
import { after, beforeEach, describe, it, mock } from "node:test";

import { NextRequest } from "next/server";

const loader = Module as unknown as { _load: (request: string, ...rest: unknown[]) => unknown };
const realLoad = loader._load;
loader._load = function (this: unknown, request: string, ...rest: unknown[]) {
  if (request === "server-only") return {};
  return realLoad.call(this, request, ...rest);
};

// ---- 가짜 백엔드(이어 가기) --------------------------------------------------

type Reply = { status: number; body?: unknown } | "down" | "timeout";
let reply: Reply = { status: 200 };
let calls = 0;

const realFetch = globalThis.fetch;
globalThis.fetch = (async () => {
  calls += 1;
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

// ---- 도구 -------------------------------------------------------------------

const ORIGIN = "https://dev-voca.vercel.app";
const TOKEN = "a".repeat(40);
const NEW = "b".repeat(40);
const DAY = 86_400;
const NOW_MS = 1_800_000_000_500;
const NOW_S = Math.floor(NOW_MS / 1000);
/** 하루가 안 지나 이어 가기를 부르지 않는 쿠키. */
const FRESH = `${TOKEN}.${NOW_S - 60}`;
/** 하루가 지나 이어 가기를 부르는 쿠키. */
const STALE = `${TOKEN}.${NOW_S - DAY * 2}`;

type Jar = { token?: string; guest?: string; length?: string };

/** 브라우저가 화면을 통째로 여는 요청. dest 를 null 로 주면 머리를 안 싣는다. */
function request(path: string, jar: Jar = {}, method = "GET", dest: string | null = "document"): NextRequest {
  const parts: string[] = [];
  if (jar.token !== undefined) parts.push(`devvoca_token=${jar.token}`);
  if (jar.guest !== undefined) parts.push(`devvoca_guest=${jar.guest}`);
  if (jar.length !== undefined) parts.push(`devvoca_daily_length=${jar.length}`);
  const headers: Record<string, string> = parts.length ? { cookie: parts.join("; ") } : {};
  if (dest !== null) headers["sec-fetch-dest"] = dest;
  return new NextRequest(`${ORIGIN}${path}`, { method, headers });
}

/** 보낸 곳의 경로. 안 보냈으면 null. */
function sentTo(res: Response): string | null {
  const location = res.headers.get("location");
  if (location === null) return null;
  const url = new URL(location);
  assert.equal(url.origin, ORIGIN, "다른 출처로 보냈다");
  return url.pathname;
}

function tokenSetCookies(res: Response): string[] {
  return res.headers.getSetCookie().filter((line) => line.startsWith("devvoca_token="));
}

function assertRedirect(res: Response, to: string) {
  assert.equal(res.status, 307);
  assert.equal(sentTo(res), to);
}

function assertPassThrough(res: Response) {
  assert.equal(sentTo(res), null, "보내면 안 되는 요청을 보냈다");
  assert.notEqual(res.status, 307);
  assert.ok(res.headers.get("content-security-policy"), "CSP 가 없다");
}

beforeEach(() => {
  reply = { status: 200, body: { token: NEW, issued_at: NOW_S } };
  calls = 0;
  mock.restoreAll();
  mock.method(Date, "now", () => NOW_MS);
});

// ---- 쿠키 조합 --------------------------------------------------------------

describe("firstScreen - 쿠키 없음·게스트", () => {
  it("아무 쿠키도 없으면 307 /start, 백엔드는 부르지 않는다", async () => {
    const res = await proxy(request("/"));
    assertRedirect(res, "/start");
    assert.deepEqual(tokenSetCookies(res), []);
    assert.equal(calls, 0);
  });

  it("게스트만 있으면 307 /start/daily", async () => {
    assertRedirect(await proxy(request("/", { guest: "1" })), "/start/daily");
  });

  for (const length of ["5m", "10m", "30m"]) {
    it(`게스트 + 공부량 ${length} 이면 홈을 그린다`, async () => {
      assertPassThrough(await proxy(request("/", { guest: "1", length })));
    });
  }

  for (const length of ["", "15m", "10M", "10", "%2010m", "5m,10m"]) {
    it(`게스트 + 이상한 공부량 ${JSON.stringify(length)} 이면 /start/daily`, async () => {
      assertRedirect(await proxy(request("/", { guest: "1", length })), "/start/daily");
    });
  }

  for (const guest of ["", "0", "true", "1 ", "11"]) {
    it(`게스트 쿠키 값이 ${JSON.stringify(guest)} 면 게스트가 아니다 - /start`, async () => {
      assertRedirect(await proxy(request("/", { guest, length: "10m" })), "/start");
    });
  }

  it("공부량 쿠키만 있고 게스트가 아니면 /start", async () => {
    assertRedirect(await proxy(request("/", { length: "10m" })), "/start");
  });
});

describe("firstScreen - 로그인 쿠키", () => {
  it("살아 있는 토큰만 있으면 보내지 않고 백엔드도 부르지 않는다", async () => {
    assertPassThrough(await proxy(request("/", { token: FRESH })));
    assert.equal(calls, 0);
  });

  it("토큰 + 게스트(공부량 없음)여도 보내지 않는다 - 공부량은 계정에 있다", async () => {
    assertPassThrough(await proxy(request("/", { token: FRESH, guest: "1" })));
  });

  it("시각 없는 옛 쿠키(토큰만)도 토큰으로 본다", async () => {
    assertPassThrough(await proxy(request("/", { token: TOKEN })));
  });

  for (const broken of ["", ".", `.${NOW_S}`]) {
    it(`토큰을 못 꺼내는 쿠키 ${JSON.stringify(broken)} 는 없는 것으로 본다`, async () => {
      assertRedirect(await proxy(request("/", { token: broken })), "/start");
      assertRedirect(await proxy(request("/", { token: broken, guest: "1" })), "/start/daily");
      assertPassThrough(await proxy(request("/", { token: broken, guest: "1", length: "5m" })));
      assert.equal(calls, 0);
    });
  }

  it("하루 지난 토큰이 새 토큰을 받으면 보내지 않고 새 쿠키를 싣는다", async () => {
    const res = await proxy(request("/", { token: STALE }));
    assertPassThrough(res);
    assert.equal(calls, 1);
    assert.equal(tokenSetCookies(res)[0]?.split("; ")[0], `devvoca_token=${NEW}.${NOW_S}`);
  });
});

describe("firstScreen - 하루 지나 401 받은 토큰", () => {
  beforeEach(() => {
    reply = { status: 401, body: { detail: "x" } };
  });

  function assertTokenDeleted(res: Response) {
    const lines = tokenSetCookies(res);
    assert.equal(lines.length, 1, lines.join(" | "));
    assert.match(lines[0], /^devvoca_token=;/);
    assert.match(lines[0], /Max-Age=0|Expires=Thu, 01 Jan 1970/);
  }

  it("게스트도 아니면 /start 로 보내며 토큰을 지운다", async () => {
    const res = await proxy(request("/", { token: STALE }));
    assertRedirect(res, "/start");
    assertTokenDeleted(res);
  });

  it("게스트인데 공부량이 없으면 /start/daily 로 보내며 토큰을 지운다", async () => {
    const res = await proxy(request("/", { token: STALE, guest: "1" }));
    assertRedirect(res, "/start/daily");
    assertTokenDeleted(res);
  });

  it("게스트 + 공부량이면 홈을 그리되 토큰은 지운다", async () => {
    const res = await proxy(request("/", { token: STALE, guest: "1", length: "30m" }));
    assertPassThrough(res);
    assertTokenDeleted(res);
  });

  it("보낼 때 게스트 쿠키·공부량 쿠키는 건드리지 않는다", async () => {
    const res = await proxy(request("/", { token: STALE, guest: "1" }));
    const others = res.headers.getSetCookie().filter((line) => !line.startsWith("devvoca_token="));
    assert.deepEqual(others, []);
  });
});

describe("firstScreen - 이어 가기가 401 이 아닌 이유로 실패", () => {
  const cases: [string, Reply][] = [
    ["500", { status: 500 }],
    ["503", { status: 503 }],
    ["403", { status: 403, body: { detail: "x" } }],
    ["연결 실패", "down"],
    ["시간 초과", "timeout"],
  ];
  for (const [name, r] of cases) {
    it(`${name}: 토큰을 믿고 보내지 않으며 쿠키도 그대로다`, async () => {
      reply = r;
      const res = await proxy(request("/", { token: STALE }));
      assertPassThrough(res);
      assert.equal(calls, 1);
      assert.deepEqual(tokenSetCookies(res), []);
    });
  }
});

// ---- 경로·메서드 ------------------------------------------------------------

describe("firstScreen - 홈이 아닌 요청은 보내지 않는다", () => {
  for (const path of ["/start", "/start/daily", "/learn/words", "/profile", "/login", "/board", "/start/"]) {
    it(`쿠키 없는 GET ${path}`, async () => {
      assertPassThrough(await proxy(request(path)));
    });
  }

  for (const method of ["POST", "HEAD", "PUT", "DELETE"]) {
    it(`쿠키 없는 ${method} /`, async () => {
      const res = await proxy(request("/", {}, method));
      assertPassThrough(res);
    });
  }

  it("401 받을 토큰이어도 POST / 는 보내지 않고 쿠키도 안 건드린다", async () => {
    reply = { status: 401, body: { detail: "x" } };
    const res = await proxy(request("/", { token: STALE }, "POST"));
    assertPassThrough(res);
    assert.deepEqual(tokenSetCookies(res), []);
    assert.equal(calls, 0);
  });

  it("검색어가 붙은 홈(/?from=app)도 홈이다 - 보낸 곳은 같은 출처의 /start", async () => {
    assertRedirect(await proxy(request("/?from=app")), "/start");
  });

  for (const dest of ["empty", null, "iframe", "script"]) {
    it(`sec-fetch-dest 가 ${dest ?? "없음"} 이면 보내지 않고 홈에 맡긴다(앱 안 이동·서버 액션의 redirect)`, async () => {
      for (const jar of [{}, { guest: "1" }] as Jar[]) {
        assertPassThrough(await proxy(request("/", jar, "GET", dest)));
      }
    });
  }

  it("rsc 머리가 붙어도 문서 요청이면 같은 규칙이다(Next 는 proxy 앞에서 rsc 를 지운다)", async () => {
    const req = request("/");
    req.headers.set("rsc", "1");
    assertRedirect(await proxy(req), "/start");
  });

  it("401 받을 토큰의 문서 아닌 요청은 보내지 않되 토큰은 지운다", async () => {
    reply = { status: 401, body: { detail: "x" } };
    const res = await proxy(request("/", { token: STALE }, "GET", "empty"));
    assertPassThrough(res);
    assert.match(tokenSetCookies(res)[0] ?? "", /^devvoca_token=;/);
  });
});
