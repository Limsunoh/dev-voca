/**
 * 백엔드가 늦을 때 끊는 시간 제한(readTimeout)과 그 오류가 화면까지 가는 길.
 *
 * 실행: cd frontend && npm test
 *
 * 계약.
 *   1. 읽기(request() 의 GET, 사진 중계 라우트)는 fetch 에 10초 signal 을 넘긴다.
 *      쓰기(request() 의 POST·PATCH·DELETE, 사진 저장 photoRequest)는 넘기지
 *      않는다 - 끊어도 백엔드가 저장을 마치면 "저장됐는데 실패" 가 된다.
 *   2. 응답 머리 전이든 본문 읽는 중이든 시간 초과면 ApiError 504 와 "늦습니다"
 *      문구. 연결 실패(status 0)와 섞이면 안 된다 - 화면 문구가 달라진다.
 *   3. 연결 실패, 4xx 안내, 204, 깨진 JSON 은 전과 같다.
 *   4. 중계(relayError)는 504 를 그대로 내보내고 쿠키를 안 지운다.
 *      사진 중계는 시간 초과에도 502(화면은 아바타로 떨어진다).
 *
 * 앞 절반은 globalThis.fetch 를 가짜로 바꾼다(client-error-field.test.mts 와
 * 같다). 뒤 절반은 진짜 fetch 와 로컬 http 서버로 본다 - 가짜로 던진
 * DOMException 이 진짜 undici 가 던지는 것과 같은지는 가짜로 증명할 수 없다.
 * 진짜 쪽은 AbortSignal.timeout 을 짧게 바꿔 기다리는 시간을 줄인다.
 */
import assert from "node:assert/strict";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { after, afterEach, beforeEach, describe, it, mock } from "node:test";

// relay.ts 가 부르는 세션은 "server-only" 라 대역으로 바꾼다(relay-forget.test.mts 와 같다).
let forgotten = 0;
mock.module("@/lib/session", {
  namedExports: {
    async forgetToken() {
      forgotten += 1;
    },
    async clearToken() {
      throw new Error("relayError 가 게스트 쿠키까지 지우면 안 된다");
    },
  },
});

const { ApiError, request, readTimeout, isBackendTimeout } = await import("./client");
const { uploadMyPhoto, deleteMyPhoto } = await import("./accounts");
const { relayError } = await import("./relay");
const photoRoute = await import("../../app/api/accounts/photo/[id]/route");

const SLOW = "서버 응답이 늦습니다. 잠시 뒤 다시 시도해주세요.";
const UNREACHABLE = "서버에 연결할 수 없습니다.";
const PHOTO_ID = "123e4567-e89b-12d3-a456-426614174000";

const realFetch = globalThis.fetch;
const realTimeout = AbortSignal.timeout.bind(AbortSignal);
const realApiUrl = process.env.API_URL;

/** AbortSignal.timeout 에 넘어온 시간을 모은다. shortMs 를 주면 실제 제한은 그 값으로 줄인다. */
let timeoutCalls: number[] = [];
function spyTimeout(shortMs?: number) {
  AbortSignal.timeout = (ms: number) => {
    timeoutCalls.push(ms);
    return realTimeout(shortMs ?? ms);
  };
}

beforeEach(() => {
  forgotten = 0;
  timeoutCalls = [];
  spyTimeout();
});
afterEach(() => {
  globalThis.fetch = realFetch;
  AbortSignal.timeout = realTimeout;
  if (realApiUrl === undefined) delete process.env.API_URL;
  else process.env.API_URL = realApiUrl;
});

type Seen = { url: string; init: RequestInit };

/** fetch 를 가짜로 바꾸고, 넘어온 인자를 seen 에 남긴다. */
function fakeFetch(respond: (init: RequestInit) => Response | Promise<Response>): Seen[] {
  const seen: Seen[] = [];
  globalThis.fetch = (async (url: string | URL | Request, init: RequestInit = {}) => {
    seen.push({ url: String(url), init });
    return respond(init);
  }) as typeof fetch;
  return seen;
}

const timeoutError = () => new DOMException("The operation was aborted due to timeout", "TimeoutError");

