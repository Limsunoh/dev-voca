/**
 * 한 판 화면의 다듬은 동작을 끝까지 돌려 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 결함은 이렇다.
 *
 *   다시 저장이 두 번 나감         중복 클릭이 요청을 겹쳐 보낸다
 *   저장 중 표시가 안 풀림         재시도가 끝나도 "저장하는 중..." 으로 잠긴다
 *   저장 응답이 새 판을 닫음       다시 저장 중에 연 판이 지난 판의 응답에 끝난다
 *   경고가 답 없는 판에 걸림       풀기도 전에 새로고침을 막는다
 *   경고가 끝난 판에 남음          결과 화면과 다른 화면에서도 브라우저가 묻는다
 *   고른 표시가 다음 문제로 샘     같은 id 의 새 보기가 고른 것처럼 보인다
 *
 * 방식은 round-again-error.test.mts 와 같다. react 훅만 대역으로 바꾸고 보드가
 * 넘긴 콜백을 진짜로 부른다.
 */
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it, mock } from "node:test";

import type { RoundSummary } from "@/lib/api/rounds";
import { connectionLostMessage } from "@/lib/connection";

const realReact = await import("react");

type Slot = { value: unknown };
type Cleanup = void | (() => void);
type Effect = () => Cleanup;
type EffectSlot = { deps: unknown[] | null; cleanup: Cleanup };

let slots: Slot[] = [];
let cursor = 0;
let queued: { state: EffectSlot; run: Effect; deps: unknown[] }[] = [];

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
    useCallback<T>(fn: T) {
      return slot(() => fn).value;
    },
    useEffect(run: Effect, deps: unknown[]) {
      const state = slot<EffectSlot>(() => ({ deps: null, cleanup: undefined })).value as EffectSlot;
      if (!state.deps || deps.some((dep, i) => !Object.is(dep, state.deps?.[i]))) {
        queued.push({ state, run, deps });
      }
    },
  },
});

mock.module("@/components/useFocusNewQuestion", {
  namedExports: { useFocusNewQuestion: () => ({ current: null }) },
});

function ExitGuardStub() {
  return null;
}

mock.module("@/components/ExitGuard", {
  namedExports: { ExitGuard: ExitGuardStub },
});

const { RoundBoard } = await import("./RoundBoard");
const { QuestionCard } = await import("./QuestionCard");

/* ---- 트리 읽기 ---- */

type El = { type: unknown; props: Record<string, unknown> };
type Style = Record<string, unknown>;

const isElement = (node: unknown): node is El =>
  typeof node === "object" && node !== null && "type" in node && "props" in node;

function flatten(node: unknown, out: El[] = []): El[] {
  if (Array.isArray(node)) {
    for (const child of node) flatten(child, out);
  } else if (isElement(node)) {
    out.push(node);
    flatten(node.props.children, out);
  }
  return out;
}

function textOf(node: unknown): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isElement(node)) return textOf(node.props.children);
  return "";
}

const named = (name: string) => (el: El) =>
  typeof el.type === "function" && (el.type as { name: string }).name === name;

const callComponent = (el: El) => (el.type as (props: unknown) => unknown)(el.props);

/* ---- 자료 ---- */

const QUESTION = {
  kind: "meaning",
  kind_label: "뜻 고르기",
  question: "이 단어의 뜻은?",
  prompt: "commit",
  category: "git",
  category_label: "Git",
  choices: [
    { id: 1, text: "a" },
    { id: 2, text: "b" },
  ],
};

const SUMMARY: RoundSummary = {
  score: 120,
  answered: 8,
  correct: 6,
  skipped: 0,
  recorded: true,
  guest: false,
};

const started = (token: string, pause = 0) => ({
  token,
  question: QUESTION,
  round_seconds: 90,
  max_skips: 3,
  reaction_pause_ms: pause,
});

const RESULT = {
  correct: true,
  score: 1,
  skipped: false,
  in_time: true,
  answer_text: "a",
  answer_extra: "",
};

const answered = (token: string, result: object = RESULT, finished = false) => ({
  token,
  question: finished ? null : QUESTION,
  result,
  finished,
});

const skippedResult = { ...RESULT, correct: false, score: 0, skipped: true };

