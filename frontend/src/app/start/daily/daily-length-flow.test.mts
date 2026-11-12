/**
 * 하루 공부량을 묻고 저장하는 흐름. 서버 액션(saveDailyLengthAction), 묻는
 * 화면(/start/daily), 홈의 보내기, 일일공부 화면의 ?choose=1, 오늘만 다른 길이
 * 링크(OtherLengthLink)를 실제 코드로 돌린다.
 *
 * 실행: cd frontend && npm test
 *
 * 세션은 "server-only" 라 대역으로 바꾼다(stale-token-pages.test.mts 와 같은
 * 방식). 쿠키 함수 자체는 lib/session-daily-length.test.mts 가 실제 코드로 본다.
 *
 * 계약.
 *   1. 액션은 5m·10m·30m 밖의 값을 백엔드에 보내지 않고 오류로 돌려준다.
 *   2. 로그인했으면 계정에 저장한다. 처음 묻는 화면에서는 홈으로, 내정보에서는
 *      그 자리에 남는다(saved).
 *   3. 토큰이 거절(401)되면 토큰을 지운다. 처음 묻는 화면은 게스트로 저장하고
 *      홈으로 간다(안 그러면 고르고 실패하기를 반복한다). 내정보는 로그인으로.
 *   4. 401 이 아닌 실패(400·500·연결 실패)는 토큰을 안 지우고 오류를 돌려준다.
 *   5. 홈은 계정 값이 "" 일 때만 묻는다. 칸이 없는 옛 백엔드, 토큰은 있는데
 *      사람을 못 받은 경우(죽은 토큰·백엔드 장애)에는 묻지 않는다 - 묻는 화면에
 *      탭바가 없어 거기 갇힌다.
 *   6. 묻는 화면은 이미 고른 사람(칸 없음 포함)을 홈으로 돌려보낸다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";
import type { ReactElement, ReactNode } from "react";

class Redirect extends Error {
  constructor(
    readonly to: string,
    readonly type?: string,
  ) {
    super("NEXT_REDIRECT");
  }
}

mock.module("next/navigation", {
  namedExports: {
    redirect: (to: string, type?: string) => {
      throw new Redirect(to, type);
    },
    RedirectType: { push: "push", replace: "replace" },
    notFound: () => {
      throw new Error("notFound");
    },
    useRouter: () => ({ push() {}, replace() {}, refresh() {} }),
    usePathname: () => "/",
    useSearchParams: () => new URLSearchParams(),
  },
});

let revalidated: string[] = [];
mock.module("next/cache", {
  namedExports: {
    revalidatePath: (path: string) => void revalidated.push(path),
  },
});

// ---- 세션 대역 --------------------------------------------------------------

const LIVE = "live-token";
let token: string | null = null;
/** getCurrentUser 가 돌려줄 사람. null 이면 못 받은 것(죽은 토큰·장애). */
let me: Record<string, unknown> | null = null;
let guest = false;
let guestLength: string | null = null;
let forgot = 0;

mock.module("@/lib/session", {
  namedExports: {
    getToken: async () => token,
    getCurrentUser: async () => me,
    isGuestChosen: async () => guest,
    getGuestDailyLength: async () => guestLength,
    setGuestDailyLength: async (length: string) => {
      guestLength = length;
    },
    forgetToken: async () => {
      forgot += 1;
      token = null;
    },
    async withTokenOrGuest<T>(t: string | null, call: (t?: string) => Promise<T>) {
      return { value: await call(t ?? undefined), token: t };
    },
  },
});

// ---- 가짜 백엔드 ------------------------------------------------------------

type Reply = { status: number; body?: unknown } | "down";
let patchReply: Reply = { status: 200 };
let patches: { auth: string | null; body: unknown }[] = [];

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
  const url = new URL(String(input));
  if (init?.method === "PATCH" && url.pathname === "/api/accounts/me/") {
    patches.push({
      auth: new Headers(init.headers).get("Authorization"),
      body: JSON.parse(String(init.body)),
    });
    if (patchReply === "down") throw new TypeError("fetch failed");
    return json(patchReply.status, patchReply.body ?? { detail: "실패" });
  }
  // 홈·허브가 그릴 때 부르는 나머지(단어, 오늘 카드). 내용은 상관없다.
  return json(200, { count: 0, results: [], lengths: [], today: null, due: 0 });
}) as typeof fetch;

