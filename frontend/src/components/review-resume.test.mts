/**
 * 복습(/test/review) 도중 새로고침해도 풀던 판을 이어 푸는지 실제로 돌려 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 보드는 판을 탭 저장소(sessionStorage)의 `review-round-<계정>` 에 적는다.
 * 잡으려는 결함은 이렇다.
 *
 *   적는 값이 화면과 다름   새로고침 뒤 맞힌 수·진행이 어긋난다
 *   끝난 판이 남음          다음에 들어오면 이미 끝난 판을 이어 풀라고 한다
 *   400 인데 판을 붙듦      만료된 토큰으로 계속 400 만 받는 막다른 길
 *   429·500 인데 판을 버림  잠깐의 장애로 풀던 판을 잃는다
 *   계정이 섞임             앞 사람이 틀린 단어가 뒷사람 문제로 뜬다
 *   저장소가 막힌 브라우저  접근 예외로 보드가 죽는다
 *   이상한 저장값           "5 / undefined" 같은 판을 편다
 *   오래된 저장값           토큰이 만료된 판을 이어 풀라고 한다
 *   떠난 뒤 온 응답         화면이 사라졌다고 새 토큰을 안 적는다
 *
 * 방식은 result-line-placement.test.mts 와 같다 - react 의 훅만 작은 대역으로
 * 바꾸고 보드가 넘긴 onStart·onPick 을 진짜로 부른다. 다른 점 하나:
 * renderToStaticMarkup 안의 useSyncExternalStore 는 서버 몫(null)만 쓰므로
 * 대역이 **브라우저 몫(getSnapshot)** 을 부르게 한다. 그래야 "이어서 풀기"
 * 가 그려지는지 볼 수 있다. 시작 화면의 버튼은 IdleCard 를 직접 불러 받은
 * 트리에서 꺼내 onClick 을 누른다 - 저장값을 읽고 고르는 길을 건너뛰지
 * 않으려고 onResume 을 직접 부르지 않는다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

import type { RoundQuestion } from "@/lib/api/rounds";
import type { ReviewAnswered, ReviewQuestion, ReviewStarted } from "@/lib/api/review";

const realReact = await import("react");

type Slot = { value: unknown };
type Effect = () => void | (() => void);

let slots: Slot[] = [];
let cursor = 0;
let effects: Effect[] = [];

function slot<T>(init: () => T): Slot {
  if (cursor >= slots.length) slots.push({ value: init() });
  return slots[cursor++];
}

mock.module("react", {
  defaultExport: realReact.default,
  namedExports: {
    ...realReact,
    useState<T>(init: T | (() => T)) {
      const s = slot(() => (typeof init === "function" ? (init as () => T)() : init));
      const set = (next: T | ((prev: T) => T)) => {
        s.value = typeof next === "function" ? (next as (prev: T) => T)(s.value as T) : next;
      };
      return [s.value, set];
    },
    useRef<T>(init: T) {
      return slot(() => ({ current: init })).value;
    },
    useEffect(run: Effect) {
      effects.push(run);
    },
    // 브라우저 몫을 쓴다. 위 머리말.
    useSyncExternalStore<T>(_subscribe: unknown, getSnapshot: () => T) {
      return getSnapshot();
    },
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { createElement } = realReact;
const { ReviewBoard } = await import("./ReviewBoard");

/* ---- 탭 저장소 대역 ---- */

/** 적힌 값과 부른 횟수를 들고 있는 가짜 sessionStorage. broken 이면 전부 던진다. */
class FakeStorage {
  data = new Map<string, string>();
  writes = 0;
  broken = false;

  private guard() {
    if (this.broken) throw new Error("SecurityError: 저장소 접근 거부");
  }
  getItem(key: string): string | null {
    this.guard();
    return this.data.has(key) ? (this.data.get(key) as string) : null;
  }
  setItem(key: string, value: string): void {
    this.guard();
    this.writes++;
    this.data.set(key, String(value));
  }
  removeItem(key: string): void {
    this.guard();
    this.writes++;
    this.data.delete(key);
  }
}

let storage: FakeStorage;
const g = globalThis as unknown as { window?: unknown };
const hadWindow = "window" in g;
const realWindow = g.window;

/* ---- 중계 대역 ---- */

type Reply = unknown | { fail: number; detail: string } | Error;

const realFetch = globalThis.fetch;
after(() => {
  globalThis.fetch = realFetch;
  if (hadWindow) g.window = realWindow;
  else delete g.window;
});

let replies: Reply[] = [];
/** 보드가 보낸 본문. */
let sent: Record<string, unknown>[] = [];

beforeEach(() => {
  slots = [];
  replies = [];
  sent = [];
  storage = new FakeStorage();
  g.window = { sessionStorage: storage };
  globalThis.fetch = (async (_url: unknown, init?: { body?: string }) => {
    sent.push(JSON.parse(init?.body ?? "{}"));
    assert.ok(replies.length > 0, "준비한 것보다 요청이 많다");
    // 약속이면 풀릴 때까지 응답을 미룬다(늦게 오는 응답). 실패도 미룰 수 있다.
    let reply = replies.shift();
    if (reply instanceof Promise) reply = await reply;
    if (reply instanceof Error) throw reply;
    if (reply && typeof reply === "object" && "fail" in reply) {
      const { fail, detail } = reply as { fail: number; detail: string };
      return { ok: false, status: fail, json: async () => ({ detail }) } as Response;
    }
    return { ok: true, status: 200, json: async () => reply } as Response;
  }) as typeof fetch;
});

/* ---- 보드 다루기 ---- */

type Node = { type?: unknown; props: Record<string, unknown> };

/** 보드를 한 번 부르고 본문 가지(overlays 다음)를 꺼낸다. */
function branch(board: () => unknown): Node {
  cursor = 0;
  effects = [];
  const tree = board() as { props: { children: unknown[] } };
  for (const run of effects) run();
  return tree.props.children[1] as Node;
}

