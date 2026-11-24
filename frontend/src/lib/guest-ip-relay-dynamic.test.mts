/**
 * 로그인하지 않고 부르는 문제풀기·순위표·소리내어 읽기가 백엔드에 접속 IP 를 싣는가.
 *
 * 실행: cd frontend && npm test
 *
 * 진짜 clientIpHeaders(lib/client-ip.ts), 진짜 withTokenOrGuest(lib/session.ts), 진짜
 * request()(lib/api/client.ts)를 돌리고, fetch 를 가로채 백엔드로 나가는 머리를 본다.
 * 길: app/api/rounds(시작·답하기·끝내기), app/api/quiz POST(단어·문장 채점),
 * app/api/talk(출제·채점), app/board/BoardScreen(순위표 셋).
 *
 * 계약.
 *   1. 토큰 없이 부르면 비밀값(X-Next-Relay)과 x-forwarded-for 맨 앞 IP(X-Next-Client-IP)를 싣는다.
 *   2. 토큰을 실은 요청에는 둘 다 없다. 처리방침 6절이 로그인하지 않았을 때만 넘긴다고 적었다.
 *   3. 쿠키의 토큰이 401 로 거절돼 withTokenOrGuest 가 토큰 없이 다시 부르면, 그 재요청에는
 *      IP 머리가 실린다(첫 요청에는 없다).
 *   4. RELAY_SECRET 이 없으면 아무것도 싣지 않고, 접속 IP 를 못 읽으면 비밀값만 싣는다.
 *   5. 브라우저가 X-Next-Client-IP·X-Next-Relay 를 지어 보내도 그 값은 백엔드로 안 간다.
 *
 * 하네스: next/headers 의 headers()·cookies() 만 대역이다. `import "server-only"` 는 Next
 * 번들러 밖에서 해석되지 않아 CJS 로더에서 빈 객체를 돌려준다(client-ip-relay-flows.test.mts).
 */
import assert from "node:assert/strict";
import Module from "node:module";
import { after, afterEach, beforeEach, describe, it, mock } from "node:test";

// ---- Next 런타임 대역 ---------------------------------------------------------

let incoming = new Headers();
const jar = new Map<string, string>();