const FINISH_ERROR = "판을 닫는 데 실패했습니다";
const START_ERROR = "새 판을 열 수 없습니다";
const INK = "0 0 0 2px var(--foreground) inset";

/* ---- 대역 ---- */

type Reply = { fail: number; detail?: string } | { throws: string } | Record<string, unknown>;

let replies: (Reply | Promise<Reply>)[] = [];
let sent: Record<string, unknown>[] = [];
let intervals = new Map<number, () => void>();
let nextInterval = 1;
let clock = 1_000_000;
let unloadHandlers = new Set<(event: unknown) => void>();

const g = globalThis as unknown as {
  document?: unknown;
  addEventListener?: unknown;
  removeEventListener?: unknown;
};
const real = {
  fetch: globalThis.fetch,
  document: g.document,
  now: Date.now,
  setInterval: globalThis.setInterval,
  clearInterval: globalThis.clearInterval,
  addEventListener: g.addEventListener,
  removeEventListener: g.removeEventListener,
};

beforeEach(() => {
  slots = [];
  queued = [];
  replies = [];
  sent = [];
  intervals = new Map();
  clock = 1_000_000;
  unloadHandlers = new Set();
  g.document = { documentElement: { style: { setProperty() {}, removeProperty() {} } } };
  g.addEventListener = (type: string, fn: (event: unknown) => void) => {
    if (type === "beforeunload") unloadHandlers.add(fn);
  };
  g.removeEventListener = (type: string, fn: (event: unknown) => void) => {
    if (type === "beforeunload") unloadHandlers.delete(fn);
  };
  Date.now = () => clock;
  globalThis.setInterval = ((fn: () => void) => {
    const id = nextInterval++;
    intervals.set(id, fn);
    return id;
  }) as unknown as typeof setInterval;
  globalThis.clearInterval = ((id: number) => {
    intervals.delete(id);
  }) as unknown as typeof clearInterval;
  globalThis.fetch = (async (_url: unknown, init?: { body?: string }) => {
    sent.push(JSON.parse(init?.body ?? "{}"));
    assert.ok(replies.length > 0, "준비한 것보다 요청이 많다");
    const reply = (await replies.shift()) as Reply;
    if ("throws" in reply) throw new TypeError(String(reply.throws));
    if ("fail" in reply) {
      return {
        ok: false,
        status: reply.fail,
        json: async () => ({ detail: (reply as { detail?: string }).detail }),
      } as unknown as Response;
    }
    return { ok: true, status: 200, json: async () => reply } as Response;
  }) as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = real.fetch;
  g.document = real.document;
  g.addEventListener = real.addEventListener;
  g.removeEventListener = real.removeEventListener;
  Date.now = real.now;
  globalThis.setInterval = real.setInterval;
  globalThis.clearInterval = real.clearInterval;
});

/* ---- 도구 ---- */

const settle = () => new Promise((r) => setTimeout(r, 0));

