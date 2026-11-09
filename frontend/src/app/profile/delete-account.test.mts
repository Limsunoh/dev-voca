/**
 * 계정 삭제 액션과 확인 창.
 *
 * 실행: cd frontend && npm test
 *
 * 대역 방식은 password-action-field.test.mts 와 같다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

let clearedToken = false;
let forgotToken = false;
let token: string | null = "tok";

mock.module("next/navigation", {
  namedExports: {
    redirect(to: string): never {
      throw new Error(`NEXT_REDIRECT ${to}`);
    },
  },
});

mock.module("next/cache", {
  namedExports: { revalidatePath() {} },
});

mock.module("@/lib/session", {
  namedExports: {
    async setToken() {},
    async clearToken() {
      clearedToken = true;
    },
    async forgetToken() {
      forgotToken = true;
    },
    async getToken() {
      return token;
    },
  },
});

const { deleteAccountAction } = await import("./actions");
const { DeleteAccount } = await import("./DeleteAccount");

const realFetch = globalThis.fetch;
after(() => {
  globalThis.fetch = realFetch;
});

let sent: { method?: string; body?: string; auth?: string } = {};

function backend(status: number, json?: unknown): void {
  globalThis.fetch = (async (_url: string, init: RequestInit) => {
    sent = {
      method: init.method,
      body: String(init.body),
      auth: (init.headers as Record<string, string>).Authorization,
    };
    return new Response(json === undefined ? null : JSON.stringify(json), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }) as unknown as typeof fetch;
}

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

beforeEach(() => {
  clearedToken = false;
  forgotToken = false;
  token = "tok";
  sent = {};
});

describe("deleteAccountAction", () => {
  it("성공하면 쿠키를 지우고 시작 화면으로 보낸다", async () => {
    backend(204);

    await assert.rejects(
      deleteAccountAction({}, form({ current_password: "pw" })),
      /NEXT_REDIRECT \/start\?deleted=1/,
    );

    assert.equal(sent.method, "DELETE");
    assert.equal(sent.auth, "Token tok");
    assert.deepEqual(JSON.parse(sent.body ?? ""), { current_password: "pw" });
    assert.equal(clearedToken, true);
  });

  it("비밀번호 칸이 없으면 이메일을 보낸다", async () => {
    backend(204);

    await assert.rejects(
      deleteAccountAction({}, form({ email: "g@example.com" })),
      /NEXT_REDIRECT/,
    );

    assert.deepEqual(JSON.parse(sent.body ?? ""), { email: "g@example.com" });
  });

  it("거절되면 문구를 돌려주고 쿠키는 그대로 둔다", async () => {
    backend(400, { current_password: ["비밀번호가 올바르지 않습니다."] });

    const state = await deleteAccountAction({}, form({ current_password: "x" }));

    assert.deepEqual(state, { error: "비밀번호가 올바르지 않습니다." });
    assert.equal(clearedToken, false);
  });

  it("토큰이 이미 무효면 게스트 선택은 두고 토큰만 지워 로그인으로 보낸다", async () => {
    backend(401, { detail: "토큰이 유효하지 않습니다." });

    await assert.rejects(
      deleteAccountAction({}, form({ current_password: "x" })),
      /NEXT_REDIRECT \/login\?next=\/profile/,
    );

    assert.equal(forgotToken, true);
    assert.equal(clearedToken, false);
  });

  it("로그인이 풀렸으면 백엔드를 부르지 않고 로그인으로 보낸다", async () => {
    token = null;
    backend(204);

    await assert.rejects(
      deleteAccountAction({}, form({ current_password: "x" })),
      /NEXT_REDIRECT \/login\?next=\/profile/,
    );

    assert.equal(sent.method, undefined);
  });
});

describe("deleteAccountAction 경계", () => {
  it("비밀번호의 앞뒤 공백을 그대로 보낸다", async () => {
    backend(204);

    await assert.rejects(
      deleteAccountAction({}, form({ current_password: "  pw  " })),
      /NEXT_REDIRECT/,
    );

    assert.deepEqual(JSON.parse(sent.body ?? ""), { current_password: "  pw  " });
  });

  it("요청 한도면 안내를 돌려주고 쿠키는 그대로 둔다", async () => {
    backend(429, { detail: "요청이 너무 많습니다." });

    const state = await deleteAccountAction({}, form({ current_password: "x" }));

    assert.equal(state.error, "요청이 너무 많습니다.");
    assert.equal(clearedToken, false);
    assert.equal(forgotToken, false);
  });

  it("서버 오류면 내부 내용을 보이지 않고 쿠키를 그대로 둔다", async () => {
    backend(500, { detail: "내부 정보" });

    const state = await deleteAccountAction({}, form({ current_password: "x" }));

    assert.doesNotMatch(state.error ?? "", /내부 정보/);
    assert.equal(clearedToken, false);
  });
});

describe("DeleteAccount", () => {
  it("처음에는 버튼만 그리고 입력칸은 창을 열 때 생긴다", () => {
    const html = renderToStaticMarkup(
      createElement(DeleteAccount, {
        action: async () => ({}),
        hasPassword: true,
        email: "a@example.com",
      }),
    );

    assert.match(html, /계정 삭제/);
    assert.doesNotMatch(html, /<dialog|<input/);
  });
});