function draw(element: unknown): string {
  cursor = 0;
  return renderToStaticMarkup(element as never);
}

async function settle() {
  for (let i = 0; i < 5; i++) await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
}

/** 트리에서 첫 <button> 요소. */
function findButton(node: unknown): Node | null {
  if (!node || typeof node !== "object") return null;
  if (Array.isArray(node)) {
    for (const child of node) {
      const hit = findButton(child);
      if (hit) return hit;
    }
    return null;
  }
  const el = node as Node;
  if (el.type === "button") return el;
  return findButton(el.props?.children);
}

/** 트리에서 글자가 name 인 <button> 요소. */
function findNamed(node: unknown, name: string): Node | null {
  if (!node || typeof node !== "object") return null;
  if (Array.isArray(node)) {
    for (const child of node) {
      const hit = findNamed(child, name);
      if (hit) return hit;
    }
    return null;
  }
  const el = node as Node;
  if (el.type === "button" && el.props?.children === name) return el;
  return findNamed(el.props?.children, name);
}

/** 시작 화면의 주 버튼을 누른다. IdleCard 를 직접 불러 받은 버튼의 onClick 이다. */
async function pressIdle(board: () => unknown): Promise<void> {
  const idle = branch(board);
  assert.equal(typeof idle.props.onResume, "function", "시작 화면이 아니다");
  const card = (idle.type as (p: unknown) => unknown)(idle.props);
  const button = findButton(card);
  assert.ok(button, "시작 화면에 버튼이 없다");
  await (button.props.onClick as () => unknown)();
  await settle();
}

async function pick(board: () => unknown, choiceId: number): Promise<void> {
  const play = branch(board);
  assert.equal(typeof play.props.onPick, "function", "문제 가지가 아니다");
  await (play.props.onPick as (id: number) => Promise<void>)(choiceId);
  await settle();
}

/* ---- 자료 ---- */

const DUE = { due: 5, round_size: 20, graduate_streak: 2 };
const KEY = "review-round-7";

function q(prompt: string, base: number, answered: number, total = 5): ReviewQuestion {
  const inner: RoundQuestion = {
    kind: "meaning",
    kind_label: "뜻 고르기",
    question: `질문-${prompt}`,
    prompt,
    category: "git",
    category_label: "Git",
    choices: [0, 1, 2, 3].map((i) => ({ id: base + i, text: `보기-${prompt}-${i}` })),
  };
  return { ...inner, answered, total };
}

const Q1 = q("commit", 10, 0, 3);
const Q2 = q("rebase", 20, 1, 3);
const Q3 = q("stash", 30, 2, 3);
const STARTED: ReviewStarted = { token: "r-1", question: Q1 };

function answer(
  correct: boolean,
  next: ReviewQuestion | null,
  token: string | null,
  graduated = false,
): ReviewAnswered {
  return {
    result: {
      correct,
      streak: correct ? 1 : 0,
      graduated,
      answer_type: "word",
      answer_text: "commit",
      answer_extra: "변경을 기록하기",
    },
    token,
    question: next,
    finished: next === null,
  } as ReviewAnswered;
}

/** 적힌 판. 적은 시각(savedAt)은 매번 달라 떼고 비교한다 - 그 값은 따로 본다. */
const stored = (key = KEY) => {
  const raw = storage.data.get(key);
  if (raw === undefined) return undefined;
  const saved = JSON.parse(raw);
  delete saved.savedAt;
  return saved;
};

const HOUR = 60 * 60 * 1000;

/** 5개 중 3개를 풀어 둔 판(맞힌 1, 뺀 1). 방금 적었다. */
const SAVED = {
  token: "r-saved",
  question: q("merge", 40, 3, 5),
  correct: 1,
  graduated: 1,
  savedAt: Date.now(),
};

/* ---- 1. 적는 값 ---- */

describe("복습 이어 풀기 - 판을 적는다", () => {
  const board = () => ReviewBoard({ due: DUE, userId: 7 });

  it("시작하면 토큰·첫 문제·0/0 을 계정 키에 적는다", async () => {
    replies = [STARTED];
    const before = Date.now();
    await pressIdle(board);
    assert.deepEqual(stored(), { token: "r-1", question: Q1, correct: 0, graduated: 0 });
    assert.deepEqual([...storage.data.keys()], [KEY]);
    // 적은 시각이 붙어야 읽을 때 오래된 판을 거른다.
    const savedAt = JSON.parse(storage.data.get(KEY) as string).savedAt;
    assert.ok(savedAt >= before && savedAt <= Date.now(), "적은 시각이 없다");
  });

  it("답할 때마다 적은 값이 화면의 진행·맞힌 수와 같고, 마지막 답에 지운다", async () => {
    replies = [STARTED];
    await pressIdle(board);

    replies = [answer(true, Q2, "r-2", true)];
    await pick(board, Q1.choices[0].id);
    assert.deepEqual(stored(), { token: "r-2", question: Q2, correct: 1, graduated: 1 });
    let html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.match(html, />1 \/ 3</, "화면 진행이 적은 값과 다르다");
    assert.ok(html.includes(Q2.prompt));

    replies = [answer(false, Q3, "r-3")];
    await pick(board, Q2.choices[1].id);
    assert.deepEqual(stored(), { token: "r-3", question: Q3, correct: 1, graduated: 1 });
    html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.match(html, />2 \/ 3</);

    // 보낸 토큰이 바로 앞 응답의 것인가.
    assert.deepEqual(
      sent.map((b) => b.token),
      [undefined, "r-1", "r-2"],
    );

    replies = [answer(true, null, null)];
    await pick(board, Q3.choices[0].id);
    assert.equal(storage.data.has(KEY), false, "끝난 판이 남았다");
    html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.match(html, />2 \/ 3</, "결과가 맞힌 수 / 푼 수가 아니다");
    assert.match(html, /1개를 다 외워 목록에서 뺐습니다/);
  });

  it("다음 토큰 없이 다음 문제가 오면 빈 토큰을 적고, 그 값은 이어 풀기로 안 뜬다", async () => {
    replies = [STARTED];
    await pressIdle(board);
    replies = [answer(true, Q2, null)];
    await pick(board, Q1.choices[0].id);
    assert.equal(stored().token, "");
    // 적는 것은 적어도 이어 풀기 판으로 읽히지 않아야 한다.
    slots = [];
    const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.doesNotMatch(html, /이어서 풀기/);
  });
});

