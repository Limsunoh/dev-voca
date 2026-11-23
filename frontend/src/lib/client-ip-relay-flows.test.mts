/**
 * 가입·로그인 길 넷이 실제 clientIpHeaders(lib/client-ip.ts)로 백엔드에 머리를 싣는가.
 *
 * 실행: cd frontend && npm test
 *
 * 길: 이메일 로그인·가입(loginAction·signUpAction), 구글 버튼(googleCredentialAction),
 * 구글 화면을 다녀오는 콜백(app/api/auth/google/callback). 다른 테스트들은
 * clientIpHeaders 를 대역으로 바꿔 "머리가 실리는가" 만 본다. 여기서는 진짜 함수를 돌려
 * 인자 없이 부른 호출이 비밀값과 접속 IP 를 제대로 넘기는지 본다.
 *
 * 처리방침 v3 시행일(2026-11-19) 전까지 IP 를 빼던 날짜 문은 지웠다. 서버 시각을 그 전날로
 * 돌리고 시각대(TZ)를 바꿔도 IP 가 실려야 한다. 지운 문처럼 Date.now() 로 날짜를 세는
 * 비교가 다시 들어오면 빨개진다. new Date() 처럼 다른 길로 시계를 읽으면 잡지 못한다.
 *
 * 하네스: next/headers 의 headers()·cookies(), next/navigation, lib/session 만 대역이다.
 * `import "server-only"` 는 Next 번들러 밖에서 해석되지 않아 CJS 로더에서 빈 객체를
 * 돌려준다(client-ip.test.mts 와 같다).
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

class RedirectError extends Error {
  constructor(readonly to: string) {
    super("NEXT_REDIRECT");
  }
}

mock.module("next/navigation", {
  namedExports: {
    redirect(to: string): never {
      throw new RedirectError(to);
    },
    RedirectType: { push: "push", replace: "replace" },
  },
});

mock.module("@/lib/session", {
  namedExports: {
    async setToken() {},
    async clearToken() {},
    async getToken() {
      return undefined;
    },
    async carryGuestDailyLength() {},
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

const { loginAction, signUpAction } = await import("../app/(auth)/actions");
const { googleCredentialAction } = await import("../app/(auth)/google-actions");
const callback = await import("../app/api/auth/google/callback/route");

// ---- 가짜 백엔드 --------------------------------------------------------------

let sent: Headers[] = [];
const realFetch = globalThis.fetch;
const realEnv = { ...process.env };

beforeEach(() => {
  sent = [];
  jar.clear();
  process.env.API_URL = "http://fake-api.test";
  globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
    sent.push(new Headers(init?.headers));
    return new Response(JSON.stringify({ token: "tok", user: { id: 1, email: "a@b.c" } }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
});

afterEach(() => {
  incoming = new Headers();
  for (const key of ["RELAY_SECRET", "API_URL", "TZ"] as const) {
    if (realEnv[key] === undefined) delete process.env[key];
    else process.env[key] = realEnv[key];
  }
});

after(() => {
  globalThis.fetch = realFetch;
  loader._load = realLoad;
});

// ---- 길 넷 --------------------------------------------------------------------

function form(fields: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.set(k, v);
  return fd;
}

async function settle(run: () => Promise<unknown>): Promise<void> {
  try {
    await run();
  } catch (error) {
    if (!(error instanceof RedirectError)) throw error;
  }
}

const PASSWORD_MARK = ["leakmark", "pw"].join("-");

const FLOWS: Array<[string, () => Promise<unknown>]> = [
  ["이메일 로그인", () => loginAction({}, form({ email: "a@b.c", password: PASSWORD_MARK }))],
  [
    "가입",
    () =>
      signUpAction(
        {},
        form({
          email: "a@b.c",
          password: PASSWORD_MARK,
          terms_agreed: "on",
          disclosure_agreed: "on",
          age_confirmed: "on",
        }),
      ),
  ],
  [
    "구글 버튼",
    () => {
      jar.set("devvoca_google_nonce", "nonce-mark");
      return googleCredentialAction({ credential: "cred-mark" });
    },
  ],
  [
    "구글 콜백",
    () => {
      jar.set("devvoca_oauth_state", "st");
      return callback.GET(
        new Request("http://localhost:3033/api/auth/google/callback?state=st&code=c"),
      );
    },
  ],
];

// 비밀값처럼 생긴 글자를 이름 옆에 적지 않는다(GitGuardian, #169·#170).
const MARK = ["leakmark", "relay"].join("-");

/** 처리방침 v3 시행일 전날 한국 시간 23:59:59(UTC 14:59:59). */
const EVE = Date.UTC(2026, 10, 18, 14, 59, 59);

describe("가입·로그인 길이 실제 clientIpHeaders 로 머리를 싣는다", () => {
  for (const [name, run] of FLOWS) {
    it(`${name}: 비밀값과 x-forwarded-for 맨 앞 IP 를 싣는다`, async () => {
      process.env.RELAY_SECRET = MARK;
      incoming = new Headers({ "x-forwarded-for": "203.0.113.7, 10.0.0.1" });
      await settle(run);
      assert.equal(sent.length, 1, "백엔드를 한 번 불러야 한다");
      assert.equal(sent[0].get("X-Next-Relay"), MARK);
      assert.equal(sent[0].get("X-Next-Client-IP"), "203.0.113.7");
    });

    it(`${name}: 시각을 시행일 전날로, 시각대를 바꿔도 IP 를 싣는다`, async () => {
      process.env.RELAY_SECRET = MARK;
      incoming = new Headers({ "x-forwarded-for": "2001:db8::1" });
      for (const tz of ["UTC", "America/Los_Angeles", "Pacific/Kiritimati", "Asia/Seoul"]) {
        process.env.TZ = tz;
        for (const now of [EVE, Date.UTC(2000, 0, 1)]) {
          const clock = mock.method(Date, "now", () => now);
          sent = [];
          try {
            await settle(run);
          } finally {
            clock.mock.restore();
          }
          assert.equal(sent[0]?.get("X-Next-Client-IP"), "2001:db8::1", `${tz} ${now}`);
        }
      }
    });

    it(`${name}: 비밀값이 없으면 아무 머리도 싣지 않는다`, async () => {
      delete process.env.RELAY_SECRET;
      incoming = new Headers({ "x-forwarded-for": "203.0.113.7" });
      await settle(run);
      assert.equal(sent[0].get("X-Next-Relay"), null);
      assert.equal(sent[0].get("X-Next-Client-IP"), null);
    });

    it(`${name}: 접속 IP 가 없으면 비밀값만 싣는다`, async () => {
      process.env.RELAY_SECRET = MARK;
      await settle(run);
      assert.equal(sent[0].get("X-Next-Relay"), MARK);
      assert.equal(sent[0].get("X-Next-Client-IP"), null);
    });
  }

  it("요청마다 그때의 접속 IP 를 읽는다(앞 요청의 IP 가 남지 않는다)", async () => {
    process.env.RELAY_SECRET = MARK;
    const [, login] = FLOWS[0];
    for (const ip of ["198.51.100.1", "198.51.100.2"]) {
      incoming = new Headers({ "x-forwarded-for": ip });
      await settle(login);
    }
    assert.deepEqual(
      sent.map((h) => h.get("X-Next-Client-IP")),
      ["198.51.100.1", "198.51.100.2"],
    );
  });
});
