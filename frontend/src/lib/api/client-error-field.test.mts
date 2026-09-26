/**
 * request() 가 실패할 때 ApiError 에 싣는 문구(message)와 칸(field)을 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - 400 대: DRF 본문의 첫 오류 문구를 message 로. 그 키가 칸 이름이면 field.
 *   - {"detail": "..."} 와 non_field_errors 는 칸이 아니라 field 가 없다.
 *   - 500 이상: 본문을 안 보고 기본 문구, field 없음.
 *
 * 비밀번호 카드는 field 로 어느 칸을 비울지 고른다. field 가 잘못 붙으면
 * 멀쩡한 칸이 지워지고, 빠지면 틀린 칸이 남는다.
 *
 * 가짜 백엔드는 globalThis.fetch 를 갈아끼운다(daily-words.test.mts 와 같다).
 */
import assert from "node:assert/strict";
import { after, describe, it } from "node:test";

import { ApiError, request } from "./client";

const realFetch = globalThis.fetch;
after(() => {
  globalThis.fetch = realFetch;
});

/** 한 번의 응답을 흉내 내고, request() 가 던진 ApiError 를 돌려준다. */
async function failWith(status: number, body: unknown, raw = false): Promise<ApiError> {
  globalThis.fetch = (async () =>
    new Response(raw ? String(body) : JSON.stringify(body), {
      status,
      headers: { "Content-Type": raw ? "text/html" : "application/json" },
    })) as typeof fetch;
  try {
    await request("/api/x/", { method: "POST", body: {} });
  } catch (error) {
    assert.ok(error instanceof ApiError, `ApiError 가 아니다: ${String(error)}`);
    return error;
  }
  assert.fail("실패 응답인데 던지지 않았다");
}

describe("칸별 오류는 칸 이름을 싣는다", () => {
  it("current_password 목록 -> 첫 줄과 칸", async () => {
    const e = await failWith(400, { current_password: ["현재 비밀번호가 올바르지 않습니다.", "둘째"] });
    assert.equal(e.message, "현재 비밀번호가 올바르지 않습니다.");
    assert.equal(e.field, "current_password");
    assert.equal(e.status, 400);
  });

  it("new_password 문자열 값도 칸을 싣는다", async () => {
    const e = await failWith(400, { new_password: "너무 짧습니다." });
    assert.equal(e.message, "너무 짧습니다.");
    assert.equal(e.field, "new_password");
  });

  it("여러 칸이면 첫 칸만", async () => {
    const e = await failWith(400, { current_password: ["a"], new_password: ["b"] });
    assert.equal(e.field, "current_password");
    assert.equal(e.message, "a");
  });

  it("빈 목록인 칸은 건너뛰고 문구가 있는 칸을 싣는다", async () => {
    // 문구는 뒤 칸에서 가져오면서 칸 이름만 앞 칸으로 남으면 엉뚱한 칸이 지워진다.
    const e = await failWith(400, { current_password: [], new_password: ["b"] });
    assert.equal(e.message, "b");
    assert.equal(e.field, "new_password");
  });

  it("중첩 객체 칸은 건너뛴다", async () => {
    const e = await failWith(400, { profile: { name: ["x"] }, new_password: ["b"] });
    assert.equal(e.message, "b");
    assert.equal(e.field, "new_password");
  });
});

describe("칸이 아닌 오류는 field 가 없다", () => {
  it('{"detail": "..."}', async () => {
    const e = await failWith(401, { detail: "자격 인증데이터가 제공되지 않았습니다." });
    assert.equal(e.message, "자격 인증데이터가 제공되지 않았습니다.");
    assert.equal(e.field, undefined);
  });

  it("요청 한도(429 detail)", async () => {
    const e = await failWith(429, { detail: "요청이 너무 많습니다." });
    assert.equal(e.field, undefined);
    assert.equal(e.status, 429);
  });

  it("detail 이 칸별 오류보다 앞선다", async () => {
    const e = await failWith(400, { current_password: ["a"], detail: "d" });
    assert.equal(e.message, "d");
    assert.equal(e.field, undefined);
  });

  it("non_field_errors", async () => {
    const e = await failWith(400, { non_field_errors: ["폼 전체 오류"] });
    assert.equal(e.message, "폼 전체 오류");
    assert.equal(e.field, undefined);
  });

  it("non_field_errors 가 비어 있으면 다음 칸으로 간다", async () => {
    const e = await failWith(400, { non_field_errors: [], new_password: ["b"] });
    assert.equal(e.message, "b");
    assert.equal(e.field, "new_password");
  });
});

describe("해석할 수 없는 본문은 기본 문구, field 없음", () => {
  it("JSON 이 아닌 400", async () => {
    const e = await failWith(400, "<html>bad</html>", true);
    assert.equal(e.message, "요청이 실패했습니다. (400)");
    assert.equal(e.field, undefined);
  });

  it("문자열 JSON", async () => {
    const e = await failWith(400, "그냥 문자열");
    assert.equal(e.message, "요청이 실패했습니다. (400)");
    assert.equal(e.field, undefined);
  });

  it("빈 객체", async () => {
    const e = await failWith(400, {});
    assert.equal(e.message, "요청이 실패했습니다. (400)");
    assert.equal(e.field, undefined);
  });
});

describe("500 이상은 본문을 안 본다", () => {
  for (const status of [500, 502, 503]) {
    it(`${status}: 칸별 오류 본문이 와도 기본 문구, field 없음`, async () => {
      const e = await failWith(status, { current_password: ["내부 사정 Traceback"] });
      assert.equal(e.message, `요청이 실패했습니다. (${status})`);
      assert.equal(e.field, undefined);
      assert.doesNotMatch(e.message, /Traceback/);
    });
  }
});

describe("연결 실패", () => {
  it("fetch 가 던지면 status 0, field 없음", async () => {
    globalThis.fetch = (async () => {
      throw new TypeError("fetch failed");
    }) as typeof fetch;
    await assert.rejects(request("/api/x/"), (e: unknown) => {
      assert.ok(e instanceof ApiError);
      assert.equal(e.status, 0);
      assert.equal(e.field, undefined);
      return true;
    });
  });
});
