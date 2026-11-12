/**
 * 홈의 오늘의 단어와 거기서 연 단어 상세를 깨뜨려 본다.
 *
 * 실행: cd frontend && npm test
 *
 * today-words-daily.test.mts 가 정한 동작의 바깥을 본다.
 *
 * - 주소의 today 값은 누구나 손으로 고칠 수 있다. 긴 값, 0, 음수, 중복,
 *   배열, 예전 today=1 이 와도 상세가 깨지지 않고 넘기는 줄이 엉뚱한 곳을
 *   가리키지 않는다.
 * - 홈이 링크에 실은 순서로 상세에서 "다음" 만 눌러 끝까지 가면 홈에서 본
 *   순서 그대로여야 한다. 홈이 일곱 개로 자른 것과 상세가 받는 개수도 같다.
 * - 일일공부 상태가 401·null·빈 목록이거나 날짜 목록까지 실패해도 홈은 뜬다.
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
            daily_length: "30m",
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

/** 일일공부 상태 응답의 today_words 칸. "omit" 이면 칸이 없다. */
let todayWords: unknown = "omit";
let dailyStatus = 200;
let listStatus = 200;
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
    if (dailyStatus !== 200) return json(dailyStatus, { detail: "거절" });
    return json(200, {
      lengths: [],
      today: null,
      daily_length: "30m",
      token: null,
      question: null,
      learning: [],
      ...(todayWords === "omit" ? {} : { today_words: todayWords }),
    });
  }
  if (url.pathname.startsWith("/api/learning/review")) {
    return json(200, { count: 0 });
  }
  const one = url.pathname.match(/^\/api\/vocab\/words\/(\d+)\/$/);
  if (one) return json(200, detail(Number(one[1])));
  if (url.pathname === "/api/vocab/words/") {
    if (listStatus !== 200) return json(listStatus, { detail: "서버 오류" });
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
const { parseTodayIds, routes } = await import("@/lib/routes");
const { HOME_WORDS } = await import("@/lib/api/vocab");

beforeEach(() => {
  cookie = null;
  todayWords = "omit";
  dailyStatus = 200;
  listStatus = 200;
  paths = [];
  logged = [];
  console.error = (message: unknown) => {
    logged.push(message);
  };
});

const bigWord = (html: string) => html.match(/id="daily-word"[^>]*>([^<]*)</)?.[1];

/** 오늘의 단어 묶음 링크: [단어 id, 주소에 실린 today 값]. */
const todayLinks = (html: string) =>
  [...html.matchAll(/href="\/learn\/words\/(\d+)\?today=([^"]*)"/g)].map(
    (m) => [Number(m[1]), m[2]] as const,
  );

const position = (html: string) =>
  html.match(/tabular-nums[^>]*>([\s\S]*?)<\/p>/)?.[1].replace(/<!-- -->/g, "");

async function renderDetail(id: number, today: string | string[] | undefined) {
  const element = await WordDetailPage({
    params: Promise.resolve({ id: String(id) }),
    searchParams: Promise.resolve(today === undefined ? {} : { today }),
  });
  return renderToStaticMarkup(element);
}

/** 상세의 되돌아가기 주소. 첫 링크다. */
const backHref = (html: string) => html.match(/href="([^"]*)"/)?.[1];

