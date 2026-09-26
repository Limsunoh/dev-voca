/**
 * relayError 가 백엔드 오류를 중계 응답으로 바꾸는 방식과, 401 에서만 토큰
 * 쿠키를 지우는지.
 *
 * 실행: cd frontend && npm test
 *
 * 계약.
 *   1. ApiError 401 -> 토큰 쿠키를 지우고 {detail} 401.
 *   2. ApiError 0(연결 실패) -> 503. 0 을 그대로 쓰면 Response 가 깨진다.
 *   3. 그 밖의 ApiError -> 그 상태 그대로. 쿠키는 안 지운다.
 *      특히 403 은 "토큰은 맞는데 권한이 없다" 라 지우면 멀쩡한 로그인이 풀린다.
 *   4. ApiError 가 아닌 것 -> 500 과 고정 문구. 원래 메시지(백엔드 주소·스택이
 *      들어 있을 수 있다)는 안 나간다.
 *
 * 세션은 "server-only" 라 Next 밖에서 import 하면 터져서 대역으로 바꾼다
 * (kind-page.test.mts 와 같은 방식). 여기서 보려는 것은 "언제 부르나" 다.
 */
import assert from "node:assert/strict";
import { beforeEach, describe, it, mock } from "node:test";

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

const { relayError } = await import("./relay");
const { ApiError } = await import("./client");

beforeEach(() => {
  forgotten = 0;
});

describe("relayError", () => {
  it("401 이면 토큰 쿠키를 지우고 문구와 401 을 돌려준다", async () => {
    const res = await relayError(new ApiError("토큰이 유효하지 않습니다.", 401));
    assert.equal(res.status, 401);
    assert.deepEqual(await res.json(), { detail: "토큰이 유효하지 않습니다." });
    assert.equal(forgotten, 1);
  });

  it("0 이면 503 이고 쿠키를 안 지운다", async () => {
    const res = await relayError(new ApiError("서버에 연결할 수 없습니다.", 0));
    assert.equal(res.status, 503);
    assert.deepEqual(await res.json(), { detail: "서버에 연결할 수 없습니다." });
    assert.equal(forgotten, 0);
  });

  for (const status of [400, 403, 404, 409, 429, 500, 502, 503]) {
    it(`${status} 는 그 상태 그대로이고 쿠키를 안 지운다`, async () => {
      const res = await relayError(new ApiError(`e${status}`, status));
      assert.equal(res.status, status);
      assert.deepEqual(await res.json(), { detail: `e${status}` });
      assert.equal(forgotten, 0);
    });
  }

  it("ApiError 가 아니면 500 과 고정 문구, 원래 메시지는 안 나간다", async () => {
    const res = await relayError(new Error("connect ECONNREFUSED 10.0.0.5:8000"));
    assert.equal(res.status, 500);
    const body = await res.json();
    assert.doesNotMatch(JSON.stringify(body), /ECONNREFUSED|10\.0\.0\.5/);
    assert.equal(forgotten, 0);
  });

  it("던져진 것이 문자열·null 이어도 500 이다", async () => {
    for (const thrown of ["boom", null, undefined, { status: 401 }]) {
      const res = await relayError(thrown);
      assert.equal(res.status, 500);
    }
    assert.equal(forgotten, 0, "ApiError 모양만 흉내 낸 객체로 쿠키가 지워지면 안 된다");
  });

  it("Promise 를 돌려준다(await 하지 않으면 쿠키 지우기가 응답보다 늦는다)", async () => {
    const out = relayError(new ApiError("x", 401));
    assert.ok(out instanceof Promise);
    await out;
  });
});
