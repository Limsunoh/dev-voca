/**
 * 이메일 변경 확인 버튼을 진짜 세션 코드(lib/session.ts)와 API 클라이언트로 민다.
 *
 * 실행: cd frontend && npm test
 *
 * confirm-action.test.mts 는 세션과 백엔드 호출을 함수째 대역으로 바꿔 액션의
 * 분기만 본다. 여기서는 그 둘을 진짜로 두고 fetch 만 가짜 백엔드로 바꿔,
 * 실제로 오가는 요청과 쿠키에 남는 값을 본다.
 *   - 백엔드로 가는 토큰: Next 가 %3A 로 넘긴 쌍점이 풀려서 간다. 두 번 바뀐
 *     %253A 는 한 번만 풀린다(풀린 값에 % 가 남아 서버가 거절한다).
 *   - 확인 요청에는 /me 로 확인된 로그인 토큰만 싣는다. 백엔드는 같은 계정의
 *     토큰이 실렸을 때만 새 토큰을 준다. 죽은 토큰을 실으면 401 로 막힌다.
 *   - 같은 계정으로 로그인해 있던 기기만 새 토큰으로 바뀐다. 로그인이 없거나
 *     죽은 토큰이거나 다른 계정이면 쿠키가 한 글자도 안 바뀐다.
 *   - 이 기기의 로그인을 확인하지 못하면(/me 가 5xx·429·연결 실패) 확인을 부르지
 *     않는다.
 *
 * 하네스: 쿠키 저장소(next/headers), revalidatePath, fetch 만 대역이다.
 * session.ts 의 `import "server-only"` 는 CJS 로더에서 빈 객체로 돌려준다
 * (api/rounds/stale-token.test.mts 와 같다).
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

let revalidated = 0;
mock.module("next/cache", {
  namedExports: {
    revalidatePath() {
      revalidated += 1;
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

// 링크의 계정(7)과 이 기기에 로그인해 있을 수 있는 다른 계정(99).
const LINK_OWNER = "owner-login";
const OTHER = "other-login";
const DEAD = "dead-login";
const ISSUED = "issued-after-confirm";
// 백엔드가 잠깐 실패해 /me 가 502 인 경우.
const BROKEN = "broken-login";
// /me 에 연결 자체가 안 되는 경우. 클라이언트가 status 0 인 ApiError 로 바꾼다.
const UNREACHABLE = "unreachable-login";
// /me 가 요청 제한(429)에 걸린 경우. 401 이 아니므로 로그인 없음으로 읽지 않는다.
const THROTTLED = "throttled-login";
// Django signing.dumps 꼴(값:시각:서명). 진짜 서명이 아니다.
const SIGNED = "payload:stamp:not-a-real-signature";

let calls: { path: string; auth: string | null; token?: string }[] = [];

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
  const url = new URL(String(input));
  const auth = new Headers(init?.headers).get("Authorization");

  if (url.pathname === "/api/accounts/me/") {
    calls.push({ path: "me", auth });
    if (auth === `Token ${BROKEN}`) return json(502, { detail: "잠시 멈춤" });
    if (auth === `Token ${UNREACHABLE}`) throw new TypeError("fetch failed");
    if (auth === `Token ${THROTTLED}`) return json(429, { detail: "요청이 너무 많습니다." });
    if (auth === `Token ${LINK_OWNER}`) return json(200, { id: 7, email: "old@example.com" });
    if (auth === `Token ${OTHER}`) return json(200, { id: 99, email: "other@example.com" });
    return json(401, { detail: "토큰이 유효하지 않습니다." });
  }
  if (url.pathname === "/api/accounts/email-change/confirm/") {
    const token = JSON.parse(String(init?.body)).token as string;
    calls.push({ path: "confirm", auth, token });
    // 서명 검사와 같다. 한 글자라도 다르면 거절한다.
    // 백엔드처럼 인증이 먼저다. 실린 토큰이 죽었으면 링크를 보기도 전에 401 이다.
    if (auth !== null && auth !== `Token ${LINK_OWNER}` && auth !== `Token ${OTHER}`) {
      return json(401, { detail: "토큰이 유효하지 않습니다." });
    }
    if (token !== SIGNED) {
      return json(400, { detail: "확인 링크가 만료되었거나 올바르지 않습니다." });
    }
    // 새 로그인 토큰은 링크의 계정(7)으로 로그인한 요청에만 준다.
    const user = { id: 7, email: "new@example.com" };
    return json(200, auth === `Token ${LINK_OWNER}` ? { token: ISSUED, user } : { user });
  }
  return json(404, {});
}) as typeof fetch;

const realError = console.error;
console.error = () => {};

after(() => {
  globalThis.fetch = realFetch;
  console.error = realError;
  loader._load = realLoad;
});

const { confirmEmailChangeAction } = await import("./actions");

beforeEach(() => {
  jar.clear();
  calls = [];
  revalidated = 0;
});

function form(token: string): FormData {
  const data = new FormData();
  data.set("token", token);
  return data;
}

/** 쿠키 값(`토큰.발급시각`)에서 토큰만. */
function cookieToken(): string | undefined {
  const value = jar.get("devvoca_token");
  return value?.slice(0, value.lastIndexOf("."));
}

const sentTokens = () => calls.filter((c) => c.path === "confirm").map((c) => c.token);