/* ---- 2. 이어 풀기 ---- */

describe("복습 이어 풀기 - 적어 둔 판을 편다", () => {
  const board = () => ReviewBoard({ due: DUE, userId: 7 });

  beforeEach(() => {
    storage.data.set(KEY, JSON.stringify(SAVED));
  });

  it("시작 화면이 '이어서 풀기' 와 몇 개 중 몇 개를 풀었는지를 보인다", () => {
    branch(board);
    const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.match(html, /<button[^>]*>이어서 풀기<\/button>/);
    assert.match(html, /풀던 판이 있습니다\. 5개 중 3개를 풀었습니다\./);
    assert.doesNotMatch(html, />시작</);
  });

  it("누르면 요청 없이 적어 둔 문제가 3 / 5 로 뜨고, 끝나면 맞힌 수가 이어진다", async () => {
    await pressIdle(board);
    assert.equal(sent.length, 0, "이어 풀기가 새 판을 요청했다");
    let html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.ok(html.includes(SAVED.question.prompt), "적어 둔 문제가 안 떴다");
    assert.match(html, />3 \/ 5</);

    const Q4 = q("fetch", 50, 4, 5);
    replies = [answer(true, Q4, "r-4")];
    await pick(board, SAVED.question.choices[0].id);
    assert.equal(sent[0].token, "r-saved", "적어 둔 토큰으로 답하지 않았다");
    assert.deepEqual(stored(), { token: "r-4", question: Q4, correct: 2, graduated: 1 });

    replies = [answer(true, null, null, true)];
    await pick(board, Q4.choices[0].id);
    assert.equal(storage.data.has(KEY), false);
    html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    // 새로고침 전 1 + 뒤 2 = 3, 푼 수는 5.
    assert.match(html, />3 \/ 5</);
    assert.match(html, /2개를 다 외워 목록에서 뺐습니다/);
  });

  it("판이 끝난 뒤 새로 불러온 시작 화면은 다시 '시작' 이다", async () => {
    await pressIdle(board);
    replies = [answer(true, q("x", 60, 4, 5), "r-4")];
    await pick(board, SAVED.question.choices[0].id);
    replies = [answer(true, null, null)];
    await pick(board, 60);
    slots = [];
    branch(board);
    const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.match(html, /<button[^>]*>시작<\/button>/);
  });

  it("'새로 시작' 은 적어 둔 판을 버리고 새 판을 요청해 덮어쓴다", async () => {
    const idle = branch(board);
    const card = (idle.type as (p: unknown) => unknown)(idle.props);
    const html = draw(card);
    assert.match(html, /<button[^>]*>새로 시작<\/button>/);
    // 코랄은 "이어서 풀기" 하나다.
    assert.equal((html.match(/var\(--coral\)/g) ?? []).length, 1);

    const again = findNamed(card, "새로 시작");
    assert.ok(again, "'새로 시작' 버튼이 없다");
    replies = [STARTED];
    await (again.props.onClick as () => unknown)();
    await settle();
    assert.equal(sent[0]?.action, "start");
    assert.deepEqual(stored(), { token: "r-1", question: Q1, correct: 0, graduated: 0 });
  });

  it("적어 둔 판이 없으면 '새로 시작' 을 그리지 않는다", () => {
    storage.data.clear();
    branch(board);
    const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.doesNotMatch(html, /새로 시작/);
  });
});

/* ---- 2-1. 화면이 떠난 뒤 온 응답 ---- */

describe("복습 이어 풀기 - 답을 보내고 응답 전에 화면을 떠나면", () => {
  const board = () => ReviewBoard({ due: DUE, userId: 7 });

  /** 보드의 이펙트를 다시 돌려 정리 함수를 부른다 - 화면이 사라진 것과 같다. */
  function leave() {
    for (const run of effects) (run() as (() => void) | undefined)?.();
  }

  it("새 토큰과 문제를 그래도 적는다", async () => {
    replies = [STARTED];
    await pressIdle(board);
    const play = branch(board);
    replies = [answer(true, Q2, "r-2")];
    const pending = (play.props.onPick as (id: number) => Promise<void>)(Q1.choices[0].id);
    leave();
    await pending;
    await settle();
    // 안 적으면 돌아와서 이미 답한 문제의 토큰으로 이어 풀다 400 을 받는다.
    assert.deepEqual(stored(), { token: "r-2", question: Q2, correct: 1, graduated: 0 });
  });

  it("마지막 답이었으면 지운다", async () => {
    replies = [STARTED];
    await pressIdle(board);
    const play = branch(board);
    replies = [answer(true, null, null)];
    const pending = (play.props.onPick as (id: number) => Promise<void>)(Q1.choices[0].id);
    leave();
    await pending;
    await settle();
    assert.equal(storage.data.has(KEY), false);
  });

  it("400 이었으면 지운다", async () => {
    storage.data.set(KEY, JSON.stringify(SAVED));
    await pressIdle(board);
    const play = branch(board);
    replies = [{ fail: 400, detail: "이미 처리한 답입니다." }];
    const pending = (play.props.onPick as (id: number) => Promise<void>)(
      SAVED.question.choices[0].id,
    );
    leave();
    await pending;
    await settle();
    assert.equal(storage.data.has(KEY), false);
  });
});

/* ---- 3. 거절과 장애 ---- */

