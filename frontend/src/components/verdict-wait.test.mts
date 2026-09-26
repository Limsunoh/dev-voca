/**
 * 마지막 답에서 판정 연출이 끝난 뒤에 결과 화면으로 넘어가는지 실제로 돌려 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 결함은 이렇다.
 *
 *   곧바로 결과로 넘김        결과 화면 가운데 글자 위로 사람·축포가 겹친다
 *   중간 답에서도 기다림      "답하면 곧바로 다음 문제" 가 1초씩 느려진다
 *   복습 오답에서 기다림      연출이 없는 답인데 빈 화면을 1초 본다
 *   기다리는 동안 보기가 열림  마지막 문제에 답이 한 번 더 나간다
 *   기다리는 사이 화면이 떠남  사라진 보드의 상태를 건드린다
 *   복습 판을 늦게 지움       기다리는 사이 떠나면 끝난 판이 탭에 남는다
 *   연출 길이를 잘못 읽음      "1s" 를 1ms 로, 움직임 줄이기에서도 1초 멈춤
 *
 * 방식은 review-resume.test.mts 와 같다 - react 훅만 대역으로 바꾸고 보드가
 * 넘긴 onPick 을 진짜로 부른다. 여기에 더해 **setTimeout 을 가로채** 0 보다
 * 긴 타이머는 붙들어 둔다. 그래야 "기다리는 중" 을 멈춰 놓고 들여다볼 수
 * 있다. 연출 길이는 window.matchMedia 와 getComputedStyle 대역으로 정한다.
 */
import assert from "node:assert/strict";
import { after, afterEach, beforeEach, describe, it, mock } from "node:test";

import type { DailyAnswered, DailyStatus, StudyProgress } from "@/lib/api/daily";
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
    useSyncExternalStore<T>(_subscribe: unknown, getSnapshot: () => T) {
      return getSnapshot();
    },
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { createElement } = realReact;
const { DailyStudyBoard } = await import("./DailyStudyBoard");
const { ReviewBoard } = await import("./ReviewBoard");
const { verdictMs } = await import("./Reaction");

/* ---- 브라우저 대역: 연출 길이 ---- */

const g = globalThis as unknown as {
  window?: unknown;
  document?: unknown;
  getComputedStyle?: unknown;
};
const saved = {
  window: g.window,
  document: g.document,
  getComputedStyle: g.getComputedStyle,
};

/** --duration-verdict 의 계산값. 브라우저는 앞뒤 공백을 붙여 줄 수 있다. */
let cssValue = "1000ms";
/** prefers-reduced-motion: reduce 인가. */
let reduce = false;
/** getComputedStyle 이 던지게 한다. */
let styleThrows = false;

class FakeStorage {
  data = new Map<string, string>();
  getItem(key: string): string | null {
    return this.data.has(key) ? (this.data.get(key) as string) : null;
  }
  setItem(key: string, value: string): void {
    this.data.set(key, String(value));
  }
  removeItem(key: string): void {
    this.data.delete(key);
  }
}
let storage: FakeStorage;

function installBrowser() {
  storage = new FakeStorage();
  g.window = {
    sessionStorage: storage,
    matchMedia: (query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion: reduce"),
    }),
  };
  g.document = { documentElement: { tag: "html" } };
  g.getComputedStyle = (el: { tag?: string }) => {
    if (styleThrows) throw new Error("getComputedStyle 실패");
    // 뿌리 요소에서 읽어야 한다. 다른 요소면 빈 값을 준다.
    return {
      getPropertyValue: (name: string) =>
        el?.tag === "html" && name === "--duration-verdict" ? cssValue : "",
    };
  };
}

/* ---- 타이머 대역 ---- */

const realSetTimeout = globalThis.setTimeout;
/** 붙들어 둔 타이머. 0 보다 긴 것만 여기 온다. */
let held: { ms: number; run: () => void }[] = [];

function holdLongTimers() {
  globalThis.setTimeout = ((fn: () => void, ms?: number, ...rest: unknown[]) => {
    if (ms && ms > 0) {
      held.push({ ms, run: () => fn(...(rest as [])) });
      return 0 as unknown as ReturnType<typeof setTimeout>;
    }
    return realSetTimeout(fn, ms, ...rest);
  }) as typeof setTimeout;
}