describe("parseTodayIds - 주소의 today 값 남용", () => {
  const cases: [string, string | string[] | undefined, number[]][] = [
    ["없음", undefined, []],
    ["빈 문자열", "", []],
    ["0", "0", []],
    ["음수", "-3", []],
    ["0 이 섞임", "5-0-6", []],
    ["앞자리 0", "05-6", []],
    ["빈 칸", "5--6", []],
    ["끝 대시", "5-6-", []],
    ["쉼표", "5,6", []],
    ["공백", " 5-6", []],
    ["글자", "abc", []],
    ["소수", "5.5", []],
    ["11자리 수", "12345678901", []],
    ["전각 숫자", "５-６", []],
    ["중복은 하나로", "5-5-6-5", [5, 6]],
    ["예전 주소", "1", [1]],
    ["배열이면 첫 값", ["3-4", "9"], [3, 4]],
    ["빈 배열", [], []],
  ];
  for (const [name, raw, want] of cases) {
    it(`${name}: ${JSON.stringify(raw)} -> ${JSON.stringify(want)}`, () => {
      assert.deepEqual(parseTodayIds(raw, HOME_WORDS), want);
    });
  }

  it("아주 긴 값도 홈 개수에서 자르고 금방 끝난다", () => {
    const raw = Array.from({ length: 20000 }, (_, i) => i + 1).join("-");
    const began = performance.now();
    const got = parseTodayIds(raw, HOME_WORDS);
    assert.deepEqual(got, [1, 2, 3, 4, 5, 6, 7]);
    assert.ok(performance.now() - began < 200, "긴 주소에서 느려졌다");
  });

  it("거의 맞는 긴 값(끝만 틀림)에서도 정규식이 폭주하지 않는다", () => {
    const raw = `${"1-".repeat(50000)}x`;
    const began = performance.now();
    assert.deepEqual(parseTodayIds(raw, HOME_WORDS), []);
    assert.ok(performance.now() - began < 200, "역추적 폭주");
  });

  it("중복을 먼저 걷어낸 뒤 자른다 - 앞이 중복이어도 일곱 개가 찬다", () => {
    assert.deepEqual(parseTodayIds("1-1-1-1-2-3-4-5-6-7-8", HOME_WORDS), [1, 2, 3, 4, 5, 6, 7]);
  });

  it("routes.todayWord 가 만든 주소는 그대로 읽힌다", () => {
    const ids = [57, 939, 576, 720];
    const href = routes.todayWord(939, ids);
    const today = new URL(href, "http://x").searchParams.get("today") ?? "";
    assert.deepEqual(parseTodayIds(today, HOME_WORDS), ids);
  });
});

describe("홈 링크와 상세 넘기기가 끝까지 같은 순서다", () => {
  it("30분을 마친 사람(배운 단어 9개)은 앞 7개만, 상세에서 다음만 눌러도 같은 순서다", async () => {
    cookie = "member-token";
    const mine = [71, 15, 302, 8, 44, 990, 3, 600, 12];
    todayWords = mine.map(card);
    const html = renderToStaticMarkup(await Home());
    const shown = mine.slice(0, HOME_WORDS);

    assert.equal(bigWord(html), "mine-71");
    const links = todayLinks(html);
    assert.deepEqual([...new Set(links.map(([id]) => id))], shown);
    const orders = new Set(links.map(([, order]) => order));
    assert.equal(orders.size, 1, "링크마다 실린 순서가 다르다");
    const order = [...orders][0];
    assert.equal(order, shown.join("-"));

    // 첫 단어 상세에서 "다음" 만 따라간다.
    const walked: number[] = [];
    let id = shown[0];
    for (let step = 0; step < 20; step += 1) {
      walked.push(id);
      const page = await renderDetail(id, order);
      assert.equal(position(page), `${walked.length} / ${shown.length}`);
      assert.equal(backHref(page), "/", "되돌아가기가 홈이 아니다");
      const navLinks = todayLinks(page);
      assert.ok(navLinks.every(([, o]) => o === order), "넘기는 링크가 순서를 바꿨다");
      const nextId = navLinks.map(([n]) => n).find((n) => shown.indexOf(n) === walked.length);
      if (nextId === undefined) break;
      id = nextId;
    }
    assert.deepEqual(walked, shown);
    assert.equal(
      paths.filter((p) => p === "/api/learning/daily/").length,
      1,
      "상세가 일일공부 상태를 다시 물었다",
    );
  });

  it("홈이 자른 뒤쪽 단어(8번째)를 주소로 열면 줄 없이 홈으로 돌아간다", async () => {
    const page = await renderDetail(600, "71-15-302-8-44-990-3");
    assert.equal(position(page), undefined);
    assert.equal(backHref(page), "/");
  });
});

