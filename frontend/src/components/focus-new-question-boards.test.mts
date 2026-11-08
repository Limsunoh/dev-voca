/**
 * 문제 화면 셋(한 판·일일공부·복습)이 초점 훅을 제대로 잇는지 실제로 불러서 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 결함은 이렇다.
 *
 *   error 를 안 넘김      채점이 실패해 문제가 그대로일 때 초점을 잃는다
 *   cardRef 를 안 넘김    훅이 돌아도 옮길 카드가 없어 아무 일도 안 일어난다
 *   조기 반환 뒤에 훅     문제가 없는 렌더에서 훅 개수가 달라져 React 가 죽는다
 *
 * PlayCard 는 내보내지 않으므로 보드가 돌려준 트리에서 꺼낸다. 훅은 spy 로 바꿔
 * 무엇을 받았는지 본다. 보드의 훅 대역과 fetch 대역은
 * result-line-placement.test.mts 와 round-board-start-time.test.mts 와 같다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

import type { DailyStatus } from "@/lib/api/daily";
import type { RoundQuestion } from "@/lib/api/rounds";

const realReact = await import("react");

type Slot = { value: unknown };

let slots: Slot[] = [];
let cursor = 0;

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
      return fn;
    },
    useEffect() {},
  },
});

const SENTINEL_REF = { current: null };
let hookArgs: unknown[][] = [];

mock.module("@/components/useFocusNewQuestion", {
  namedExports: {
    useFocusNewQuestion(...args: unknown[]) {
      hookArgs.push(args);
      return SENTINEL_REF;
    },
  },
});

function ExitGuardStub() {
  return null;
}

mock.module("@/components/ExitGuard", {
  namedExports: { ExitGuard: ExitGuardStub },
});

const { RoundBoard } = await import("./RoundBoard");
const { DailyStudyBoard } = await import("./DailyStudyBoard");
const { ReviewBoard } = await import("./ReviewBoard");

type El = { type: unknown; props: Record<string, unknown> };

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

const named = (name: string) => (el: El) =>
  typeof el.type === "function" && (el.type as { name: string }).name === name;

/* ---- 자료 ---- */

const QUESTION: RoundQuestion = {
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

const DAILY: DailyStatus = {
  lengths: [],
  today: {
    length: "5m",
    total: 10,
    answered: 0,
    correct: 0,
    score: 0,
    bonus: 0,
    done: false,
    chunk_size: 3,
    chunk_count: 2,
    chunk_index: 0,
  },
  token: "tok-1",
  question: QUESTION,
  learning: [],
};

const DUE = { due: 5, round_size: 20, graduate_streak: 2 };

/* ---- 대역 ---- */

const realFetch = globalThis.fetch;
const realDocument = (globalThis as { document?: unknown }).document;
after(() => {
  globalThis.fetch = realFetch;
  (globalThis as { document?: unknown }).document = realDocument;
});

let startReply: unknown = null;

beforeEach(() => {
  slots = [];
  hookArgs = [];
  (globalThis as { document?: unknown }).document = {
    documentElement: { style: { setProperty() {}, removeProperty() {} } },
  };
  globalThis.fetch = (async () =>
    ({ ok: true, status: 200, json: async () => startReply }) as Response) as typeof fetch;
});

const settle = () => new Promise((r) => setTimeout(r, 0));

function callBoard(board: () => unknown): unknown {
  cursor = 0;
  return board();
}

function playCard(tree: unknown): El {
  const found = flatten(tree).find(named("PlayCard"));
  assert.ok(found, "PlayCard 가 안 그려졌다");
  return found;
}

/** 시작 버튼을 누른 뒤의 PlayCard. 한 판과 복습이 쓴다. */
async function started(board: () => unknown, reply: unknown): Promise<El> {
  startReply = reply;
  const idle = flatten(callBoard(board)).find((el) => typeof el.props.onStart === "function");
  assert.ok(idle, "시작 버튼이 없다");
  (idle.props.onStart as () => Promise<void>)();
  await settle();
  return playCard(callBoard(board));
}

const openRound = () =>
  started(() => RoundBoard({ isGuest: false }), {
    token: "t0",
    question: QUESTION,
    round_seconds: 90,
    max_skips: 3,
    reaction_pause_ms: 0,
  });

const openReview = () =>
  started(() => ReviewBoard({ due: DUE }), {
    token: "r-1",
    question: { ...QUESTION, answered: 0, total: 5 },
  });

const openDaily = async () => playCard(callBoard(() => DailyStudyBoard({ status: DAILY })));

/** PlayCard 를 한 번 부른다. 받은 트리를 돌려준다. */
function callCard(card: El, override: Record<string, unknown> = {}) {
  hookArgs = [];
  return (card.type as (props: unknown) => unknown)({ ...card.props, ...override });
}

const SCREENS = [
  ["한 판", openRound],
  ["일일공부", openDaily],
  ["복습", openReview],
] as const;

/* ---- 테스트 ---- */

for (const [name, open] of SCREENS) {
  describe(`${name} PlayCard 의 초점 훅`, () => {
    it("훅에 question 과 error 를 그대로 넘긴다", async () => {
      const card = await open();
      const question = { ...QUESTION };
      callCard(card, { question, error: "채점하지 못했습니다." });
      assert.equal(hookArgs.length, 1, "렌더 한 번에 훅은 한 번");
      assert.equal(hookArgs[0].length, 2);
      assert.equal(hookArgs[0][0], question);
      assert.equal(hookArgs[0][1], "채점하지 못했습니다.");
    });

    it("훅이 돌려준 ref 를 QuestionCard 의 cardRef 로 넘긴다", async () => {
      const card = await open();
      const inner = flatten(callCard(card, { busy: false, ending: false }));
      const question = inner.find(named("QuestionCard"));
      assert.ok(question, "QuestionCard 가 없다");
      assert.equal(question.props.cardRef, SENTINEL_REF);
    });
  });
}

describe("카드를 안 그리는 렌더에서도 훅은 불린다", () => {
  // 훅 개수가 렌더마다 달라지면 React 가 "Rendered fewer hooks" 로 죽는다.
  it("한 판: question 이 null 이면 null 을 돌려주고 훅은 불렸다", async () => {
    const card = await openRound();
    assert.equal(callCard(card, { question: null }), null);
    assert.equal(hookArgs.length, 1);
    assert.equal(hookArgs[0][0], null);
  });

  it("일일공부: ending 이면 카드 없이 훅은 불렸다", async () => {
    const card = await openDaily();
    const inner = flatten(callCard(card, { ending: true }));
    assert.equal(inner.some(named("QuestionCard")), false);
    assert.equal(hookArgs.length, 1);
  });

  it("일일공부: 익히기를 기다리면 카드 없이 훅은 불렸다", async () => {
    const card = await openDaily();
    const inner = flatten(callCard(card, { onLearn: () => {} }));
    assert.equal(inner.some(named("QuestionCard")), false);
    assert.equal(hookArgs.length, 1);
  });

  it("복습: ending 이면 카드 없이 훅은 불렸다", async () => {
    const card = await openReview();
    const inner = flatten(callCard(card, { ending: true }));
    assert.equal(inner.some(named("QuestionCard")), false);
    assert.equal(hookArgs.length, 1);
  });
});
