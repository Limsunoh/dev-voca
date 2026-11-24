/**
 * 로그인 쿠키는 있는데 백엔드가 답하지 않을 때(getLoginState 의 unreachable) 홈과 내정보가
 * 멀쩡한 로그인을 첫 화면·로그인 화면으로 보내지 않는지 깨뜨려 본다.
 *
 * 실행: cd frontend && npm test
 *
 * lib/session.ts 는 대역 없이 실제 코드로 돌린다. 쿠키(next/headers)와 백엔드(fetch)만
 * 가짜다. 그래야 "401 이 아닌 실패" 를 session 이 어떻게 가르는지까지 같이 본다.
 *
 * 계약.
 *   1. 토큰이 있고 /me 가 연결 실패·시간 초과·5xx·403·이상한 본문이면 홈은 "/" 로,
 *      내정보는 "/profile" 로 다시 시도하는 화면(LoginCheckFailed)을 그린다. 어디로도
 *      보내지 않는다. 게스트 쿠키가 없어도 같다.
 *   2. /me 가 401 이면 예전 그대로다. 홈은 게스트 쿠키가 없으면 /start, 내정보는
 *      /login?next=/profile.
 *   3. 토큰이 없으면 백엔드에 묻지 않는다(unreachable 이 아니다).
 *   4. 홈은 일일공부 상태·복습 요청을 /me 답을 기다리지 않고 띄운다. 다시 시도 화면으로
 *      끝나도 남은 요청이 처리되지 않은 거부로 새지 않는다.
 *   5. 내정보는 다시 시도 화면일 때 순위·기록을 부르지 않는다.
 *   6. 로그인·가입·첫 화면·공부량 화면은 로그인을 확인하지 못하면 홈("/")으로 보낸다.
 *      거기 남으면 "둘러보기" 를 눌러 멀쩡한 로그인을 지운다. 홈이 다시 시도 화면을 그리므로
 *      보내고 받는 사이에 고리가 생기지 않는다. 401 이면 예전처럼 그 화면을 그린다.
 *
 * 하네스: session.ts 의 `import "server-only"` 는 CJS 로더에서 빈 객체로 돌려준다
 * (session-stale-token.test.mts 와 같은 우회). redirect 는 던져서 어디로 보냈는지 본다.
 */
import assert from "node:assert/strict";
import Module from "node:module";
import { after, beforeEach, describe, it, mock } from "node:test";

mock.module("next/navigation", {
  namedExports: {
    redirect: (to: string) => {
      throw new Error(`redirect ${to}`);
    },
    notFound: () => {
      throw new Error("notFound");
    },
    useRouter: () => ({ push() {}, replace() {}, refresh() {}, back() {}, prefetch() {} }),
    usePathname: () => "/",
    useSearchParams: () => new URLSearchParams(),
  },
});

const jar = new Map<string, string>();
mock.module("next/headers", {
  namedExports: {
    async cookies() {
      return {
        get: (name: string) => (jar.has(name) ? { name, value: jar.get(name) } : undefined),
        set: (name: string, value: string) => void jar.set(name, value),
        delete: (name: string) => void jar.delete(name),
      };
    },
    async headers() {
      return new Headers();
    },
  },
});

mock.module("next/cache", {
  namedExports: { revalidatePath() {}, revalidateTag() {} },
});

const loader = Module as unknown as { _load: (request: string, ...rest: unknown[]) => unknown };
const realLoad = loader._load;
loader._load = function (this: unknown, request: string, ...rest: unknown[]) {
  if (request === "server-only") return {};
  return realLoad.call(this, request, ...rest);
};
// 첫 화면(start/page.tsx)이 로고 그림을 import 한다. 노드는 그림을 못 읽으니 크기만 둔다.
(Module as unknown as { _extensions: Record<string, (m: { exports: unknown }) => void> })._extensions[".webp"] =
  (m) => void (m.exports = { src: "/logo.webp", width: 1, height: 1 });

// ---- 가짜 백엔드 ------------------------------------------------------------

/** 백엔드 상태. "ok" 면 정상, 나머지는 모든 요청이 그렇게 실패한다. */
type Backend = "ok" | "down" | "timeout" | 500 | 502 | 503 | 403 | 429 | "html" | 401;
let backend: Backend = "ok";
/** /me 만 따로 실패시킬 때. null 이면 backend 를 따른다. */
let meOnly: Backend | null = null;
/** /me 답을 붙잡아 두는 문. null 이면 바로 답한다. */
let meGate: Promise<void> | null = null;
let starts: string[] = [];

const ME = "/api/accounts/me/";
const DAILY = "/api/learning/daily/";

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const member = {
  id: 1,
  email: "member@example.com",
  display_name: "회원",
  name: "회원",
  daily_length: "10m",
  avatar: "",
  avatar_display: { type: "preset", key: "a1" },
};

