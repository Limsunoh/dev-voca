/**
 * 화면이 쿠키에 남은 죽은 토큰을 어떻게 다루는지.
 *
 * 실행: cd frontend && npm test
 *
 * 세션은 "server-only" 라 대역으로 바꾼다. getToken 은 쿠키 값(cookie)을
 * 돌려준다. 가짜 백엔드는 실제 DRF 처럼 무효 토큰(DEAD)이 실리면 어느 API 든
 * 401 을 준다. withTokenOrGuest 대역은 실제와 같은 규칙(401 이면 토큰 없이 한
 * 번 더)으로 돌고, 받은 forget 값을 적어 둔다 - 함수 자체는
 * session-stale-token.test.mts 가 실제 코드로 본다. 여기서 보는 것은 화면이
 * 무엇을 넘기고 결과를 어떻게 쓰는지다.
 *
 * 원칙: 평소처럼 쿠키의 토큰을 싣고, 서버가 거절(401)했을 때만 처리한다.
 * 어느 화면도 로그인 확인(/me)을 먼저 해서 토큰을 고르지 않는다.
 *
 * 계약.
 *   1. 한 판(/test/round): 쿠키에 토큰이 있는지만 본다(isGuest = !getToken()).
 *      죽은 토큰이면 isGuest 가 false 인 채 그려지고, 결과 화면에서 서버가 준
 *      guest 로 바로잡는다(exit-destinations.test.mts 가 본다).
 *   2. 순위표(BoardScreen): 쿠키 토큰을 withTokenOrGuest(forget: false)로
 *      싣는다. 거절되면 토큰 없이 다시 받아 isGuest. 쿠키는 안 지운다(화면을
 *      그리는 중이라 못 지운다).
 *   3. 일일공부·복습: 쿠키 토큰(getToken)으로 바로 묻는다. 토큰이 없거나
 *      백엔드가 401 이면 /login?next=... 로 보낸다. 다른 오류는 실패 화면.
 *   4. 오늘 카드(loadToday): 토큰이 없으면 묻지 않고 둘 다 null. 실패하면
 *      null 로 바꾸되 401 은 로그를 안 남기고 그 밖의 실패만 남긴다. 홈은
 *      getToken 을 그대로 넘긴다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";
import type { ReactElement, ReactNode } from "react";

import { ApiError } from "../../lib/api/client";

class Redirect extends Error {
  constructor(readonly to: string) {
    super("NEXT_REDIRECT");
  }
}

mock.module("next/navigation", {
  namedExports: {
    redirect: (to: string) => {
      throw new Redirect(to);
    },
    notFound: () => {
      throw new Error("notFound");
    },
    useRouter: () => ({ push() {}, replace() {}, refresh() {} }),
    usePathname: () => "/",
    useSearchParams: () => new URLSearchParams(),
  },
});

const DEAD = "dead-token";
const LIVE = "live-token";
/** 쿠키에 든 토큰. */
let cookie: string | null = null;
let forgets: boolean[] = [];

mock.module("@/lib/session", {
  namedExports: {
    getToken: async () => cookie,
    getCurrentUser: async () => (cookie === LIVE ? { id: 1, email: "a@b.c" } : null),
    isGuestChosen: async () => true,
    forgetToken: async () => {
      throw new Error("화면을 그리는 중에는 쿠키를 지울 수 없다");
    },
    async withTokenOrGuest<T>(
      token: string | null,
      call: (token?: string) => Promise<T>,
      { forget }: { forget: boolean },
    ) {
      forgets.push(forget);
      if (!token) return { value: await call(undefined), token: null };
      try {
        return { value: await call(token), token };
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401) throw error;
        if (forget) throw new Error("화면을 그리는 중에는 쿠키를 지울 수 없다");
        return { value: await call(undefined), token: null };
      }
    },
  },
});

// ---- 가짜 백엔드 ------------------------------------------------------------

