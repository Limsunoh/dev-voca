/**
 * changePasswordAction 이 돌려주는 PasswordState.field 를 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 화면(PasswordCard)은 field 로 어느 칸을 비울지 고른다. 계약:
 *   - 새 비밀번호가 비었으면 "new_password" (백엔드에 안 보낸다)
 *   - 확인 값이 다르면 "new_password_confirm" (백엔드에 안 보낸다)
 *   - 백엔드가 current_password / new_password 를 짚으면 그대로
 *   - 그 밖(다른 칸 이름, detail, non_field_errors, 500, 연결 끊김)은 field 없음
 *   - 성공하면 saved, field 없음
 *
 * actions.ts 는 "use server" 파일이라 Next 런타임 대역이 필요하다. 방식은
 * (auth)/actions.test.mts 와 같다 - redirect·revalidatePath·세션만 갈아끼우고
 * 요청·에러 해석(client.ts)은 실제 코드를 돌린다. 그래야 client.ts 가 싣는
 * field 와 여기서 거르는 field 가 이어져 있는지까지 본다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

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
  },
});

mock.module("next/cache", {
  namedExports: { revalidatePath() {} },
});

const cookieJar = new Map<string, string>();

mock.module("@/lib/session", {
  namedExports: {
    async setToken(token: string) {
      cookieJar.set("devvoca_token", token);
    },
    async clearToken() {
      cookieJar.delete("devvoca_token");
    },
    async getToken() {
      return cookieJar.get("devvoca_token");
    },
  },
});

const { changePasswordAction } = await import("./actions");

const realFetch = globalThis.fetch;
after(() => {
  globalThis.fetch = realFetch;
});

/** 백엔드에 실제로 나간 요청 수. 화면에서 걸러야 할 것이 새는지 본다. */
let calls = 0;

beforeEach(() => {
  calls = 0;
  cookieJar.clear();
  cookieJar.set("devvoca_token", "tok-old");
});

function backend(status: number, json: unknown): void {
  globalThis.fetch = (async () => {
    calls += 1;
    return new Response(JSON.stringify(json), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
}

function form(fields: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.set(k, v);
  return fd;
}

const filled = {
  current_password: "old-pass-1!",
  new_password: "new-pass-1!",
  new_password_confirm: "new-pass-1!",
};

describe("화면에서 거르는 실패", () => {
  it("새 비밀번호가 비었으면 new_password, 백엔드에 안 보낸다", async () => {
    backend(200, {});
    const s = await changePasswordAction({}, form({ ...filled, new_password: "" }));
    assert.equal(s.field, "new_password");
    assert.ok(s.error);
    assert.equal(calls, 0);
  });

  it("확인 값이 다르면 new_password_confirm, 백엔드에 안 보낸다", async () => {
    backend(200, {});
    const s = await changePasswordAction({}, form({ ...filled, new_password_confirm: "other" }));
    assert.equal(s.field, "new_password_confirm");
    assert.equal(calls, 0);
  });

  it("공백만 다른 확인 값도 다르다(trim 하지 않는다)", async () => {
    backend(200, {});
    const s = await changePasswordAction(
      {},
      form({ ...filled, new_password_confirm: `${filled.new_password} ` }),
    );
    assert.equal(s.field, "new_password_confirm");
    assert.equal(calls, 0);
  });
});

describe("백엔드가 짚은 칸", () => {
  it("current_password 는 그대로", async () => {
    backend(400, { current_password: ["현재 비밀번호가 올바르지 않습니다."] });
    const s = await changePasswordAction({}, form(filled));
    assert.equal(s.field, "current_password");
    assert.equal(s.error, "현재 비밀번호가 올바르지 않습니다.");
    assert.equal(s.saved, undefined);
    // 실패하면 쿠키를 건드리지 않는다.
    assert.equal(cookieJar.get("devvoca_token"), "tok-old");
  });

  it("new_password 는 그대로", async () => {
    backend(400, { new_password: ["비밀번호가 너무 짧습니다.", "너무 흔합니다."] });
    const s = await changePasswordAction({}, form(filled));
    assert.equal(s.field, "new_password");
    assert.equal(s.error, "비밀번호가 너무 짧습니다.");
  });

  it("백엔드가 new_password_confirm 을 짚어도 받지 않는다(백엔드가 모르는 칸)", async () => {
    backend(400, { new_password_confirm: ["?"] });
    const s = await changePasswordAction({}, form(filled));
    assert.equal(s.field, undefined);
  });

  for (const [label, status, json] of [
    ["다른 칸 이름(email)", 400, { email: ["x"] }],
    ["non_field_errors", 400, { non_field_errors: ["폼 오류"] }],
    ["detail(요청 한도)", 429, { detail: "잠시 후 다시" }],
    ["detail(인증)", 401, { detail: "로그인이 필요합니다." }],
    ["500 에 칸별 본문", 500, { current_password: ["내부"] }],
  ] as const) {
    it(`${label} 이면 field 없음`, async () => {
      backend(status, json);
      const s = await changePasswordAction({}, form(filled));
      assert.equal(s.field, undefined, JSON.stringify(s));
      assert.ok(s.error);
    });
  }

  it("연결 끊김이면 field 없음", async () => {
    globalThis.fetch = (async () => {
      throw new TypeError("fetch failed");
    }) as typeof fetch;
    const s = await changePasswordAction({}, form(filled));
    assert.equal(s.field, undefined);
    assert.equal(s.error, "서버에 연결할 수 없습니다.");
  });
});

describe("성공", () => {
  it("saved 이고 field·error 가 없으며 비밀번호가 결과에 안 실린다", async () => {
    backend(200, { token: "tok-new", created: false });
    const s = await changePasswordAction({}, form(filled));
    assert.deepEqual(s, { saved: true, created: false });
    assert.equal(cookieJar.get("devvoca_token"), "tok-new");
    assert.doesNotMatch(JSON.stringify(s), /pass-1/);
  });
});

describe("로그인이 풀렸으면", () => {
  it("로그인 화면으로 보낸다", async () => {
    cookieJar.clear();
    backend(200, {});
    await assert.rejects(changePasswordAction({}, form(filled)), (e: unknown) => {
      assert.ok(e instanceof RedirectError);
      assert.equal(e.to, "/login?next=/profile");
      return true;
    });
    assert.equal(calls, 0);
  });
});
