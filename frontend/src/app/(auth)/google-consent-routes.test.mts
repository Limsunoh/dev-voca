/**
 * 구글 왕복에서 가입 동의를 나르는 두 라우트.
 *
 * 실행: cd frontend && npm test
 *
 * 시작 라우트(/api/auth/google)
 *   consent=1 이고 우리 화면에서 누른 링크일 때만 10분짜리 쿠키를 굽는다.
 *   그 밖의 경우는 전에 남은 동의까지 지운다. 남겨 두면 체크박스를 본 적 없는
 *   새 계정에 예전 동의가 적용된다.
 * 콜백(/api/auth/google/callback)
 *   쿠키가 있을 때만 동의 값을 백엔드에 싣는다. 어떤 길로 끝나든 쿠키는
 *   지운다. consent_required 면 가입 화면으로, 그 밖의 실패는 로그인 화면으로.
 *
 * NextResponse·요청 해석은 실제 코드를 돌리고, 쿠키 저장소(next/headers)와
 * 백엔드(fetch)만 대역으로 둔다. "server-only" 는 Next 밖에서 해석되지 않아
 * stale-token.test.mts 와 같은 방법으로 빈 객체를 돌려준다.
 */
import assert from "node:assert/strict";
import Module from "node:module";
import { after, afterEach, beforeEach, describe, it, mock } from "node:test";

// ---- 쿠키 대역 --------------------------------------------------------------

type CookieOptions = Record<string, unknown>;

const jar = new Map<string, string>();
const written = new Map<string, CookieOptions | undefined>();
let deleted: string[] = [];