/** 붙든 타이머를 모두 풀고 뒤따르는 약속까지 흘린다. */
async function release() {
  // 풀고 나서 또 붙드는 경우(두 번 기다리게 바뀐 코드)까지 다 흘린다. 한 번만
  // 풀면 그런 변경이 실패가 아니라 무한 대기로 나타난다.
  for (let round = 0; round < 10 && held.length > 0; round++) {
    const now = held;
    held = [];
    for (const t of now) t.run();
    await settle();
  }
}

/* ---- 중계 대역 ---- */

const realFetch = globalThis.fetch;
let replies: unknown[] = [];
let sent: Record<string, unknown>[] = [];

after(() => {
  globalThis.fetch = realFetch;
  globalThis.setTimeout = realSetTimeout;
  for (const [key, value] of Object.entries(saved)) {
    if (value === undefined) delete (g as Record<string, unknown>)[key];
    else (g as Record<string, unknown>)[key] = value;
  }
});

// 테스트 러너도 같은 전역 setTimeout 을 쓸 수 있어, 붙드는 것은 테스트 안에서만.
afterEach(() => {
  globalThis.setTimeout = realSetTimeout;
});

beforeEach(() => {
  slots = [];
  replies = [];
  sent = [];
  held = [];
  cssValue = "1000ms";
  reduce = false;
  styleThrows = false;
  installBrowser();
  holdLongTimers();
  globalThis.fetch = (async (_url: unknown, init?: { body?: string }) => {
    sent.push(JSON.parse(init?.body ?? "{}"));
    const body = replies.shift();
    assert.ok(body, "준비한 것보다 요청이 많다");
    return { ok: true, status: 200, json: async () => body } as Response;
  }) as typeof fetch;
});

/* ---- 보드 다루기 ---- */

type Node = { type?: unknown; props: Record<string, unknown> };

/** 보드를 부르고 이펙트를 돌린 뒤 본문 가지를 꺼낸다. */
function branch(board: () => unknown): Node {
  cursor = 0;
  effects = [];
  const tree = board() as { props: { children: unknown[] } };
  for (const run of effects) run();
  return tree.props.children[1] as Node;
}

/** 이펙트를 안 돌리고 본문 가지만 본다. 떠난 화면을 들여다볼 때 쓴다. */
function peek(board: () => unknown): Node {
  cursor = 0;
  effects = [];
  const tree = board() as { props: { children: unknown[] } };
  return tree.props.children[1] as Node;
}

/** 이펙트 정리 함수를 부른다 - 화면이 사라진 것과 같다. */
function leave(board: () => unknown) {
  cursor = 0;
  effects = [];
  board();
  for (const run of effects) (run() as (() => void) | undefined)?.();
}

function draw(element: unknown): string {
  cursor = 0;
  return renderToStaticMarkup(element as never);
}

async function settle() {
  for (let i = 0; i < 5; i++) await Promise.resolve();
  await new Promise((r) => realSetTimeout(r, 0));
}

const isPlay = (node: Node) => typeof node.props.onPick === "function";
const isDone = (node: Node) => !isPlay(node) && ("study" in node.props || "onAgain" in node.props);
/** 누를 수 있는 보기 버튼 수. */
const liveChoices = (html: string) =>
  [...html.matchAll(/<li><button([^>]*)>/g)].filter((m) => !/\sdisabled=""/.test(m[1])).length;

/* ---- 자료 ---- */

function question(prompt: string, base: number): RoundQuestion {
  return {
    kind: "meaning",
    kind_label: "뜻 고르기",
    question: `질문-${prompt}`,
    prompt,
    category: "git",
    category_label: "Git",
    choices: [0, 1, 2, 3].map((i) => ({ id: base + i, text: `보기-${prompt}-${i}` })),
  };
}

const FIRST = question("commit", 10);
const NEXT = question("rebase", 20);

/* ================================================================ */

