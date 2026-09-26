/**
 * 죽은 로그인 쿠키를 들고 한 판(/api/rounds)·소리내어 읽기(/api/talk) 중계를
 * 부를 때. 세션·중계 오류 변환은 대역 없이 실제 코드를 돌리고, 백엔드만
 * 가짜로 둔다.
 *
 * 실행: cd frontend && npm test
 *
 * 가짜 백엔드는 실제 DRF 처럼 군다 - 공개 API 라도 무효 토큰이 실리면 401.
 *
 * 계약.
 *   1. 어느 동작도 /me 를 묻지 않는다(로그인한 사람의 요청마다 왕복이 는다).
 *   2. start 는 쿠키 토큰을 실어 부른다. 401 이면 토큰 쿠키를 지우고
 *      Authorization 없이 한 번 더 불러 게스트 판을 연다. 게스트 쿠키는 남긴다.
 *      그래서 죽은 토큰이면 백엔드에 두 번(토큰 → 토큰 없이) 간다.
 *   3. 이어지는 answer/finish 는 쿠키가 지워졌으므로 토큰 없이 간다.
 *   4. start 가 401 이 아닌 오류(5xx·연결 실패)면 다시 부르지 않고 그 상태를
 *      돌려주며 쿠키도 안 지운다 - 게스트 판으로 바꿔 열면 로그인한 사람의
 *      기록이 말없이 사라진다.
 *   5. answer/finish 는 쿠키 토큰을 그대로 싣는다. 백엔드가 401 을 주면
 *      relayError 가 토큰 쿠키를 지운다.
 *   6. talk 는 start·grade 둘 다 2·4 와 같다(grade 는 읽는 사이 토큰이 죽을 수
 *      있다). 오류 변환은 라우트 자체다 - ApiError 면 그 상태, 연결 실패(0)면 502.
 *
 * 하네스: session.ts 의 `import "server-only"` 는 Next 밖에서 해석되지 않아
 * CJS 로더에서 그 이름만 빈 객체로 돌려준다(session-stale-token.test.mts 와 같다).
 */
import assert from "node:assert/strict";
import Module from "node:module";
import { after, beforeEach, describe, it, mock } from "node:test";

// ---- 쿠키 대역 --------------------------------------------------------------

const jar = new Map<string, string>();

mock.module("next/headers", {
  namedExports: {
    async cookies() {
      return {
        get: (name: string) =>
          jar.has(name) ? { name, value: jar.get(name) } : undefined,
        set: (name: string, value: string) => void jar.set(name, value),
        delete: (name: string) => void jar.delete(name),
      };
    },
  },
});

const loader = Module as unknown as {
  _load: (request: string, ...rest: unknown[]) => unknown;
};
const realLoad = loader._load;
loader._load = function (this: unknown, request: string, ...rest: unknown[]) {
  if (request === "server-only") return {};
  return realLoad.call(this, request, ...rest);
};

// ---- 가짜 백엔드 ------------------------------------------------------------

const DEAD = "dead-token";
const LIVE = "live-token";

/**
 * 토큰을 싣고 가는 첫 요청(한 판 열기·읽을 것 받기·채점)을 어떻게 받을지.
 * "ok" 면 토큰으로 판단한다.
 */
let startMode: "ok" | 500 | "down" = "ok";
let calls: { path: string; auth: string | null }[] = [];

const ROUND = { token: "round-1", question: null, remaining_seconds: 90 };
const PROMPT = { token: "talk-1", id: 1, kind: "word", term: "x" };

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const isStart = (path: string) =>
  path === "/api/learning/rounds/" ||
  path.startsWith("/api/vocab/talk/question/") ||
  path === "/api/vocab/talk/grade/";

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
  const url = new URL(String(input));
  const auth = new Headers(init?.headers).get("Authorization");
  calls.push({ path: url.pathname, auth });

  if (isStart(url.pathname)) {
    if (startMode === "down") throw new TypeError("fetch failed");
    if (startMode === 500) return json(500, { detail: "서버 오류" });
  }
  // DRF 의 TokenAuthentication: 무효 토큰이면 어느 API 든 401.
  if (auth === `Token ${DEAD}`) {
    return json(401, { detail: "토큰이 유효하지 않습니다." });
  }
  if (url.pathname === "/api/accounts/me/") return json(200, { id: 1 });
  if (url.pathname === "/api/learning/rounds/") return json(200, ROUND);
  if (url.pathname.startsWith("/api/learning/rounds/")) return json(200, {});
  if (url.pathname.startsWith("/api/vocab/talk/question/")) return json(200, PROMPT);
  if (url.pathname === "/api/vocab/talk/grade/") return json(200, {});
  return json(404, {});
}) as typeof fetch;