const realError = console.error;
console.error = () => {};
after(() => {
  globalThis.fetch = realFetch;
  console.error = realError;
});

const { saveDailyLengthAction } = await import("./actions");
const StartDailyPage = (await import("./page")).default;
const Home = (await import("../../page")).default;
const { OtherLengthLink } = await import("../../../components/TodayCards");
const DailyPage = (await import("../../test/daily/page")).default;
const { DailyStudyBoard } = await import("../../../components/DailyStudyBoard");

beforeEach(() => {
  token = null;
  me = null;
  guest = false;
  guestLength = null;
  forgot = 0;
  patches = [];
  patchReply = { status: 200 };
  revalidated = [];
});

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [k, v] of Object.entries(fields)) data.set(k, v);
  return data;
}

async function caught(run: () => Promise<unknown>): Promise<Redirect | null> {
  try {
    await run();
    return null;
  } catch (error) {
    if (error instanceof Redirect) return error;
    throw error;
  }
}

/** 화면(page.tsx)의 redirect. 화면의 redirect 는 원래 바꿔치기라 type 을 안 넘긴다. */
async function redirectOf(run: () => Promise<unknown>): Promise<string | null> {
  return (await caught(run))?.to ?? null;
}

/**
 * 액션의 redirect. 모두 바꿔치기여야 한다. 묻는 화면이 기록에 남으면 홈에서
 * 뒤로 가기가 거기로 가서 앱이 안 닫힌다(lib/history-nav.ts).
 */
async function actionRedirectOf(run: () => Promise<unknown>): Promise<string | null> {
  const r = await caught(run);
  if (r) assert.equal(r.type, "replace", `${r.to} 로 쌓으며 간다`);
  return r?.to ?? null;
}

// ---------------------------------------------------------------------------

describe("saveDailyLengthAction - 입력", () => {
  for (const bad of ["", "99m", "5M", " 5m", "10m ", "5", "SHORT", "5분", "5m\u0000"]) {
    it(`length=${JSON.stringify(bad)} 은 오류이고 아무것도 저장하지 않는다`, async () => {
      token = LIVE;
      const result = await saveDailyLengthAction({}, form({ length: bad, from: "start" }));

      assert.deepEqual(result, { error: "길이를 골라주세요." });
      assert.equal(patches.length, 0);
      assert.equal(guestLength, null);
    });
  }

  it("length 가 없으면 오류다", async () => {
    const result = await saveDailyLengthAction({}, form({ from: "start" }));
    assert.deepEqual(result, { error: "길이를 골라주세요." });
  });

  it("length 가 파일이면 오류다", async () => {
    const data = form({ from: "start" });
    data.set("length", new Blob(["10m"]), "10m");
    const result = await saveDailyLengthAction({}, data);
    assert.deepEqual(result, { error: "길이를 골라주세요." });
    assert.equal(guestLength, null);
  });
});

describe("saveDailyLengthAction - 로그인한 사람", () => {
  it("처음 묻는 화면: 계정에 저장하고 홈으로", async () => {
    token = LIVE;
    const to = await actionRedirectOf(() =>
      saveDailyLengthAction({}, form({ length: "30m", from: "start" })),
    );

    assert.equal(to, "/");
    assert.deepEqual(patches, [{ auth: `Token ${LIVE}`, body: { daily_length: "30m" } }]);
    assert.equal(guestLength, null, "계정에 저장했는데 게스트 쿠키에도 넣었다");
    assert.deepEqual(revalidated, ["/"]);
  });

  it("내정보: 계정에 저장하고 그 자리에 남는다", async () => {
    token = LIVE;
    const result = await saveDailyLengthAction({}, form({ length: "5m", from: "profile" }));

    assert.deepEqual(result, { saved: true });
    assert.equal(patches.length, 1);
  });

  it("from 을 모르는 값으로 바꾸면 처음 묻는 화면처럼 홈으로 간다", async () => {
    token = LIVE;
    const to = await actionRedirectOf(() =>
      saveDailyLengthAction({}, form({ length: "5m", from: "https://evil.example" })),
    );
    assert.equal(to, "/");
  });
});

