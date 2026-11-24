/**
 * 홈이 오늘 일일공부를 앞세우는 동작(page.tsx studyFirst, StudyFirstCard)을
 * 깨뜨려 본다. 사용자 결정 11-23: "첫 입장 시에는 일일공부가 주가 되도록".
 *
 * 실행: cd frontend && npm test
 *
 * - 오늘 몫을 안 끝낸 회원: 일일공부 카드 하나. 오늘의 단어·오늘 더 볼 단어·
 *   다시 보기 카드가 없고, 날짜 단어 요청(/api/vocab/words/)도 안 나간다.
 * - 시작 전: 고른 길이의 계획(STUDY_PLANS)대로 제목·설명·막대·링크.
 * - 하다 만 판: 서버가 연 판(chunk_size·chunk_count)대로 진행과 막대.
 * - 끝낸 뒤, 게스트, 상태를 못 받음(401·500), 길이 목록에 하루 공부량이
 *   없음: 예전 홈 그대로.
 * - 옛 백엔드(lengths 에 chunk_size·chunk_count 없음): 막대 없이 숫자만.
 *
 * 백엔드는 fetch 대역이다. 계획 숫자는 backend/apps/learning/models.py
 * STUDY_PLANS 를 그대로 옮겼다(5m 2x4+2, 10m 5x4+5, 30m 5x6+10).
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
/** 계정의 하루 공부량. */
let dailyLength = "10m";

// 이 테스트의 회원. 쿠키가 없으면 로그인 안 한 사람이다.
const member = () =>
  cookie
    ? {
        id: 1,
        email: "member@example.com",
        name: "회원",
        daily_length: dailyLength,
        avatar_display: { type: "preset", key: "a1" },
      }
    : null;

mock.module("@/lib/session", {
  namedExports: {
    getToken: async () => cookie,
    getCurrentUser: async () => member(),
    getLoginState: async () => ({ user: member(), unreachable: false }),
    isGuestChosen: async () => true,
    getGuestDailyLength: async () => "10m",
  },
});

// 다시 시도 화면(LoginCheckFailed)의 로그아웃 버튼이 가져온다. 진짜 모듈은
// lib/client-ip.ts 의 "server-only" 때문에 Next 밖에서 열리지 않는다.
mock.module("@/app/(auth)/actions", {
  namedExports: { logoutAction: async () => {} },
});

// ---- 가짜 백엔드 ------------------------------------------------------------

type Length = {
  value: string;
  label: string;
  questions: number;
  bonus: number;
  words: number;
  chunk_size?: number;
  chunk_count?: number;
};

const PLANS: Length[] = [
  { value: "5m", label: "5분", questions: 10, bonus: 5, words: 8, chunk_size: 2, chunk_count: 4 },
  { value: "10m", label: "10분", questions: 25, bonus: 10, words: 20, chunk_size: 5, chunk_count: 4 },
  { value: "30m", label: "30분", questions: 40, bonus: 25, words: 30, chunk_size: 5, chunk_count: 6 },
];

/** chunk_size·chunk_count 칸이 생기기 전 백엔드의 길이 목록. */
const OLD_PLANS: Length[] = PLANS.map((one) => {
  const old = { ...one };
  delete old.chunk_size;
  delete old.chunk_count;
  return old;
});

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

/** 서버가 연 판. answered 만 바꿔 쓰는 일이 많아 10분 기본값을 둔다. */
function progress(over: Partial<Record<string, unknown>> = {}) {
  const base = {
    length: "10m",
    total: 25,
    answered: 0,
    correct: 0,
    score: 0,
    bonus: 10,
    done: false,
    chunk_size: 5,
    chunk_count: 4,
    chunk_index: 0,
    ...over,
  };
  return base;
}