describe("verdictMs - 연출 길이 읽기", () => {
  const cases: [string, number][] = [
    ["1000ms", 1000],
    ["1s", 1000],
    ["1.5s", 1500],
    ["0.25s", 250],
    ["  700ms ", 700],
    ["1e3ms", 1000],
    ["0ms", 0],
    ["0s", 0],
    ["", 0],
    ["   ", 0],
    ["abc", 0],
    ["-300ms", 0],
    ["-1s", 0],
    ["Infinity", 0],
    ["NaN", 0],
    // 대소문자를 안 가린다. "500MS" 를 초로 읽으면 8분을 잠근다.
    ["500MS", 500],
    ["1S", 1000],
    // 단위가 없으면 ms 로 본다.
    ["1000", 1000],
    // 상한 3초. 잘못 적은 값이 화면을 오래 잠그지 않게 한다.
    ["10s", 3000],
    ["1000px", 1000],
    ["5000ms", 3000],
  ];
  for (const [raw, want] of cases) {
    it(`"${raw}" 는 ${want}ms`, () => {
      cssValue = raw;
      assert.equal(verdictMs(), want);
    });
  }

  it("움직임 줄이기면 값과 무관하게 0 이다", () => {
    reduce = true;
    cssValue = "1000ms";
    assert.equal(verdictMs(), 0);
  });

  it("window 가 없으면(서버 렌더) 던지지 않고 0 이다", () => {
    delete g.window;
    assert.equal(verdictMs(), 0);
  });

  it("matchMedia 가 없으면 던지지 않고 0 이다", () => {
    g.window = {};
    assert.equal(verdictMs(), 0);
  });

  it("getComputedStyle 이 던지면 0 이다", () => {
    styleThrows = true;
    assert.equal(verdictMs(), 0);
  });

  it("값을 부를 때마다 새로 읽는다(한 판이 덮어쓴 값을 따른다)", () => {
    cssValue = "1000ms";
    assert.equal(verdictMs(), 1000);
    cssValue = "400ms";
    assert.equal(verdictMs(), 400);
  });
});

/* ---- 일일공부 ---- */

function progress(answered: number, total = 2): StudyProgress {
  return {
    length: "5m",
    total,
    answered,
    correct: 0,
    score: 0,
    bonus: 0,
    done: false,
    chunk_size: 3,
    chunk_count: 1,
    chunk_index: 0,
  };
}

const PLAYING: DailyStatus = {
  lengths: [],
  today: progress(0),
  token: "tok-1",
  question: FIRST,
  learning: [],
};

function dailyAnswer(correct: boolean, last: boolean): DailyAnswered {
  return {
    result: {
      correct,
      skipped: false,
      in_time: true,
      score: correct ? 1 : 0,
      elapsed_ms: 1000,
      answer_type: "word",
      answer_text: "commit",
      answer_extra: "변경을 기록하기",
    },
    token: last ? null : "tok-2",
    question: last ? null : NEXT,
    finished: last,
    study: progress(last ? 2 : 1),
    learning: [],
  };
}