/** 본문을 읽으면 그때 TimeoutError 가 나는 응답. 머리는 이미 온 상태를 흉내 낸다. */
function bodyStallsThenTimesOut(status: number): Response {
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('{"detail":'));
      queueMicrotask(() => controller.error(timeoutError()));
    },
  });
  return new Response(stream, { status, headers: { "Content-Type": "application/json" } });
}

function isSlow(e: unknown): boolean {
  assert.ok(e instanceof ApiError, `ApiError 가 아니다: ${String(e)}`);
  assert.equal(e.status, 504);
  assert.equal(e.message, SLOW);
  assert.equal(e.field, undefined);
  return true;
}

function isUnreachable(e: unknown): boolean {
  assert.ok(e instanceof ApiError, `ApiError 가 아니다: ${String(e)}`);
  assert.equal(e.status, 0);
  assert.equal(e.message, UNREACHABLE);
  return true;
}

const photoFile = () => new File([new Uint8Array([1, 2, 3])], "a.webp", { type: "image/webp" });

describe("readTimeout / isBackendTimeout", () => {
  it("읽기는 10초", () => {
    readTimeout();
    assert.deepEqual(timeoutCalls, [10_000]);
  });

  it("부를 때마다 새 signal 이다(이미 끊긴 signal 을 돌려 쓰면 다음 요청이 바로 죽는다)", () => {
    const a = readTimeout();
    const b = readTimeout();
    assert.notEqual(a, b);
    assert.equal(a.aborted, false);
    assert.equal(b.aborted, false);
  });

  it("TimeoutError 만 시간 초과로 본다", () => {
    assert.equal(isBackendTimeout(timeoutError()), true);
    assert.equal(isBackendTimeout(new DOMException("x", "AbortError")), false);
    assert.equal(isBackendTimeout(new TypeError("fetch failed")), false);
    // 이름만 흉내 낸 객체·Error 는 아니다.
    assert.equal(isBackendTimeout({ name: "TimeoutError" }), false);
    const e = new Error("x");
    e.name = "TimeoutError";
    assert.equal(isBackendTimeout(e), false);
    for (const v of [null, undefined, "TimeoutError", 0]) assert.equal(isBackendTimeout(v), false);
  });
});

describe("request() 가 fetch 에 시간 제한을 넘긴다", () => {
  it("GET 은 10초 signal 을 넘긴다", async () => {
    const seen = fakeFetch(() => Response.json({ ok: 1 }));
    await request("/api/x/");
    assert.ok(seen[0].init.signal instanceof AbortSignal, "signal 이 안 넘어갔다");
    assert.equal(seen[0].init.signal.aborted, false);
    assert.deepEqual(timeoutCalls, [10_000]);
  });

  for (const method of ["POST", "PATCH", "DELETE"] as const) {
    it(`${method} 는 시간 제한을 넘기지 않는다(저장됐는데 실패로 보이는 일을 막는다)`, async () => {
      const seen = fakeFetch(() => new Response(null, { status: 204 }));
      await request("/api/x/", { method, body: {} });
      assert.equal(seen[0].init.signal, undefined);
      assert.equal(seen[0].init.method, method);
      assert.deepEqual(timeoutCalls, []);
    });
  }
});

describe("request() 의 시간 초과는 504", () => {
  it("머리 전에 끊기면 504 와 늦다는 문구(연결 실패 문구가 아니다)", async () => {
    fakeFetch(() => {
      throw timeoutError();
    });
    await assert.rejects(request("/api/x/"), isSlow);
  });

  it("200 머리 뒤 본문 읽는 중에 끊기면 504", async () => {
    fakeFetch(() => bodyStallsThenTimesOut(200));
    await assert.rejects(request("/api/x/"), isSlow);
  });

  it("500 은 본문을 안 읽으므로 본문이 멈춰도 500 이다", async () => {
    fakeFetch(() => bodyStallsThenTimesOut(500));
    await assert.rejects(request("/api/x/"), (e: unknown) => {
      assert.ok(e instanceof ApiError);
      assert.equal(e.status, 500);
      return true;
    });
  });

  it("400 본문을 읽다 끊겨도 504(\"요청이 실패했습니다 (400)\" 로 새지 않는다)", async () => {
    // errorDetail 이 본문 읽기의 TimeoutError 를 삼키지 않고 다시 던진다.
    fakeFetch(() => bodyStallsThenTimesOut(400));
    await assert.rejects(request("/api/x/"), isSlow);
  });
});