describe("복습 이어 풀기 - 답이 거절되거나 실패하면", () => {
  const board = () => ReviewBoard({ due: DUE, userId: 7 });

  beforeEach(() => {
    storage.data.set(KEY, JSON.stringify(SAVED));
  });

  it("400 이면 적어 둔 판을 지우고 시작 화면으로 가서 오류를 보인다", async () => {
    await pressIdle(board);
    replies = [{ fail: 400, detail: "복습이 만료됐습니다. 다시 시작해주세요." }];
    await pick(board, SAVED.question.choices[0].id);

    assert.equal(storage.data.has(KEY), false, "막다른 판이 남았다");
    const idle = branch(board);
    assert.equal(typeof idle.props.onResume, "function", "시작 화면으로 안 갔다");
    const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    // 서버 문구 대신 시작 화면에 맞는 문구를 보인다.
    assert.match(html, /role="alert"[^>]*>이 판은 더 이어갈 수 없습니다\. 새로 시작해주세요\.</);
    assert.doesNotMatch(html, /복습이 만료됐습니다/);
    assert.match(html, /<button[^>]*>시작<\/button>/);
    assert.doesNotMatch(html, /이어서 풀기/);

    // 거기서 시작하면 새 판이 열리고 새로 적힌다.
    replies = [STARTED];
    await pressIdle(board);
    assert.deepEqual(stored(), { token: "r-1", question: Q1, correct: 0, graduated: 0 });
    assert.equal(sent.at(-1)?.action, "start");
  });

  for (const [label, reply] of [
    ["429", { fail: 429, detail: "잠시 후 다시 시도해주세요." }],
    ["500", { fail: 500, detail: "알 수 없는 오류가 발생했습니다." }],
    ["503", { fail: 503, detail: "서버에 연결할 수 없습니다." }],
    ["401", { fail: 401, detail: "로그인이 필요합니다." }],
    ["네트워크 실패", new TypeError("Failed to fetch")],
  ] as const) {
    it(`${label} 이면 판을 그대로 두고 문제 화면에 오류를 보인다`, async () => {
      await pressIdle(board);
      const before = storage.data.get(KEY);
      replies = [reply];
      await pick(board, SAVED.question.choices[0].id);

      assert.equal(storage.data.get(KEY), before, "잠깐의 장애로 판이 바뀌었다");
      const play = branch(board);
      assert.equal(typeof play.props.onPick, "function", "문제 화면을 떠났다");
      const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
      assert.ok(html.includes(SAVED.question.prompt));
      assert.match(html, />3 \/ 5</);
      const shown = reply instanceof Error ? reply.message : reply.detail;
      assert.ok(html.includes(shown), "오류 문구가 안 보인다");

      // 같은 토큰으로 다시 보내면 이어진다.
      const Q4 = q("fetch", 50, 4, 5);
      replies = [answer(true, Q4, "r-4")];
      await pick(board, SAVED.question.choices[0].id);
      assert.equal(sent.at(-1)?.token, "r-saved");
      assert.deepEqual(stored(), { token: "r-4", question: Q4, correct: 2, graduated: 1 });
    });
  }

  it("시작이 400 이면 아무것도 적지 않고 시작 화면에 오류를 보인다", async () => {
    storage.data.clear();
    replies = [{ fail: 400, detail: "복습할 것이 없습니다. 문제를 더 풀어보세요." }];
    await pressIdle(board);
    assert.equal(storage.writes, 0);
    const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.match(html, /복습할 것이 없습니다/);
    assert.match(html, /<button[^>]*>시작<\/button>/);
  });
});

/* ---- 4. 계정 ---- */

describe("복습 이어 풀기 - 계정", () => {
  for (const [label, props] of [
    ["userId 가 null", { due: DUE, userId: null }],
    ["userId 를 안 넘김", { due: DUE }],
  ] as const) {
    it(`${label} 이면 저장소에 한 번도 쓰지 않는다`, async () => {
      const board = () => ReviewBoard(props);
      replies = [STARTED];
      await pressIdle(board);
      replies = [answer(true, Q2, "r-2")];
      await pick(board, Q1.choices[0].id);
      replies = [{ fail: 400, detail: "만료" }];
      await pick(board, Q2.choices[0].id);
      replies = [STARTED];
      await pressIdle(board);
      replies = [answer(true, Q2, "r-2"), answer(true, Q3, "r-3"), answer(true, null, null)];
      await pick(board, Q1.choices[0].id);
      await pick(board, Q2.choices[0].id);
      await pick(board, Q3.choices[0].id);
      assert.equal(storage.writes, 0);
      assert.equal(storage.data.size, 0);
    });
  }

  it("userId 가 null 이면 누가 적어 둔 판도 안 읽는다", () => {
    storage.data.set(KEY, JSON.stringify(SAVED));
    storage.data.set("review-round-null", JSON.stringify(SAVED));
    storage.data.set("review-round-", JSON.stringify(SAVED));
    branch(() => ReviewBoard({ due: DUE, userId: null }));
    const html = draw(createElement(ReviewBoard, { due: DUE, userId: null }));
    assert.doesNotMatch(html, /이어서 풀기|풀던 판/);
  });

  it("다른 계정의 판은 안 읽고, 내 판을 적어도 남의 판은 건드리지 않는다", async () => {
    storage.data.set("review-round-8", JSON.stringify(SAVED));
    storage.data.set("review-round-70", JSON.stringify(SAVED));
    const board = () => ReviewBoard({ due: DUE, userId: 7 });
    branch(board);
    const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.doesNotMatch(html, /이어서 풀기|풀던 판/);

    replies = [STARTED];
    await pressIdle(board);
    replies = [answer(true, null, null)];
    await pick(board, Q1.choices[0].id);
    assert.equal(storage.data.get("review-round-8"), JSON.stringify(SAVED));
    assert.equal(storage.data.get("review-round-70"), JSON.stringify(SAVED));
  });

  it("userId 0 도 계정이다 - review-round-0 에 적는다", async () => {
    replies = [STARTED];
    await pressIdle(() => ReviewBoard({ due: DUE, userId: 0 }));
    assert.ok(storage.data.has("review-round-0"));
  });
});