const realError = console.error;
console.error = () => {};

after(() => {
  globalThis.fetch = realFetch;
  console.error = realError;
  loader._load = realLoad;
});

const rounds = await import("./route");
const talk = await import("../talk/route");

beforeEach(() => {
  jar.clear();
  calls = [];
  startMode = "ok";
});

function withToken(token: string) {
  jar.set("devvoca_token", token);
  jar.set("devvoca_guest", "1");
}

function post(handler: (r: Request) => Promise<Response>, body: unknown) {
  return handler(
    new Request("http://x/api", { method: "POST", body: JSON.stringify(body) }),
  );
}

const meCount = () => calls.filter((c) => c.path === "/api/accounts/me/").length;

// ---------------------------------------------------------------------------

describe("/api/rounds start", () => {
  it("죽은 토큰이면 토큰으로 한 번, 거절되면 토큰 없이 한 번 더 불러 게스트 판을 연다", async () => {
    withToken(DEAD);
    const res = await post(rounds.POST, { action: "start" });
    assert.equal(res.status, 200);
    assert.equal((await res.json()).token, "round-1");
    assert.deepEqual(calls, [
      { path: "/api/learning/rounds/", auth: `Token ${DEAD}` },
      { path: "/api/learning/rounds/", auth: null },
    ]);
    assert.equal(jar.has("devvoca_token"), false, "토큰 쿠키가 지워져야 한다");
    assert.equal(jar.get("devvoca_guest"), "1", "게스트 쿠키는 남아야 한다");
  });

  it("이어지는 answer·finish 에는 토큰이 안 실리고 끝까지 200 이다", async () => {
    withToken(DEAD);
    await post(rounds.POST, { action: "start" });
    calls = [];
    const a = await post(rounds.POST, { action: "answer", token: "round-1", choice_id: 3 });
    const f = await post(rounds.POST, { action: "finish", token: "round-1" });
    assert.equal(a.status, 200);
    assert.equal(f.status, 200);
    assert.equal(calls.length, 2);
    assert.ok(calls.every((c) => c.auth === null));
  });

  it("살아 있는 토큰이면 한 번만, 그 토큰을 싣고 부르며 /me 는 묻지 않는다", async () => {
    withToken(LIVE);
    const res = await post(rounds.POST, { action: "start" });
    assert.equal(res.status, 200);
    assert.equal(jar.get("devvoca_token"), LIVE);
    assert.deepEqual(calls, [
      { path: "/api/learning/rounds/", auth: `Token ${LIVE}` },
    ]);
  });

  for (const [mode, status] of [
    [500, 500],
    ["down", 503],
  ] as const) {
    it(`백엔드가 ${mode} 면 게스트로 다시 열지 않고 ${status} 를 돌려주며 쿠키를 남긴다`, async () => {
      withToken(LIVE);
      startMode = mode;
      const res = await post(rounds.POST, { action: "start" });
      assert.equal(res.status, status);
      assert.equal(jar.get("devvoca_token"), LIVE);
      assert.deepEqual(calls, [
        { path: "/api/learning/rounds/", auth: `Token ${LIVE}` },
      ]);
    });
  }

  it("토큰이 없으면 토큰 없이 한 번 부른다", async () => {
    const res = await post(rounds.POST, { action: "start" });
    assert.equal(res.status, 200);
    assert.deepEqual(calls, [{ path: "/api/learning/rounds/", auth: null }]);
  });

  it("잘못된 action·본문이면 백엔드에 안 가고 쿠키도 안 지운다", async () => {
    withToken(DEAD);
    for (const body of [{ action: "START" }, { action: ["start"] }, "start", null]) {
      const res = await post(rounds.POST, body);
      assert.equal(res.status, 400);
    }
    assert.equal(calls.length, 0);
    assert.equal(jar.get("devvoca_token"), DEAD);
  });
});

