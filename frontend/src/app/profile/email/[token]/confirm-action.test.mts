/**
 * 이메일 변경 확인 버튼(confirmEmailChangeAction).
 *
 * 실행: cd frontend && npm test
 *
 * 세 가지를 본다.
 *   - 주소에서 꺼낸 토큰의 쌍점이 %3A 로 와도 원래 글자로 백엔드에 보낸다.
 *     이것이 깨지면 모든 확인 링크가 "만료되었거나 올바르지 않습니다" 가 된다.
 *   - 같은 계정으로 로그인해 있던 기기만 새 토큰으로 로그인을 이어 간다.
 *     로그인이 없거나 다른 계정이면 쿠키를 건드리지 않는다.
 *   - 확인된 로그인 토큰만 백엔드에 실어 보낸다. 백엔드는 같은 계정의 토큰이
 *     실려 있을 때만 새 토큰을 주고, 죽은 토큰이 실리면 401 로 주소 변경까지 막는다.
 *   - 이 기기의 로그인을 확인하지 못하면(401 이 아닌 실패) 확인 전에 멈춘다.
 *
 * 백엔드 호출, 세션, revalidatePath 는 대역이다.
 */
import assert from "node:assert/strict";
import { beforeEach, describe, it, mock } from "node:test";

class FakeApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}
mock.module("@/lib/api/client", {
  namedExports: { ApiError: FakeApiError },
});

let order: string[] = [];
let sentTokens: string[] = [];
let sentLogins: (string | undefined)[] = [];
let confirmReply: () => Promise<unknown>;
let meReply: () => Promise<unknown>;
mock.module("@/lib/api/accounts", {
  namedExports: {
    async getMe() {
      order.push("me");
      return meReply();
    },
    async confirmEmailChange(token: string, login?: string) {
      order.push("confirm");
      sentTokens.push(token);
      sentLogins.push(login);
      return confirmReply();
    },
  },
});