/* ---- 5. 막힌 저장소 ---- */

describe("복습 이어 풀기 - 저장소 접근이 예외를 던지는 브라우저", () => {
  const board = () => ReviewBoard({ due: DUE, userId: 7 });

  it("시작·답·거절·끝까지 보드가 죽지 않는다", async () => {
    storage.broken = true;
    branch(board);
    let html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.match(html, /<button[^>]*>시작<\/button>/);

    replies = [STARTED];
    await pressIdle(board);
    replies = [answer(true, Q2, "r-2")];
    await pick(board, Q1.choices[0].id);
    replies = [{ fail: 400, detail: "만료" }];
    await pick(board, Q2.choices[0].id);
    html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.match(html, /더 이어갈 수 없습니다/);

    replies = [STARTED, answer(true, Q2, "r-2"), answer(false, Q3, "r-3"), answer(true, null, null)];
    await pressIdle(board);
    await pick(board, Q1.choices[0].id);
    await pick(board, Q2.choices[0].id);
    await pick(board, Q3.choices[0].id);
    html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.match(html, />2 \/ 3</);
  });

  it("window 가 아예 없어도(서버) 시작 화면은 그려진다", () => {
    delete g.window;
    branch(board);
    const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.match(html, /<button[^>]*>시작<\/button>/);
  });
});

/* ---- 6. 이상한 저장값 ---- */

describe("복습 이어 풀기 - 판이 아닌 저장값은 없는 것으로 본다", () => {
  const board = () => ReviewBoard({ due: DUE, userId: 7 });
  const base = () => JSON.parse(JSON.stringify(SAVED));
  const withQ = (patch: Record<string, unknown>) => {
    const s = base();
    Object.assign(s.question, patch);
    return JSON.stringify(s);
  };
  const withTop = (patch: Record<string, unknown>) => JSON.stringify({ ...base(), ...patch });
  const without = (field: string) => {
    const s = base();
    delete s[field];
    return JSON.stringify(s);
  };

  const cases: [string, string][] = [
    ["깨진 JSON", "{token:"],
    ["빈 글", ""],
    ["null", "null"],
    ["숫자", "42"],
    ["문자열", '"r-saved"'],
    ["배열", "[]"],
    ["빈 객체", "{}"],
    ["토큰 없음", without("token")],
    ["빈 토큰", withTop({ token: "" })],
    ["숫자 토큰", withTop({ token: 123 })],
    ["문제 없음", without("question")],
    ["문제가 null", withTop({ question: null })],
    ["문제가 문자열", withTop({ question: "q" })],
    ["보기 없음", withQ({ choices: undefined })],
    ["보기가 객체", withQ({ choices: {} })],
    ["answered == total", withQ({ answered: 5, total: 5 })],
    ["answered > total", withQ({ answered: 6, total: 5 })],
    ["total 0", withQ({ answered: 0, total: 0 })],
    ["answered 음수", withQ({ answered: -1 })],
    ["answered 소수", withQ({ answered: 1.5 })],
    ["answered 문자열", withQ({ answered: "3" })],
    ["total 문자열", withQ({ total: "5" })],
    ["total 없음", withQ({ total: undefined })],
    ["correct 음수", withTop({ correct: -1 })],
    ["correct 소수", withTop({ correct: 0.5 })],
    ["correct 문자열", withTop({ correct: "1" })],
    ["correct 없음", without("correct")],
    ["graduated 없음", without("graduated")],
    ["graduated null", withTop({ graduated: null })],
    ["보기에 null", withQ({ choices: [null] })],
    ["보기가 빔", withQ({ choices: [] })],
    ["보기 id 가 문자열", withQ({ choices: [{ id: "1", text: "a" }] })],
    ["보기 글자 없음", withQ({ choices: [{ id: 1 }] })],
    ["answered 1e21", withQ({ answered: 1e21, total: 1e22 })],
    ["correct > answered", withTop({ correct: 4 })],
    ["graduated > correct", withTop({ graduated: 2 })],
    ["적은 시각 없음", without("savedAt")],
    ["적은 시각이 문자열", withTop({ savedAt: String(Date.now()) })],
    ["6시간 전", withTop({ savedAt: Date.now() - 6 * HOUR })],
    ["5시간 51분 전", withTop({ savedAt: Date.now() - (5 * 60 + 51) * 60 * 1000 })],
    ["앞날", withTop({ savedAt: Date.now() + HOUR })],
  ];

  for (const [label, raw] of cases) {
    it(`${label} -> '시작'`, () => {
      storage.data.set(KEY, raw);
      branch(board);
      const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
      assert.match(html, /<button[^>]*>시작<\/button>/, `${label} 을 판으로 읽었다`);
      assert.doesNotMatch(html, /풀던 판|undefined|NaN/);
    });
  }

  it("대조군: 맞는 모양이면 '이어서 풀기'", () => {
    storage.data.set(KEY, withQ({}));
    branch(board);
    const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.match(html, /이어서 풀기/);
  });

  it("대조군: 5시간 49분 전에 적은 판은 아직 이어 푼다", () => {
    storage.data.set(KEY, withTop({ savedAt: Date.now() - (5 * 60 + 49) * 60 * 1000 }));
    branch(board);
    const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.match(html, /이어서 풀기/);
  });

  it("버려진 값으로 시작하면 요청을 보내 새 판을 연다", async () => {
    storage.data.set(KEY, withQ({ answered: 5, total: 5 }));
    replies = [STARTED];
    await pressIdle(board);
    assert.equal(sent[0]?.action, "start");
    assert.deepEqual(stored(), { token: "r-1", question: Q1, correct: 0, graduated: 0 });
  });
});

/* ---- 7. 새로 시작·복제 탭·시계 경계 ---- */

