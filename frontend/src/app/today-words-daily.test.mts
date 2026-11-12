/**
 * 홈의 오늘의 단어가 오늘 일일공부 단어인가(사용자 결정 11-12, 안 A).
 *
 * 실행: cd frontend && npm test
 *
 * 로그인한 사람은 일일공부 상태(GET /api/learning/daily/)가 실어 주는
 * today_words 를 오늘의 단어로 그린다. 시작 전이면 서버가 미리 뽑은 첫 묶음,
 * 시작했으면 오늘 배운 단어다. 그것이 없으면(게스트, 옛 백엔드, 실패) 날짜로
 * 고른 단어로 떨어지고, 홈은 어떤 경우에도 뜬다.
 *
 * 홈에서 연 단어 상세의 이전 / n / 다음 줄도 같은 묶음을 써야 한다. 홈이 그
 * 순서를 주소에 실어 주고(routes.todayWord), 상세는 서버에 다시 묻지 않는다.
 * 다른 묶음을 쓰면 홈에서 누른 단어가 상세에서 "묶음에 없음" 이 되어 줄이
 * 사라진다.
 *
 * 백엔드는 fetch 대역이다. 보려는 것은 화면이 받은 값으로 무엇을 그리고
 * 무엇을 부르는가다.
 */
import assert from "node:assert/strict";
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

/** 쿠키의 토큰. null 이면 게스트. */
let cookie: string | null = null;

mock.module("@/lib/session", {
  namedExports: {
    getToken: async () => cookie,
    getCurrentUser: async () =>
      cookie
        ? {
            id: 1,
            email: "member@example.com",
            name: "회원",
            daily_length: "10m",
            avatar_display: { type: "preset", key: "a1" },
          }
        : null,
    isGuestChosen: async () => true,
    getGuestDailyLength: async () => "10m",
  },
});

// ---- 가짜 백엔드 ------------------------------------------------------------

const card = (id: number) => ({
  id,
  term: `mine-${id}`,
  pronunciation: "",
  reading: "",
  meaning: `내 뜻-${id}`,
  description: "",
  example: "",
  example_translation: "",
  category_label: "",
});

const listed = (id: number) => ({
  id,
  term: `date-${id}`,
  pronunciation: "",
  reading: "",
  meaning: `날짜 뜻-${id}`,
  difficulty: 1,
  difficulty_label: "쉬움",
});

const detail = (id: number) => ({
  ...listed(id),
  reading_note: "",
  category: "devops",
  category_label: "배포",
  is_exam: false,
  exam_subject: "",
  exam_subject_label: "",
  description: "",
  example: "",
  example_translation: "",
  aliases: "",
});

const DATE_IDS = [901, 902, 903];

/** 일일공부 상태 응답. undefined 면 today_words 칸이 없는 옛 백엔드다. */
let todayWords: ReturnType<typeof card>[] | undefined;
let dailyStatus: 200 | 500 = 200;
let paths: string[] = [];

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request) => {
  const url = new URL(String(input));
  paths.push(url.pathname);
  if (url.pathname === "/api/learning/daily/") {
    if (dailyStatus !== 200) return json(dailyStatus, { detail: "서버 오류" });
    return json(200, {
      lengths: [],
      today: null,
      daily_length: "10m",
      token: null,
      question: null,
      learning: [],
      ...(todayWords === undefined ? {} : { today_words: todayWords }),
    });
  }
  if (url.pathname.startsWith("/api/learning/review")) {
    return json(200, { count: 0 });
  }
  const one = url.pathname.match(/^\/api\/vocab\/words\/(\d+)\/$/);
  if (one) return json(200, detail(Number(one[1])));
  if (url.pathname === "/api/vocab/words/") {
    return json(200, {
      count: DATE_IDS.length,
      next: null,
      previous: null,
      results: DATE_IDS.map(listed),
    });
  }
  throw new Error(`대역에 없는 요청: ${url}`);
}) as typeof fetch;

const realError = console.error;
let logged: unknown[] = [];

after(() => {
  globalThis.fetch = realFetch;
  console.error = realError;
});

const { renderToStaticMarkup } = await import("react-dom/server");
const Home = (await import("./page")).default;
const WordDetailPage = (await import("./learn/words/[id]/page")).default;
const { pickTodayWords } = await import("@/lib/api/daily");

beforeEach(() => {
  cookie = null;
  todayWords = undefined;
  dailyStatus = 200;
  paths = [];
  logged = [];
  console.error = (message: unknown) => {
    logged.push(message);
  };
});

const listCalls = () => paths.filter((p) => p === "/api/vocab/words/").length;

