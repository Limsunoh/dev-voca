/**
 * 구글 버튼(화면 아래 계정 창, FedCM)으로 로그인하는 서버 액션.
 *
 * 실행: cd frontend && npm test
 *
 * prepareGoogleButton
 *   클라이언트 ID 가 없으면 null(버튼은 예전 링크를 보인다). 있으면 비밀값을
 *   1시간짜리 httpOnly 쿠키에 넣고, 구글에 넘길 nonce 로는 그 sha256 을 준다.
 *   토큰 안의 nonce 는 누구나 읽으므로 대조는 비밀값으로 한다.
 * googleCredentialAction
 *   신분 토큰과 쿠키의 nonce 를 백엔드에 넘긴다. nonce 쿠키는 어떤 길로
 *   끝나든 지운다. 동의 값은 consent 가 정확히 true 일 때만 싣는다. 끝나면
 *   바꿔치기(replace)로 보낸다. 성공은 돌아갈 곳, consent_required 는 가입
 *   화면, 그 밖의 실패는 로그인 화면(error=google).
 *
 * 쿠키 저장소(next/headers), redirect, 백엔드 호출, 세션은 대역이다.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import Module from "node:module";
import { after, beforeEach, describe, it, mock } from "node:test";

type CookieOptions = Record<string, unknown>;
const jar = new Map<string, string>();
const written = new Map<string, CookieOptions | undefined>();
let deleted: string[] = [];

mock.module("next/headers", {
  namedExports: {
    async cookies() {
      return {
        get: (name: string) => (jar.has(name) ? { name, value: jar.get(name) } : undefined),
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

class Redirect extends Error {
  constructor(
    readonly to: string,
    readonly type: string | undefined,
  ) {
    super(`NEXT_REDIRECT ${to}`);
  }
}
mock.module("next/navigation", {
  namedExports: {
    redirect(to: string, type?: string): never {
      throw new Redirect(to, type);
    },
    RedirectType: { push: "push", replace: "replace" },
  },
});

let calls: Record<string, unknown>[] = [];
let reply: () => Promise<unknown> = async () => ({ token: "tok", user: { id: 1 } });
mock.module("@/lib/api/accounts", {
  namedExports: {
    async logInWithGoogle(body: Record<string, unknown>) {
      calls.push(body);
      return reply();
    },
  },
});

const sessions: string[] = [];
mock.module("@/lib/session", {
  namedExports: {
    async setToken(token: string) {
      sessions.push(`set ${token}`);
    },
    async carryGuestDailyLength(token: string) {
      sessions.push(`carry ${token}`);
    },
  },
});

const loader = Module as unknown as { _load: (request: string, ...rest: unknown[]) => unknown };
const realLoad = loader._load;
loader._load = function (this: unknown, request: string, ...rest: unknown[]) {
  if (request === "server-only") return {};
  return realLoad.call(this, request, ...rest);
};

const { prepareGoogleButton, googleCredentialAction } = await import("./google-actions");
const { ApiError } = await import("@/lib/api/client");

const NONCE = "devvoca_google_nonce";
const env = { ...process.env };

after(() => {
  loader._load = realLoad;
  process.env = env;
});

beforeEach(() => {
  jar.clear();
  written.clear();
  deleted = [];
  calls = [];
  sessions.length = 0;
  reply = async () => ({ token: "tok", user: { id: 1 } });
  process.env.GOOGLE_CLIENT_ID = "test-client.apps.googleusercontent.com";
});

/** 액션을 돌려 어디로 보냈는지 돌려준다. */
async function run(input: Parameters<typeof googleCredentialAction>[0]) {
  let result: Awaited<ReturnType<typeof googleCredentialAction>>;
  try {
    result = await googleCredentialAction(input);
  } catch (error) {
    if (error instanceof Redirect) return { to: error.to, type: error.type };
    throw error;
  }
  // 실패는 화면을 옮기지 않고 { failed: true } 를 돌려준다. 화면(GoogleButton)이
  // 그것을 받아 로그인 화면을 문서째 바꿔치기한다. 그 결과로 바꿔 본다.
  if (result?.failed) return { to: "/login?error=google", type: "replace" };
  assert.fail("redirect 하지 않았고 실패도 아니다");
}

