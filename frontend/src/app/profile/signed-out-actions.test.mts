/**
 * 내정보 액션 여섯이 "로그인이 풀린 것(401)" 과 "그 밖의 실패" 를 가르는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - 백엔드가 401 이면 죽은 쿠키를 지우고(forgetToken) /login?next=/profile 로
 *     바꿔치기(replace) 한다. 문구를 돌려주면 몇 번을 눌러도 같은 401 이다.
 *   - 400·403·429·500·502·503·연결 실패는 문구만 돌려준다. 로그인 화면으로 보내거나
 *     쿠키를 지우면 잠깐의 장애나 오타 하나에 로그아웃된다.
 *
 * 여섯 액션을 한 표로 돈다. 하나라도 catch 에서 401 처리를 빠뜨리면 그 줄만
 * 빨개진다. 사진 둘은 공용 request() 가 아니라 photoRequest 를 거쳐 오류 해석이
 * 다르므로, 같은 표에 두어 그 길도 함께 본다.
 *
 * 대역 방식은 password-action-field.test.mts 와 같다. redirect·revalidatePath·
 * 세션만 갈아끼우고 요청·오류 해석은 실제 코드를 돌린다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

class RedirectError extends Error {
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
      throw new RedirectError(to, type);
    },
    RedirectType: { push: "push", replace: "replace" },
  },
});

mock.module("next/cache", {
  namedExports: { revalidatePath() {} },
});

/** 세션에 일어난 일. 순서까지 본다. */
let session: string[] = [];

mock.module("@/lib/session", {
  namedExports: {
    async setToken(token: string) {
      session.push(`set ${token}`);
    },
    async forgetToken() {
      session.push("forget");
    },
    async clearToken() {
      session.push("clear");
    },
    async getToken() {
      return "tok-old";
    },
  },
});

const actions = await import("./actions");

const realFetch = globalThis.fetch;
after(() => {
  globalThis.fetch = realFetch;
});

let calls = 0;

beforeEach(() => {
  session = [];
  calls = 0;
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

function unreachable(): void {
  globalThis.fetch = (async () => {
    calls += 1;
    throw new TypeError("fetch failed");
  }) as typeof fetch;
}

function form(fields: Record<string, string | File>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.set(k, v);
  return fd;
}

/** 각 액션을 백엔드까지 닿는 폼으로 부른다. */
const runs: [string, () => Promise<unknown>][] = [
  ["이름 저장", () => actions.updateProfileAction({}, form({ display_name: "초롱", avatar: "a1" }))],
  [
    "이메일 변경 신청",
    () =>
      actions.requestEmailChangeAction(
        {},
        form({ new_email: "next@example.com", current_password: "probe-pass-1" }),
      ),
  ],
  [
    "비밀번호 변경",
    () =>
      actions.changePasswordAction(
        {},
        form({
          current_password: "probe-pass-1",
          new_password: "probe-pass-2",
          new_password_confirm: "probe-pass-2",
        }),
      ),
  ],
  ["계정 삭제", () => actions.deleteAccountAction({}, form({ current_password: "probe-pass-1" }))],
  [
    "사진 올리기",
    () =>
      actions.uploadPhotoAction(
        {},
        form({ photo: new File([new Uint8Array([1, 2, 3])], "a.png", { type: "image/png" }) }),
      ),
  ],
  ["사진 지우기", () => actions.deletePhotoAction()],
];

describe("백엔드가 401 이면 쿠키를 지우고 로그인 화면으로 바꿔치기한다", () => {
  for (const [label, run] of runs) {
    it(label, async () => {
      backend(401, { detail: "토큰이 유효하지 않습니다." });

      await assert.rejects(run(), (e: unknown) => {
        assert.ok(e instanceof RedirectError, `redirect 가 아니다: ${String(e)}`);
        assert.equal(e.to, "/login?next=/profile");
        assert.equal(e.type, "replace");
        return true;
      });

      assert.equal(calls, 1);
      // 계정 삭제도 clearToken(게스트 선택까지 지움)이 아니라 forgetToken 이다.
      assert.deepEqual(session, ["forget"]);
    });
  }
});

describe("401 이 아닌 실패는 문구만 돌려주고 쿠키는 그대로 둔다", () => {
  const failures: [string, () => void][] = [
    ["400 detail", () => backend(400, { detail: "요청이 올바르지 않습니다." })],
    ["400 칸별", () => backend(400, { current_password: ["비밀번호가 올바르지 않습니다."] })],
    ["403", () => backend(403, { detail: "관리자 계정은 관리자 화면에서 지워주세요." })],
    ["429", () => backend(429, { detail: "잠시 후 다시 시도해주세요." })],
    ["500", () => backend(500, { detail: "Traceback" })],
    ["502", () => backend(502, { detail: "확인 메일을 보내지 못했습니다." })],
    ["503", () => backend(503, { detail: "지금은 확인 메일을 보낼 수 없습니다." })],
    ["연결 실패", unreachable],
  ];

  for (const [label, run] of runs) {
    for (const [failure, install] of failures) {
      it(`${label} - ${failure}`, async () => {
        install();

        const state = (await run()) as { error?: string; saved?: boolean };

        assert.equal(typeof state.error, "string");
        assert.ok(state.error, "빈 문구다");
        assert.equal(state.saved, undefined);
        assert.deepEqual(session, [], "실패했는데 세션을 건드렸다");
        // 서버 오류의 본문은 그대로 나가지 않는다.
        assert.doesNotMatch(state.error ?? "", /Traceback/);
      });
    }
  }
});

describe("이메일 변경 신청의 메일 실패 안내", () => {
  it("503 이면 백엔드가 쓴 안내가 그대로 화면에 간다", async () => {
    backend(503, { detail: "지금은 확인 메일을 보낼 수 없습니다. 잠시 후 다시 시도해주세요." });
    const state = await actions.requestEmailChangeAction(
      {},
      form({ new_email: "next@example.com", current_password: "probe-pass-1" }),
    );
    assert.deepEqual(state, {
      error: "지금은 확인 메일을 보낼 수 없습니다. 잠시 후 다시 시도해주세요.",
    });
  });

  it("502 도 같다", async () => {
    backend(502, { detail: "확인 메일을 보내지 못했습니다. 잠시 후 다시 시도해주세요." });
    const state = await actions.requestEmailChangeAction(
      {},
      form({ new_email: "next@example.com", current_password: "probe-pass-1" }),
    );
    assert.deepEqual(state, { error: "확인 메일을 보내지 못했습니다. 잠시 후 다시 시도해주세요." });
  });
});