/** 큰 카드의 단어 이름. */
const bigWord = (html: string) => html.match(/id="daily-word"[^>]*>([^<]*)</)?.[1];

/** 홈에서 상세로 가는 링크(오늘의 단어 묶음): [단어 id, 주소에 실린 순서]. */
const todayLinks = (html: string) =>
  [...html.matchAll(/href="\/learn\/words\/(\d+)\?today=([\d-]+)"/g)].map(
    (m) => [Number(m[1]), m[2]] as const,
  );

describe("pickTodayWords", () => {
  it("내 단어가 있으면 그것을 홈 개수(7)까지만 쓰고 날짜 목록은 안 부른다", async () => {
    const mine = Array.from({ length: 9 }, (_, i) => card(i + 1));
    const got = await pickTodayWords(mine);
    assert.deepEqual(
      got.map((w) => w.id),
      [1, 2, 3, 4, 5, 6, 7],
    );
    assert.equal(listCalls(), 0);
  });

  it("두 개뿐이면(5분 첫 묶음) 두 개 그대로다 - 날짜 단어로 채우지 않는다", async () => {
    const got = await pickTodayWords([card(1), card(2)]);
    assert.deepEqual(
      got.map((w) => w.id),
      [1, 2],
    );
    assert.equal(listCalls(), 0);
  });

  for (const own of [[], undefined, null]) {
    it(`내 단어가 ${JSON.stringify(own)} 이면 날짜로 고른 단어다`, async () => {
      const got = await pickTodayWords(own);
      assert.ok(got.length > 0);
      assert.ok(got.every((w) => DATE_IDS.includes(w.id)));
    });
  }
});

describe("홈의 오늘의 단어", () => {
  it("로그인했으면 일일공부 단어를 그린다 - 큰 카드는 첫 단어, 아래는 나머지", async () => {
    cookie = "member-token";
    todayWords = [card(11), card(12), card(13), card(14), card(15)];
    const html = renderToStaticMarkup(await Home());

    assert.equal(bigWord(html), "mine-11");
    // 큰 카드의 "더 보기" 도 오늘의 단어 묶음 링크다(첫 번째). 링크마다 홈이
    // 보여준 순서를 그대로 싣는다 - 상세가 그 순서로 넘긴다.
    const links = todayLinks(html);
    assert.deepEqual([...new Set(links.map(([id]) => id))], [11, 12, 13, 14, 15]);
    assert.ok(links.every(([, order]) => order === "11-12-13-14-15"), JSON.stringify(links));
    assert.equal(listCalls(), 0, "내 단어가 있으면 날짜 목록을 부르지 않는다");
    // 일일공부 상태는 한 번만 묻는다(카드와 오늘의 단어가 같은 응답).
    assert.equal(paths.filter((p) => p === "/api/learning/daily/").length, 1);
  });

  it("옛 백엔드(today_words 칸이 없음)면 날짜로 고른 단어로 뜬다", async () => {
    cookie = "member-token";
    const html = renderToStaticMarkup(await Home());
    assert.match(bigWord(html) ?? "", /^date-/);
    assert.ok(listCalls() >= 1);
  });

  it("일일공부 상태를 못 받으면(500) 날짜로 고른 단어로 뜨고 로그를 남긴다", async () => {
    cookie = "member-token";
    dailyStatus = 500;
    const html = renderToStaticMarkup(await Home());
    assert.match(bigWord(html) ?? "", /^date-/);
    assert.ok(logged.length >= 1);
  });

  it("게스트는 일일공부를 묻지 않고 날짜로 고른 단어다", async () => {
    const html = renderToStaticMarkup(await Home());
    assert.match(bigWord(html) ?? "", /^date-/);
    assert.equal(paths.filter((p) => p.startsWith("/api/learning/")).length, 0);
  });
});

describe("홈에서 연 단어 상세", () => {
  async function render(id: number, today: string) {
    const element = await WordDetailPage({
      params: Promise.resolve({ id: String(id) }),
      searchParams: Promise.resolve({ today }),
    });
    return renderToStaticMarkup(element);
  }

  const position = (html: string) =>
    html.match(/tabular-nums[^>]*>([\s\S]*?)<\/p>/)?.[1].replace(/<!-- -->/g, "");

  it("로그인했어도 주소에 실린 순서로 넘기고 서버에 다시 묻지 않는다", async () => {
    cookie = "member-token";
    const html = await render(12, "11-12-13");
    assert.equal(position(html), "2 / 3");
    assert.deepEqual(
      todayLinks(html).map(([id]) => id),
      [11, 13],
    );
    assert.equal(paths.filter((p) => p.startsWith("/api/learning/")).length, 0);
    assert.equal(listCalls(), 0);
  });
});