describe("request() 의 다른 실패와 성공은 전과 같다", () => {
  it("일반 연결 실패는 status 0", async () => {
    fakeFetch(() => {
      throw new TypeError("fetch failed");
    });
    await assert.rejects(request("/api/x/"), isUnreachable);
  });

  it("시간 제한이 아닌 중단(AbortError)은 시간 초과로 보지 않는다(status 0)", async () => {
    fakeFetch(() => {
      throw new DOMException("This operation was aborted", "AbortError");
    });
    await assert.rejects(request("/api/x/"), isUnreachable);
  });

  it("4xx 안내 문구와 칸 이름이 그대로 실린다(본문 읽기를 try 로 감싸도 ApiError 가 다시 감싸이지 않는다)", async () => {
    fakeFetch(() => Response.json({ email: ["이미 가입된 이메일입니다."] }, { status: 400 }));
    await assert.rejects(request("/api/x/", { method: "POST", body: {} }), (e: unknown) => {
      assert.ok(e instanceof ApiError);
      assert.equal(e.status, 400);
      assert.equal(e.message, "이미 가입된 이메일입니다.");
      assert.equal(e.field, "email");
      return true;
    });
  });

  it("401 은 401 그대로(504 로 바뀌면 relay 가 쿠키를 못 지운다)", async () => {
    fakeFetch(() => Response.json({ detail: "토큰이 유효하지 않습니다." }, { status: 401 }));
    await assert.rejects(request("/api/x/"), (e: unknown) => {
      assert.ok(e instanceof ApiError);
      assert.equal(e.status, 401);
      return true;
    });
  });

  it("백엔드가 504 를 직접 주면 기본 문구의 504(늦다는 문구가 아니다)", async () => {
    fakeFetch(() => new Response("gateway", { status: 504 }));
    await assert.rejects(request("/api/x/"), (e: unknown) => {
      assert.ok(e instanceof ApiError);
      assert.equal(e.status, 504);
      assert.equal(e.message, "요청이 실패했습니다. (504)");
      return true;
    });
  });

  it("204 는 undefined", async () => {
    fakeFetch(() => new Response(null, { status: 204 }));
    assert.equal(await request("/api/x/", { method: "DELETE" }), undefined);
  });

  it("200 JSON 은 그대로 돌려준다", async () => {
    fakeFetch(() => Response.json({ results: [1, 2] }));
    assert.deepEqual(await request("/api/x/"), { results: [1, 2] });
  });

  it("200 인데 깨진 JSON 은 SyntaxError 그대로(504 로 둔갑하지 않는다)", async () => {
    fakeFetch(() => new Response("<html>", { status: 200 }));
    await assert.rejects(request("/api/x/"), SyntaxError);
  });
});

describe("사진 저장(photoRequest)은 쓰기라 시간 제한이 없다", () => {
  it("올리기 POST, 지우기 DELETE 모두 signal 을 넘기지 않는다", async () => {
    const seen = fakeFetch(() => Response.json({ id: 1 }));
    await uploadMyPhoto("t", photoFile());
    await deleteMyPhoto("t");
    assert.equal(seen[0].init.method, "POST");
    assert.equal(seen[1].init.method, "DELETE");
    for (const s of seen) assert.equal(s.init.signal, undefined);
    assert.deepEqual(timeoutCalls, []);
  });

  it("연결 실패는 0", async () => {
    fakeFetch(() => {
      throw new TypeError("fetch failed");
    });
    await assert.rejects(uploadMyPhoto("t", photoFile()), isUnreachable);
  });

  it("4xx 안내는 그대로", async () => {
    fakeFetch(() => Response.json({ photo: ["파일이 너무 큽니다."] }, { status: 400 }));
    await assert.rejects(uploadMyPhoto("t", photoFile()), (e: unknown) => {
      assert.ok(e instanceof ApiError);
      assert.equal(e.status, 400);
      assert.equal(e.message, "파일이 너무 큽니다.");
      return true;
    });
  });

  it("200 인데 깨진 JSON 은 SyntaxError 그대로", async () => {
    fakeFetch(() => new Response("nope", { status: 200 }));
    await assert.rejects(deleteMyPhoto("t"), SyntaxError);
  });
});