describe("백엔드로 가는 토큰", () => {
  it("Next 가 넘긴 %3A 를 풀어 서명 그대로 보낸다", async () => {
    const state = await confirmEmailChangeAction({}, form(SIGNED.replaceAll(":", "%3A")));
    assert.deepEqual(sentTokens(), [SIGNED]);
    assert.equal(state.changedTo, "new@example.com");
  });

  it("소문자 %3a 도 푼다", async () => {
    await confirmEmailChangeAction({}, form(SIGNED.replaceAll(":", "%3a")));
    assert.deepEqual(sentTokens(), [SIGNED]);
  });

  it("두 번 바뀐 %253A 는 한 번만 풀어 서버가 거절하게 둔다", async () => {
    const state = await confirmEmailChangeAction({}, form(SIGNED.replaceAll(":", "%253A")));
    assert.deepEqual(sentTokens(), [SIGNED.replaceAll(":", "%3A")]);
    assert.equal(state.error, "확인 링크가 만료되었거나 올바르지 않습니다.");
    assert.equal(jar.size, 0);
  });

  it("죽은 로그인 토큰은 확인 요청에 싣지 않는다", async () => {
    jar.set("devvoca_token", `${DEAD}.1700000000`);
    const state = await confirmEmailChangeAction({}, form(SIGNED));
    const confirm = calls.find((c) => c.path === "confirm");
    assert.equal(confirm?.auth, null);
    assert.equal(state.changedTo, "new@example.com");
  });

  it("확인된 같은 계정의 로그인 토큰은 확인 요청에 싣는다", async () => {
    jar.set("devvoca_token", `${LINK_OWNER}.1700000000`);
    await confirmEmailChangeAction({}, form(SIGNED));
    const confirm = calls.find((c) => c.path === "confirm");
    assert.equal(confirm?.auth, `Token ${LINK_OWNER}`);
  });
});

describe("쿠키에 남는 것", () => {
  it("로그인이 없으면 쿠키를 만들지 않는다", async () => {
    const state = await confirmEmailChangeAction({}, form(SIGNED));
    assert.equal(jar.size, 0);
    assert.equal(revalidated, 0);
    assert.deepEqual(state, { changedTo: "new@example.com" });
  });

  it("죽은 토큰 쿠키는 로그인이 없는 것과 같아 그대로 둔다", async () => {
    jar.set("devvoca_token", `${DEAD}.1700000000`);
    const state = await confirmEmailChangeAction({}, form(SIGNED));
    assert.equal(jar.get("devvoca_token"), `${DEAD}.1700000000`);
    assert.equal(state.signedIn, undefined);
  });

  it("같은 계정이면 끊긴 옛 토큰 대신 새 토큰을 넣는다", async () => {
    jar.set("devvoca_token", `${LINK_OWNER}.1700000000`);
    const state = await confirmEmailChangeAction({}, form(SIGNED));
    assert.equal(cookieToken(), ISSUED);
    assert.equal(revalidated, 1);
    assert.deepEqual(state, { changedTo: "new@example.com", signedIn: true });
  });

  it("다른 계정이면 쿠키 값이 한 글자도 안 바뀐다", async () => {
    jar.set("devvoca_token", `${OTHER}.1700000000`);
    const state = await confirmEmailChangeAction({}, form(SIGNED.replaceAll(":", "%3A")));
    assert.equal(jar.get("devvoca_token"), `${OTHER}.1700000000`);
    assert.equal(revalidated, 0);
    assert.deepEqual(state, { changedTo: "new@example.com" });
  });

  it("로그인 확인이 502 면 확인을 부르지 않고 쿠키도 그대로 둔다", async () => {
    jar.set("devvoca_token", `${BROKEN}.1700000000`);
    const state = await confirmEmailChangeAction({}, form(SIGNED));
    assert.equal(state.error, "잠시 후 다시 시도해주세요.");
    assert.deepEqual(sentTokens(), []);
    assert.equal(jar.get("devvoca_token"), `${BROKEN}.1700000000`);
  });

  it("로그인 확인에 연결이 안 되거나 429 여도 확인을 부르지 않는다", async () => {
    // 클라이언트는 연결 실패를 status 0 인 ApiError 로 바꾼다. "5xx 만 멈춘다" 로
    // 좁히면 이 둘이 로그인 없음으로 읽혀, 같은 계정 기기가 새 토큰 없이 확인된다.
    for (const login of [UNREACHABLE, THROTTLED]) {
      jar.clear();
      calls = [];
      jar.set("devvoca_token", `${login}.1700000000`);
      const state = await confirmEmailChangeAction({}, form(SIGNED));
      assert.equal(state.error, "잠시 후 다시 시도해주세요.", login);
      assert.deepEqual(sentTokens(), [], login);
      assert.equal(jar.get("devvoca_token"), `${login}.1700000000`, login);
    }
  });

  it("누가 로그인했는지는 그 기기의 토큰으로, 확인보다 먼저 묻는다", async () => {
    jar.set("devvoca_token", `${OTHER}.1700000000`);
    await confirmEmailChangeAction({}, form(SIGNED));
    assert.deepEqual(
      calls.map((c) => [c.path, c.auth]),
      [
        ["me", `Token ${OTHER}`],
        // 살아 있는 토큰이라 싣는다. 다른 계정이라 서버는 새 토큰을 안 준다.
        ["confirm", `Token ${OTHER}`],
      ],
    );
  });

  it("거절되면 다른 계정 쿠키도 그대로 둔다", async () => {
    jar.set("devvoca_token", `${OTHER}.1700000000`);
    await confirmEmailChangeAction({}, form("not-signed"));
    assert.equal(jar.get("devvoca_token"), `${OTHER}.1700000000`);
  });
});
