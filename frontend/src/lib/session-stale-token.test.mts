/**
 * lib/session.ts 의 로그인 확인(getCurrentUser), 토큰을 싣고 거절되면 게스트로
 * 다시 부르는 withTokenOrGuest, 쿠키 지우기 둘(forgetToken·clearToken)을 실제
 * 코드로 돌린다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약.
 *   1. getLiveToken·takeLiveToken·checkLogin 은 없다 - 로그인 확인(/me)을 먼저
 *      해서 토큰을 고르는 설계를 버렸다(로그인한 사람의 요청마다 왕복이 는다).
 *   2. getCurrentUser: 쿠키에 토큰이 없으면 null 이고 백엔드에 묻지 않는다.
 *      /me 가 200 이면 사용자, 실패면 null. 401 은 로그를 안 남기고 그 밖의
 *      실패(5xx·연결 실패)만 남긴다. 어느 경우에도 쿠키는 안 지운다(화면을
 *      그리는 중에 불린다).
 *   3. 한 요청 안에서 여러 번 불러도 /me 는 한 번이다(cache).
 *   4. withTokenOrGuest: /me 를 부르지 않는다. 토큰이 없으면 call(undefined),
 *      있으면 call(token). ApiError 401 일 때만 토큰 없이 한 번 더 부르고
 *      (forget 이면 토큰 쿠키만 지운다), 그 밖의 오류는 그대로 던지고 쿠키도
 *      안 건드린다. 다시 부른 것이 실패하면 그 오류를 던진다.
 *   5. forgetToken 은 토큰 쿠키만, clearToken 은 둘 다 지운다.
 *
 * 하네스 두 가지.
 *   - session.ts 맨 위의 `import "server-only"` 는 Next 번들러 밖에서 해석되지
 *     않는다(next 안에만 있다). mock.module 도 이름을 먼저 해석하려다 같은
 *     자리에서 터지므로, CJS 로더(Module._load)에서 그 이름만 빈 객체로
 *     돌려준다. 코드 결함이 아니라 하네스 제약이다.
 *   - react 의 cache 는 Node 기본 조건(클라이언트 빌드)에서 아무것도 기억하지
 *     않는다. "한 요청에 한 번" 을 보려면 기억하는 대역이 필요해서, 테스트마다
 *     비우는 memo 로 바꾼다. 테스트 하나 = 요청 하나.
 */
import assert from "node:assert/strict";
import Module from "node:module";
import { after, beforeEach, describe, it, mock } from "node:test";

// ---- 쿠키 대역 --------------------------------------------------------------

const jar = new Map<string, string>();
let deleted: string[] = [];

mock.module("next/headers", {
  namedExports: {
    async cookies() {
      return {
        get: (name: string) =>
          jar.has(name) ? { name, value: jar.get(name) } : undefined,
        set: (name: string, value: string) => void jar.set(name, value),
        delete: (name: string) => {
          deleted.push(name);
          jar.delete(name);
        },
      };
    },
  },
});

// ---- 요청 하나 동안만 기억하는 cache ---------------------------------------

let requestMemo = new Map<unknown, Promise<unknown>>();
mock.module("react", {
  namedExports: {
    cache<A extends unknown[], R>(fn: (...args: A) => R) {
      return (...args: A) => {
        if (!requestMemo.has(fn)) requestMemo.set(fn, Promise.resolve(fn(...args)));
        return requestMemo.get(fn) as R;
      };
    },
  },
});

// ---- server-only 우회 -------------------------------------------------------

const loader = Module as unknown as {
  _load: (request: string, ...rest: unknown[]) => unknown;
};
const realLoad = loader._load;
loader._load = function (this: unknown, request: string, ...rest: unknown[]) {
  if (request === "server-only") return {};
  return realLoad.call(this, request, ...rest);
};

// ---- 가짜 백엔드 ------------------------------------------------------------

type Reply = { status: number } | "down";
let reply: Reply = { status: 200 };
let meCalls: { url: string; auth: string | null }[] = [];
const USER = { id: 1, email: "a@b.c", display_name: "a" };

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
  const headers = new Headers(init?.headers);
  meCalls.push({ url: String(input), auth: headers.get("Authorization") });
  if (reply === "down") throw new TypeError("fetch failed");
  const body = reply.status === 200 ? USER : { detail: "토큰이 유효하지 않습니다." };
  return new Response(JSON.stringify(body), {
    status: reply.status,
    headers: { "Content-Type": "application/json" },
  });
}) as typeof fetch;

// 5xx·연결 실패는 console.error 로 남긴다. 출력을 덮지 않게 묶고, 몇 번
// 남겼는지만 센다.
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
const { ApiError } = await import("./api/client");

const TOKEN = "tok-abc";

beforeEach(() => {
  jar.clear();
  deleted = [];
  meCalls = [];
  requestMemo = new Map();
  reply = { status: 200 };
  logged = 0;
});