function later() {
  let resolve!: (reply: Reply) => void;
  const promise = new Promise<Reply>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function render(): El[] {
  cursor = 0;
  queued = [];
  const tree = flatten(RoundBoard({ isGuest: false }));
  for (const { state, run, deps } of queued) {
    if (typeof state.cleanup === "function") state.cleanup();
    state.cleanup = run();
    state.deps = deps;
  }
  return tree;
}

/** 화면을 떠날 때처럼 모든 effect 를 정리한다. */
function unmount() {
  for (const { value } of slots) {
    const cleanup = (value as EffectSlot | null)?.cleanup;
    if (typeof cleanup === "function") cleanup();
  }
}

function withProp(tree: El[], name: string): El {
  const found = tree.find((e) => typeof e.props[name] === "function");
  assert.ok(found, `${name} 를 가진 요소가 없다`);
  return found;
}

function press(name: "onStart" | "onAgain" | "onSkip" | "onRetrySave"): Promise<void> {
  return (withProp(render(), name).props[name] as () => Promise<void>)();
}

function pick(id = 1): Promise<void> {
  return (withProp(render(), "onPick").props.onPick as (id: number) => Promise<void>)(id);
}

async function openRound(token = "t0", pause = 0) {
  replies.push(started(token, pause));
  await press("onStart");
  render();
}

async function tick() {
  for (const run of [...intervals.values()]) run();
  await settle();
}

/** 판을 닫다가 실패한 화면까지 간다. */
async function failToSave(token = "t0") {
  await openRound(token);
  clock += 90_001;
  replies.push({ fail: 503, detail: FINISH_ERROR });
  await tick();
}

function card() {
  const el = render().find(named("RoundResultCard"));
  assert.ok(el, "결과 카드가 안 그려졌다");
  const root = callComponent(el);
  const inner = flatten(root);
  const button = (label: RegExp) =>
    inner.find((e) => e.type === "button" && label.test(textOf(e)));
  return {
    props: el.props,
    text: textOf(root),
    save: button(/다시 저장|저장하는 중/),
    again: button(/한 판 더|여는 중/) as El,
  };
}

const playCard = () => render().find(named("PlayCard"));
const isPlaying = () => playCard() !== undefined;
const actions = () => sent.map((body) => body.action);
const pickedNow = () => playCard()?.props.pickedId;

/* ---- 다시 저장 ---- */

describe("다시 저장", () => {
  beforeEach(() => failToSave());

  it("판을 못 닫은 화면에만 버튼이 있고 눌리는 상태다", () => {
    const { save, text } = card();
    assert.ok(save, "다시 저장이 없다");
    assert.equal(save.props.disabled, false);
    assert.match(text, new RegExp(FINISH_ERROR));
  });

  it("재시도가 성공하면 같은 토큰으로 닫고 결과와 점수를 보여 준다", async () => {
    replies.push(SUMMARY);
    await press("onRetrySave");

    const after = card();
    assert.equal(after.props.summary, SUMMARY);
    assert.equal(after.props.error, "");
    assert.equal(after.props.saving, false);
    assert.equal(after.save, undefined, "결과가 있는데 다시 저장이 남았다");
    assert.deepEqual(actions(), ["start", "finish", "finish"]);
    assert.equal(sent[2].token, "t0");
  });

  it("연속으로 실패해도 매번 다시 누를 수 있고, 새 문구로 바뀌고, 결국 저장된다", async () => {
    for (const [i, detail] of ["두 번째 실패", "세 번째 실패"].entries()) {
      replies.push({ fail: 503, detail });
      await press("onRetrySave");
      const after = card();
      assert.equal(after.props.summary, null);
      assert.equal(after.props.error, detail);
      assert.equal(after.props.saving, false, `${i + 2}번째 실패 뒤에 저장 중으로 남았다`);
      assert.equal(after.save?.props.disabled, false, "실패 뒤에 버튼이 잠겼다");
      assert.ok(!after.text.includes(FINISH_ERROR), "지난 문구가 남았다");
    }

    replies.push({ throws: "Failed to fetch" });
    await press("onRetrySave");
    assert.equal(card().props.error, connectionLostMessage());

    replies.push(SUMMARY);
    await press("onRetrySave");
    assert.equal(card().props.summary, SUMMARY);
    assert.deepEqual(actions(), ["start", "finish", "finish", "finish", "finish", "finish"]);
  });

  it("저장을 기다리는 동안 버튼이 잠기고 문구가 바뀌며, 끝나면 풀린다", async () => {
    const closing = later();
    replies.push(closing.promise);
    const retrying = press("onRetrySave");
    await settle();

    const waiting = card();
    assert.equal(waiting.props.saving, true);
    assert.equal(textOf(waiting.save), "저장하는 중...");
    assert.equal(waiting.save?.props.disabled, true);

    closing.resolve({ fail: 503, detail: "또 실패" });
    await retrying;
    const after = card();
    assert.equal(after.props.saving, false);
    assert.equal(textOf(after.save), "다시 저장");
    assert.equal(after.save?.props.disabled, false);
  });

  it("한 틱 안의 중복 클릭은 요청 하나고 저장 중 표시도 유지한다", async () => {
    const closing = later();
    replies.push(closing.promise);
    const onRetry = withProp(render(), "onRetrySave").props.onRetrySave as () => Promise<void>;
    const first = onRetry();
    const second = onRetry();
    await settle();

    assert.deepEqual(actions(), ["start", "finish", "finish"], "요청이 겹쳐 나갔다");
    assert.equal(card().props.saving, true, "요청이 도는데 저장 중 표시가 풀렸다");

    closing.resolve(SUMMARY);
    await Promise.all([first, second]);
    assert.equal(card().props.summary, SUMMARY);
    assert.equal(card().props.saving, false);
  });

  it("저장 중에 한 판 더 를 눌러도 지난 판의 응답이 새 판을 닫지 않는다", async () => {
    const closing = later();
    replies.push(closing.promise);
    const retrying = press("onRetrySave");
    await settle();

    const { again } = card();
    if (!again.props.disabled) {
      replies.push(started("t2"));
      await (again.props.onClick as () => Promise<void>)();
      assert.ok(isPlaying(), "준비 실패: 새 판이 안 열렸다");
    }

    closing.resolve(SUMMARY);
    await retrying;
    await settle();
    if (!again.props.disabled) {
      assert.ok(isPlaying(), "지난 판의 저장 응답이 방금 연 판을 닫았다");
      assert.equal(render().some(named("RoundResultCard")), false);
    }
  });

  it("새 판을 여는 동안에는 다시 저장을 못 누른다", async () => {
    const opening = later();
    replies.push(opening.promise);
    const pending = press("onAgain");
    await settle();

    const waiting = card();
    assert.equal(waiting.save?.props.disabled, true);

    opening.resolve({ fail: 503, detail: START_ERROR });
    await pending;
    assert.equal(card().save?.props.disabled, false);
  });

  it("한 판 더 가 실패한 뒤에도 원래 판을 저장할 수 있고 문구가 지워진다", async () => {
    replies.push({ fail: 503, detail: START_ERROR });
    await press("onAgain");
    assert.equal(card().props.error, START_ERROR);

    replies.push(SUMMARY);
    await press("onRetrySave");
    const after = card();
    assert.equal(after.props.summary, SUMMARY);
    assert.equal(after.props.error, "");
    assert.equal(sent.at(-1)?.token, "t0");
  });

  it("재시도가 실패한 뒤 새 판을 열면 그 판의 토큰으로 저장한다", async () => {
    replies.push({ fail: 503, detail: "또 실패" });
    await press("onRetrySave");

    replies.push(started("t2"));
    await press("onAgain");
    render();
    assert.ok(isPlaying());
    assert.equal(playCard()?.props.error, "");

    clock += 90_001;
    replies.push({ fail: 503, detail: FINISH_ERROR });
    await tick();
    replies.push(SUMMARY);
    await press("onRetrySave");
    assert.equal(sent.at(-1)?.token, "t2");
    assert.equal(card().props.summary, SUMMARY);
  });

  it("실패 화면에서 타이머가 스스로 다시 보내지 않는다", async () => {
    render();
    assert.equal(intervals.size, 0, "끝난 판의 타이머가 돈다");
    const before = sent.length;
    await tick();
    assert.equal(sent.length, before);
  });
});

describe("다시 저장이 나오는 자리", () => {
  it("판의 마지막 답 뒤 닫기가 실패하면 그 답의 새 토큰으로 다시 보낸다", async () => {
    await openRound();
    replies.push(answered("t1", RESULT, true), { fail: 503, detail: FINISH_ERROR });
    await pick();

    replies.push(SUMMARY);
    await press("onRetrySave");
    assert.equal(sent.at(-1)?.token, "t1");
    assert.equal(card().props.summary, SUMMARY);
  });

  it("정상 결과에서 한 판 더 가 실패해도 다시 저장은 없다", async () => {
    await openRound();
    clock += 90_001;
    replies.push(SUMMARY);
    await tick();

    replies.push({ fail: 503, detail: START_ERROR });
    await press("onAgain");
    assert.equal(card().save, undefined);
  });
});

/* ---- 새로고침 경고 ---- */

describe("새로고침 경고", () => {
  const warned = () => unloadHandlers.size > 0;

  it("답을 안 한 판에는 안 걸린다", async () => {
    await openRound();
    assert.equal(warned(), false);
  });

  it("시작 전 화면에는 안 걸린다", () => {
    render();
    assert.equal(warned(), false);
  });

  it("답 하나를 받으면 걸리고, 브라우저가 묻게 한다", async () => {
    await openRound();
    replies.push(answered("t1"));
    await pick();
    render();
    assert.equal(warned(), true);

    let prevented = false;
    const event = {
      preventDefault() {
        prevented = true;
      },
      returnValue: "x" as unknown,
    };
    for (const handler of unloadHandlers) handler(event);
    assert.equal(prevented, true);
    assert.equal(event.returnValue, "");
  });

  it("답이 서버에서 실패하면 센 것이 없어 안 걸린다", async () => {
    await openRound();
    replies.push({ fail: 500, detail: "x" });
    await pick();
    render();
    assert.equal(warned(), false);
  });

  it("넘기기도 답으로 쳐서 걸린다", async () => {
    await openRound();
    replies.push(answered("t1", skippedResult));
    await press("onSkip");
    render();
    assert.equal(warned(), true);
  });

  it("판이 끝나면 풀린다", async () => {
    await openRound();
    replies.push(answered("t1"));
    await pick();
    render();
    assert.equal(warned(), true, "준비 실패: 답 뒤에 경고가 안 걸렸다");

    replies.push(answered("t2", RESULT, true), SUMMARY);
    await pick();
    render();
    assert.equal(card().props.summary, SUMMARY);
    render();
    assert.equal(warned(), false);
  });

  it("한 판 더 로 연 새 판은 첫 답 전까지 안 걸린다", async () => {
    await openRound();
    replies.push(answered("t1", RESULT, true), SUMMARY);
    await pick();
    render();

    replies.push(started("t2"));
    await press("onAgain");
    render();
    assert.equal(warned(), false);

    replies.push(answered("t3"));
    await pick();
    render();
    assert.equal(warned(), true);
  });

  it("화면을 떠나면 풀린다", async () => {
    await openRound();
    replies.push(answered("t1"));
    await pick();
    render();
    assert.equal(warned(), true);
    unmount();
    assert.equal(warned(), false);
  });
});

/* ---- 고른 보기 표시 ---- */

describe("고른 보기 표시", () => {
  it("채점을 기다리는 동안 고른 보기만 표시한다", async () => {
    await openRound();
    const grading = later();
    replies.push(grading.promise);
    const picking = pick(2);
    await settle();

    assert.equal(pickedNow(), 2);
    const el = playCard();
    assert.ok(el);
    const inner = flatten(callComponent(el)).find(named("QuestionCard"));
    assert.equal(inner?.props.pickedId, 2, "PlayCard 가 QuestionCard 로 안 넘겼다");
    grading.resolve(answered("t1"));
    await picking;
  });

  it("넘기기는 pickedId 를 쓰지 않는다", async () => {
    await openRound();
    const grading = later();
    replies.push(grading.promise);
    const skipping = press("onSkip");
    await settle();

    assert.equal(pickedNow(), null);
    assert.equal(sent.at(-1)?.skip, true);
    grading.resolve(answered("t1", skippedResult));
    await skipping;
    assert.equal(pickedNow(), null);
  });

  it("다음 문제가 뜨면 지워져 같은 id 의 새 보기로 안 샌다", async () => {
    await openRound();
    replies.push(answered("t1"));
    await pick(1);
    assert.equal(pickedNow(), null);
  });

  it("연출로 멈추는 동안에는 남아 있고, 끝나면 지워진다", async () => {
    await openRound("t0", 30);
    replies.push(answered("t1"));
    const picking = pick(1);
    await settle();
    assert.equal(pickedNow(), 1, "연출 중에 표시가 사라졌다");
    await picking;
    assert.equal(pickedNow(), null);
  });

  it("채점이 실패해도 지워진다", async () => {
    await openRound();
    replies.push({ fail: 500, detail: "x" });
    await pick(1);
    assert.equal(pickedNow(), null);
  });

  it("같은 틱의 두 번째 고르기는 표시를 안 바꾸고 요청도 안 나간다", async () => {
    await openRound();
    const grading = later();
    replies.push(grading.promise);
    const first = pick(1);
    const second = pick(2);
    await settle();

    assert.equal(pickedNow(), 1);
    assert.deepEqual(actions(), ["start", "answer"]);
    grading.resolve(answered("t1"));
    await Promise.all([first, second]);
  });

  it("판의 마지막 답에서 지워지고 다음 판에 안 남는다", async () => {
    await openRound();
    replies.push(answered("t1", RESULT, true), SUMMARY);
    await pick(1);
    assert.equal(card().props.summary, SUMMARY);

    replies.push(started("t2"));
    await press("onAgain");
    assert.equal(pickedNow(), null);
  });

  it("답한 사이 마감이 지나 닫혀도 지워진다", async () => {
    await openRound();
    const grading = later();
    replies.push(grading.promise, SUMMARY);
    const picking = pick(1);
    await settle();
    clock += 90_001;
    grading.resolve(answered("t1"));
    await picking;

    replies.push(started("t2"));
    await press("onAgain");
    assert.equal(pickedNow(), null);
  });
});

/* ---- QuestionCard ---- */

describe("QuestionCard 의 pickedId", () => {
  const styles = (props: { pickedId?: number | null } = {}) =>
    flatten(QuestionCard({ question: QUESTION as never, busy: false, onPick() {}, ...props }))
      .filter((e) => e.type === "button")
      .map((e) => e.props.style as Style);

  it("안 주면, null 이면, 없는 id 면 전과 같은 두께다", () => {
    const untouched = styles();
    for (const style of untouched) {
      assert.equal(style["--lift"], "var(--lift-card)");
      assert.equal("--lift-hover" in style, false);
    }
    assert.deepEqual(styles({ pickedId: undefined }), untouched);
    assert.deepEqual(styles({ pickedId: null }), untouched);
    assert.deepEqual(styles({ pickedId: 99 }), untouched);
  });

  it("고른 보기만 잉크 테두리다", () => {
    const [first, second] = styles({ pickedId: 2 });
    assert.equal(first["--lift"], "var(--lift-card)");
    assert.equal(second["--lift"], INK);
  });

  it("id 가 0 인 보기도 표시한다", () => {
    const question = { ...QUESTION, choices: [{ id: 0, text: "z" }] };
    const [only] = flatten(
      QuestionCard({ question: question as never, busy: false, onPick() {}, pickedId: 0 }),
    )
      .filter((e) => e.type === "button")
      .map((e) => e.props.style as Style);
    assert.equal(only["--lift"], INK);
  });

  it("마우스가 올라가 있어도 잉크 테두리가 남는다", () => {
    // .dv-card-press:hover 는 disabled 와 무관하게 --lift-hover 로 덮어쓴다.
    // 방금 누른 보기에는 마우스가 올라가 있으므로 이 값이 실제로 보이는 쪽이다.
    const [, second] = styles({ pickedId: 2 });
    assert.equal(second["--lift-hover"], INK);
  });
});

/* ---- 문구 ---- */

describe("문구", () => {
  const resultLine = () => {
    const el = playCard();
    assert.ok(el);
    const line = flatten(callComponent(el)).find((e) => e.props["aria-live"] === "polite");
    assert.ok(line, "결과 줄이 없다");
    return textOf(line);
  };

  it("첫 답 전에는 '방금' 이 없다", async () => {
    await openRound();
    assert.equal(resultLine(), "");
  });

  for (const [name, result] of [
    ["정답", RESULT],
    ["오답", { ...RESULT, correct: false, score: -1 }],
    ["넘김", skippedResult],
  ] as const) {
    it(`${name} 결과 줄 앞에 '방금' 이 한 번 붙는다`, async () => {
      await openRound();
      replies.push(answered("t1", result));
      await pick();
      const line = resultLine();
      assert.match(line, /^방금 /);
      assert.equal(line.split("방금").length - 1, 1);
    });
  }

  for (const score of [120, 0, -3]) {
    it(`결과 점수 ${score} 뒤에 '점' 이 붙는다`, async () => {
      await openRound();
      clock += 90_001;
      replies.push({ ...SUMMARY, score });
      await tick();
      assert.ok(card().text.includes(`${score}점`));
    });
  }

  it("시작 카드에 시간 규칙과 넘기기가 있다", () => {
    const el = render().find(named("StartCard"));
    assert.ok(el);
    const text = textOf(callComponent(el));
    assert.match(text, /문제마다 정해진 시간 안에 맞히면 \+1/);
    assert.match(text, /틀리면 -1/);
    assert.match(text, /0점/);
    assert.match(text, /세 번까지/);
  });
});