describe("saveDailyLengthAction - 토큰이 거절(401)되면", () => {
  it("처음 묻는 화면: 토큰을 지우고 게스트로 저장한 뒤 홈으로", async () => {
    token = LIVE;
    patchReply = { status: 401 };
    const to = await actionRedirectOf(() =>
      saveDailyLengthAction({}, form({ length: "10m", from: "start" })),
    );

    assert.equal(to, "/");
    assert.equal(forgot, 1);
    assert.equal(guestLength, "10m");
  });

  it("내정보: 토큰을 지우고 로그인으로, 게스트 쿠키에는 안 넣는다", async () => {
    token = LIVE;
    patchReply = { status: 401 };
    const to = await actionRedirectOf(() =>
      saveDailyLengthAction({}, form({ length: "10m", from: "profile" })),
    );

    assert.equal(to, "/login?next=/profile");
    assert.equal(forgot, 1);
    assert.equal(guestLength, null);
  });
});

for (const [label, r] of [
  ["400", { status: 400, body: { daily_length: ["올바르지 않은 값"] } }],
  ["500", { status: 500, body: { detail: "서버 오류" } }],
  ["연결 실패", "down"],
] as [string, Reply][]) {
  describe(`saveDailyLengthAction - 백엔드가 ${label} 이면`, () => {
    it("토큰을 지우지 않고 오류를 돌려준다(던지지 않는다)", async () => {
      token = LIVE;
      patchReply = r;
      const result = await saveDailyLengthAction({}, form({ length: "10m", from: "start" }));

      assert.equal(typeof result.error, "string");
      assert.ok(result.error!.length > 0, "빈 오류 문구");
      assert.equal(forgot, 0);
      assert.equal(guestLength, null);
    });
  });
}

describe("saveDailyLengthAction - 게스트", () => {
  it("처음 묻는 화면: 쿠키에 저장하고 홈으로, 백엔드에는 안 묻는다", async () => {
    guest = true;
    const to = await actionRedirectOf(() =>
      saveDailyLengthAction({}, form({ length: "30m", from: "start" })),
    );

    assert.equal(to, "/");
    assert.equal(guestLength, "30m");
    assert.equal(patches.length, 0);
  });

  it("from=profile 로 조작해도 쿠키에 안 넣고 로그인으로 보낸다", async () => {
    guest = true;
    const to = await actionRedirectOf(() =>
      saveDailyLengthAction({}, form({ length: "30m", from: "profile" })),
    );

    assert.equal(to, "/login?next=/profile");
    assert.equal(guestLength, null);
  });
});

// ---------------------------------------------------------------------------

describe("홈 - 하루 공부량을 물을지", () => {
  it("계정 값이 비었으면 /start/daily 로", async () => {
    token = LIVE;
    me = { id: 1, email: "a@b.c", daily_length: "" };
    assert.equal(await redirectOf(() => Home()), "/start/daily");
  });

  it("계정 값이 있으면 묻지 않는다", async () => {
    token = LIVE;
    me = { id: 1, email: "a@b.c", daily_length: "10m" };
    assert.equal(await redirectOf(() => Home()), null);
  });

  it("칸이 없는 옛 백엔드면 묻지 않는다", async () => {
    token = LIVE;
    me = { id: 1, email: "a@b.c" };
    assert.equal(await redirectOf(() => Home()), null);
  });

  it("토큰은 있는데 사람을 못 받았으면(죽은 토큰·장애) 묻지 않는다", async () => {
    token = LIVE;
    me = null;
    guest = true;
    assert.equal(await redirectOf(() => Home()), null);
  });

  it("게스트가 안 골랐으면 /start/daily 로", async () => {
    guest = true;
    assert.equal(await redirectOf(() => Home()), "/start/daily");
  });

  it("게스트가 골랐으면 묻지 않는다", async () => {
    guest = true;
    guestLength = "5m";
    assert.equal(await redirectOf(() => Home()), null);
  });

  it("게스트도 로그인도 아니면 /start 가 먼저다", async () => {
    assert.equal(await redirectOf(() => Home()), "/start");
  });
});