describe("일일공부 - 마지막 답은 연출이 끝난 뒤 결과로", () => {
  const board = () => DailyStudyBoard({ status: PLAYING });

  /**
   * 답하고, 그 순간 붙든 타이머 길이들을 돌려준다. 돌려주기 전에 붙든 것을
   * 풀어 끝까지 흘린다 - 안 풀면 기다리면 안 되는 자리에서 기다리게 만든
   * 변경이 실패가 아니라 멈춤(무한 대기)으로 나타난다.
   */
  async function answerFirst(reply: DailyAnswered): Promise<number[]> {
    const play = branch(board);
    assert.ok(isPlay(play), "시작이 문제 가지가 아니다");
    replies = [reply];
    const pending = (play.props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    const waited = held.map((t) => t.ms);
    await release();
    await pending;
    return waited;
  }

  /** onPick 을 부르되 끝나기를 기다리지 않는다 - 기다리는 중을 보려고. */
  async function answerHeld(reply: DailyAnswered): Promise<{ pending: Promise<void> }> {
    const play = branch(board);
    replies = [reply];
    const pending = (play.props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    // 약속을 그대로 돌려주면 async 가 풀어 버려 기다리는 중을 못 본다. 싸서 준다.
    return { pending };
  }

  it("중간 답에서는 안 기다리고 곧바로 다음 문제다", async () => {
    const waited = await answerFirst(dailyAnswer(true, false));
    assert.deepEqual(waited, [], "중간 답인데 타이머를 걸었다");
    const now = branch(board);
    assert.ok(isPlay(now));
    assert.equal((now.props.question as RoundQuestion).prompt, NEXT.prompt);
    assert.equal(now.props.busy, false);
  });

  for (const correct of [true, false]) {
    it(`마지막 답(${correct ? "정답" : "오답"})이면 연출 길이만큼 기다린다`, async () => {
      const { pending } = await answerHeld(dailyAnswer(correct, true));
      assert.deepEqual(held.map((t) => t.ms), [1000], "연출 길이만큼 기다리지 않는다");

      // 기다리는 동안은 아직 문제 화면이고 보기가 막혀 있다.
      const waiting = branch(board);
      assert.ok(isPlay(waiting), "기다리는 중인데 벌써 결과 화면이다");
      assert.equal(waiting.props.busy, true, "기다리는 중인데 보기가 열려 있다");
      const html = draw(createElement(DailyStudyBoard, { status: PLAYING }));
      assert.equal(liveChoices(html), 0, "기다리는 중에 누를 수 있는 보기가 있다");
      // 방금 답한 문제가 "앞 문제" 결과 줄 아래 그대로 남으면 안 된다.
      assert.equal((html.match(/<li><button/g) ?? []).length, 0, "기다리는 중에 문제 카드가 남았다");
      // 결과 줄은 이 답의 판정을 보인다.
      assert.match(html, correct ? /정답/ : /오답 · commit/);

      // 기다리는 중에 한 번 더 눌러도 요청이 안 나간다.
      await (waiting.props.onPick as (id: number) => Promise<void>)(FIRST.choices[1].id);
      await settle();
      assert.equal(sent.length, 1, "기다리는 중에 답이 한 번 더 나갔다");

      await release();
      await pending;
      const done = branch(board);
      assert.ok(isDone(done), "기다린 뒤 결과 화면으로 안 넘어갔다");
      assert.equal((done.props.study as StudyProgress).answered, 2);
    });
  }

  it("연출 길이를 CSS 에서 읽는다(1s 이면 1000, 2s 이면 2000)", async () => {
    cssValue = "2s";
    const { pending } = await answerHeld(dailyAnswer(true, true));
    assert.deepEqual(held.map((t) => t.ms), [2000]);
    await release();
    await pending;
    assert.ok(isDone(branch(board)));
  });

  it("움직임 줄이기면 안 붙들고 곧바로 결과다", async () => {
    reduce = true;
    const waited = await answerFirst(dailyAnswer(true, true));
    assert.deepEqual(waited, []);
    assert.ok(isDone(branch(board)));
  });

  it("기다리는 사이 화면이 사라지면 결과로 안 바꾼다", async () => {
    const { pending } = await answerHeld(dailyAnswer(true, true));
    assert.equal(held.length, 1);
    leave(board);
    await release();
    await pending;
    // 떠난 뒤 phase 를 done 으로 바꾸지 않았다.
    assert.ok(isPlay(peek(board)), "떠난 화면의 phase 를 바꿨다");
  });
});

/* ---- 복습 ---- */

const DUE = { due: 5, round_size: 20, graduate_streak: 2 };
const KEY = "review-round-7";

function rq(q: RoundQuestion, answered: number): ReviewQuestion {
  return { ...q, answered, total: 2 };
}

const STARTED: ReviewStarted = { token: "r-1", question: rq(FIRST, 0) };

function reviewAnswer(correct: boolean, last: boolean): ReviewAnswered {
  return {
    result: {
      correct,
      streak: correct ? 1 : 0,
      graduated: false,
      answer_type: "word",
      answer_text: "commit",
      answer_extra: "변경을 기록하기",
    },
    token: last ? null : "r-2",
    question: last ? null : rq(NEXT, 1),
    finished: last,
  } as ReviewAnswered;
}

describe("복습 - 마지막 정답만 연출이 끝난 뒤 결과로", () => {
  const board = () => ReviewBoard({ due: DUE, userId: 7 });

  async function playing(): Promise<Node> {
    const idle = branch(board);
    replies = [STARTED];
    await (idle.props.onStart as () => Promise<void>)();
    await settle();
    const play = branch(board);
    assert.ok(isPlay(play), "시작했는데 문제 가지가 아니다");
    assert.ok(storage.data.has(KEY), "시작한 판을 탭에 안 적었다");
    return play;
  }

  async function answerHeld(reply: ReviewAnswered): Promise<{ pending: Promise<void> }> {
    const play = await playing();
    replies = [reply];
    const pending = (play.props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    // 약속을 그대로 돌려주면 async 가 풀어 버려 기다리는 중을 못 본다. 싸서 준다.
    return { pending };
  }

  it("중간 정답에서는 안 기다리고 곧바로 다음 문제다", async () => {
    const { pending } = await answerHeld(reviewAnswer(true, false));
    // 타이머를 풀기 전에 이미 다음 문제여야 한다. 풀기는 뒷정리다.
    assert.equal(held.length, 0, "중간 답인데 타이머를 걸었다");
    const now = branch(board);
    assert.ok(isPlay(now));
    assert.equal((now.props.question as RoundQuestion).prompt, NEXT.prompt);
    await release();
    await pending;
  });

  it("마지막 오답은 안 기다리고 곧바로 결과다(연출이 없다)", async () => {
    const { pending } = await answerHeld(reviewAnswer(false, true));
    assert.equal(held.length, 0, "연출 없는 오답인데 기다린다");
    assert.ok(isDone(branch(board)));
    await release();
    await pending;
    assert.equal(storage.data.has(KEY), false, "끝난 판이 탭에 남았다");
  });

  it("마지막 정답은 기다리는 동안 문제 화면·보기 막힘이고, 뒤에 결과다", async () => {
    const { pending } = await answerHeld(reviewAnswer(true, true));
    assert.deepEqual(held.map((t) => t.ms), [1000]);

    const waiting = branch(board);
    assert.ok(isPlay(waiting), "기다리는 중인데 벌써 결과 화면이다");
    assert.equal(waiting.props.busy, true);
    const html = draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));
    assert.equal(liveChoices(html), 0, "기다리는 중에 누를 수 있는 보기가 있다");
    // 방금 답한 문제가 "앞 문제" 결과 줄 아래 그대로 남으면 안 된다.
    assert.equal((html.match(/<li><button/g) ?? []).length, 0, "기다리는 중에 문제 카드가 남았다");

    await (waiting.props.onPick as (id: number) => Promise<void>)(FIRST.choices[1].id);
    await settle();
    assert.equal(sent.length, 2, "기다리는 중에 답이 한 번 더 나갔다"); // start + answer

    await release();
    await pending;
    const done = branch(board);
    assert.ok(isDone(done), "기다린 뒤 결과 화면으로 안 넘어갔다");
    assert.equal(done.props.correct, 1);
    assert.equal(done.props.answered, 1);
  });

  it("끝난 판은 기다리기 전에 이미 탭에서 지운다", async () => {
    const { pending } = await answerHeld(reviewAnswer(true, true));
    assert.equal(held.length, 1);
    // 아직 연출 중인데 탭에는 없어야 한다 - 이 사이에 떠나거나 새로고침해도
    // 끝난 판을 이어 풀라고 하지 않는다.
    assert.equal(storage.data.has(KEY), false, "기다리는 동안 끝난 판이 탭에 남았다");
    await release();
    await pending;
  });

  it("기다리는 사이 화면이 사라지면 결과로 안 바꾸고, 탭은 비어 있다", async () => {
    const { pending } = await answerHeld(reviewAnswer(true, true));
    leave(board);
    await release();
    await pending;
    assert.ok(isPlay(peek(board)), "떠난 화면의 phase 를 바꿨다");
    assert.equal(storage.data.has(KEY), false);
  });

  it("움직임 줄이기면 마지막 정답도 곧바로 결과다", async () => {
    reduce = true;
    const { pending } = await answerHeld(reviewAnswer(true, true));
    assert.equal(held.length, 0);
    assert.ok(isDone(branch(board)));
    await release();
    await pending;
  });
});

/* ================================================================
 * ending 이 새는 길. 마지막 답의 "문제 카드 비우기" 가 다음 판·다른
 * 가지·중간 답으로 번지면 문제가 안 보이는 막다른 화면이 된다.
 * ================================================================ */

/** 실패 응답을 섞을 수 있는 중계 대역. replies 에 { fail, detail } 을 넣으면 그 상태로 거절한다. */
function installFailableFetch() {
  globalThis.fetch = (async (_url: unknown, init?: { body?: string }) => {
    sent.push(JSON.parse(init?.body ?? "{}"));
    const body = replies.shift() as { fail?: number; detail?: string } | undefined;
    assert.ok(body, "준비한 것보다 요청이 많다");
    if (body.fail) {
      const detail = body.detail;
      return { ok: false, status: body.fail, json: async () => ({ detail }) } as Response;
    }
    return { ok: true, status: 200, json: async () => body } as Response;
  }) as typeof fetch;
}

/** 그려진 문제 카드의 보기 수(잠긴 것 포함). 0 이면 문제 카드가 없다. */
const cardChoices = (html: string) => (html.match(/<li><button/g) ?? []).length;

/** 트리에서 글자가 name 인 <button>. 없으면 null. */
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
  if (el.type === "button") {
    const text = el.props?.children;
    if (text === name || (Array.isArray(text) && text.includes(name))) return el;
  }
  return findNamed(el.props?.children, name);
}

