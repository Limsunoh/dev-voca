/**
 * 로그인·가입 Server Action 이 되돌려주는 값 검증.
 *
 * 러너는 daily-words.test.mts 와 같다(node 내장 test + tsx). 가짜 백엔드도
 * 같은 방식으로 globalThis.fetch 를 갈아끼운다.
 *
 * 다만 actions.ts 는 곧바로 import 할 수 없다. "use server" 파일이라
 * next/navigation 의 redirect 와 lib/session 의 setToken 을 부르는데, 둘 다
 * Next 런타임 밖에서는 던진다. 그 둘만 mock.module 로 갈아끼우고 나머지
 * (요청·에러 해석·되살릴 값 구성)는 실제 코드를 그대로 돌린다.
 *
 * **`--experimental-test-module-mocks` 가 필요하다.** package.json 의 test
 * 스크립트가 이 플래그를 붙인다. 플래그는 프로세스가 뜰 때 읽히므로 파일
 * 안에서 켤 수 없다 - 없이 돌리면 `mock.module is not a function` 이다.
 *
 *   cd frontend
 *   npx tsx --test --experimental-test-module-mocks "src/app/(auth)/actions.test.mts"
 *
 * 여기서 못 박으려는 계약은 셋이다.
 *   1. 실패하면 친 값이 values 로 돌아온다(연속 실패·값을 고친 실패 포함)
 *   2. 비밀번호는 어떤 경로로도 안 돌아온다
 *   3. 성공하면 redirect 하고 아무 값도 안 남긴다
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

// ---------------------------------------------------------------------------
// Next 런타임 대역. actions.ts 를 import 하기 전에 등록해야 한다.
// ---------------------------------------------------------------------------

/** setToken 이 넣은 쿠키. 비밀번호가 여기 새는지도 본다. */
const cookieJar = new Map<string, string>();

/** redirect 는 실제로도 던진다. 성공 경로를 잡는 방식이 같아야 의미가 있다. */
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

/**
 * 쿠키 보관을 맡는 lib/session 대역.
 *
 * next/headers 만 갈아끼우면 될 것 같지만 안 된다 - lib/session.ts 맨 위의
 * `import "server-only"` 가 Next 번들러 밖에서는 해석되지 않는다(그 패키지는
 * next 안에만 있고 node_modules 최상위에 없다). 이건 코드 결함이 아니라
 * 하네스 제약이라 세션 모듈 자체를 대역으로 둔다.
 *
 * 그래도 잃는 것이 없다. 여기서 확인하려는 것은 "성공하면 토큰이 저장되고
 * 실패하면 저장되지 않는가" 이고, 그 호출은 actions.ts 안에 있다.
 */
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

// ---------------------------------------------------------------------------
// 가짜 백엔드
// ---------------------------------------------------------------------------

const realFetch = globalThis.fetch;
after(() => {
  globalThis.fetch = realFetch;
});

/** 백엔드가 실제로 받은 본문. 비밀번호가 제대로·그대로 나가는지 확인에 쓴다. */
let sent: Array<{ path: string; body: Record<string, unknown> }> = [];

beforeEach(() => {
  sent = [];
  cookieJar.clear();
});

/**
 * DRF 응답 흉내.
 *
 * 400 본문은 실제 백엔드 모양({"non_field_errors": [...]})을 쓴다.
 * {"detail"} 로만 시험하면 client.ts 의 칸별 오류 분기가 안 돌아
 * 그쪽 회귀를 못 잡는다.
 */