mock.module("next/headers", {
  namedExports: {
    async cookies() {
      return {
        get: (name: string) =>
          jar.has(name) ? { name, value: jar.get(name) } : undefined,
        set: (name: string, value: string, options?: CookieOptions) => {
          jar.set(name, value);
          written.set(name, options);
        },
        delete: (name: string) => {
          deleted.push(name);
          jar.delete(name);
        },
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

const start = await import("../api/auth/google/route");
const callback = await import("../api/auth/google/callback/route");

const ORIGIN = "http://localhost:3033";
const STATE = "devvoca_oauth_state";
const NEXT = "devvoca_oauth_next";
const CONSENT = "devvoca_oauth_consent";

const realFetch = globalThis.fetch;
const env = { ...process.env };

after(() => {
  globalThis.fetch = realFetch;
  loader._load = realLoad;
});

beforeEach(() => {
  jar.clear();
  written.clear();
  deleted = [];
  process.env.GOOGLE_CLIENT_ID = "test-client";
  process.env.API_URL = "http://fake-api.test";
  delete process.env.APP_ORIGIN;
});

afterEach(() => {
  process.env.GOOGLE_CLIENT_ID = env.GOOGLE_CLIENT_ID;
  process.env.API_URL = env.API_URL;
  if (env.GOOGLE_CLIENT_ID === undefined) delete process.env.GOOGLE_CLIENT_ID;
  if (env.API_URL === undefined) delete process.env.API_URL;
});

// ---- 시작 라우트 -------------------------------------------------------------

function begin(query: string, site?: string): Promise<Response> {
  const headers: Record<string, string> =
    site === undefined ? {} : { "Sec-Fetch-Site": site };
  return start.GET(new Request(`${ORIGIN}/api/auth/google${query}`, { headers }));
}

describe("구글 시작: 동의 쿠키를 굽는 조건", () => {
  for (const [label, site] of [
    ["same-origin", "same-origin"],
    ["헤더 없음(옛 브라우저)", undefined],
  ] as const) {
    it(`consent=1 + ${label} 이면 10분 쿠키 "1" 을 굽는다`, async () => {
      const res = await begin("?consent=1", site);

      assert.equal(jar.get(CONSENT), "1");
      assert.deepEqual(written.get(CONSENT), {
        httpOnly: true,
        secure: false,
        sameSite: "lax",
        path: "/",
        maxAge: 600,
      });
      assert.equal(res.status, 307);
      assert.match(res.headers.get("location") ?? "", /^https:\/\/accounts\.google\.com\//);
    });
  }

  for (const site of ["cross-site", "same-site", "none", "SAME-ORIGIN", "", "same-origin, cross-site"]) {
    it(`consent=1 이어도 Sec-Fetch-Site=${JSON.stringify(site)} 는 동의가 아니다`, async () => {
      jar.set(CONSENT, "1");

      await begin("?consent=1", site);

      assert.equal(jar.has(CONSENT), false);
      assert.ok(deleted.includes(CONSENT), "전에 남은 쿠키를 지우지 않았다");
    });
  }

  for (const query of ["", "?consent=0", "?consent=true", "?consent=", "?next=%2Fboard"]) {
    it(`same-origin 이어도 ${JSON.stringify(query)} 면 전에 남은 쿠키를 지운다`, async () => {
      jar.set(CONSENT, "1");

      await begin(query, "same-origin");

      assert.equal(jar.has(CONSENT), false);
      assert.ok(deleted.includes(CONSENT));
    });
  }

  it("클라이언트 ID 가 없으면 쿠키 없이 로그인 화면으로 보낸다", async () => {
    delete process.env.GOOGLE_CLIENT_ID;

    const res = await begin("?consent=1", "same-origin");

    assert.equal(res.headers.get("location"), `${ORIGIN}/login?error=google`);
    assert.equal(jar.has(CONSENT), false);
  });

  it("consent 와 함께 온 next 는 그대로 기억하고 밖으로 나가는 주소는 버린다", async () => {
    await begin("?consent=1&next=%2Fboard", "same-origin");
    assert.equal(jar.get(NEXT), "/board");

    await begin("?consent=1&next=%2F%2Fevil.example", "same-origin");
    assert.equal(jar.get(NEXT), "/");
  });
});

// ---- 콜백 -------------------------------------------------------------------

type Sent = { path: string; body: Record<string, unknown> };

let sent: Sent[] = [];

/** 백엔드가 줄 응답을 정한다. */
function backend(status: number, body: unknown): void {
  globalThis.fetch = (async (input: unknown, init?: RequestInit) => {
    sent.push({
      path: String(input),
      body: JSON.parse(String(init?.body)) as Record<string, unknown>,
    });
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
}

function cookies(values: { consent?: string; next?: string; state?: string }): void {
  jar.set(STATE, values.state ?? "s1");
  if (values.next !== undefined) jar.set(NEXT, values.next);
  if (values.consent !== undefined) jar.set(CONSENT, values.consent);
}

function back(query = "?state=s1&code=c1"): Promise<Response> {
  return callback.GET(new Request(`${ORIGIN}/api/auth/google/callback${query}`));
}

const OK = { token: "t1", user: { id: 1 } };
const ALL_GONE = [STATE, NEXT, CONSENT];

function assertAllCleared(): void {
  for (const name of ALL_GONE) {
    assert.equal(jar.has(name), false, `${name} 쿠키가 남았다`);
    assert.ok(deleted.includes(name), `${name} 를 지우지 않았다`);
  }
}

describe("구글 콜백: 동의 값 싣기", () => {
  beforeEach(() => {
    sent = [];
  });

  it('쿠키가 "1" 이면 두 값을 true 로 싣는다', async () => {
    backend(201, OK);
    cookies({ consent: "1" });

    await back();

    assert.equal(sent.length, 1);
    assert.equal(sent[0].path, "http://fake-api.test/api/accounts/google/");
    assert.deepEqual(sent[0].body, {
      code: "c1",
      redirect_uri: `${ORIGIN}/api/auth/google/callback`,
      terms_agreed: true,
      disclosure_agreed: true,
      age_confirmed: true,
    });
  });

  for (const [label, value] of [
    ["없음", undefined],
    ['"0"', "0"],
    ['"true"', "true"],
    ["빈 값", ""],
  ] as const) {
    it(`쿠키가 ${label} 이면 동의 값을 아예 싣지 않는다`, async () => {
      backend(200, OK);
      cookies({ consent: value });

      await back();

      assert.deepEqual(sent[0].body, {
        code: "c1",
        redirect_uri: `${ORIGIN}/api/auth/google/callback`,
      });
    });
  }
});

describe("구글 콜백: 어디로 돌아가나", () => {
  beforeEach(() => {
    sent = [];
  });

  it("consent_required 면 가입 화면으로 보내고 토큰을 넣지 않는다", async () => {
    backend(400, { code: "consent_required" });
    cookies({});

    const res = await back();

    assert.equal(res.headers.get("location"), `${ORIGIN}/signup?error=consent`);
    assert.equal(jar.has("devvoca_token"), false);
    assertAllCleared();
  });

  it("돌아갈 곳이 있으면 가입 화면까지 들고 간다", async () => {
    backend(400, { code: "consent_required" });
    cookies({ next: "/board/streak?x=1" });

    const res = await back();

    assert.equal(
      res.headers.get("location"),
      `${ORIGIN}/signup?error=consent&next=%2Fboard%2Fstreak%3Fx%3D1`,
    );
  });

  for (const next of ["//evil.example", "https://evil.example", "/"]) {
    it(`돌아갈 곳이 ${next} 면 next 를 붙이지 않는다`, async () => {
      backend(400, { code: "consent_required" });
      cookies({ next });

      const res = await back();

      assert.equal(res.headers.get("location"), `${ORIGIN}/signup?error=consent`);
    });
  }

  for (const [label, status, body] of [
    ["detail 오류", 400, { detail: "구글 확인 실패" }],
    ["code 칸 검증 오류", 400, { code: ["필수 항목입니다."] }],
    ["다른 code 값", 400, { code: "something_else" }],
    ["서버 오류 본문에 consent_required", 500, { code: "consent_required" }],
    ["다른 칸에 consent_required", 400, { email: "consent_required" }],
  ] as const) {
    it(`${label} 는 가입 화면이 아니라 로그인 화면으로 보낸다`, async (t) => {
      t.mock.method(console, "error", () => {});
      backend(status, body);
      cookies({ consent: "1", next: "/board" });

      const res = await back();

      assert.equal(res.headers.get("location"), `${ORIGIN}/login?error=google`);
      assertAllCleared();
    });
  }

  it("성공하면 토큰을 넣고 돌아갈 곳으로 간다", async () => {
    backend(201, OK);
    cookies({ consent: "1", next: "/board" });

    const res = await back();

    assert.equal(jar.get("devvoca_token"), "t1");
    assert.equal(res.headers.get("location"), `${ORIGIN}/board`);
    assertAllCleared();
  });

  for (const [label, query, value] of [
    ["구글에서 취소", "?error=access_denied", "s1"],
    ["state 불일치", "?state=WRONG&code=c1", "s1"],
    ["state 없음", "?code=c1", "s1"],
    ["code 없음", "?state=s1", "s1"],
  ] as const) {
    it(`${label}: 백엔드를 부르지 않고 쿠키를 모두 지운다`, async (t) => {
      t.mock.method(console, "error", () => {});
      backend(201, OK);
      cookies({ consent: "1", next: "/board", state: value });

      const res = await back(query);

      assert.equal(sent.length, 0);
      assert.match(res.headers.get("location") ?? "", /\/login(\?error=google)?$/);
      assertAllCleared();
    });
  }
});