let loginToken: string | null = null;
let savedTokens: string[] = [];
let cookieStoreBroken = false;
mock.module("@/lib/session", {
  namedExports: {
    async getToken() {
      return loginToken;
    },
    async setToken(token: string) {
      if (cookieStoreBroken) throw new Error("cookie store closed");
      savedTokens.push(token);
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

const { confirmEmailChangeAction } = await import("./actions");

function form(token: string): FormData {
  const data = new FormData();
  data.set("token", token);
  return data;
}

const LINK_OWNER = { id: 7 };

beforeEach(() => {
  order = [];
  sentTokens = [];
  sentLogins = [];
  savedTokens = [];
  revalidated = 0;
  loginToken = null;
  cookieStoreBroken = false;
  meReply = async () => LINK_OWNER;
  confirmReply = async () => ({
    token: "new-login",
    user: { id: 7, email: "new@example.com" },
  });
});

describe("주소에서 온 토큰", () => {
  it("%3A 로 바뀐 쌍점을 되돌려 보낸다", async () => {
    await confirmEmailChangeAction({}, form("payload%3Astamp%3Asig"));
    assert.deepEqual(sentTokens, ["payload:stamp:sig"]);
  });

  it("이미 풀린 토큰은 그대로 보낸다", async () => {
    await confirmEmailChangeAction({}, form("payload:stamp:sig"));
    assert.deepEqual(sentTokens, ["payload:stamp:sig"]);
  });

  it("풀 수 없는 값은 그대로 보내 서버가 거절하게 둔다", async () => {
    confirmReply = async () => {
      throw new FakeApiError("확인 링크가 만료되었거나 올바르지 않습니다.", 400);
    };
    const state = await confirmEmailChangeAction({}, form("abc%E0%A4%A"));
    assert.deepEqual(sentTokens, ["abc%E0%A4%A"]);
    assert.equal(state.error, "확인 링크가 만료되었거나 올바르지 않습니다.");
    assert.deepEqual(savedTokens, []);
  });

  it("빈 토큰은 백엔드를 부르지 않는다", async () => {
    const state = await confirmEmailChangeAction({}, form(""));
    assert.equal(state.error, "확인 링크가 올바르지 않습니다.");
    assert.deepEqual(order, []);
  });
});

describe("이 기기의 로그인", () => {
  it("확인된 로그인 토큰만 실어 보낸다", async () => {
    loginToken = "owner-login";
    await confirmEmailChangeAction({}, form("a:b:c"));
    assert.deepEqual(sentLogins, ["owner-login"]);
  });

  it("죽은 토큰(401)과 로그인이 없는 것은 싣지 않는다", async () => {
    await confirmEmailChangeAction({}, form("a:b:c"));
    loginToken = "dead-login";
    meReply = async () => {
      throw new FakeApiError("토큰이 유효하지 않습니다.", 401);
    };
    await confirmEmailChangeAction({}, form("a:b:c"));
    assert.deepEqual(sentLogins, [undefined, undefined]);
  });

  it("같은 계정이어도 백엔드가 새 토큰을 안 주면 쿠키를 건드리지 않는다", async () => {
    loginToken = "owner-login";
    confirmReply = async () => ({ user: { id: 7, email: "new@example.com" } });
    const state = await confirmEmailChangeAction({}, form("a:b:c"));
    assert.deepEqual(savedTokens, []);
    assert.equal(revalidated, 0);
    assert.deepEqual(state, { changedTo: "new@example.com" });
  });

  it("같은 계정으로 로그인돼 있으면 새 토큰으로 이어 간다", async () => {
    loginToken = "owner-login";
    const state = await confirmEmailChangeAction({}, form("a:b:c"));
    assert.deepEqual(savedTokens, ["new-login"]);
    assert.equal(revalidated, 1);
    assert.deepEqual(state, { changedTo: "new@example.com", signedIn: true });
  });

  it("로그인이 없으면 쿠키를 건드리지 않고 다시 로그인하라고 한다", async () => {
    const state = await confirmEmailChangeAction({}, form("a:b:c"));
    assert.deepEqual(savedTokens, []);
    assert.equal(revalidated, 0);
    assert.deepEqual(state, { changedTo: "new@example.com" });
    assert.deepEqual(order, ["confirm"]);
  });

  it("다른 계정으로 로그인돼 있으면 쿠키를 그대로 둔다", async () => {
    loginToken = "other-login";
    meReply = async () => ({ id: 99 });
    const state = await confirmEmailChangeAction({}, form("a:b:c"));
    assert.deepEqual(savedTokens, []);
    assert.equal(revalidated, 0);
    assert.deepEqual(state, { changedTo: "new@example.com" });
  });

  it("죽은 토큰(401)은 로그인이 없는 것과 같다", async () => {
    loginToken = "dead-login";
    meReply = async () => {
      throw new FakeApiError("토큰이 유효하지 않습니다.", 401);
    };
    const state = await confirmEmailChangeAction({}, form("a:b:c"));
    assert.deepEqual(savedTokens, []);
    assert.deepEqual(state, { changedTo: "new@example.com" });
  });

  it("로그인을 확인하지 못하면 확인 전에 멈춘다", async () => {
    loginToken = "other-login";
    for (const failure of [
      () => new FakeApiError("요청이 실패했습니다.", 502),
      () => new FakeApiError("서버에 연결할 수 없습니다.", 0),
      () => new FakeApiError("요청이 너무 많습니다.", 429),
      () => new Error("network"),
    ]) {
      order = [];
      meReply = async () => {
        throw failure();
      };
      const state = await confirmEmailChangeAction({}, form("a:b:c"));
      assert.equal(state.error, "잠시 후 다시 시도해주세요.");
      assert.deepEqual(order, ["me"]);
    }
    assert.deepEqual(savedTokens, []);
  });

  it("누가 로그인했는지는 확인 전에 묻는다", async () => {
    loginToken = "owner-login";
    await confirmEmailChangeAction({}, form("a:b:c"));
    assert.deepEqual(order, ["me", "confirm"]);
  });

  it("백엔드가 거절하면 쿠키를 건드리지 않는다", async () => {
    loginToken = "owner-login";
    confirmReply = async () => {
      throw new FakeApiError("이미 가입된 이메일입니다.", 400);
    };
    const state = await confirmEmailChangeAction({}, form("a:b:c"));
    assert.equal(state.error, "이미 가입된 이메일입니다.");
    assert.deepEqual(savedTokens, []);
  });

  it("주소가 바뀐 뒤 쿠키를 못 넣으면 다시 로그인하라는 안내로 끝낸다", async () => {
    loginToken = "owner-login";
    cookieStoreBroken = true;
    const state = await confirmEmailChangeAction({}, form("a:b:c"));
    assert.deepEqual(state, { changedTo: "new@example.com" });
    assert.equal(revalidated, 0);
  });

  it("알 수 없는 실패는 다시 시도 안내를 낸다", async () => {
    confirmReply = async () => {
      throw new Error("network");
    };
    const state = await confirmEmailChangeAction({}, form("a:b:c"));
    assert.equal(state.error, "잠시 후 다시 시도해주세요.");
  });
});

describe("서버 로그", () => {
  // 사용자에게는 "다시 시도" 나 "다시 로그인" 만 보여서, 왜 그랬는지는 서버 로그에만
  // 남는다. 백엔드가 이유를 말해 준 거절(ApiError)은 남기지 않는다.
  it("원인을 말할 수 없는 실패는 한 번씩 남긴다", async (t) => {
    const logged = t.mock.method(console, "error", () => {});
    const cases: [string, () => void][] = [
      ["로그인 확인 실패", () => {
        loginToken = "owner-login";
        meReply = async () => {
          throw new FakeApiError("요청이 실패했습니다.", 502);
        };
      }],
      ["확인 중 알 수 없는 실패", () => {
        confirmReply = async () => {
          throw new Error("network");
        };
      }],
      ["쿠키 실패", () => {
        loginToken = "owner-login";
        cookieStoreBroken = true;
      }],
    ];
    for (const [name, arrange] of cases) {
      logged.mock.resetCalls();
      loginToken = null;
      cookieStoreBroken = false;
      meReply = async () => LINK_OWNER;
      confirmReply = async () => ({
        token: "new-login",
        user: { id: 7, email: "new@example.com" },
      });
      arrange();
      await confirmEmailChangeAction({}, form("a:b:c"));
      assert.equal(logged.mock.callCount(), 1, name);
    }
  });

  it("백엔드가 거절한 것과 로그인이 없는 것은 남기지 않는다", async (t) => {
    const logged = t.mock.method(console, "error", () => {});
    loginToken = "dead-login";
    meReply = async () => {
      throw new FakeApiError("토큰이 유효하지 않습니다.", 401);
    };
    confirmReply = async () => {
      throw new FakeApiError("확인 링크가 만료되었거나 올바르지 않습니다.", 400);
    };
    await confirmEmailChangeAction({}, form("a:b:c"));
    assert.equal(logged.mock.callCount(), 0);
  });
});

describe("확인과 로그인 확인이 엇갈릴 때", () => {
  // /me 로 확인한 뒤 확인 요청 전에 토큰이 죽을 수 있다(다른 기기에서 로그아웃 등).
  // 백엔드는 실린 토큰이 죽었으면 401 을 내고 주소를 안 바꾼다.
  it("확인이 401 이면 쿠키를 건드리지 않고 백엔드 안내를 보인다", async () => {
    loginToken = "owner-login";
    confirmReply = async () => {
      throw new FakeApiError("토큰이 유효하지 않습니다.", 401);
    };
    const state = await confirmEmailChangeAction({}, form("a:b:c"));
    assert.deepEqual(savedTokens, []);
    assert.equal(revalidated, 0);
    assert.equal(state.error, "토큰이 유효하지 않습니다.");
    assert.equal(state.changedTo, undefined);
  });

  it("다른 계정의 확인된 토큰은 실어 보내지만 돌아온 토큰은 넣지 않는다", async () => {
    // 백엔드가 계정을 대조한다. 혹시 토큰이 돌아와도 화면이 한 번 더 막는다.
    loginToken = "other-login";
    meReply = async () => ({ id: 99 });
    const state = await confirmEmailChangeAction({}, form("a:b:c"));
    assert.deepEqual(sentLogins, ["other-login"]);
    assert.deepEqual(savedTokens, []);
    assert.deepEqual(state, { changedTo: "new@example.com" });
  });

  it("빈 문자열 토큰은 백엔드에 싣지 않는다", async () => {
    // getToken 이 빈 값을 주면 로그인이 없는 것이다. /me 도 부르지 않는다.
    loginToken = "";
    await confirmEmailChangeAction({}, form("a:b:c"));
    assert.deepEqual(order, ["confirm"]);
    assert.deepEqual(sentLogins, [undefined]);
  });
});