describe("복습 이어 풀기 - '새로 시작' 과 겹치는 조작", () => {
  const board = () => ReviewBoard({ due: DUE, userId: 7 });

  beforeEach(() => {
    storage.data.set(KEY, JSON.stringify(SAVED));
  });

  /** 시작 화면 카드를 부른다(IdleCard 를 직접 불러 버튼을 꺼낼 수 있게). */
  function idleCard(): unknown {
    const idle = branch(board);
    assert.equal(typeof idle.props.onResume, "function", "시작 화면이 아니다");
    return (idle.type as (p: unknown) => unknown)(idle.props);
  }

  /** 응답을 나중에 풀어주는 자리. json() 이 이 약속을 기다린다. */
  function deferred<T>() {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>((r) => (resolve = r));
    return { promise, resolve };
  }

  it("여는 중에 '새로 시작' 을 또 눌러도 요청은 하나다", async () => {
    const card = idleCard();
    const again = findNamed(card, "새로 시작");
    assert.ok(again);
    const late = deferred<ReviewStarted>();
    replies = [late.promise];
    const first = (again.props.onClick as () => Promise<void>)();
    const second = (again.props.onClick as () => Promise<void>)();
    late.resolve(STARTED);
    await Promise.all([first, second]);
    await settle();
    assert.equal(sent.length, 1, "busy 중 두 번째 새 판 요청이 나갔다");
    assert.deepEqual(stored(), { token: "r-1", question: Q1, correct: 0, graduated: 0 });
  });

  it("여는 중에는 '이어서 풀기' 와 '새로 시작' 이 둘 다 막혀 있다", async () => {
    const again = findNamed(idleCard(), "새로 시작");
    const late = deferred<ReviewStarted>();
    replies = [late.promise];
    const pending = (again!.props.onClick as () => Promise<void>)();

    // 요청이 떠 있는 동안 다시 그린 시작 화면.
    const card = idleCard();
    const html = draw(card);
    const buttons = html.match(/<button[^>]*>[^<]*<\/button>/g) ?? [];
    assert.ok(buttons.length >= 2, html);
    // class 의 "disabled:opacity-50" 에 걸리지 않게 속성으로 본다.
    for (const b of buttons) assert.match(b, / disabled=""/, `막히지 않은 버튼: ${b}`);

    late.resolve(STARTED);
    await pending;
    await settle();
  });

  for (const [label, reply] of [
    ["500", { fail: 500, detail: "알 수 없는 오류가 발생했습니다." }],
    ["400(복습할 것이 없음)", { fail: 400, detail: "복습할 것이 없습니다. 문제를 더 풀어보세요." }],
    ["네트워크 실패", new TypeError("Failed to fetch")],
  ] as const) {
    it(`'새로 시작' 이 ${label} 로 실패하면 적어 둔 판은 그대로 이어 풀 수 있다`, async () => {
      const before = storage.data.get(KEY);
      const again = findNamed(idleCard(), "새로 시작");
      replies = [reply];
      await (again!.props.onClick as () => Promise<void>)();
      await settle();

      assert.equal(storage.data.get(KEY), before, "새 판을 못 열었는데 옛 판이 바뀌었다");
      const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
      assert.match(html, /이어서 풀기/);
      const shown = reply instanceof Error ? reply.message : reply.detail;
      assert.ok(html.includes(shown), "실패 문구가 안 보인다");

      // 이어 풀면 오류 문구가 걷히고 적어 둔 토큰으로 답한다.
      await pressIdle(board);
      const play = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
      assert.ok(!play.includes(shown), "이어 푼 문제 화면에 앞 오류가 남았다");
      replies = [answer(true, q("fetch", 50, 4, 5), "r-4")];
      await pick(board, SAVED.question.choices[0].id);
      assert.equal(sent.at(-1)?.token, "r-saved");
    });
  }

  it("이어 풀다 400 으로 돌아온 시작 화면에는 '새로 시작' 이 없고 '시작' 하나다", async () => {
    await pressIdle(board);
    replies = [{ fail: 400, detail: "이미 처리한 답입니다." }];
    await pick(board, SAVED.question.choices[0].id);
    const html = draw(idleCard());
    assert.doesNotMatch(html, /<button[^>]*>(새로 시작|이어서 풀기)<\/button>/);
    assert.match(html, /<button[^>]*>시작<\/button>/);
  });

  it("이어 풀기로 답하면 적은 시각이 새로 찍힌다 - 토큰을 서버가 다시 서명하므로", async () => {
    const old = Date.now() - 5 * HOUR;
    storage.data.set(KEY, JSON.stringify({ ...SAVED, savedAt: old }));
    await pressIdle(board);
    replies = [answer(true, q("fetch", 50, 4, 5), "r-4")];
    const before = Date.now();
    await pick(board, SAVED.question.choices[0].id);
    const savedAt = JSON.parse(storage.data.get(KEY) as string).savedAt;
    assert.ok(savedAt >= before, "답한 뒤에도 옛 시각이라 5시간 50분에 멀쩡한 판을 버린다");
  });

  it("떠난 사이 늦은 응답이 다음 토큰을 적었으면, 그 전에 그려진 '이어서 풀기' 도 그 토큰으로 편다", async () => {
    await pressIdle(board);
    const play = branch(board);
    const late = deferred<ReviewAnswered>();
    replies = [late.promise];
    const pending = (play.props.onPick as (id: number) => Promise<void>)(
      SAVED.question.choices[0].id,
    );
    // 화면을 떠났다가(정리 함수) 곧장 돌아와 새 보드가 시작 화면을 그린다.
    for (const run of effects) (run() as (() => void) | undefined)?.();
    slots = [];
    const card = idleCard();
    const resume = findNamed(card, "이어서 풀기");
    assert.ok(resume, "돌아온 시작 화면에 이어서 풀기가 없다");

    // 이제 앞 답의 응답이 와서 다음 토큰을 적는다.
    const Q4 = q("fetch", 50, 4, 5);
    late.resolve(answer(true, Q4, "r-4"));
    await pending;
    await settle();
    assert.equal(stored().token, "r-4");

    // 그린 순간의 버튼을 누른다. 그린 때의 판(r-saved)이 아니라 지금 적힌
    // 판으로 열어야 한다 - 옛 토큰이면 이미 쓴 순번이라 답하자마자 400 이다.
    (resume.props.onClick as () => void)();
    replies = [answer(true, null, null)];
    await pick(board, Q4.choices[0].id);
    assert.equal(sent.at(-1)?.token, "r-4", "그린 때의 옛 토큰으로 이어 풀었다");
  });

  for (const [label, lateReply] of [
    ["성공", answer(true, q("fetch", 50, 4, 5), "r-4")],
    ["400", { fail: 400, detail: "이미 처리한 답입니다." }],
  ] as const) {
    it(`떠난 사이 '새로 시작' 했으면 옛 판의 늦은 ${label} 응답이 새 판을 덮거나 지우지 않는다`, async () => {
      await pressIdle(board);
      const play = branch(board);
      const late = deferred<unknown>();
      replies = [late.promise];
      const pending = (play.props.onPick as (id: number) => Promise<void>)(
        SAVED.question.choices[0].id,
      );
      for (const run of effects) (run() as (() => void) | undefined)?.();

      // 돌아와서 새로 시작한다. 탭에는 새 판(r-1)이 적힌다.
      slots = [];
      const again = findNamed(idleCard(), "새로 시작");
      assert.ok(again);
      replies.push(STARTED);
      const opening = (again.props.onClick as () => Promise<void>)();
      await opening;
      await settle();
      assert.equal(stored().token, "r-1");

      // 옛 판의 응답이 이제야 온다.
      late.resolve(lateReply);
      await pending;
      await settle();
      assert.equal(stored()?.token, "r-1", "옛 판의 늦은 응답이 새 판을 건드렸다");
    });
  }
});