function installBackend(
  reply: (body: Record<string, unknown>) => { status: number; json: unknown },
): void {
  globalThis.fetch = (async (
    url: string | URL | Request,
    init?: RequestInit,
  ) => {
    const href = typeof url === "string" ? url : url.toString();
    const body = JSON.parse(String(init?.body ?? "{}"));
    sent.push({ path: new URL(href).pathname, body });

    const { status, json } = reply(body);
    return new Response(JSON.stringify(json), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
}

/** 늘 거절하는 백엔드. */
function installRejectingBackend(
  message = "이메일 또는 비밀번호가 올바르지 않습니다.",
): void {
  installBackend(() => ({
    status: 400,
    json: { non_field_errors: [message] },
  }));
}

/** 늘 성공하는 백엔드. */
function installAcceptingBackend(token = "tok-ok"): void {
  installBackend(() => ({
    status: 200,
    json: { token, user: { id: 1, email: "a@b.c" } },
  }));
}

function form(fields: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.set(k, v);
  return fd;
}

// 대역 등록 뒤에 불러와야 한다.
const { loginAction, signUpAction } = await import("./actions");
type FormState = Awaited<ReturnType<typeof loginAction>>;
type Action = (prev: FormState, fd: FormData) => Promise<FormState>;

/** redirect 는 던지므로 성공 경로는 이걸로 잡는다. */
async function run(
  action: Action,
  prev: FormState,
  fields: Record<string, string>,
): Promise<{ state?: FormState; redirect?: string }> {
  try {
    return { state: await action(prev, form(fields)) };
  } catch (error) {
    if (error instanceof RedirectError) return { redirect: error.to };
    throw error;
  }
}

/** 돌아온 값 어디에도 비밀번호가 없는지. JSON 전체를 훑는다. */
function assertNoPassword(
  state: FormState | undefined,
  password: string,
): void {
  const dump = JSON.stringify(state ?? {});
  assert.ok(
    !dump.includes(password),
    `되돌려준 값에 비밀번호가 들어 있다: ${dump}`,
  );
  // 키 자체도 없어야 한다. 빈 문자열로라도 들어오면 다음 사람이 채운다.
  assert.ok(
    !("password" in (state?.values ?? {})),
    "values 에 password 키가 있다",
  );
}

// ---------------------------------------------------------------------------

describe("loginAction - 실패하면 이메일이 남는다", () => {
  it("한 번 실패하면 친 이메일이 values 로 돌아온다", async () => {
    installRejectingBackend();
    const { state } = await run(
      loginAction,
      {},
      { email: "nobody-1@example.com", password: "wrong-pw" },
    );

    assert.equal(state?.values?.email, "nobody-1@example.com");
    assert.ok(state?.error);
  });

  it("연속 세 번 실패해도 계속 남는다", async () => {
    installRejectingBackend();

    // 화면은 직전 state 를 prev 로 넘긴다. 그 연쇄를 그대로 재현한다.
    let state: FormState = {};
    for (let i = 0; i < 3; i += 1) {
      const result = await run(loginAction, state, {
        email: "nobody-2@example.com",
        password: `wrong-${i}`,
      });
      state = result.state!;
      assert.equal(
        state.values?.email,
        "nobody-2@example.com",
        `${i + 1}번째 실패에서 이메일이 사라졌다`,
      );
    }
  });

  it("이메일을 고쳐 치고 실패하면 고친 값이 남는다", async () => {
    installRejectingBackend();

    const first = await run(
      loginAction,
      {},
      { email: "old@example.com", password: "x1234567" },
    );
    assert.equal(first.state?.values?.email, "old@example.com");

    // 사용자가 칸을 고쳤다. 새 FormData 에는 새 값만 들어 있다.
    const second = await run(loginAction, first.state!, {
      email: "new@example.com",
      password: "x1234567",
    });
    assert.equal(
      second.state?.values?.email,
      "new@example.com",
      "옛 값으로 되돌아갔다",
    );
  });

  it("빈 비밀번호로 제출해도 친 이메일은 남는다", async () => {
    installRejectingBackend();
    const { state } = await run(
      loginAction,
      {},
      { email: "typed@example.com", password: "" },
    );

    assert.equal(state?.values?.email, "typed@example.com");
    assert.equal(sent.length, 0, "빈 비밀번호가 서버까지 갔다");
  });

  it("이메일도 비우면 values.email 은 빈 문자열이다", async () => {
    installRejectingBackend();
    const { state } = await run(loginAction, {}, { email: "", password: "" });
    assert.equal(state?.values?.email, "");
  });
});

describe("loginAction - 비밀번호는 안 남는다", () => {
  it("서버 거절 응답에도 비밀번호가 안 실린다", async () => {
    installRejectingBackend();
    const { state } = await run(
      loginAction,
      {},
      { email: "nobody-3@example.com", password: "Sup3rSecret!pw" },
    );
    assertNoPassword(state, "Sup3rSecret!pw");
  });

  it("빈 칸 거절(서버 안 감)에도 안 실린다", async () => {
    installRejectingBackend();
    const { state } = await run(
      loginAction,
      {},
      { email: "", password: "Sup3rSecret!pw" },
    );
    assertNoPassword(state, "Sup3rSecret!pw");
  });

  it("실패해도 토큰 쿠키가 안 생긴다", async () => {
    installRejectingBackend();
    await run(
      loginAction,
      {},
      { email: "nobody-9@example.com", password: "wrong-pw" },
    );
    assert.equal(cookieJar.size, 0, "실패했는데 쿠키가 생겼다");
  });
});

describe("loginAction - 성공", () => {
  it("성공하면 redirect 하고 아무 값도 안 남긴다", async () => {
    installAcceptingBackend();
    const result = await run(
      loginAction,
      {},
      { email: "ok@example.com", password: "QaProbe2026!x" },
    );

    assert.equal(result.state, undefined, "성공했는데 state 가 돌아왔다");
    assert.equal(result.redirect, "/");
    assert.equal(cookieJar.get("devvoca_token"), "tok-ok");
  });

  it("next 가 있으면 그리로 간다", async () => {
    installAcceptingBackend();
    const result = await run(loginAction, {}, {
      email: "ok@example.com",
      password: "QaProbe2026!x",
      next: "/learn/words",
    });
    assert.equal(result.redirect, "/learn/words");
  });

  it("바깥 주소는 next 로 안 받는다", async () => {
    installAcceptingBackend();
    const result = await run(loginAction, {}, {
      email: "ok@example.com",
      password: "QaProbe2026!x",
      next: "//evil.example.com",
    });
    assert.equal(result.redirect, "/");
  });

  it("실패 뒤 성공하면 직전 values 가 따라오지 않는다", async () => {
    installRejectingBackend();
    const failed = await run(
      loginAction,
      {},
      { email: "nobody-5@example.com", password: "wrong-pw" },
    );

    installAcceptingBackend();
    const ok = await run(loginAction, failed.state!, {
      email: "ok@example.com",
      password: "QaProbe2026!x",
    });
    assert.equal(ok.state, undefined);
    assert.equal(ok.redirect, "/");
  });
});

describe("signUpAction - 이메일·이름이 남는다", () => {
  it("실패하면 이메일과 이름이 둘 다 돌아온다", async () => {
    installRejectingBackend("이미 가입된 이메일입니다.");
    const { state } = await run(signUpAction, {}, {
      email: "dup@example.com",
      password: "QaProbe2026!x",
      display_name: "임선오",
    });

    assert.equal(state?.values?.email, "dup@example.com");
    assert.equal(state?.values?.display_name, "임선오");
  });

  it("이름을 비운 채 실패하면 빈 칸이다", async () => {
    installRejectingBackend("이미 가입된 이메일입니다.");
    const { state } = await run(signUpAction, {}, {
      email: "dup@example.com",
      password: "QaProbe2026!x",
      display_name: "",
    });

    assert.equal(state?.values?.display_name, "");
    // undefined 가 아니어야 한다. defaultValue={undefined} 는 React 가
    // "제어하지 않음" 으로 읽어 직전 DOM 값이 남을 수 있다.
    assert.notEqual(state?.values?.display_name, undefined);
  });

  it("이름 칸이 아예 없어도 터지지 않는다", async () => {
    installRejectingBackend();
    const { state } = await run(signUpAction, {}, {
      email: "dup@example.com",
      password: "QaProbe2026!x",
    });
    assert.equal(state?.values?.display_name, "");
  });

  it("공백만 친 이름은 다듬어져 빈 칸으로 돌아온다", async () => {
    installRejectingBackend();
    const { state } = await run(signUpAction, {}, {
      email: "dup@example.com",
      password: "QaProbe2026!x",
      display_name: "   ",
    });
    assert.equal(state?.values?.display_name, "");
  });

  it("연속 세 번 실패해도 두 칸이 다 남는다", async () => {
    installRejectingBackend("이미 가입된 이메일입니다.");
    let state: FormState = {};
    for (let i = 0; i < 3; i += 1) {
      const result = await run(signUpAction, state, {
        email: "dup@example.com",
        password: `QaProbe2026!x${i}`,
        display_name: "임선오",
      });
      state = result.state!;
      assert.equal(state.values?.email, "dup@example.com");
      assert.equal(state.values?.display_name, "임선오");
    }
  });

  it("비밀번호는 가입에서도 안 남는다", async () => {
    installRejectingBackend();
    const { state } = await run(signUpAction, {}, {
      email: "dup@example.com",
      password: "Sup3rSecret!pw",
      display_name: "임선오",
    });
    assertNoPassword(state, "Sup3rSecret!pw");
  });

  it("아주 긴 이메일도 그대로 되돌아온다", async () => {
    installRejectingBackend();
    // 백엔드 EmailField(max_length=254) 경계 근처.
    const long = `${"a".repeat(240)}@example.com`;
    const { state } = await run(signUpAction, {}, {
      email: long,
      password: "QaProbe2026!x",
    });
    assert.equal(state?.values?.email, long);
  });

  it("이름이 빈 문자열이면 백엔드에 display_name 을 안 보낸다", async () => {
    installRejectingBackend();
    await run(signUpAction, {}, {
      email: "dup@example.com",
      password: "QaProbe2026!x",
      display_name: "",
    });
    assert.ok(
      !("display_name" in sent[0].body),
      "빈 이름이 서버로 나갔다 - 서버가 자동으로 지어줄 기회를 잃는다",
    );
  });
});

describe("입력 다듬기와 서버 오류", () => {
  it("이메일 앞뒤 공백은 떼고 되돌려준다", async () => {
    installRejectingBackend();
    const { state } = await run(loginAction, {}, {
      email: "  spaced@example.com  ",
      password: "QaProbe2026!x",
    });
    assert.equal(state?.values?.email, "spaced@example.com");
  });

  it("공백만 친 이메일은 서버까지 안 간다", async () => {
    installRejectingBackend();
    const { state } = await run(loginAction, {}, {
      email: "   ",
      password: "QaProbe2026!x",
    });
    assert.equal(sent.length, 0);
    assert.equal(state?.values?.email, "");
  });

  it("비밀번호의 앞뒤 공백은 안 뗀다", async () => {
    installRejectingBackend();
    await run(loginAction, {}, {
      email: "nobody-6@example.com",
      password: "  spaced  ",
    });
    assert.equal(
      sent[0].body.password,
      "  spaced  ",
      "비밀번호를 다듬으면 공백이 든 비밀번호로 영영 로그인 못 한다",
    );
  });

  it("서버가 500 이면 내부 사정을 안 보여주고 값은 남긴다", async () => {
    installBackend(() => ({ status: 500, json: { detail: "traceback ..." } }));
    const { state } = await run(loginAction, {}, {
      email: "nobody-7@example.com",
      password: "QaProbe2026!x",
    });
    assert.ok(!state?.error?.includes("traceback"));
    assert.equal(state?.values?.email, "nobody-7@example.com");
  });

  it("백엔드가 안 떠 있어도 값은 남긴다", async () => {
    globalThis.fetch = (async () => {
      throw new TypeError("fetch failed");
    }) as typeof fetch;
    const { state } = await run(loginAction, {}, {
      email: "nobody-8@example.com",
      password: "QaProbe2026!x",
    });
    assert.equal(state?.error, "서버에 연결할 수 없습니다.");
    assert.equal(state?.values?.email, "nobody-8@example.com");
  });

  it("시도 제한(429)에 걸려도 값은 남긴다", async () => {
    installBackend(() => ({
      status: 429,
      json: { detail: "요청이 너무 잦습니다. 60초 뒤에 다시 시도해주세요." },
    }));
    const { state } = await run(loginAction, {}, {
      email: "nobody-10@example.com",
      password: "QaProbe2026!x",
    });
    assert.ok(state?.error?.includes("너무 잦"));
    assert.equal(state?.values?.email, "nobody-10@example.com");
  });
});