function fail(mode: Exclude<Backend, "ok">): Response {
  if (mode === "down") throw new TypeError("fetch failed");
  if (mode === "timeout") throw new DOMException("The operation was aborted due to timeout", "TimeoutError");
  if (mode === "html") return new Response("<html>bad gateway</html>", { status: 200 });
  return json(mode, { detail: "x" });
}

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request) => {
  const url = new URL(String(input));
  const path = url.pathname;
  starts.push(path);
  if (path === ME) {
    if (meGate) await meGate;
    const mode = meOnly ?? backend;
    return mode === "ok" ? json(200, member) : fail(mode);
  }
  if (backend !== "ok") return fail(backend);
  if (path === DAILY) {
    return json(200, { lengths: [], today: null, daily_length: "10m", today_words: [] });
  }
  if (path.startsWith("/api/learning/review")) return json(200, { due: 0, round_size: 10, streak_to_clear: 2 });
  if (path === "/api/vocab/words/") return json(200, { count: 0, next: null, previous: null, results: [] });
  return json(200, {});
}) as typeof fetch;

const realError = console.error;
console.error = () => {};

const leaked: unknown[] = [];
const onLeak = (reason: unknown) => void leaked.push(reason);
process.on("unhandledRejection", onLeak);

after(() => {
  globalThis.fetch = realFetch;
  console.error = realError;
  loader._load = realLoad;
  process.off("unhandledRejection", onLeak);
});

const { renderToStaticMarkup } = await import("react-dom/server");
const Home = (await import("./page")).default;
const ProfilePage = (await import("./profile/page")).default;
const LoginPage = (await import("./(auth)/login/page")).default;
const SignupPage = (await import("./(auth)/signup/page")).default;
const StartPage = (await import("./start/page")).default;
const DailyLengthStartPage = (await import("./start/daily/page")).default;

const noParams = { searchParams: Promise.resolve({}) };
/** 로그인을 확인하지 못하면 홈으로 보내야 하는 화면들. 남기면 "둘러보기" 로 로그인을 지운다. */
const ENTRY_PAGES: [string, () => Promise<unknown>][] = [
  ["/login", () => LoginPage(noParams as never)],
  ["/signup", () => SignupPage(noParams as never)],
  ["/start", () => StartPage(noParams as never)],
  ["/start/daily", () => DailyLengthStartPage()],
];

// ---- 도구 -------------------------------------------------------------------

const TOKEN = "a".repeat(40);

type Outcome = { redirect: string } | { html: string };

async function open(page: () => Promise<unknown>): Promise<Outcome> {
  try {
    return { html: renderToStaticMarkup((await page()) as never) };
  } catch (error) {
    const match = error instanceof Error && error.message.match(/^redirect (.*)$/);
    if (match) return { redirect: match[1] };
    throw error;
  }
}

/** 처리되지 않은 거부가 잡힐 틈을 준다. */
const settle = () => new Promise((resolve) => setImmediate(resolve));

function assertRetryScreen(outcome: Outcome, retry: string) {
  assert.ok("html" in outcome, `보냈다: ${JSON.stringify(outcome)}`);
  const html = outcome.html;
  assert.ok(html.includes("로그인을 확인하지 못했습니다"), "다시 시도 화면이 아니다");
  assert.ok(html.includes(`href="${retry}"`), `다시 시도 링크가 ${retry} 가 아니다`);
  assert.ok(html.includes("다시 시도"));
}

function signIn() {
  jar.set("devvoca_token", `${TOKEN}.${Math.floor(Date.now() / 1000)}`);
}

beforeEach(() => {
  jar.clear();
  backend = "ok";
  meOnly = null;
  meGate = null;
  starts = [];
  leaked.length = 0;
});

const UNREACHABLE: Backend[] = ["down", "timeout", 500, 502, 503, 403, 429, "html"];

// ---- 홈 ---------------------------------------------------------------------

describe("홈 - 백엔드가 답하지 않으면 다시 시도 화면", () => {
  for (const mode of UNREACHABLE) {
    it(`${mode}: 게스트 쿠키가 없어도 /start 로 안 보낸다`, async () => {
      signIn();
      backend = mode;
      assertRetryScreen(await open(Home), "/");
      await settle();
      assert.deepEqual(leaked, []);
    });
  }

  it("게스트 쿠키·공부량 쿠키가 있어도 게스트 홈이 아니라 다시 시도 화면이다", async () => {
    signIn();
    jar.set("devvoca_guest", "1");
    jar.set("devvoca_daily_length", "10m");
    backend = "down";
    assertRetryScreen(await open(Home), "/");
  });

  it("/me 만 500 이고 나머지가 살아 있어도 다시 시도 화면이다", async () => {
    signIn();
    meOnly = 500;
    assertRetryScreen(await open(Home), "/");
  });

  it("다시 시도 화면을 그릴 때 쿠키를 지우지 않는다", async () => {
    signIn();
    jar.set("devvoca_guest", "1");
    backend = "down";
    await open(Home);
    assert.ok(jar.has("devvoca_token"));
    assert.ok(jar.has("devvoca_guest"));
  });
});