describe("상세 - 손으로 고친 today", () => {
  it("예전 주소 today=1 은 줄 없이 홈으로", async () => {
    const page = await renderDetail(77, "1");
    assert.equal(position(page), undefined);
    assert.equal(backHref(page), "/");
  });

  for (const bad of ["0", "-3", "abc", "5,6", ""]) {
    it(`today=${JSON.stringify(bad)} 는 홈에서 온 것이 아니다 - 단어장으로`, async () => {
      const page = await renderDetail(77, bad);
      assert.equal(position(page), undefined);
      assert.equal(backHref(page), routes.words);
    });
  }

  it("중복이 섞여도 같은 자리로 되돌아가지 않는다", async () => {
    const page = await renderDetail(6, "5-5-6-6");
    assert.equal(position(page), "2 / 2");
    assert.deepEqual(
      todayLinks(page).map(([id]) => id),
      [5],
    );
  });

  it("배열로 와도(today 두 번) 첫 값을 쓴다", async () => {
    const page = await renderDetail(4, ["3-4", "9-4"]);
    assert.equal(position(page), "2 / 2");
  });

  it("아주 긴 today 도 일곱 개짜리 줄이다", async () => {
    const raw = Array.from({ length: 5000 }, (_, i) => i + 1).join("-");
    const page = await renderDetail(7, raw);
    assert.equal(position(page), "7 / 7");
    assert.ok(todayLinks(page).every(([, o]) => o === "1-2-3-4-5-6-7"), "긴 값을 링크에 그대로 실었다");
  });

  it("상세는 일일공부도 날짜 목록도 부르지 않는다", async () => {
    cookie = "member-token";
    await renderDetail(2, "1-2-3");
    assert.equal(paths.filter((p) => p.startsWith("/api/learning/")).length, 0);
    assert.equal(paths.filter((p) => p === "/api/vocab/words/").length, 0);
  });
});

describe("홈 - 일일공부 상태가 이상할 때", () => {
  it("401(만료 토큰)이면 날짜 단어로 뜨고 로그는 안 남긴다", async () => {
    cookie = "stale-token";
    dailyStatus = 401;
    const html = renderToStaticMarkup(await Home());
    assert.match(bigWord(html) ?? "", /^date-/);
    assert.equal(logged.length, 0, JSON.stringify(logged));
  });

  it("today_words 가 null 이면 날짜 단어", async () => {
    cookie = "member-token";
    todayWords = null;
    const html = renderToStaticMarkup(await Home());
    assert.match(bigWord(html) ?? "", /^date-/);
  });

  it("today_words 가 비었고 날짜 목록도 실패하면 홈은 '못 불러옴' 으로라도 뜬다", async () => {
    cookie = "member-token";
    todayWords = [];
    listStatus = 500;
    const html = renderToStaticMarkup(await Home());
    assert.equal(bigWord(html), undefined);
    assert.equal(todayLinks(html).length, 0);
    assert.ok(logged.length >= 1, "실패를 로그에 남기지 않았다");
  });

  it("일일공부 상태가 500 이고 날짜 목록도 500 이어도 홈은 던지지 않는다", async () => {
    cookie = "member-token";
    dailyStatus = 500;
    listStatus = 500;
    const html = renderToStaticMarkup(await Home());
    assert.equal(bigWord(html), undefined);
  });

  it("5분 첫 묶음(2개)은 날짜 단어를 섞지 않고 둘 다 같은 순서를 싣는다", async () => {
    cookie = "member-token";
    todayWords = [card(40), card(41)];
    const html = renderToStaticMarkup(await Home());
    assert.equal(bigWord(html), "mine-40");
    assert.ok(!html.includes("date-"), "날짜 단어가 섞였다");
    assert.deepEqual(
      [...new Set(todayLinks(html).map(([, o]) => o))],
      ["40-41"],
    );
  });
});