function loggedIn() {
  jar.set("devvoca_token", TOKEN);
  jar.set("devvoca_guest", "1");
}

// ---------------------------------------------------------------------------

describe("옛 설계의 함수", () => {
  it("getLiveToken·takeLiveToken·checkLogin 은 내보내지 않는다", () => {
    const exported = session as Record<string, unknown>;
    for (const name of ["getLiveToken", "takeLiveToken", "checkLogin"]) {
      assert.equal(exported[name], undefined, name);
    }
  });
});

describe("getCurrentUser - 토큰 쿠키가 없으면", () => {
  it("null 이고 백엔드에 묻지 않는다", async () => {
    assert.equal(await session.getCurrentUser(), null);
    assert.equal(meCalls.length, 0);
    assert.deepEqual(deleted, []);
  });

  it("빈 문자열 쿠키도 없는 것으로 본다", async () => {
    jar.set("devvoca_token", "");
    assert.equal(await session.getCurrentUser(), null);
    assert.equal(meCalls.length, 0);
  });
});

describe("getCurrentUser - /me 가 200 이면", () => {
  it("사용자를 돌려주고 쿠키를 안 건드린다", async () => {
    loggedIn();
    assert.deepEqual(await session.getCurrentUser(), USER);
    assert.deepEqual(deleted, []);
    assert.equal(logged, 0);
  });

  it("/me 에 쿠키의 토큰을 Token 헤더로 싣는다", async () => {
    loggedIn();
    await session.getCurrentUser();
    assert.equal(meCalls.length, 1);
    assert.match(meCalls[0].url, /\/api\/accounts\/me\/$/);
    assert.equal(meCalls[0].auth, `Token ${TOKEN}`);
  });
});

describe("getCurrentUser - /me 가 401 이면 (거절)", () => {
  it("null 이고 로그를 안 남기며 쿠키를 안 지운다(화면 그리는 중에 불린다)", async () => {
    loggedIn();
    reply = { status: 401 };
    assert.equal(await session.getCurrentUser(), null);
    assert.equal(logged, 0, "죽은 토큰은 오류가 아니다 - 화면마다 로그가 쌓인다");
    assert.deepEqual(deleted, []);
    assert.equal(jar.get("devvoca_token"), TOKEN);
  });
});

for (const [label, r] of [
  ["403", { status: 403 }],
  ["500", { status: 500 }],
  ["503", { status: 503 }],
  ["연결 실패", "down"],
] as [string, Reply][]) {
  describe(`getCurrentUser - /me 가 ${label} 이면 (거절 아님)`, () => {
    it("null 이고 로그를 남기며 쿠키를 안 지운다", async () => {
      loggedIn();
      reply = r;
      assert.equal(await session.getCurrentUser(), null);
      assert.equal(logged, 1, "백엔드 장애가 로그 없이 로그아웃처럼 보이면 안 된다");
      assert.deepEqual(deleted, []);
    });
  });
}

describe("getCurrentUser - 한 요청 안에서는 /me 를 한 번만 묻는다", () => {
  it("여러 번 불러도 한 번", async () => {
    loggedIn();
    await session.getCurrentUser();
    await session.getCurrentUser();
    await session.getCurrentUser();
    assert.equal(meCalls.length, 1);
  });

  it("거절된 뒤 같은 요청에서 다시 물어도 결과가 같다", async () => {
    loggedIn();
    reply = { status: 401 };
    assert.equal(await session.getCurrentUser(), null);
    assert.equal(await session.getCurrentUser(), null);
    assert.equal(meCalls.length, 1);
  });
});

// ---- withTokenOrGuest ------------------------------------------------------

/**
 * 부를 때마다 받은 토큰을 적고, 차례대로 outcomes 를 낸다(Error 면 던진다).
 * 백엔드 대역(fetch)은 거치지 않는다 - /me 가 안 불렸는지만 meCalls 로 본다.
 */
function recorder(...outcomes: unknown[]) {
  const seen: (string | undefined)[] = [];
  const call = async (token?: string) => {
    seen.push(token);
    const out = outcomes[Math.min(seen.length, outcomes.length) - 1];
    if (out instanceof Error) throw out;
    return out;
  };
  return { call, seen };
}

const rejected = () => new ApiError("토큰이 유효하지 않습니다.", 401);