describe("복습 이어 풀기 - 탭 복제", () => {
  it("복제한 두 탭이 같은 판을 이어 풀면 먼저 답한 쪽만 이어지고, 늦은 쪽은 자기 탭만 지운다", async () => {
    const board = () => ReviewBoard({ due: DUE, userId: 7 });
    const tabA = storage;
    tabA.data.set(KEY, JSON.stringify(SAVED));
    const tabB = new FakeStorage();
    tabB.data.set(KEY, tabA.data.get(KEY) as string);

    // 탭 A 가 먼저 답한다.
    await pressIdle(board);
    const Q4 = q("fetch", 50, 4, 5);
    replies = [answer(true, Q4, "r-4")];
    await pick(board, SAVED.question.choices[0].id);
    assert.equal(stored().token, "r-4");

    // 탭 B 는 복제 시점의 판을 편다. 서버는 같은 순번이라 400 을 준다.
    slots = [];
    storage = tabB;
    g.window = { sessionStorage: tabB };
    await pressIdle(board);
    assert.equal(sent.length, 1, "이어 풀기가 요청을 보냈다");
    replies = [{ fail: 400, detail: "이미 처리한 답입니다." }];
    await pick(board, SAVED.question.choices[0].id);
    assert.equal(sent.at(-1)?.token, "r-saved");

    assert.equal(tabB.data.has(KEY), false, "막다른 판이 탭 B 에 남았다");
    assert.equal(JSON.parse(tabA.data.get(KEY) as string).token, "r-4", "탭 A 의 판이 건드려졌다");
    const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.match(html, /더 이어갈 수 없습니다/);
  });
});

describe("복습 이어 풀기 - 적은 시각의 경계", () => {
  const board = () => ReviewBoard({ due: DUE, userId: 7 });
  const KEEP = (6 * 60 - 10) * 60 * 1000;
  const NOW = 1_800_000_000_000;

  function shownAt(savedAt: unknown): string {
    storage.data.set(KEY, JSON.stringify({ ...SAVED, savedAt }));
    const clock = mock.method(Date, "now", () => NOW);
    try {
      branch(board);
      return draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    } finally {
      clock.mock.restore();
    }
  }

  for (const [label, savedAt, resumable] of [
    ["방금(나이 0)", NOW, true],
    ["창 끝 1ms 안쪽", NOW - KEEP + 1, true],
    ["정확히 창 끝", NOW - KEEP, false],
    ["1ms 앞날", NOW + 1, false],
    ["0(1970)", 0, false],
    ["아주 큰 수", 1e300, false],
    ["아주 작은 수", -1e300, false],
    ["NaN 이 JSON 에서 null 로", NaN, false],
  ] as const) {
    it(`${label} -> ${resumable ? "이어서 풀기" : "시작"}`, () => {
      const html = shownAt(savedAt);
      if (resumable) assert.match(html, /이어서 풀기/);
      else assert.match(html, /<button[^>]*>시작<\/button>/);
    });
  }
});