describe("prepareGoogleButton", () => {
  it("클라이언트 ID 가 없으면 null 이고 쿠키를 굽지 않는다", async () => {
    delete process.env.GOOGLE_CLIENT_ID;
    assert.equal(await prepareGoogleButton(), null);
    assert.equal(jar.size, 0);
  });

  it("비밀값은 1시간짜리 httpOnly 쿠키에, 구글에는 그 sha256 을 준다", async () => {
    const prep = await prepareGoogleButton();
    assert.ok(prep);
    assert.equal(prep.clientId, "test-client.apps.googleusercontent.com");
    const secret = jar.get(NONCE);
    assert.match(secret ?? "", /^[0-9a-f]{64}$/);
    assert.notEqual(prep.nonce, secret, "비밀값을 구글에 그대로 넘겼다");
    assert.equal(prep.nonce, createHash("sha256").update(secret ?? "").digest("hex"));
    const opts = written.get(NONCE);
    assert.equal(opts?.httpOnly, true);
    assert.equal(opts?.maxAge, 3600);
    assert.equal(opts?.sameSite, "lax");
  });

  it("인자가 객체가 아니어도 500 이 아니라 로그인 화면으로", async () => {
    jar.set(NONCE, "n1");
    const errors = mock.method(console, "error", () => {});
    try {
      for (const input of [null, undefined, "jwt", 3]) {
        assert.equal(
          (await run(input as unknown as Parameters<typeof googleCredentialAction>[0])).to,
          "/login?error=google",
        );
      }
    } finally {
      errors.mock.restore();
    }
    assert.deepEqual(calls, []);
  });

  it("부를 때마다 새 nonce 다", async () => {
    const a = await prepareGoogleButton();
    const b = await prepareGoogleButton();
    assert.notEqual(a?.nonce, b?.nonce);
  });
});

describe("googleCredentialAction", () => {
  it("성공하면 토큰을 저장하고 돌아갈 곳으로 바꿔치기한다", async () => {
    jar.set(NONCE, "n1");
    const res = await run({ credential: "jwt", next: "/learn/words" });
    assert.deepEqual(res, { to: "/learn/words", type: "replace" });
    assert.deepEqual(calls, [{ credential: "jwt", nonce: "n1" }]);
    assert.deepEqual(sessions, ["set tok", "carry tok"]);
    assert.ok(deleted.includes(NONCE), "nonce 쿠키를 안 지웠다");
  });

  it("동의 값은 consent 가 정확히 true 일 때만 싣는다", async () => {
    jar.set(NONCE, "n1");
    await run({ credential: "jwt", consent: true });
    assert.deepEqual(calls[0], {
      credential: "jwt",
      nonce: "n1",
      terms_agreed: true,
      disclosure_agreed: true,
      age_confirmed: true,
    });
    for (const consent of ["true", 1, {}]) {
      calls = [];
      jar.set(NONCE, "n1");
      await run({ credential: "jwt", consent });
      assert.deepEqual(calls[0], { credential: "jwt", nonce: "n1" }, String(consent));
    }
  });

  it("돌아갈 곳이 바깥 주소면 홈으로", async () => {
    jar.set(NONCE, "n1");
    assert.deepEqual(await run({ credential: "jwt", next: "https://evil.example" }), {
      to: "/",
      type: "replace",
    });
  });

  it("nonce 쿠키가 없거나 신분 토큰이 글자가 아니면 백엔드를 부르지 않고 로그인 화면으로", async () => {
    assert.deepEqual(await run({ credential: "jwt" }), {
      to: "/login?error=google",
      type: "replace",
    });
    for (const credential of ["", 3, null, { a: 1 }]) {
      jar.set(NONCE, "n1");
      const res = await run({ credential });
      assert.equal(res.to, "/login?error=google");
      assert.ok(!jar.has(NONCE), "실패해도 nonce 를 지운다");
    }
    assert.deepEqual(calls, []);
    assert.deepEqual(sessions, []);
  });

  it("새 계정인데 동의가 없으면 가입 화면으로(돌아갈 곳을 싣고)", async () => {
    jar.set(NONCE, "n1");
    reply = async () => {
      throw new ApiError("consent_required", 400, "code");
    };
    assert.deepEqual(await run({ credential: "jwt", next: "/board" }), {
      to: "/signup?error=consent&next=%2Fboard",
      type: "replace",
    });
    jar.set(NONCE, "n1");
    assert.equal((await run({ credential: "jwt" })).to, "/signup?error=consent");
    assert.deepEqual(sessions, []);
  });

  it("실패는 화면을 옮기지 않고 { failed: true } 를 돌려준다(같은 로그인 화면에서 버튼이 새로 붙게)", async () => {
    jar.set(NONCE, "n1");
    reply = async () => {
      throw new ApiError("구글 로그인을 확인하지 못했습니다.", 400);
    };
    const errors = mock.method(console, "error", () => {});
    try {
      assert.deepEqual(await googleCredentialAction({ credential: "jwt" }), { failed: true });
    } finally {
      errors.mock.restore();
    }
  });

  it("그 밖의 실패는 로그인 화면(error=google)으로, 토큰은 저장하지 않는다", async () => {
    jar.set(NONCE, "n1");
    reply = async () => {
      throw new ApiError("구글 로그인을 확인하지 못했습니다.", 400);
    };
    const errors = mock.method(console, "error", () => {});
    try {
      assert.deepEqual(await run({ credential: "jwt", next: "/board" }), {
        to: "/login?error=google",
        type: "replace",
      });
    } finally {
      errors.mock.restore();
    }
    assert.deepEqual(sessions, []);
  });
});