describe("/api/rounds answer·finish", () => {
  it("살아 있는 토큰은 그대로 싣고 /me 를 묻지 않는다", async () => {
    withToken(LIVE);
    await post(rounds.POST, { action: "answer", token: "round-1", skip: true });
    await post(rounds.POST, { action: "finish", token: "round-1" });
    assert.equal(meCount(), 0);
    assert.equal(calls.length, 2);
    assert.ok(calls.every((c) => c.auth === `Token ${LIVE}`));
  });

  for (const action of ["answer", "finish"] as const) {
    it(`${action} 도중 토큰이 죽으면 401 을 돌려주고 토큰 쿠키만 지운다(다시 부르지 않는다)`, async () => {
      withToken(DEAD);
      const res = await post(rounds.POST, { action, token: "round-1", skip: true });
      assert.equal(res.status, 401);
      assert.deepEqual(await res.json(), { detail: "토큰이 유효하지 않습니다." });
      assert.equal(jar.has("devvoca_token"), false);
      assert.equal(jar.get("devvoca_guest"), "1");
      assert.equal(calls.length, 1);
    });
  }

  it("판 정보가 없어 400 이면 쿠키를 안 지운다", async () => {
    withToken(DEAD);
    const res = await post(rounds.POST, { action: "finish" });
    assert.equal(res.status, 400);
    assert.equal(jar.get("devvoca_token"), DEAD);
    assert.equal(calls.length, 0);
  });
});

describe("/api/talk", () => {
  it("start: 죽은 토큰이면 거절된 뒤 토큰 없이 다시 받고 쿠키를 지운다", async () => {
    withToken(DEAD);
    const res = await post(talk.POST, { action: "start" });
    assert.equal(res.status, 200);
    assert.equal((await res.json()).token, "talk-1");
    assert.equal(calls.length, 2);
    assert.deepEqual(
      calls.map((c) => c.auth),
      [`Token ${DEAD}`, null],
    );
    assert.equal(meCount(), 0);
    assert.equal(jar.has("devvoca_token"), false);
    assert.equal(jar.get("devvoca_guest"), "1");
  });

  it("start: 살아 있는 토큰이면 한 번만 싣고 부른다", async () => {
    withToken(LIVE);
    const res = await post(talk.POST, { action: "start" });
    assert.equal(res.status, 200);
    assert.deepEqual(
      calls.map((c) => c.auth),
      [`Token ${LIVE}`],
    );
  });

  const grade = { action: "grade", token: "talk-1", heard: ["x"] };

  for (const [action, body] of [
    ["start", { action: "start" }],
    ["grade", grade],
  ] as const) {
    for (const [mode, status] of [
      [500, 500],
      ["down", 502],
    ] as const) {
      it(`${action}: 백엔드가 ${mode} 면 게스트로 다시 부르지 않고 ${status} 이며 쿠키를 남긴다`, async () => {
        withToken(LIVE);
        startMode = mode;
        const res = await post(talk.POST, body);
        assert.equal(res.status, status);
        assert.equal(calls.length, 1);
        assert.equal(jar.get("devvoca_token"), LIVE);
      });
    }
  }

  it("grade: /me 를 묻지 않고 살아 있는 토큰을 한 번만 싣는다", async () => {
    withToken(LIVE);
    const res = await post(talk.POST, grade);
    assert.equal(res.status, 200);
    assert.deepEqual(calls, [{ path: "/api/vocab/talk/grade/", auth: `Token ${LIVE}` }]);
    assert.equal(jar.get("devvoca_token"), LIVE);
  });

  it("grade: 읽는 사이 토큰이 죽었으면 거절된 뒤 토큰 없이 채점하고 쿠키를 지운다", async () => {
    withToken(DEAD);
    const res = await post(talk.POST, grade);
    assert.equal(res.status, 200);
    assert.deepEqual(calls, [
      { path: "/api/vocab/talk/grade/", auth: `Token ${DEAD}` },
      { path: "/api/vocab/talk/grade/", auth: null },
    ]);
    assert.equal(jar.has("devvoca_token"), false);
    assert.equal(jar.get("devvoca_guest"), "1");
  });

  it("grade: 채점할 문장 토큰이 없으면 400 이고 백엔드·쿠키를 건드리지 않는다", async () => {
    withToken(DEAD);
    const res = await post(talk.POST, { action: "grade", heard: ["x"] });
    assert.equal(res.status, 400);
    assert.equal(calls.length, 0);
    assert.equal(jar.get("devvoca_token"), DEAD);
  });

  it("start 뒤 grade 까지 죽은 토큰이 다시 실리지 않는다", async () => {
    withToken(DEAD);
    await post(talk.POST, { action: "start" });
    calls = [];
    const res = await post(talk.POST, { action: "grade", token: "talk-1", heard: ["x"] });
    assert.equal(res.status, 200);
    assert.deepEqual(calls, [{ path: "/api/vocab/talk/grade/", auth: null }]);
  });
});
