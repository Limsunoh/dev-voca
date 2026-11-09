/**
 * 문제풀기 채점 중계(/api/quiz POST)가 로그인 토큰을 어떻게 싣는가.
 * 세션·중계 코드는 실제 것을 돌리고 백엔드만 가짜로 둔다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약.
 *   1. 쿠키에 토큰이 있으면 Authorization 으로 싣고, /me 를 먼저 묻지 않는다.
 *      오답 노트에 넣으려면 백엔드가 누구인지 알아야 한다.
 *   2. 토큰이 거절되면(401) 쿠키를 지우고 토큰 없이 한 번 더 부른다. 게스트
 *      쿠키는 남긴다. 채점은 로그인 없이도 되는 요청이라 막히면 안 된다.
 *   3. 401 이 아닌 오류는 다시 부르지 않고 쿠키도 안 지운다. 서버가 잠깐 죽었다고
 *      로그인을 날리면 그 뒤로 틀린 문제가 조용히 안 쌓인다.
 *   4. 본문의 token 은 문제 토큰이고 헤더의 토큰은 로그인 토큰이다. 뒤바뀌면
 *      정상 사용자가 전부 401 을 받는다.
 *   5. ?content 는 화이트리스트다. 백엔드 경로가 되는 값이다.
 *
 * 하네스: session.ts 의 "server-only" 는 Next 밖에서 해석되지 않아 빈 객체로
 * 돌려준다(api/rounds/stale-token.test.mts 와 같다).
 */
import assert from "node:assert/strict";
import Module from "node:module";
import { after, beforeEach, describe, it, mock } from "node:test";

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

const DEAD = "dead-login-token";
const LIVE = "live-login-token";
const QUESTION = "question-token";
const WORDS = "/api/vocab/words/grade/";
const SENTENCES = "/api/vocab/sentences/grade/";
const GRADED = { correct: false, answer_id: 7, word: { term: "x" } };

let mode: "ok" | 400 | 403 | 404 | 500 | "down" = "ok";
let calls: { path: string; auth: string | null; body: unknown }[] = [];

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
  calls.push({
    path: url.pathname,
    auth,
    body: init?.body ? JSON.parse(String(init.body)) : undefined,
  });

  // DRF 의 토큰 인증은 뷰보다 먼저 돈다. 무효 토큰이면 어느 API 든 401.
  if (auth === `Token ${DEAD}`) {
    return json(401, { detail: "토큰이 유효하지 않습니다." });
  }
  if (mode === "down") throw new TypeError("fetch failed");
  if (mode !== "ok") return json(mode, { detail: `백엔드 ${mode}` });
  return json(200, GRADED);
}) as typeof fetch;

const realError = console.error;
console.error = () => {};

after(() => {
  globalThis.fetch = realFetch;
  console.error = realError;
  loader._load = realLoad;
});

const route = await import("./route");

beforeEach(() => {
  jar.clear();
  calls = [];
  mode = "ok";
});

function withLogin(token: string) {
  jar.set("devvoca_token", token);
  jar.set("devvoca_guest", "1");
}

function grade(body: unknown, query = "") {
  return route.POST(
    new Request(`http://x/api/quiz${query}`, {
      method: "POST",
      body: typeof body === "string" ? body : JSON.stringify(body),
    }),
  );
}

const valid = { token: QUESTION, picked: 3 };

