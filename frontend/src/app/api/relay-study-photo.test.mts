/**
 * 로그인이 필요한 중계(/api/daily, /api/review)와 프로필 사진 중계.
 * 세션과 오류 변환은 실제 코드를 돌리고 백엔드만 가짜로 둔다.
 *
 * 실행: cd frontend && npm test
 *
 * 하네스는 rounds/stale-token.test.mts 와 같다.
 *
 * 계약.
 *   1. 잘못된 요청과 로그인 안 한 요청은 백엔드에 가지 않는다.
 *   2. 쿠키의 토큰을 실어 부르고 응답을 그대로 돌려준다.
 *   3. 백엔드가 토큰을 거절하면(401) 쿠키를 지운다. 다른 오류면 로그인을 유지한다.
 *   4. 사진 중계는 토큰을 싣지 않는다. 남의 아바타를 볼 때 내 인증이 나가면 안 된다.
 *   5. 사진 주소는 UUID 만 받는다. 인코딩된 ../ 가 API 밖으로 나가면 안 된다.
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

const COOKIE = "devvoca_token";
const LIVE = "live-token";
const ID = "123e4567-e89b-12d3-a456-426614174000";

type Call = { path: string; auth: string | null; etag: string | null; body: string };

let calls: Call[] = [];
let backend: () => Response;

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
  const headers = new Headers(init?.headers);
  calls.push({
    path: new URL(String(input)).pathname,
    auth: headers.get("Authorization"),
    etag: headers.get("If-None-Match"),
    body: String(init?.body ?? ""),
  });
  return backend();
}) as typeof fetch;

const realError = console.error;
console.error = () => {};

after(() => {
  globalThis.fetch = realFetch;
  console.error = realError;
  loader._load = realLoad;
});

const daily = await import("./daily/route");
const review = await import("./review/route");
const photo = await import("./accounts/photo/[id]/route");

beforeEach(() => {
  jar.clear();
  calls = [];
  backend = () => json(200, { from: "backend" });
});

function post(handler: (r: Request) => Promise<Response>, body: unknown) {
  return handler(
    new Request("http://x/api", {
      method: "POST",
      body: typeof body === "string" ? body : JSON.stringify(body),
    }),
  );
}

const ANSWER = { action: "answer", token: "round-1", choice_id: 3 };

for (const [name, route, start, base] of [
  ["/api/daily", daily, { action: "start", length: "short" }, "/api/learning/daily/"],
  ["/api/review", review, { action: "start" }, "/api/learning/review/"],
] as const) {
  describe(`${name} 중계`, () => {
    beforeEach(() => void jar.set(COOKIE, LIVE));

    it("로그인 안 했으면 백엔드에 안 가고 401 이다", async () => {
      jar.clear();

      const res = await post(route.POST, start);

      assert.equal(res.status, 401);
      assert.deepEqual(calls, []);
    });

    it("시작에 토큰을 싣고 응답을 그대로 돌려준다", async () => {
      const res = await post(route.POST, start);

      assert.equal(res.status, 200);
      assert.deepEqual(await res.json(), { from: "backend" });
      assert.equal(calls.length, 1);
      assert.equal(calls[0].auth, `Token ${LIVE}`);
      assert.equal(calls[0].path, base);
    });

    it("답에는 토큰과 판·보기 번호를 싣는다", async () => {
      const res = await post(route.POST, ANSWER);

      assert.equal(res.status, 200);
      assert.equal(calls[0].auth, `Token ${LIVE}`);
      assert.equal(calls[0].path, `${base}answer/`);
      assert.match(calls[0].body, /round-1/);
      assert.match(calls[0].body, /"choice_id":3/);
    });

    for (const [label, body] of [
      ["JSON 이 아니면", "not json"],
      ["action 이 없으면", {}],
      ["action 이 다르면", { action: "finish" }],
      ["판 토큰이 없으면", { action: "answer", choice_id: 3 }],
      ["보기 번호가 문자열이면", { ...ANSWER, choice_id: "3" }],
      ["보기 번호가 정수가 아니면", { ...ANSWER, choice_id: 1.5 }],
    ] as const) {
      it(`${label} 백엔드에 안 가고 400 이며 로그인을 유지한다`, async () => {
        const res = await post(route.POST, body);

        assert.equal(res.status, 400);
        assert.deepEqual(calls, []);
        assert.equal(jar.get(COOKIE), LIVE);
      });
    }

    it("백엔드가 토큰을 거절하면 401 이고 쿠키를 지운다", async () => {
      backend = () => json(401, { detail: "토큰이 유효하지 않습니다." });

      const res = await post(route.POST, start);

      assert.equal(res.status, 401);
      assert.equal(jar.has(COOKIE), false);
    });

    it("백엔드 500 은 그 상태이고 로그인을 유지한다", async () => {
      backend = () => json(500, { detail: "서버 오류" });

      const res = await post(route.POST, ANSWER);

      assert.equal(res.status, 500);
      assert.equal(jar.get(COOKIE), LIVE);
    });

    it("연결이 안 되면 503 이고 로그인을 유지한다", async () => {
      backend = () => {
        throw new TypeError("fetch failed");
      };

      const res = await post(route.POST, start);

      assert.equal(res.status, 503);
      assert.equal(jar.get(COOKIE), LIVE);
    });
  });
}

describe("/api/daily 길이", () => {
  it("고른 길이를 백엔드로 넘긴다", async () => {
    jar.set(COOKIE, LIVE);

    await post(daily.POST, { action: "start", length: "long" });

    assert.match(calls[0].body, /"length":"long"/);
  });

  it("길이를 안 고르면 백엔드에 안 가고 400 이다", async () => {
    jar.set(COOKIE, LIVE);

    const res = await post(daily.POST, { action: "start" });

    assert.equal(res.status, 400);
    assert.deepEqual(calls, []);
  });
});

describe("/api/accounts/photo/[id] 중계", () => {
  const get = (id: string, headers: Record<string, string> = {}) =>
    photo.GET(new Request("http://x/p", { headers }), {
      params: Promise.resolve({ id }),
    });

  for (const bad of ["1", "..%2F..%2Fadmin", `${ID}/../x`, `../${ID}`, ""]) {
    it(`UUID 가 아닌 ${JSON.stringify(bad)} 는 백엔드에 안 가고 404 다`, async () => {
      const res = await get(bad);

      assert.equal(res.status, 404);
      assert.deepEqual(calls, []);
    });
  }

  it("로그인 쿠키가 있어도 토큰을 싣지 않는다", async () => {
    jar.set(COOKIE, LIVE);

    await get(ID);

    assert.deepEqual(calls.map((c) => [c.path, c.auth]), [
      [`/api/accounts/photo/${ID}/`, null],
    ]);
  });

  it("그림과 캐시 머리를 그대로 넘긴다", async () => {
    backend = () =>
      new Response("image-bytes", {
        headers: {
          "Content-Type": "image/png",
          "Cache-Control": "public, max-age=60",
          ETag: '"v1"',
        },
      });

    const res = await get(ID);

    assert.equal(res.status, 200);
    assert.equal(await res.text(), "image-bytes");
    assert.equal(res.headers.get("Content-Type"), "image/png");
    assert.equal(res.headers.get("Cache-Control"), "public, max-age=60");
    assert.equal(res.headers.get("ETag"), '"v1"');
  });

  it("브라우저의 If-None-Match 를 넘기고 304 를 돌려준다", async () => {
    backend = () => new Response(null, { status: 304, headers: { ETag: '"v1"' } });

    const res = await get(ID, { "if-none-match": '"v1"' });

    assert.equal(calls[0].etag, '"v1"');
    assert.equal(res.status, 304);
    assert.equal(res.headers.get("ETag"), '"v1"');
  });

  it("백엔드 404 는 404, 연결 실패는 502 다", async () => {
    backend = () => new Response(null, { status: 404 });
    assert.equal((await get(ID)).status, 404);

    backend = () => {
      throw new TypeError("fetch failed");
    };
    assert.equal((await get(ID)).status, 502);
  });
});