let calls: { path: string; auth: string | null }[] = [];
/** 토큰 문제가 아닌 백엔드 장애. */
let backend: "ok" | 500 | "down" = "ok";
const BODY = { kind: "weekly", rows: [], me: null, count: 0, results: [] };

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
  const url = new URL(String(input));
  const auth = new Headers(init?.headers).get("Authorization");
  calls.push({ path: url.pathname, auth });
  if (backend === "down") throw new TypeError("fetch failed");
  if (backend === 500) return json(500, { detail: "서버 오류" });
  if (auth === `Token ${DEAD}`) {
    return json(401, { detail: "토큰이 유효하지 않습니다." });
  }
  return json(200, BODY);
}) as typeof fetch;

/** console.error 로 남긴 첫 인자(문구)들. */
let logged: unknown[] = [];
const realError = console.error;
console.error = (message: unknown) => {
  logged.push(message);
};

after(() => {
  globalThis.fetch = realFetch;
  console.error = realError;
});

const RoundPage = (await import("./round/page")).default;
const DailyPage = (await import("./daily/page")).default;
const ReviewPage = (await import("./review/page")).default;
const Home = (await import("../page")).default;
const { BoardScreen } = await import("../board/BoardScreen");
const { loadToday } = await import("../../components/TodayCards");

beforeEach(() => {
  calls = [];
  cookie = null;
  forgets = [];
  backend = "ok";
  logged = [];
});

/** 죽은 토큰이 쿠키에 남은 상태. 서버는 받지 않는다. */
function deadCookie() {
  cookie = DEAD;
}

function liveCookie() {
  cookie = LIVE;
}

/** 트리에서 isGuest 를 받은 첫 요소의 그 값. 렌더하지 않고 props 만 본다. */
function findIsGuest(node: ReactNode): boolean | undefined {
  if (!node || typeof node !== "object") return undefined;
  if (Array.isArray(node)) {
    for (const child of node) {
      const found = findIsGuest(child);
      if (found !== undefined) return found;
    }
    return undefined;
  }
  const props = (node as ReactElement<Record<string, unknown>>).props ?? {};
  if ("isGuest" in props) return props.isGuest as boolean;
  return findIsGuest(props.children as ReactNode);
}

/** 트리의 글자를 모두 이어 붙인다(렌더하지 않고 children 만 따라간다). */
function textOf(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  const props = (node as ReactElement<Record<string, unknown>>).props ?? {};
  return textOf(props.children as ReactNode);
}

// ---------------------------------------------------------------------------

describe("한 판 화면", () => {
  it("쿠키에 토큰이 있으면 백엔드에 묻지 않고 로그인한 화면으로 연다", async () => {
    deadCookie();
    assert.equal(findIsGuest(await RoundPage()), false);
    assert.equal(calls.length, 0, "화면을 열 때 로그인 확인 왕복이 없어야 한다");
  });

  it("쿠키에 토큰이 없으면 게스트로 연다", async () => {
    assert.equal(findIsGuest(await RoundPage()), true);
  });
});

describe("순위표", () => {
  it("죽은 토큰은 거절된 뒤 토큰 없이 다시 받아 게스트로 그리고 쿠키는 안 건드린다", async () => {
    deadCookie();
    const tree = await BoardScreen({ kind: "weekly" });
    assert.equal(findIsGuest(tree), true, "순위표가 떠야 한다(실패 화면이 아니라)");
    assert.deepEqual(
      calls.map((c) => c.auth),
      [`Token ${DEAD}`, null],
    );
    assert.deepEqual(forgets, [false]);
  });

  it("살아 있는 토큰은 한 번만 싣고 로그인한 화면이다", async () => {
    liveCookie();
    const tree = await BoardScreen({ kind: "weekly" });
    assert.equal(findIsGuest(tree), false);
    assert.deepEqual(
      calls.map((c) => c.auth),
      [`Token ${LIVE}`],
    );
  });

  it("토큰이 없으면 토큰 없이 받아 게스트로 그린다", async () => {
    const tree = await BoardScreen({ kind: "weekly" });
    assert.equal(findIsGuest(tree), true);
    assert.deepEqual(
      calls.map((c) => c.auth),
      [null],
    );
  });

  for (const mode of [500, "down"] as const) {
    it(`백엔드가 ${mode} 면 게스트로 다시 받지 않고 실패 화면이다`, async () => {
      liveCookie();
      backend = mode;
      const tree = await BoardScreen({ kind: "weekly" });
      assert.equal(findIsGuest(tree), undefined);
      assert.match(textOf(tree), /순위표를 불러오지 못했습니다/);
      assert.equal(calls.length, 1);
    });
  }
});