for (const forget of [true, false]) {
  describe(`withTokenOrGuest (forget: ${forget})`, () => {
    it("토큰이 null 이면 토큰 없이 한 번 부르고 token 은 null", async () => {
      const { call, seen } = recorder("v");
      assert.deepEqual(await session.withTokenOrGuest(null, call, { forget }), {
        value: "v",
        token: null,
      });
      assert.deepEqual(seen, [undefined]);
      assert.equal(meCalls.length, 0);
      assert.deepEqual(deleted, []);
    });

    it("빈 문자열 토큰도 없는 것으로 본다", async () => {
      const { call, seen } = recorder("v");
      const out = await session.withTokenOrGuest("", call, { forget });
      assert.equal(out.token, null);
      assert.deepEqual(seen, [undefined]);
    });

    it("토큰이 받아들여지면 한 번만 부르고 그 토큰을 돌려준다(/me 없음)", async () => {
      loggedIn();
      const { call, seen } = recorder("v");
      assert.deepEqual(await session.withTokenOrGuest(TOKEN, call, { forget }), {
        value: "v",
        token: TOKEN,
      });
      assert.deepEqual(seen, [TOKEN]);
      assert.equal(meCalls.length, 0, "정상 경로에 로그인 확인 왕복이 없어야 한다");
      assert.deepEqual(deleted, []);
    });

    it("401 이면 토큰 없이 한 번 더 부르고 token 은 null", async () => {
      loggedIn();
      const { call, seen } = recorder(rejected(), "guest");
      assert.deepEqual(await session.withTokenOrGuest(TOKEN, call, { forget }), {
        value: "guest",
        token: null,
      });
      assert.deepEqual(seen, [TOKEN, undefined]);
      assert.equal(meCalls.length, 0);
      if (forget) {
        assert.deepEqual(deleted, ["devvoca_token"], "토큰 쿠키만 지운다");
        assert.equal(jar.get("devvoca_guest"), "1", "게스트 선택은 남아야 한다");
      } else {
        assert.deepEqual(deleted, [], "화면을 그리는 중에는 쿠키를 건드리면 안 된다");
        assert.equal(jar.get("devvoca_token"), TOKEN);
      }
    });

    it("토큰 없이 다시 부른 것도 401 이면 그대로 던지고 더 부르지 않는다", async () => {
      loggedIn();
      const { call, seen } = recorder(rejected(), rejected());
      await assert.rejects(session.withTokenOrGuest(TOKEN, call, { forget }), (e) => {
        assert.ok(e instanceof ApiError);
        assert.equal(e.status, 401);
        return true;
      });
      assert.deepEqual(seen, [TOKEN, undefined]);
    });

    it("토큰 없이 다시 부른 것이 다른 오류면 그 오류를 던진다", async () => {
      loggedIn();
      const down = new ApiError("서버에 연결할 수 없습니다.", 0);
      const { call, seen } = recorder(rejected(), down);
      await assert.rejects(
        session.withTokenOrGuest(TOKEN, call, { forget }),
        (e) => e === down,
      );
      assert.deepEqual(seen, [TOKEN, undefined]);
    });

    for (const status of [0, 400, 403, 404, 429, 500, 503]) {
      it(`${status} 는 다시 부르지 않고 그대로 던지며 쿠키를 안 지운다`, async () => {
        loggedIn();
        const error = new ApiError(`e${status}`, status);
        const { call, seen } = recorder(error, "guest");
        await assert.rejects(
          session.withTokenOrGuest(TOKEN, call, { forget }),
          (e) => e === error,
        );
        assert.deepEqual(
          seen,
          [TOKEN],
          "게스트로 바꿔 부르면 로그인한 사람의 기록이 말없이 사라진다",
        );
        assert.deepEqual(deleted, []);
      });
    }

    it("ApiError 가 아닌 것은 status 가 401 이라도 그대로 던진다", async () => {
      loggedIn();
      for (const thrown of [
        new TypeError("fetch failed"),
        Object.assign(new Error("흉내"), { status: 401 }),
      ]) {
        const { call, seen } = recorder(thrown, "guest");
        await assert.rejects(
          session.withTokenOrGuest(TOKEN, call, { forget }),
          (e) => e === thrown,
        );
        assert.deepEqual(seen, [TOKEN]);
      }
      assert.deepEqual(deleted, []);
    });

    it("토큰이 없을 때 난 오류는 그대로 던진다(다시 부르지 않는다)", async () => {
      const { call, seen } = recorder(rejected(), "again");
      await assert.rejects(session.withTokenOrGuest(null, call, { forget }), ApiError);
      assert.deepEqual(seen, [undefined]);
      assert.deepEqual(deleted, []);
    });
  });
}

describe("쿠키 지우기", () => {
  it("forgetToken 은 토큰 쿠키만 지운다", async () => {
    loggedIn();
    await session.forgetToken();
    assert.deepEqual(deleted, ["devvoca_token"]);
    assert.equal(jar.get("devvoca_guest"), "1");
  });

  it("clearToken 은 토큰·게스트 쿠키를 둘 다 지운다", async () => {
    loggedIn();
    await session.clearToken();
    assert.deepEqual([...deleted].sort(), ["devvoca_guest", "devvoca_token"]);
    assert.equal(jar.size, 0);
  });
});