let lengths: Length[] = PLANS;
let today: ReturnType<typeof progress> | null = null;
let dailyStatus: 200 | 401 | 500 = 200;
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
      lengths,
      today,
      daily_length: dailyLength,
      token: null,
      question: null,
      learning: [],
      today_words: [card(11), card(12), card(13)],
    });
  }
  if (url.pathname.startsWith("/api/learning/review")) {
    // 다시 볼 것이 있다. 예전 홈이면 "다시 보기" 카드가 뜬다.
    return json(200, { due: 3, round_size: 10, streak_to_clear: 2 });
  }
  if (url.pathname === "/api/vocab/words/") {
    return json(200, {
      count: 3,
      next: null,
      previous: null,
      results: [901, 902, 903].map(listed),
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

beforeEach(() => {
  cookie = "member-token";
  dailyLength = "10m";
  lengths = PLANS;
  today = null;
  dailyStatus = 200;
  paths = [];
  logged = [];
  console.error = (message: unknown) => {
    logged.push(message);
  };
});

// ---- 읽는 도구 --------------------------------------------------------------

async function render() {
  return renderToStaticMarkup(await Home());
}

/** 태그를 지우고 React 가 끼우는 <!-- --> 도 지운 글. */
const text = (html: string) =>
  html
    .replace(/<!-- -->/g, "")
    .replace(/<br\/?>/g, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&#x27;/g, "'");

/** 일일공부 카드(section) 한 덩어리. 없으면 null. */
const studyCard = (html: string) =>
  html.match(/<section aria-labelledby="daily-study"[\s\S]*?<\/section>/)?.[0] ?? null;

const title = (html: string) =>
  text(html.match(/<h1 id="daily-study"[^>]*>([\s\S]*?)<\/h1>/)?.[1] ?? "");

/** 카드 설명 문단. */
const summary = (card: string) =>
  text(card.match(/<p class="mt-3"[^>]*>([\s\S]*?)<\/p>/)?.[1] ?? "");

/** 막대 칸들: [라벨, flex-grow, 채운 폭(%), 강조인가]. */
function track(card: string) {
  const bar = card.match(/<div aria-hidden="true" class="mt-5 flex gap-1.5">([\s\S]*)<\/div><\/div><\/div>/);
  if (!bar) return [];
  return [
    ...bar[1].matchAll(
      /style="flex:(\d+) 1 0"[\s\S]*?width:([\d.]+)%[\s\S]*?<span[^>]*style="([^"]*)"[^>]*>([^<]*)<\/span>/g,
    ),
  ].map((m) => ({
    label: m[4],
    grow: Number(m[1]),
    width: Number(m[2]),
    current: m[3].includes("var(--brand)"),
  }));
}

/** 카드 버튼: [주소, 글]. */
const button = (card: string) => {
  const m = card.match(/<a[^>]*href="([^"]*)"[^>]*>([^<]*)<\/a>/);
  return m ? [m[1], m[2]] : null;
};

const dateCalls = () => paths.filter((p) => p === "/api/vocab/words/").length;

/** 예전 홈의 표지들이 있는가. */
function oldHomeParts(html: string) {
  return {
    dailyWord: html.includes('id="daily-word"'),
    upNext: html.includes("오늘 더 볼 단어"),
    review: text(html).includes("다시 보기"),
    todayCards: text(html).includes("일일공부") && html.includes('href="/test/daily"'),
  };
}

function assertStudyFirstOnly(html: string) {
  assert.ok(studyCard(html), "일일공부 카드가 없다");
  assert.equal(html.match(/aria-labelledby="daily-study"/g)?.length, 1, "카드가 둘이다");
  assert.ok(!html.includes('id="daily-word"'), "오늘의 단어가 같이 그려졌다");
  assert.ok(!html.includes("오늘 더 볼 단어"), "오늘 더 볼 단어가 같이 그려졌다");
  assert.ok(!text(html).includes("다시 보기"), "다시 보기 카드가 같이 그려졌다");
  assert.ok(!text(html).includes("시작 전"), "예전 할 일 카드(시작 전)가 같이 그려졌다");
  assert.equal(dateCalls(), 0, "그리지 않을 날짜 단어를 불렀다");
}

function assertOldHome(html: string) {
  assert.equal(studyCard(html), null, "일일공부 카드가 그려졌다");
  assert.ok(!text(html).includes("일일공부를 마치면"), "안내 문구가 남았다");
  assert.ok(
    html.includes('id="daily-word"') || text(html).includes("불러오지"),
    "오늘의 단어 자리가 없다",
  );
}

// ---- 시작 전 ----------------------------------------------------------------

describe("시작 전 회원 홈", () => {
  it("10분: 제목·설명·막대·버튼·링크·안내가 계획대로다", async () => {
    const html = await render();
    assertStudyFirstOnly(html);
    const c = studyCard(html)!;

    assert.equal(title(c), "하루 10분");
    assert.equal(
      summary(c),
      "단어 20개를 5개씩 익히고 바로 문제로 확인합니다. 마지막 5문제는 단어와 문장 전체에서 나옵니다.",
    );
    assert.deepEqual(button(c), ["/test/daily", "시작하기"]);
    assert.deepEqual(
      track(c).map(({ label, grow, width, current }) => [label, grow, width, current]),
      [
        ["1", 5, 0, false],
        ["2", 5, 0, false],
        ["3", 5, 0, false],
        ["4", 5, 0, false],
        ["전체", 5, 0, false],
      ],
    );

    const all = text(html);
    assert.ok(all.includes("하루 10분 · 오늘만 다른 길이로"));
    assert.ok(html.includes('href="/test/daily?choose=1"'));
    assert.ok(all.includes("일일공부를 마치면\n오늘 배운 단어가 여기에 모입니다."));
    // 일일공부 상태는 한 번만 묻는다.
    assert.equal(paths.filter((p) => p === "/api/learning/daily/").length, 1);
  });

  it("5분: 2개씩 네 묶음 + 전체 2", async () => {
    dailyLength = "5m";
    const html = await render();
    assertStudyFirstOnly(html);
    const c = studyCard(html)!;
    assert.equal(title(c), "하루 5분");
    assert.equal(
      summary(c),
      "단어 8개를 2개씩 익히고 바로 문제로 확인합니다. 마지막 2문제는 단어와 문장 전체에서 나옵니다.",
    );
    assert.deepEqual(
      track(c).map(({ label, grow }) => [label, grow]),
      [
        ["1", 2],
        ["2", 2],
        ["3", 2],
        ["4", 2],
        ["전체", 2],
      ],
    );
    assert.ok(text(html).includes("하루 5분 · 오늘만 다른 길이로"));
  });

  it("30분: 일곱 칸이고 전체 칸이 묶음 칸의 두 배 폭이다", async () => {
    dailyLength = "30m";
    const html = await render();
    const c = studyCard(html)!;
    assert.equal(title(c), "하루 30분");
    assert.equal(
      summary(c),
      "단어 30개를 5개씩 익히고 바로 문제로 확인합니다. 마지막 10문제는 단어와 문장 전체에서 나옵니다.",
    );
    const parts = track(c);
    assert.deepEqual(
      parts.map((p) => p.label),
      ["1", "2", "3", "4", "5", "6", "전체"],
    );
    assert.ok(parts.slice(0, 6).every((p) => p.grow === 5));
    assert.equal(parts[6].grow, 10);
    // 칸 폭의 합이 문제 수와 같아야 비율이 맞다.
    assert.equal(
      parts.reduce((sum, p) => sum + p.grow, 0),
      40,
    );
  });

  it("옛 백엔드(chunk_size·chunk_count 없음)면 막대 없이 숫자만 적는다", async () => {
    lengths = OLD_PLANS;
    const html = await render();
    assertStudyFirstOnly(html);
    const c = studyCard(html)!;
    assert.equal(summary(c), "단어 20개를 익히고 문제 25개를 풉니다.");
    assert.ok(!c.includes('class="mt-5 flex gap-1.5"'), "막대가 그려졌다");
    assert.deepEqual(button(c), ["/test/daily", "시작하기"]);
  });

  it("chunk_size 가 0 인 길이면(학습 없는 계획) 막대 없이 숫자만", async () => {
    lengths = PLANS.map((one) => (one.value === "10m" ? { ...one, chunk_size: 0, chunk_count: 0, words: 0 } : one));
    const html = await render();
    const c = studyCard(html)!;
    assert.equal(summary(c), "단어 0개를 익히고 문제 25개를 풉니다.");
    assert.ok(!c.includes('class="mt-5 flex gap-1.5"'));
    assert.ok(!/NaN|Infinity|undefined/.test(c), c);
  });

  it("학습분이 문제 수와 같으면(전체 구간 없음) 마지막 문장과 전체 칸이 없다", async () => {
    lengths = PLANS.map((one) =>
      one.value === "10m" ? { ...one, questions: 20, words: 20, chunk_size: 5, chunk_count: 4 } : one,
    );
    const html = await render();
    const c = studyCard(html)!;
    assert.equal(summary(c), "단어 20개를 5개씩 익히고 바로 문제로 확인합니다.");
    assert.deepEqual(
      track(c).map((p) => p.label),
      ["1", "2", "3", "4"],
    );
  });
});

// ---- 하다 만 판 ---------------------------------------------------------------

describe("하다 만 판", () => {
  /** answered 별 기대: [설명 앞부분, 막대 채움(%), 강조 칸 라벨]. */
  const cases: [number, string, number[], string][] = [
    [0, "1번째 묶음을 하던 중입니다.", [0, 0, 0, 0, 0], "1"],
    [3, "1번째 묶음을 하던 중입니다.", [60, 0, 0, 0, 0], "1"],
    [4, "1번째 묶음을 하던 중입니다.", [80, 0, 0, 0, 0], "1"],
    [5, "2번째 묶음을 하던 중입니다.", [100, 0, 0, 0, 0], "2"],
    [10, "3번째 묶음을 하던 중입니다.", [100, 100, 0, 0, 0], "3"],
    [19, "4번째 묶음을 하던 중입니다.", [100, 100, 100, 80, 0], "4"],
    [20, "마지막 문제들을 풀던 중입니다.", [100, 100, 100, 100, 0], "전체"],
    [22, "마지막 문제들을 풀던 중입니다.", [100, 100, 100, 100, 40], "전체"],
    [24, "마지막 문제들을 풀던 중입니다.", [100, 100, 100, 100, 80], "전체"],
  ];

  for (const [answered, where, widths, current] of cases) {
    it(`10분 ${answered}/25`, async () => {
      today = progress({ answered });
      const html = await render();
      assertStudyFirstOnly(html);
      const c = studyCard(html)!;
      assert.equal(title(c), `${answered}/25문제`);
      assert.equal(summary(c), `${where} 들어가면 멈춘 곳부터 이어집니다.`);
      const parts = track(c);
      assert.deepEqual(
        parts.map((p) => p.width),
        widths,
      );
      assert.deepEqual(
        parts.filter((p) => p.current).map((p) => p.label),
        [current],
        "강조 칸은 정확히 하나",
      );
      assert.deepEqual(button(c), ["/test/daily", "이어서 하기"]);
      // 시작한 뒤에는 길이를 못 바꾸므로 링크가 없다.
      assert.ok(!html.includes("choose=1"));
      assert.ok(text(html).includes("일일공부를 마치면"));
    });
  }

  it("30분 일곱 칸: 26/40 이면 여섯째 묶음, 막대 폭 비율은 5:10", async () => {
    dailyLength = "30m";
    today = progress({ length: "30m", total: 40, bonus: 25, chunk_count: 6, answered: 26 });
    const c = studyCard(await render())!;
    assert.equal(summary(c), "6번째 묶음을 하던 중입니다. 들어가면 멈춘 곳부터 이어집니다.");
    const parts = track(c);
    assert.deepEqual(
      parts.map((p) => [p.label, p.grow, p.width]),
      [
        ["1", 5, 100],
        ["2", 5, 100],
        ["3", 5, 100],
        ["4", 5, 100],
        ["5", 5, 100],
        ["6", 5, 20],
        ["전체", 10, 0],
      ],
    );
    assert.deepEqual(
      parts.filter((p) => p.current).map((p) => p.label),
      ["6"],
    );
  });

  it("하루 공부량과 다른 길이로 연 판이면 서버가 연 판대로 그린다", async () => {
    dailyLength = "10m";
    today = progress({ length: "5m", total: 10, chunk_size: 2, chunk_count: 4, answered: 7 });
    const c = studyCard(await render())!;
    assert.equal(title(c), "7/10문제");
    assert.equal(summary(c).split(" 들어가면")[0], "4번째 묶음을 하던 중입니다.");
    assert.equal(track(c).length, 5);
  });

  it("서버가 묶음을 줄여 연 판(학습 2묶음)이면 그만큼만 칸이 있다", async () => {
    today = progress({ chunk_count: 2, answered: 10 });
    const c = studyCard(await render())!;
    assert.deepEqual(
      track(c).map((p) => [p.label, p.grow]),
      [
        ["1", 5],
        ["2", 5],
        ["전체", 15],
      ],
    );
    assert.equal(summary(c).split(" 들어가면")[0], "마지막 문제들을 풀던 중입니다.");
  });

  it("chunk_size 0 인 판(학습 없이 문제만)도 깨지지 않고 전체 한 칸이다", async () => {
    today = progress({ chunk_size: 0, chunk_count: 0, answered: 3 });
    const html = await render();
    assertStudyFirstOnly(html);
    const c = studyCard(html)!;
    assert.ok(!/NaN|Infinity|undefined/.test(c), c);
    assert.equal(title(c), "3/25문제");
    assert.deepEqual(
      track(c).map((p) => [p.label, p.grow, p.width]),
      [["전체", 25, 12]],
    );
    // 칸이 "전체" 하나라 어디쯤인지 말하지 않는다. "마지막 문제들" 이라고
    // 하면 0/25 에서도 끝나 가는 것처럼 읽힌다.
    assert.equal(summary(c), "들어가면 멈춘 곳부터 이어집니다.");
    assert.deepEqual(button(c), ["/test/daily", "이어서 하기"]);
  });

  it("하다 만 판은 길이 목록에 하루 공부량이 없어도 앞세운다", async () => {
    lengths = [];
    today = progress({ answered: 2 });
    const html = await render();
    assertStudyFirstOnly(html);
  });
});

// ---- 예전 홈으로 떨어지는 경우 -------------------------------------------------

describe("예전 홈 그대로", () => {
  it("오늘 몫을 끝냈으면 오늘의 단어와 할 일 카드다", async () => {
    today = progress({ answered: 25, done: true, chunk_index: 3 });
    const html = await render();
    assertOldHome(html);
    const parts = oldHomeParts(html);
    assert.ok(parts.dailyWord && parts.upNext && parts.review && parts.todayCards, JSON.stringify(parts));
    assert.ok(text(html).includes("오늘 몫 완료"));
  });

  it("게스트는 일일공부를 묻지 않고 예전 홈이다", async () => {
    cookie = null;
    const html = await render();
    assertOldHome(html);
    assert.equal(paths.filter((p) => p.startsWith("/api/learning/")).length, 0);
    assert.ok(dateCalls() >= 1);
  });

  for (const status of [401, 500] as const) {
    it(`일일공부 상태가 ${status} 이면 예전 홈이고 날짜 단어를 부른다`, async () => {
      dailyStatus = status;
      const html = await render();
      assertOldHome(html);
      assert.ok(dateCalls() >= 1);
      // 401 은 로그를 안 남기고, 500 은 남긴다(loadToday 규칙).
      if (status === 401) assert.equal(logged.length, 0, JSON.stringify(logged));
      else assert.ok(logged.length >= 1);
    });
  }

  it("길이 목록이 비어 있으면(시작 전) 예전 홈이다", async () => {
    lengths = [];
    const html = await render();
    assertOldHome(html);
  });

  it("하루 공부량이 길이 목록에 없으면 예전 홈이다", async () => {
    dailyLength = "45m";
    const html = await render();
    assertOldHome(html);
  });

  it("계정에 하루 공부량 칸이 없으면(옛 백엔드) 예전 홈이다", async () => {
    dailyLength = undefined as unknown as string;
    const html = await render();
    assertOldHome(html);
  });
});