describe("/api/quiz POST 로그인 토큰", () => {
  it("살아 있는 토큰이면 한 번, 그 토큰을 헤더에 싣는다", async () => {
    withLogin(LIVE);
    const res = await grade(valid);
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), GRADED);
    assert.deepEqual(calls, [
      { path: WORDS, auth: `Token ${LIVE}`, body: valid },
    ]);
    assert.equal(jar.get("devvoca_token"), LIVE);
  });

  it("문장 채점에도 토큰이 실린다", async () => {
    withLogin(LIVE);
    await grade(valid, "?content=sentences");
    assert.deepEqual(calls, [
      { path: SENTENCES, auth: `Token ${LIVE}`, body: valid },
    ]);
  });

  it("토큰이 없으면 Authorization 없이 한 번 부른다", async () => {
    const res = await grade(valid);
    assert.equal(res.status, 200);
    assert.deepEqual(calls, [{ path: WORDS, auth: null, body: valid }]);
  });

  it("거절된 토큰이면 쿠키를 지우고 토큰 없이 다시 불러 채점을 돌려준다", async () => {
    withLogin(DEAD);
    const res = await grade(valid, "?content=sentences");
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), GRADED);
    assert.deepEqual(calls, [
      { path: SENTENCES, auth: `Token ${DEAD}`, body: valid },
      { path: SENTENCES, auth: null, body: valid },
    ]);
    assert.equal(jar.has("devvoca_token"), false);
    assert.equal(jar.get("devvoca_guest"), "1", "게스트 쿠키는 남는다");
  });

  it("거절 뒤 다음 채점에는 죽은 토큰이 다시 실리지 않는다", async () => {
    withLogin(DEAD);
    await grade(valid);
    calls = [];
    await grade(valid);
    assert.deepEqual(calls, [{ path: WORDS, auth: null, body: valid }]);
  });

  it("거절 뒤 게스트 재시도가 실패하면 그 상태를 돌려주고 쿠키는 이미 지워져 있다", async () => {
    withLogin(DEAD);
    mode = 400;
    const res = await grade(valid);
    assert.equal(res.status, 400);
    assert.deepEqual(await res.json(), { detail: "백엔드 400" });
    assert.equal(calls.length, 2);
    assert.equal(jar.has("devvoca_token"), false);
  });

  for (const [backend, relayed] of [
    [400, 400],
    [403, 403],
    [404, 404],
    [500, 500],
    ["down", 503],
  ] as const) {
    it(`백엔드가 ${backend} 면 다시 부르지 않고 ${relayed} 이며 로그인을 유지한다`, async () => {
      withLogin(LIVE);
      mode = backend;
      const res = await grade(valid);
      assert.equal(res.status, relayed);
      assert.equal(calls.length, 1, "게스트로 다시 부르면 오답이 조용히 사라진다");
      assert.equal(jar.get("devvoca_token"), LIVE);
    });
  }

  it("응답에 로그인 토큰이 섞여 나가지 않는다", async () => {
    withLogin(DEAD);
    mode = 400;
    const res = await grade(valid);
    assert.equal((await res.text()).includes(DEAD), false);
  });

  it("?content 가 화이트리스트 밖이면 단어로 간다", async () => {
    withLogin(LIVE);
    for (const query of ["?content=../../accounts/me", "?content=", "?content=SENTENCES"]) {
      calls = [];
      await grade(valid, query);
      assert.equal(calls[0].path, WORDS, query);
    }
  });

  it("picked 0 은 값으로 넘어간다", async () => {
    withLogin(LIVE);
    await grade({ token: QUESTION, picked: 0 });
    assert.deepEqual(calls[0].body, { token: QUESTION, picked: 0 });
  });
});

describe("/api/quiz POST 입력 검증", () => {
  for (const [name, body] of [
    ["깨진 JSON", "{"],
    ["토큰 없음", { picked: 1 }],
    ["빈 토큰", { token: "", picked: 1 }],
    ["picked 없음", { token: QUESTION }],
    ["picked 문자열", { token: QUESTION, picked: "1" }],
    ["picked null", { token: QUESTION, picked: null }],
    ["배열 본문", []],
    ["문자열 본문", '"x"'],
    ["숫자 본문", "1"],
    ["null 본문", "null"],
  ] as const) {
    it(`${name}: 400 이고 백엔드에 안 가며 쿠키를 안 지운다`, async () => {
      withLogin(DEAD);
      const res = await grade(body);
      assert.equal(res.status, 400);
      assert.equal(calls.length, 0);
      assert.equal(jar.get("devvoca_token"), DEAD);
    });
  }

  it("문제 토큰이 문자열이 아니면 그대로 넘겨 백엔드의 400 을 돌려준다", async () => {
    withLogin(LIVE);
    mode = 400;
    const res = await grade({ token: 123, picked: 1 });
    assert.equal(res.status, 400);
    assert.equal(calls.length, 1);
    assert.equal(jar.get("devvoca_token"), LIVE);
  });
});