describe("relayError 는 504 를 504 로", () => {
  it("시간 초과 오류는 504 와 늦다는 문구, 쿠키는 그대로", async () => {
    fakeFetch(() => {
      throw timeoutError();
    });
    const error = await request("/api/x/").catch((e: unknown) => e);
    const res = await relayError(error);
    assert.equal(res.status, 504);
    assert.deepEqual(await res.json(), { detail: SLOW });
    assert.equal(forgotten, 0);
  });
});

describe("사진 중계 라우트", () => {
  const call = () =>
    photoRoute.GET(new Request(`http://localhost/api/accounts/photo/${PHOTO_ID}`), {
      params: Promise.resolve({ id: PHOTO_ID }),
    });

  it("GET 10초 signal 을 넘긴다", async () => {
    const seen = fakeFetch(() => new Response(new Uint8Array([1]), { status: 200 }));
    const res = await call();
    assert.equal(res.status, 200);
    assert.ok(seen[0].init.signal instanceof AbortSignal);
    assert.deepEqual(timeoutCalls, [10_000]);
  });

  it("시간 초과면 502(아바타로 떨어진다)", async () => {
    fakeFetch(() => {
      throw timeoutError();
    });
    const res = await call();
    assert.equal(res.status, 502);
  });

  it("UUID 가 아니면 백엔드를 안 부르고 시간 제한도 안 만든다", async () => {
    const seen = fakeFetch(() => new Response(null));
    const res = await photoRoute.GET(new Request("http://localhost/x"), {
      params: Promise.resolve({ id: "..%2F..%2Fadmin" }),
    });
    assert.equal(res.status, 404);
    assert.equal(seen.length, 0);
    assert.deepEqual(timeoutCalls, []);
  });
});

/**
 * 진짜 fetch 와 로컬 서버. 시간 제한은 150ms 로 줄인다.
 * 서버는 요청마다 handler 를 갈아 끼운다.
 */
describe("진짜 fetch 로 본 시간 초과", () => {
  // signal 이 빠지면 머리를 안 보내는 서버 앞에서 영원히 기다린다. 멈추지 말고 빨개지게 한다.
  const LIMIT = { timeout: 3_000 };
  const SHORT = 150;
  let handler: http.RequestListener = () => {};
  const server = http.createServer((req, res) => handler(req, res));
  let base = "";

  const ready = new Promise<void>((resolve) =>
    server.listen(0, "127.0.0.1", () => {
      base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
      resolve();
    }),
  );
  after(() => {
    server.closeAllConnections();
    server.close();
  });

  beforeEach(async () => {
    await ready;
    process.env.API_URL = base;
    spyTimeout(SHORT);
  });

  it("머리를 안 보내는 백엔드 -> 504", LIMIT, async () => {
    handler = () => {};
    await assert.rejects(request("/api/x/"), isSlow);
  });

  it("머리 뒤 본문이 멈추는 백엔드 -> 504", LIMIT, async () => {
    handler = (_req, res) => {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.write('{"results": [');
    };
    await assert.rejects(request("/api/x/"), isSlow);
  });

  it("제한 안에 답하면 성공한다(시간 제한이 정상 요청을 끊지 않는다)", LIMIT, async () => {
    handler = (_req, res) => {
      setTimeout(() => {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end('{"ok":true}');
      }, 20);
    };
    assert.deepEqual(await request("/api/x/"), { ok: true });
  });

  it("연결을 끊어 버리는 백엔드 -> 0(시간 초과와 다르다)", LIMIT, async () => {
    handler = (req) => req.socket.destroy();
    await assert.rejects(request("/api/x/"), isUnreachable);
  });

  it("사진 중계도 머리를 안 보내면 502", LIMIT, async () => {
    handler = () => {};
    const res = await photoRoute.GET(new Request(`http://localhost/api/accounts/photo/${PHOTO_ID}`), {
      params: Promise.resolve({ id: PHOTO_ID }),
    });
    assert.equal(res.status, 502);
  });
});