for (const [name, Page, next, failText] of [
  ["일일공부", DailyPage, "/test/daily", /일일공부를 불러오지 못했습니다/],
  ["복습", ReviewPage, "/test/review", /복습을 불러오지 못했습니다/],
] as const) {
  describe(`${name} 화면`, () => {
    const toLogin = (error: unknown) => {
      assert.ok(error instanceof Redirect, String(error));
      assert.equal(error.to, `/login?next=${next}`);
      return true;
    };

    it("쿠키에 토큰이 없으면 로그인 화면으로 보내고 백엔드에 묻지 않는다", async () => {
      await assert.rejects(Page(), toLogin);
      assert.equal(calls.length, 0);
    });

    it("백엔드가 토큰을 거절하면(401) 로그인 화면으로 보낸다", async () => {
      deadCookie();
      await assert.rejects(Page(), toLogin);
      assert.ok(calls.length >= 1, "쿠키 토큰으로 바로 물어야 한다");
      assert.ok(calls.every((c) => c.auth === `Token ${DEAD}`));
    });

    it("쿠키 토큰으로 바로 묻고 정상 화면을 그린다", async () => {
      liveCookie();
      const tree = await Page();
      assert.ok(calls.length >= 1);
      assert.ok(calls.every((c) => c.auth === `Token ${LIVE}`));
      assert.doesNotMatch(textOf(tree), failText);
    });

    for (const [mode, offline] of [
      [500, false],
      ["down", true],
    ] as const) {
      it(`백엔드가 ${mode} 면 로그인 화면이 아니라 실패 화면이다`, async () => {
        liveCookie();
        backend = mode;
        const tree = await Page();
        const text = textOf(tree);
        assert.match(text, failText);
        assert.equal(/서버에 연결할 수 없습니다/.test(text), offline);
      });
    }
  });
}

const isToday = (path: string) =>
  path.startsWith("/api/learning/daily") || path.startsWith("/api/learning/review");

describe("오늘 카드(loadToday)", () => {
  it("토큰이 없으면 묻지 않고 둘 다 null", async () => {
    assert.deepEqual(await loadToday(null), { daily: null, due: null });
    assert.equal(calls.length, 0);
  });

  it("서버가 토큰을 거절하면(401) 둘 다 null 이고 로그를 안 남긴다", async () => {
    assert.deepEqual(await loadToday(DEAD), { daily: null, due: null });
    assert.equal(calls.filter((c) => isToday(c.path)).length, 2);
    assert.deepEqual(logged, [], "죽은 토큰은 오류가 아니다 - 홈을 열 때마다 두 줄씩 쌓인다");
  });

  for (const mode of [500, "down"] as const) {
    it(`백엔드가 ${mode} 면 둘 다 null 이고 두 실패를 로그에 남긴다`, async () => {
      backend = mode;
      assert.deepEqual(await loadToday(LIVE), { daily: null, due: null });
      assert.equal(logged.length, 2, JSON.stringify(logged));
    });
  }
});

describe("홈", () => {
  it("쿠키의 토큰을 오늘 카드 두 조회에 그대로 싣는다", async () => {
    liveCookie();
    await Home();
    const today = calls.filter((c) => isToday(c.path));
    assert.equal(today.length, 2, JSON.stringify(calls));
    assert.ok(today.every((c) => c.auth === `Token ${LIVE}`));
  });

  it("죽은 토큰이어도 홈이 뜨고 오늘 카드의 401 은 로그에 안 남는다", async () => {
    deadCookie();
    await Home();
    const today = calls.filter((c) => isToday(c.path));
    assert.equal(today.length, 2, JSON.stringify(calls));
    assert.ok(today.every((c) => c.auth === `Token ${DEAD}`));
    assert.deepEqual(logged, []);
  });
});
