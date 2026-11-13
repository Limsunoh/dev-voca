/**
 * 구글 버튼 서버 액션(googleCredentialAction)의 경계와 남용.
 *
 * 실행: cd frontend && npm test
 *
 * google-actions.test.mts 가 기본 흐름을 본다. 여기서는 그 바깥을 민다:
 *   - 한 번 쓴 nonce 를 다시 쓰기(같은 브라우저에서 콜백이 두 번 온 경우와 같다)
 *   - 바깥으로 나가는 next 의 여러 꼴
 *   - 백엔드 실패 종류마다 어디로 가는지, 그리고 전부 바꿔치기(replace)인지
 *   - 토큰을 받았는데 세션 저장이 실패한 경우
 *
 * 쿠키 저장소(next/headers), redirect, 백엔드 호출, 세션은 대역이다.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import Module from "node:module";
import { after, beforeEach, describe, it, mock } from "node:test";

const jar = new Map<string, string>();

mock.module("next/headers", {
  namedExports: {
    async cookies() {
      return {
        get: (name: string) => (jar.has(name) ? { name, value: jar.get(name) } : undefined),
        set: (name: string, value: string) => {
          jar.set(name, value);
        },
        delete: (name: string) => {
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

let sessions: string[] = [];
let setTokenFails = false;
mock.module("@/lib/session", {
  namedExports: {
    async setToken(token: string) {
      if (setTokenFails) throw new Error("cookie write failed");
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
const errors = mock.method(console, "error", () => {});

after(() => {
  loader._load = realLoad;
  process.env = env;
  errors.mock.restore();
});

beforeEach(() => {
  jar.clear();
  calls = [];
  sessions = [];
  setTokenFails = false;
  reply = async () => ({ token: "tok", user: { id: 1 } });
  process.env.GOOGLE_CLIENT_ID = "test-client.apps.googleusercontent.com";
});

/** 액션을 돌려 어디로 보냈는지 돌려준다. redirect 를 안 하면 실패. */
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

const sha256 = (value: unknown) => createHash("sha256").update(String(value)).digest("hex");

describe("한 번 쓴 nonce", () => {
  it("성공한 뒤 같은 브라우저에서 다시 부르면 백엔드를 부르지 않고 로그인 화면으로", async () => {
    const prep = await prepareGoogleButton();
    assert.ok(prep);
    assert.equal((await run({ credential: "jwt", next: "/board" })).to, "/board");
    assert.equal(calls.length, 1);
    // 백엔드에는 쿠키의 비밀값이 가고, 구글에 넘긴 nonce 는 그 해시다.
    assert.equal(sha256(calls[0].nonce), prep.nonce);

    // 콜백이 두 번 온 경우. 쿠키의 nonce 는 이미 지워졌다.
    const second = await run({ credential: "jwt", next: "/board" });
    assert.deepEqual(second, { to: "/login?error=google", type: "replace" });
    assert.equal(calls.length, 1, "두 번째에 백엔드를 불렀다");
  });

  it("실패한 뒤에도 nonce 는 남지 않는다", async () => {
    await prepareGoogleButton();
    reply = async () => {
      throw new ApiError("구글 로그인을 확인하지 못했습니다.", 400);
    };
    await run({ credential: "jwt" });
    assert.ok(!jar.has(NONCE));
  });

  it("버튼을 다시 그리면 새 nonce 로 바뀌고 옛 값은 쓰이지 않는다", async () => {
    const a = await prepareGoogleButton();
    const b = await prepareGoogleButton();
    await run({ credential: "jwt" });
    assert.equal(sha256(calls[0].nonce), b?.nonce);
    assert.notEqual(sha256(calls[0].nonce), a?.nonce);
  });
});

describe("동의 값 위조", () => {
  for (const consent of ["true", "1", 1, [true], { valueOf: () => true }, null]) {
    it(`consent=${JSON.stringify(consent) ?? String(consent)} 이면 동의를 싣지 않는다`, async () => {
      jar.set(NONCE, "n1");
      await run({ credential: "jwt", consent });
      assert.deepEqual(Object.keys(calls[0]).sort(), ["credential", "nonce"]);
    });
  }
});

describe("돌아갈 곳(next)", () => {
  const outside: unknown[] = [
    "//evil.example",
    "/\\evil.example",
    "\\\\evil.example",
    "https://evil.example/x",
    "javascript:alert(1)",
    "/\t/evil.example",
    " /board",
    ["/board"],
    42,
  ];
  for (const next of outside) {
    it(`${JSON.stringify(next)} 는 홈으로`, async () => {
      jar.set(NONCE, "n1");
      assert.deepEqual(await run({ credential: "jwt", next }), { to: "/", type: "replace" });
    });
  }

  it("내부 경로는 쿼리까지 그대로", async () => {
    jar.set(NONCE, "n1");
    assert.equal(
      (await run({ credential: "jwt", next: "/learn/words?page=2&q=a" })).to,
      "/learn/words?page=2&q=a",
    );
  });

  it("동의가 필요할 때 바깥 next 는 가입 화면 주소에 싣지 않는다", async () => {
    reply = async () => {
      throw new ApiError("consent_required", 400, "code");
    };
    jar.set(NONCE, "n1");
    assert.equal((await run({ credential: "jwt", next: "//evil.example" })).to, "/signup?error=consent");
  });
});

describe("백엔드 실패 종류별 이동", () => {
  const failures: [string, () => unknown, string][] = [
    ["400 구글 거절", () => new ApiError("구글 로그인을 확인하지 못했습니다.", 400), "/login?error=google"],
    ["429 제한", () => new ApiError("요청이 너무 많습니다.", 429), "/login?error=google"],
    ["500 서버 오류", () => new ApiError("서버 오류", 500), "/login?error=google"],
    ["연결 실패(ApiError 아님)", () => new TypeError("fetch failed"), "/login?error=google"],
    ["code 칸인데 다른 문구", () => new ApiError("something_else", 400, "code"), "/login?error=google"],
    ["consent_required 인데 칸 없음", () => new ApiError("consent_required", 400), "/login?error=google"],
    ["consent_required", () => new ApiError("consent_required", 400, "code"), "/signup?error=consent"],
  ];
  for (const [name, make, to] of failures) {
    it(`${name} -> ${to}, replace, 세션 없음`, async () => {
      jar.set(NONCE, "n1");
      reply = async () => {
        throw make();
      };
      assert.deepEqual(await run({ credential: "jwt" }), { to, type: "replace" });
      assert.deepEqual(sessions, []);
    });
  }

  it("백엔드는 됐는데 세션 저장이 실패하면 로그인 화면으로(replace)", async () => {
    jar.set(NONCE, "n1");
    setTokenFails = true;
    assert.deepEqual(await run({ credential: "jwt", next: "/board" }), {
      to: "/login?error=google",
      type: "replace",
    });
  });

  it("이동은 전부 replace 다(성공·동의·실패·nonce 없음)", async () => {
    const types = new Set<string | undefined>();
    jar.set(NONCE, "n1");
    types.add((await run({ credential: "jwt" })).type);
    jar.set(NONCE, "n1");
    reply = async () => {
      throw new ApiError("consent_required", 400, "code");
    };
    types.add((await run({ credential: "jwt" })).type);
    jar.set(NONCE, "n1");
    reply = async () => {
      throw new ApiError("x", 400);
    };
    types.add((await run({ credential: "jwt" })).type);
    types.add((await run({ credential: "jwt" })).type);
    assert.deepEqual([...types], ["replace"]);
  });
});