describe("복습 - ending 이 다음 판에 남지 않는다", () => {
  beforeEach(installFailableFetch);

  const board = () => ReviewBoard({ due: DUE, userId: 7 });
  const html = () => draw(createElement(ReviewBoard, { due: DUE, userId: 7 }));

  function lastAnswer(extra: Partial<ReviewAnswered["result"]> = {}): ReviewAnswered {
    const a = reviewAnswer(true, true);
    return { ...a, result: { ...a.result, ...extra } } as ReviewAnswered;
  }

  async function begin(): Promise<void> {
    const idle = branch(board);
    replies = [STARTED];
    await (idle.props.onStart as () => Promise<void>)();
    await settle();
  }

  /** 새 판을 열고 마지막 정답까지 가서, 연출을 기다린 뒤 결과 화면을 돌려준다. */
  async function finishCorrect(): Promise<Node> {
    await begin();
    const play = branch(board);
    replies = [lastAnswer()];
    const pending = (play.props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    assert.equal(held.length, 1, "마지막 정답인데 기다리지 않는다");
    assert.equal(branch(board).props.ending, true, "기다리는 중인데 ending 이 꺼져 있다");
    await release();
    await pending;
    const done = branch(board);
    assert.ok(isDone(done), "기다린 뒤 결과 화면이 아니다");
    return done;
  }

  it("끝 -> '이어서 더' 로 연 새 판은 문제 카드가 보이고 보기를 누를 수 있다", async () => {
    const done = await finishCorrect();
    replies = [{ token: "r-9", question: rq(NEXT, 0) } satisfies ReviewStarted];
    await (done.props.onAgain as () => Promise<void>)();
    await settle();

    const play = branch(board);
    assert.ok(isPlay(play), "새 판이 문제 가지가 아니다");
    assert.equal(play.props.ending, false, "지난 판의 ending 이 새 판에 남았다");
    const h = html();
    assert.equal(cardChoices(h), 4, "새 판인데 문제 카드가 없다");
    assert.equal(liveChoices(h), 4, "새 판 보기가 잠겨 있다");
    assert.match(h, /보기-rebase-0/);
    // 지난 판의 결과 줄도 없어야 한다.
    assert.doesNotMatch(h, /앞 문제/);
  });

  it("끝 -> 새 판 -> 그 판의 중간 답은 곧바로 다음 문제를 그린다", async () => {
    const done = await finishCorrect();
    replies = [{ token: "r-9", question: rq(NEXT, 0) } satisfies ReviewStarted];
    await (done.props.onAgain as () => Promise<void>)();
    await settle();

    const play = branch(board);
    replies = [{ ...reviewAnswer(true, false), question: rq(FIRST, 1) } as ReviewAnswered];
    const pending = (play.props.onPick as (id: number) => Promise<void>)(NEXT.choices[0].id);
    await settle();
    assert.equal(held.length, 0, "중간 답인데 기다린다");
    assert.equal(branch(board).props.ending, false);
    const h = html();
    assert.equal(liveChoices(h), 4, "중간 답 뒤 다음 문제 보기가 없다");
    assert.match(h, /보기-commit-0/);
    await release();
    await pending;
  });

  it("끝 -> 새 판 시작이 실패하면 결과 화면에 오류를 보이고, 다시 누르면 문제가 보인다", async () => {
    const done = await finishCorrect();
    replies = [{ fail: 503, detail: "잠시 뒤 다시" }];
    await (done.props.onAgain as () => Promise<void>)();
    await settle();
    const still = branch(board);
    assert.ok(isDone(still), "시작 실패인데 결과 화면을 떠났다");
    assert.match(html(), /잠시 뒤 다시/);

    replies = [{ token: "r-9", question: rq(NEXT, 0) } satisfies ReviewStarted];
    await (still.props.onAgain as () => Promise<void>)();
    await settle();
    assert.equal(branch(board).props.ending, false);
    assert.equal(liveChoices(html()), 4, "다시 연 판에 문제 카드가 없다");
  });

  it("끝 -> 새 판 도중 새로고침 -> 이어서 풀기로 연 판은 문제 카드가 보인다", async () => {
    const done = await finishCorrect();
    replies = [{ token: "r-9", question: rq(NEXT, 0) } satisfies ReviewStarted];
    await (done.props.onAgain as () => Promise<void>)();
    await settle();
    assert.ok(storage.data.has(KEY), "새 판을 탭에 안 적었다");

    // 새로고침: 같은 탭 저장소, 새 보드.
    slots = [];
    const idle = branch(board);
    assert.equal(typeof idle.props.onResume, "function", "새로고침 뒤 시작 화면이 아니다");
    const card = (idle.type as (p: unknown) => unknown)(idle.props);
    const resume = findNamed(card, "이어서 풀기");
    assert.ok(resume, "이어서 풀기 버튼이 없다");
    (resume.props.onClick as () => void)();
    await settle();

    const play = branch(board);
    assert.ok(isPlay(play));
    assert.equal(play.props.ending, false);
    assert.equal(liveChoices(html()), 4, "이어 푼 판에 문제 카드가 없다");
  });

  it("끝난 뒤 새로고침하면 끝난 판을 이어 풀라고 하지 않는다", async () => {
    await finishCorrect();
    slots = [];
    const idle = branch(board);
    const card = (idle.type as (p: unknown) => unknown)(idle.props);
    assert.equal(findNamed(card, "이어서 풀기"), null, "끝난 판을 이어 풀라고 한다");
    assert.ok(findNamed(card, "시작"), "시작 버튼이 없다");
  });

  it("기다리는 중 화면: 결과 줄·진행은 보이고, 문제 카드·지난 오류는 없다", async () => {
    await begin();

    // 마지막 답이 한 번 실패한다. ending 은 안 켜지고 문제·오류가 그대로다.
    replies = [{ fail: 500, detail: "채점 서버가 바쁩니다" }];
    await (branch(board).props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    let h = html();
    assert.match(h, /채점 서버가 바쁩니다/);
    assert.equal(branch(board).props.ending, false, "실패한 마지막 답이 ending 을 켰다");
    assert.equal(liveChoices(h), 4, "실패 뒤 다시 누를 보기가 없다");

    // 다시 눌러 맞힌다.
    replies = [lastAnswer({ graduated: true, streak: 2 })];
    const pending = (branch(board).props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    assert.equal(held.length, 1);
    h = html();
    assert.equal(cardChoices(h), 0, "기다리는 중에 문제 카드가 남았다");
    assert.doesNotMatch(h, /질문-commit/, "기다리는 중에 방금 답한 문제 글이 남았다");
    assert.doesNotMatch(h, /role="alert"/, "기다리는 중에 지난 오류가 남았다");
    assert.match(h, /앞 문제/);
    assert.match(h, /다 외웠습니다/);
    assert.match(h, /aria-valuenow="1"/, "진행이 방금 답을 안 셌다");
    await release();
    await pending;
    assert.ok(isDone(branch(board)));
  });

  it("finished 가 false 여도 다음 문제가 없으면 마지막으로 보고 기다린다", async () => {
    await begin();
    replies = [{ ...lastAnswer(), finished: false } as ReviewAnswered];
    const pending = (branch(board).props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    assert.equal(held.length, 1);
    assert.equal(cardChoices(html()), 0);
    await release();
    await pending;
    assert.ok(isDone(branch(board)));
  });

  it("중간 정답은 ending 을 안 켜고 다음 문제를 그린다(타이머를 풀기 전에)", async () => {
    await begin();
    replies = [reviewAnswer(true, false)];
    const pending = (branch(board).props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    assert.equal(branch(board).props.ending, false);
    const h = html();
    assert.equal(liveChoices(h), 4);
    assert.match(h, /보기-rebase-0/);
    assert.match(h, /앞 문제/);
    await release();
    await pending;
  });
});

describe("일일공부 - ending 이 학습 가지·중간 답과 겹치지 않는다", () => {
  beforeEach(installFailableFetch);

  const CARD = {
    id: 1,
    term: "rebase",
    pronunciation: "",
    reading: "",
    meaning: "커밋을 옮겨 쌓기",
    description: "",
    example: "",
    example_translation: "",
    category_label: "Git",
  };

  const board = () => DailyStudyBoard({ status: PLAYING });
  const html = () => draw(createElement(DailyStudyBoard, { status: PLAYING }));

  function reply(correct: boolean, last: boolean, learning: (typeof CARD)[] = []): DailyAnswered {
    return { ...dailyAnswer(correct, last), learning } as DailyAnswered;
  }

  it("중간 답이 학습을 열고, 익힌 뒤 푼 마지막 답에서만 문제 카드가 비워진다", async () => {
    // 1. 중간 답: 다음 묶음 학습이 기다린다.
    replies = [reply(true, false, [CARD])];
    await (branch(board).props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    assert.equal(held.length, 0, "중간 답인데 기다린다");
    let play = branch(board);
    assert.equal(play.props.ending, false, "중간 답에 ending 이 켜졌다");
    assert.equal(typeof play.props.onLearn, "function", "학습 버튼이 없다");
    assert.match(html(), /이어서 익히기/);

    // 2. 학습으로 갔다가 돌아온다.
    (play.props.onLearn as () => void)();
    const learning = branch(board);
    assert.equal(typeof learning.props.onDone, "function", "학습 가지가 아니다");
    (learning.props.onDone as () => void)();
    play = branch(board);
    assert.ok(isPlay(play));
    assert.equal(play.props.ending, false);
    let h = html();
    assert.equal(liveChoices(h), 4, "익힌 뒤 문제 보기가 없다");
    assert.match(h, /보기-rebase-0/);

    // 3. 마지막 답.
    replies = [reply(false, true)];
    const pending = (play.props.onPick as (id: number) => Promise<void>)(NEXT.choices[0].id);
    await settle();
    assert.equal(held.length, 1);
    h = html();
    assert.equal(cardChoices(h), 0, "기다리는 중에 문제 카드가 남았다");
    assert.doesNotMatch(h, /이어서 익히기|새 단어를 익힌 뒤/, "기다리는 중에 학습 안내가 떴다");
    assert.match(h, /앞 문제/);
    assert.match(h, /aria-valuenow="2"/, "진행이 마지막 답을 안 셌다");
    await release();
    await pending;
    assert.ok(isDone(branch(board)));
  });

  it("마지막 답 응답에 학습 카드가 딸려 와도 학습 안내 없이 연출 뒤 결과로", async () => {
    replies = [reply(true, true, [CARD])];
    const pending = (branch(board).props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    assert.equal(held.length, 1);
    const play = branch(board);
    assert.equal(play.props.ending, true);
    assert.equal(play.props.onLearn, undefined, "끝난 판인데 학습으로 넘길 길이 열렸다");
    const h = html();
    assert.equal(cardChoices(h), 0);
    assert.doesNotMatch(h, /이어서 익히기|새 단어를 익힌 뒤/);
    await release();
    await pending;
    assert.ok(isDone(branch(board)), "학습 카드 때문에 결과로 안 넘어갔다");
  });

  it("마지막 답이 실패하면 ending 없이 문제와 오류가 보이고, 다시 누르면 기다린 뒤 결과", async () => {
    replies = [{ fail: 500, detail: "채점하지 못했어요" }];
    await (branch(board).props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    assert.equal(held.length, 0);
    let play = branch(board);
    assert.equal(play.props.ending, false, "실패한 답이 ending 을 켰다");
    let h = html();
    assert.match(h, /채점하지 못했어요/);
    assert.match(h, /화면 새로 불러오기/);
    assert.equal(liveChoices(h), 4, "실패 뒤 다시 누를 보기가 없다");

    replies = [reply(true, true)];
    const pending = (play.props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    play = branch(board);
    assert.equal(play.props.ending, true);
    h = html();
    assert.equal(cardChoices(h), 0);
    assert.doesNotMatch(h, /role="alert"|화면 새로 불러오기/, "기다리는 중에 지난 오류가 남았다");
    assert.match(h, /정답/);
    await release();
    await pending;
    assert.ok(isDone(branch(board)));
  });

  it("finished 가 false 여도 다음 문제가 없으면 마지막으로 보고 기다린다", async () => {
    replies = [{ ...reply(true, true), finished: false } as DailyAnswered];
    const pending = (branch(board).props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    assert.equal(held.length, 1);
    assert.equal(cardChoices(html()), 0);
    await release();
    await pending;
    assert.ok(isDone(branch(board)));
  });

  it("길이를 골라 연 판은 ending 이 꺼진 채로 시작한다", async () => {
    const CHOOSING = { lengths: [], today: null, token: null, question: null, learning: [] } as unknown as DailyStatus;
    const fresh = () => DailyStudyBoard({ status: CHOOSING });
    const choose = branch(fresh);
    assert.equal(typeof choose.props.onStart, "function", "고르기 화면이 아니다");
    replies = [{ token: "tok-9", question: FIRST, study: progress(0), learning: [] }];
    await (choose.props.onStart as (l: string) => Promise<void>)("5m");
    await settle();
    const play = branch(fresh);
    assert.ok(isPlay(play));
    assert.equal(play.props.ending, false);
    assert.equal(liveChoices(draw(createElement(DailyStudyBoard, { status: CHOOSING }))), 4);
  });
});