describe("/start/daily - 이미 고른 사람은 돌려보낸다", () => {
  it("계정 값이 있으면 홈으로", async () => {
    token = LIVE;
    me = { id: 1, email: "a@b.c", daily_length: "30m" };
    assert.equal(await redirectOf(() => StartDailyPage()), "/");
  });

  it("칸이 없는 옛 백엔드면 홈으로(홈과 같은 기준이라 고리가 안 생긴다)", async () => {
    token = LIVE;
    me = { id: 1, email: "a@b.c" };
    assert.equal(await redirectOf(() => StartDailyPage()), "/");
  });

  it("계정 값이 비었으면 묻는다", async () => {
    token = LIVE;
    me = { id: 1, email: "a@b.c", daily_length: "" };
    assert.equal(await redirectOf(() => StartDailyPage()), null);
  });

  it("게스트가 골랐으면 홈으로, 안 골랐으면 묻는다", async () => {
    guest = true;
    assert.equal(await redirectOf(() => StartDailyPage()), null);
    guestLength = "10m";
    assert.equal(await redirectOf(() => StartDailyPage()), "/");
  });

  it("게스트도 로그인도 아니면 /start 로", async () => {
    assert.equal(await redirectOf(() => StartDailyPage()), "/start");
  });

  it("죽은 토큰 + 게스트 쿠키 없음이면 /start 로(홈과 고리를 만들지 않는다)", async () => {
    token = LIVE;
    me = null;
    assert.equal(await redirectOf(() => StartDailyPage()), "/start");
    assert.equal(await redirectOf(() => Home()), "/start");
  });
});

// ---------------------------------------------------------------------------

function textOf(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  const el = node as ReactElement<{ children?: ReactNode }>;
  return textOf(el.props?.children);
}

describe("OtherLengthLink - 오늘만 다른 길이로", () => {
  const started = { length: "10m", done: false } as never;

  it("공부량이 있고 오늘 시작 전이면 ?choose=1 링크", () => {
    const el = OtherLengthLink({ length: "30m", daily: null }) as ReactElement<{
      href: string;
      children: ReactNode;
    }>;
    assert.ok(el);
    assert.equal(el.props.href, "/test/daily?choose=1");
    assert.equal(textOf(el), "하루 30분 · 오늘만 다른 길이로");
  });

  it("오늘 시작했으면 그리지 않는다", () => {
    assert.equal(OtherLengthLink({ length: "30m", daily: started }), null);
  });

  for (const length of ["", undefined, "99m"]) {
    it(`공부량이 ${JSON.stringify(length)} 이면 그리지 않는다`, () => {
      assert.equal(OtherLengthLink({ length, daily: null }), null);
    });
  }
});

// ---------------------------------------------------------------------------

/** 트리에서 type 이 같은 첫 요소. */
function findEl(node: ReactNode, type: unknown): ReactElement<Record<string, unknown>> | null {
  if (node == null || typeof node !== "object") return null;
  if (Array.isArray(node)) {
    for (const one of node) {
      const hit = findEl(one, type);
      if (hit) return hit;
    }
    return null;
  }
  const el = node as ReactElement<{ children?: ReactNode }>;
  if (el.type === type) return el as ReactElement<Record<string, unknown>>;
  return findEl(el.props?.children, type);
}

describe("/test/daily - ?choose=1 이면 고르는 화면", () => {
  async function chooseProp(params?: Record<string, string | string[]>) {
    token = LIVE;
    const tree = await DailyPage(
      params === undefined ? {} : { searchParams: Promise.resolve(params) },
    );
    const board = findEl(tree as ReactNode, DailyStudyBoard);
    assert.ok(board, "DailyStudyBoard 를 못 찾았다");
    return board.props.choose;
  }

  it("?choose=1 이면 choose=true", async () => {
    assert.equal(await chooseProp({ choose: "1" }), true);
  });

  const cases: (Record<string, string | string[]> | undefined)[] = [
    undefined,
    {},
    { choose: "0" },
    { choose: "true" },
    { choose: ["1", "1"] },
  ];
  for (const params of cases) {
    it(`${JSON.stringify(params)} 이면 저장한 길이로 바로 시작(choose=false)`, async () => {
      assert.equal(await chooseProp(params), false);
    });
  }
});