describe("복습 이어 풀기 - 보낸 토큰으로 가르는 적기가 정상 흐름을 막지 않는다", () => {
  const board = () => ReviewBoard({ due: DUE, userId: 7 });
  const KEEP = (6 * 60 - 10) * 60 * 1000;
  const NOW = 1_800_000_000_000;
  const MIN = 60 * 1000;

  /** 시계를 at 에 두고 run 을 부른다. 끝나면 되돌린다. */
  async function at<T>(time: number, run: () => Promise<T>): Promise<T> {
    const clock = mock.method(Date, "now", () => time);
    try {
      return await run();
    } finally {
      clock.mock.restore();
    }
  }

  const savedAt = () => JSON.parse(storage.data.get(KEY) as string).savedAt as number;

  it("살아 있는 화면에서 다섯 문제를 끝까지 연속으로 풀면 매번 적고 마지막에 지운다", async () => {
    const qs = [0, 1, 2, 3, 4].map((i) => q(`w${i}`, 100 + i * 10, i, 5));
    replies = [{ token: "t-0", question: qs[0] }];
    await pressIdle(board);
    for (let i = 0; i < 4; i++) {
      replies = [answer(i % 2 === 0, qs[i + 1], `t-${i + 1}`)];
      await pick(board, qs[i].choices[0].id);
      assert.deepEqual(
        stored(),
        { token: `t-${i + 1}`, question: qs[i + 1], correct: Math.floor(i / 2) + 1, graduated: 0 },
        `${i + 1}번째 답 뒤 적은 값이 다르다`,
      );
    }
    replies = [answer(true, null, null)];
    await pick(board, qs[4].choices[0].id);
    assert.equal(storage.data.has(KEY), false, "끝난 판이 남았다");
    assert.deepEqual(
      sent.map((b) => b.token),
      [undefined, "t-0", "t-1", "t-2", "t-3", "t-4"],
    );
  });

  it("이어 풀기 직후 곧장 답해도 적히고, 그대로 끝까지 이어진다", async () => {
    storage.data.set(KEY, JSON.stringify(SAVED));
    await pressIdle(board);
    assert.equal(sent.length, 0, "이어 풀기가 요청을 보냈다");

    const Q4 = q("fetch", 50, 4, 5);
    replies = [answer(true, Q4, "r-4", true)];
    await pick(board, SAVED.question.choices[0].id);
    assert.deepEqual(stored(), { token: "r-4", question: Q4, correct: 2, graduated: 2 });

    replies = [answer(false, null, null)];
    await pick(board, Q4.choices[1].id);
    assert.equal(storage.data.has(KEY), false);
    assert.deepEqual(sent.map((b) => b.token), ["r-saved", "r-4"]);
  });

  it("켜 둔 화면에서 5시간 55분 뒤 답하면(저장값은 KEEP 을 넘었고 토큰은 산다) 그래도 적는다", async () => {
    replies = [STARTED];
    await at(NOW, () => pressIdle(board));
    assert.equal(savedAt(), NOW);

    // 탭을 켜 둔 채 5시간 55분이 흘렀다. 저장값은 이어 풀기로는 이미 못 쓴다.
    const later = NOW + 6 * 60 * MIN - 5 * MIN;
    assert.ok(later - NOW > KEEP);
    replies = [answer(true, Q2, "r-2")];
    await at(later, () => pick(board, Q1.choices[0].id));
    assert.deepEqual(
      stored(),
      { token: "r-2", question: Q2, correct: 1, graduated: 0 },
      "저장값의 나이만 늙었는데 다음 토큰을 안 적었다",
    );
    assert.equal(savedAt(), later, "적은 시각이 새로 찍히지 않았다");

    // 그 뒤 새로고침하면 이어 풀린다.
    slots = [];
    const html = await at(later + MIN, async () => {
      branch(board);
      return draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    });
    assert.match(html, /이어서 풀기/);
  });

  it("켜 둔 화면에서 5시간 55분 뒤 마지막 답을 하면 늙은 저장값도 지운다", async () => {
    replies = [{ token: "r-1", question: q("only", 10, 0, 1) }];
    await at(NOW, () => pressIdle(board));
    replies = [answer(true, null, null)];
    await at(NOW + 355 * MIN, () => pick(board, 10));
    assert.equal(storage.data.has(KEY), false, "끝난 판이 남았다");
  });

  it("켜 둔 화면에서 5시간 55분 뒤 400 을 받으면 늙은 저장값도 지운다", async () => {
    replies = [STARTED];
    await at(NOW, () => pressIdle(board));
    replies = [{ fail: 400, detail: "판이 만료됐습니다." }];
    await at(NOW + 355 * MIN, () => pick(board, Q1.choices[0].id));
    assert.equal(storage.data.has(KEY), false, "막다른 판이 남았다");
  });

  it("5시간 49분 된 판을 이어 풀고 2분 뒤(저장값은 KEEP 을 넘음) 답해도 적는다", async () => {
    storage.data.set(KEY, JSON.stringify({ ...SAVED, savedAt: NOW - KEEP + MIN }));
    await at(NOW, () => pressIdle(board));
    assert.equal(sent.length, 0, "이어 풀지 않고 새 판을 열었다");

    const Q4 = q("fetch", 50, 4, 5);
    replies = [answer(true, Q4, "r-4")];
    await at(NOW + 2 * MIN, () => pick(board, SAVED.question.choices[0].id));
    assert.equal(stored().token, "r-4", "이어 푼 판의 다음 토큰을 안 적었다");
    assert.equal(savedAt(), NOW + 2 * MIN);
  });

  it("'이어서 풀기' 를 그린 뒤 누르기 전에 저장값이 창을 넘기면 옛 판을 펴지 않고 새 판을 연다", async () => {
    storage.data.set(KEY, JSON.stringify({ ...SAVED, savedAt: NOW - KEEP + 1000 }));
    const card = await at(NOW, async () => {
      const idle = branch(board);
      return (idle.type as (p: unknown) => unknown)(idle.props);
    });
    const resume = findNamed(card, "이어서 풀기");
    assert.ok(resume, "그릴 때는 이어서 풀기였어야 한다");

    replies = [STARTED];
    await at(NOW + 2000, async () => {
      await (resume.props.onClick as () => unknown)();
      await settle();
    });
    assert.deepEqual(sent, [{ action: "start" }], "만료된 판을 요청 없이 폈다");
    assert.equal(stored().token, "r-1");
  });

  it("탭 저장값이 판이 아닌 글로 바뀌어 있어도 답의 응답은 화면을 다음 문제로 넘긴다", async () => {
    replies = [STARTED];
    await pressIdle(board);
    storage.data.set(KEY, "not json");
    replies = [answer(true, Q2, "r-2")];
    await pick(board, Q1.choices[0].id);
    const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.ok(html.includes(Q2.prompt), "저장값 때문에 화면이 멈췄다");
  });
});