describe("홈 - 401 과 토큰 없음은 예전 그대로", () => {
  it("/me 401 + 게스트 쿠키 없음: /start", async () => {
    signIn();
    meOnly = 401;
    assert.deepEqual(await open(Home), { redirect: "/start" });
  });

  it("/me 401 + 게스트 + 공부량: 게스트 홈을 그린다(다시 시도 화면 아님)", async () => {
    signIn();
    meOnly = 401;
    jar.set("devvoca_guest", "1");
    jar.set("devvoca_daily_length", "10m");
    const outcome = await open(Home);
    assert.ok("html" in outcome, JSON.stringify(outcome));
    assert.ok(!outcome.html.includes("로그인을 확인하지 못했습니다"));
  });

  it("토큰 없음 + 게스트 없음: /start 이고 /me 를 묻지 않는다", async () => {
    assert.deepEqual(await open(Home), { redirect: "/start" });
    assert.ok(!starts.includes(ME));
  });

  it("토큰 없음 + 백엔드 꺼짐 + 게스트 + 공부량: 다시 시도 화면이 아니다", async () => {
    backend = "down";
    jar.set("devvoca_guest", "1");
    jar.set("devvoca_daily_length", "5m");
    const outcome = await open(Home);
    assert.ok("html" in outcome, JSON.stringify(outcome));
    assert.ok(!outcome.html.includes("로그인을 확인하지 못했습니다"));
  });

  it("정상 회원은 홈을 그린다", async () => {
    signIn();
    const outcome = await open(Home);
    assert.ok("html" in outcome, JSON.stringify(outcome));
    assert.ok(!outcome.html.includes("로그인을 확인하지 못했습니다"));
  });
});

describe("홈 - /me 와 일일공부 상태를 동시에 띄운다", () => {
  it("/me 답이 오기 전에 일일공부 상태·복습 요청이 이미 나갔다", async () => {
    signIn();
    let release!: () => void;
    meGate = new Promise((resolve) => (release = resolve));

    const pending = open(Home);
    for (let i = 0; i < 20; i += 1) await settle();
    const before = [...starts];
    release();
    await pending;

    assert.ok(before.includes(ME), `/me 를 아직 안 불렀다: ${before}`);
    assert.ok(before.includes(DAILY), `/me 를 기다린 뒤에야 일일공부 상태를 불렀다: ${before}`);
    assert.ok(before.some((p) => p.startsWith("/api/learning/review")), `복습 요청이 늦다: ${before}`);
  });

  it("일일공부 상태는 한 번만 묻는다", async () => {
    signIn();
    await open(Home);
    assert.equal(starts.filter((p) => p === DAILY).length, 1);
    assert.equal(starts.filter((p) => p === ME).length, 1);
  });
});

// ---- 내정보 -----------------------------------------------------------------

describe("내정보 - 백엔드가 답하지 않으면 다시 시도 화면", () => {
  for (const mode of UNREACHABLE) {
    it(`${mode}: 로그인 화면으로 안 보내고 순위·기록을 부르지 않는다`, async () => {
      signIn();
      backend = mode;
      assertRetryScreen(await open(ProfilePage), "/profile");
      assert.deepEqual(starts, [ME]);
    });
  }
});

describe("내정보 - 401 과 토큰 없음은 예전 그대로", () => {
  it("/me 401: /login?next=/profile", async () => {
    signIn();
    meOnly = 401;
    assert.deepEqual(await open(ProfilePage), { redirect: "/login?next=/profile" });
  });

  it("토큰 없음: /login?next=/profile 이고 백엔드에 묻지 않는다", async () => {
    backend = "down";
    assert.deepEqual(await open(ProfilePage), { redirect: "/login?next=/profile" });
    assert.deepEqual(starts, []);
  });

  it("깨진 토큰 쿠키(.123)는 토큰 없음과 같다", async () => {
    jar.set("devvoca_token", ".123");
    backend = "down";
    assert.deepEqual(await open(ProfilePage), { redirect: "/login?next=/profile" });
    assert.deepEqual(await open(Home), { redirect: "/start" });
  });
});

// ---- 로그인·가입·첫 화면·공부량 화면 --------------------------------------------

describe("진입 화면 - 로그인을 확인하지 못하면 홈으로", () => {
  for (const [name, page] of ENTRY_PAGES) {
    for (const mode of ["down", 500, "timeout"] as Backend[]) {
      it(`${name} ${mode}: "/" 로 보내고, 홈은 다시 시도 화면이다(고리 없음)`, async () => {
        signIn();
        backend = mode;
        assert.deepEqual(await open(page), { redirect: "/" });
        assertRetryScreen(await open(Home), "/");
      });
    }

    it(`${name} /me 401 + 게스트 아님: 홈으로 보내지 않는다`, async () => {
      signIn();
      meOnly = 401;
      const outcome = await open(page);
      assert.notDeepEqual(outcome, { redirect: "/" });
    });
  }
});