mock.module("next/headers", {
  namedExports: {
    async headers() {
      return incoming;
    },
    async cookies() {
      return {
        get: (name: string) => (jar.has(name) ? { name, value: jar.get(name) } : undefined),
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

const rounds = await import("../app/api/rounds/route");
const quiz = await import("../app/api/quiz/route");
const talk = await import("../app/api/talk/route");
const { BoardScreen } = await import("../app/board/BoardScreen");
const { request } = await import("./api/client");
const { TOKEN_COOKIE, formatTokenCookie } = await import("./token-cookie");

// ---- 가짜 백엔드 --------------------------------------------------------------

type Sent = { url: string; headers: Headers };
let sent: Sent[] = [];
const realFetch = globalThis.fetch;
const realEnv = { ...process.env };

const LIVE = "live-token";
const DEAD = "dead-token";
// 비밀값처럼 생긴 글자를 이름 옆에 적지 않는다(GitGuardian, #169·#170).
const MARK = ["leakmark", "relay"].join("-");
const IP = "203.0.113.7";

beforeEach(() => {
  sent = [];
  jar.clear();
  process.env.API_URL = "http://fake-api.test";
  process.env.RELAY_SECRET = MARK;
  incoming = new Headers({ "x-forwarded-for": `${IP}, 10.0.0.1` });
  globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    sent.push({ url: String(url), headers });
    // 실제 DRF 처럼 무효 토큰이면 로그인 없이 쓰는 API 라도 401 이다.
    if (headers.get("Authorization") === `Token ${DEAD}`) {
      return new Response(JSON.stringify({ detail: "토큰이 유효하지 않습니다." }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify({ ok: true, entries: [], me: null }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
});

afterEach(() => {
  for (const key of ["RELAY_SECRET", "API_URL"] as const) {
    if (realEnv[key] === undefined) delete process.env[key];
    else process.env[key] = realEnv[key];
  }
});

after(() => {
  globalThis.fetch = realFetch;
  loader._load = realLoad;
});

function login(token: string | null) {
  if (token) jar.set(TOKEN_COOKIE, formatTokenCookie(token, Date.now() / 1000));
}

function post(path: string, body: unknown): Request {
  return new Request(`http://localhost:3000${path}`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

// ---- 길 --------------------------------------------------------------------

type Flow = {
  name: string;
  run: () => Promise<unknown>;
  /** 백엔드 경로. 다른 곳을 부르지 않았는지 본다. */
  path: string;
  /** 쿠키 토큰이 401 이면 토큰 없이 다시 부르는 길인가(withTokenOrGuest). */
  retries: boolean;
};

const FLOWS: Flow[] = [
  {
    name: "한 판 시작",
    run: () => rounds.POST(post("/api/rounds", { action: "start" })),
    path: "/api/learning/rounds/",
    retries: true,
  },
  {
    name: "한 판 답하기",
    run: () => rounds.POST(post("/api/rounds", { action: "answer", token: "rt", choice_id: 3 })),
    path: "/api/learning/rounds/answer/",
    retries: false,
  },
  {
    name: "한 판 끝내기",
    run: () => rounds.POST(post("/api/rounds", { action: "finish", token: "rt" })),
    path: "/api/learning/rounds/finish/",
    retries: false,
  },
  {
    name: "단어 낱개 채점",
    run: () => quiz.POST(post("/api/quiz", { token: "qt", picked: 1 })),
    path: "/api/vocab/words/grade/",
    retries: true,
  },
  {
    name: "문장 낱개 채점",
    run: () => quiz.POST(post("/api/quiz?content=sentences", { token: "qt", picked: 1 })),
    path: "/api/vocab/sentences/grade/",
    retries: true,
  },
  {
    name: "소리내어 읽기 출제",
    run: () => talk.POST(post("/api/talk", { action: "start", kind: "daily" })),
    path: "/api/vocab/talk/question/",
    retries: true,
  },
  {
    name: "소리내어 읽기 채점",
    run: () => talk.POST(post("/api/talk", { action: "grade", token: "tt", heard: ["hello"] })),
    path: "/api/vocab/talk/grade/",
    retries: true,
  },
  ...(["weekly", "all_time", "streak"] as const).map((kind) => ({
    name: `순위표 ${kind}`,
    run: () => BoardScreen({ kind }),
    path: `/api/learning/leaderboards/${kind === "all_time" ? "all-time" : kind}/`,
    retries: true,
  })),
];

function assertGuest(h: Headers, what: string) {
  assert.equal(h.get("Authorization"), null, `${what}: 토큰이 실렸다`);
  assert.equal(h.get("X-Next-Relay"), MARK, `${what}: 비밀값이 없다`);
  assert.equal(h.get("X-Next-Client-IP"), IP, `${what}: 접속 IP 가 없다`);
}

function assertMember(h: Headers, token: string, what: string) {
  assert.equal(h.get("Authorization"), `Token ${token}`, `${what}: 토큰이 없다`);
  assert.equal(h.get("X-Next-Relay"), null, `${what}: 로그인한 요청에 비밀값이 실렸다`);
  assert.equal(h.get("X-Next-Client-IP"), null, `${what}: 로그인한 요청에 IP 가 실렸다`);
}

describe("로그인하지 않은 요청만 접속 IP 를 싣는다", () => {
  for (const flow of FLOWS) {
    it(`${flow.name}: 토큰이 없으면 비밀값과 접속 IP 를 싣는다`, async () => {
      await flow.run();
      assert.equal(sent.length, 1);
      assert.equal(new URL(sent[0].url).pathname, flow.path);
      assertGuest(sent[0].headers, flow.name);
    });

    it(`${flow.name}: 토큰이 있으면 IP 머리를 싣지 않는다`, async () => {
      login(LIVE);
      await flow.run();
      assert.equal(sent.length, 1);
      assertMember(sent[0].headers, LIVE, flow.name);
    });

    it(`${flow.name}: 쿠키 토큰이 401 이면 ${flow.retries ? "토큰 없이 다시 부르는 쪽에만 IP 를 싣는다" : "다시 부르지 않고 IP 도 싣지 않는다"}`, async () => {
      login(DEAD);
      await flow.run();
      assertMember(sent[0].headers, DEAD, `${flow.name} 첫 요청`);
      if (flow.retries) {
        assert.equal(sent.length, 2, "토큰 없이 다시 부르지 않았다");
        assert.equal(new URL(sent[1].url).pathname, flow.path);
        assertGuest(sent[1].headers, `${flow.name} 재요청`);
      } else {
        assert.equal(sent.length, 1);
      }
    });

    it(`${flow.name}: RELAY_SECRET 이 없으면 아무 머리도 싣지 않는다`, async () => {
      delete process.env.RELAY_SECRET;
      await flow.run();
      assert.equal(sent[0].headers.get("X-Next-Relay"), null);
      assert.equal(sent[0].headers.get("X-Next-Client-IP"), null);
    });

    it(`${flow.name}: 접속 IP 를 못 읽으면 비밀값만 싣는다`, async () => {
      incoming = new Headers();
      await flow.run();
      assert.equal(sent[0].headers.get("X-Next-Relay"), MARK);
      assert.equal(sent[0].headers.get("X-Next-Client-IP"), null);
    });

    it(`${flow.name}: 브라우저가 지어 보낸 IP·비밀값 머리는 백엔드로 안 간다`, async () => {
      incoming = new Headers({
        "x-forwarded-for": IP,
        "x-next-client-ip": "6.6.6.6",
        "x-next-relay": "browser-made",
      });
      await flow.run();
      assertGuest(sent[0].headers, flow.name);

      // 비밀값이 없는 로컬에서도 브라우저 값이 새지 않는다.
      sent = [];
      delete process.env.RELAY_SECRET;
      await flow.run();
      assert.equal(sent[0].headers.get("X-Next-Relay"), null);
      assert.equal(sent[0].headers.get("X-Next-Client-IP"), null);
    });
  }
});

describe("request() 의 guestHeaders", () => {
  const guest = { "X-Next-Relay": MARK, "X-Next-Client-IP": IP };

  it("토큰이 있으면 버리고, 없으면 싣는다", async () => {
    await request("/x/", { token: LIVE, guestHeaders: guest });
    await request("/x/", { guestHeaders: guest });
    assertMember(sent[0].headers, LIVE, "토큰 있음");
    assertGuest(sent[1].headers, "토큰 없음");
  });

  it("빈 토큰은 토큰이 없는 것이다(Authorization 도 없다)", async () => {
    await request("/x/", { token: "", guestHeaders: guest });
    assertGuest(sent[0].headers, "빈 토큰");
  });
});
