/**
 * 한 판 결과 화면의 오류 문구가 맞는 때에 한 번만 뜨는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 결함은 이렇다.
 *
 *   "한 판 더" 실패를 안 그림     버튼만 되돌아와 아무 일도 안 일어난 것처럼 보인다
 *   판 도중 채점 실패가 남음      정상 결과 아래 오류가 떠 점수가 안 남은 것으로 읽힌다
 *   판을 못 닫은 오류를 지움      결과도 문구도 없이 "결과를 불러오지 못했습니다" 만 남는다
 *   결과 없는 갈래에 문단이 겹침  같은 문구가 두 번 나오고 낭독기도 두 번 읽는다
 *   다시 눌러도 오류가 남음       새 판이 열렸는데 지난 실패 문구가 따라온다
 *
 * 방식은 round-board-start-time.test.mts 와 같다. react 훅만 대역으로 바꾸고
 * 보드가 넘긴 콜백을 진짜로 부른다. 여기에 더해 시간을 다루려고 Date.now 와
 * setInterval 을 대역으로 바꾼다. 마감으로 닫히는 길은 타이머 effect 안에 있어,
 * 끝까지 돌려 봐야 한다.
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
    // finish 는 deps 가 [] 다. 첫 함수를 계속 돌려줘야 타이머 effect 가 렌더마다 안 돈다.
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

/* ---- 트리 읽기 ---- */

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

function textOf(node: unknown): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isElement(node)) return textOf(node.props.children);
  return "";
}

const named = (name: string) => (el: El) =>
  typeof el.type === "function" && (el.type as { name: string }).name === name;

const times = (text: string, needle: string) => text.split(needle).length - 1;

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

const started = (token: string) => ({
  token,
  question: QUESTION,
  round_seconds: 90,
  max_skips: 3,
  reaction_pause_ms: 0,
});

const GRADE_ERROR = "채점 서버가 바쁩니다";
const FINISH_ERROR = "판을 닫는 데 실패했습니다";
const START_ERROR = "새 판을 열 수 없습니다";

/* ---- 대역 ---- */

type Reply =
  | { fail: number; detail?: string; noBody?: boolean }
  | { throws: string }
  | Record<string, unknown>;

/** 차례대로 내줄 응답. Promise 를 넣으면 풀릴 때까지 응답이 안 온다. */
let replies: (Reply | Promise<Reply>)[] = [];
let sent: Record<string, unknown>[] = [];
let intervals = new Map<number, () => void>();
let nextInterval = 1;
let clock = 1_000_000;

const g = globalThis as unknown as { document?: unknown };
const real = {
  fetch: globalThis.fetch,
  document: g.document,
  now: Date.now,
  setInterval: globalThis.setInterval,
  clearInterval: globalThis.clearInterval,
};

beforeEach(() => {
  slots = [];
  queued = [];
  replies = [];
  sent = [];
  intervals = new Map();
  clock = 1_000_000;
  g.document = { documentElement: { style: { setProperty() {}, removeProperty() {} } } };
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
      const { detail, noBody } = reply as { detail?: string; noBody?: boolean };
      return {
        ok: false,
        status: reply.fail,
        json: async () => {
          if (noBody) throw new SyntaxError("본문이 JSON 이 아니다");
          return { detail };
        },
      } as unknown as Response;
    }
    return { ok: true, status: 200, json: async () => reply } as Response;
  }) as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = real.fetch;
  g.document = real.document;
  Date.now = real.now;
  globalThis.setInterval = real.setInterval;
  globalThis.clearInterval = real.clearInterval;
});

/* ---- 도구 ---- */

const settle = () => new Promise((r) => setTimeout(r, 0));

/** 나중에 풀어 주는 응답. "응답을 기다리는 중" 을 멈춰 놓고 볼 때 쓴다. */
function later() {
  let resolve!: (reply: Reply) => void;
  const promise = new Promise<Reply>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

/** 보드를 그리고 React 처럼 바뀐 effect 를 돌린다. */
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

function withProp(tree: El[], name: string): El {
  const found = tree.find((e) => typeof e.props[name] === "function");
  assert.ok(found, `${name} 를 가진 요소가 없다`);
  return found;
}

function press(name: "onStart" | "onAgain"): Promise<void> {
  return (withProp(render(), name).props[name] as () => Promise<void>)();
}

function pick(): Promise<void> {
  return (withProp(render(), "onPick").props.onPick as (id: number) => Promise<void>)(1);
}

/** 판을 연다. 타이머 effect 까지 돌아 있는 상태로 돌려준다. */
async function openRound(token = "t0") {
  replies.push(started(token));
  await press("onStart");
  render();
}

/** 90초를 넘긴다. 타이머는 안 돌린다. */
const passDeadline = () => {
  clock += 90_001;
};

/** 타이머 한 틱. */
async function tick() {
  for (const run of [...intervals.values()]) run();
  await settle();
}

/** 정상으로 닫힌 결과 화면까지 간다. */
async function finishRound() {
  await openRound();
  passDeadline();
  replies.push(SUMMARY);
  await tick();
}

/** 지금 그려진 결과 카드의 안쪽을 읽는다. */
function readCard(props: Record<string, unknown> = {}) {
  const card = render().find(named("RoundResultCard"));
  assert.ok(card, "결과 카드가 안 그려졌다");
  const root = (card.type as (p: unknown) => unknown)({ ...card.props, ...props });
  const inner = flatten(root);
  return {
    props: { ...card.props, ...props },
    alerts: inner.filter((el) => el.props.role === "alert"),
    text: textOf(root),
    button: inner.find((el) => el.type === "button") as El,
  };
}

function assertOneAlert(card: ReturnType<typeof readCard>, message: string) {
  assert.equal(card.alerts.length, 1, "alert 문단이 하나가 아니다");
  assert.equal(card.alerts[0].props.children, message);
  assert.equal(times(card.text, message), 1, "문구가 카드에 한 번만 나와야 한다");
}

function assertClean(card: ReturnType<typeof readCard>, ...absent: string[]) {
  assert.equal(card.alerts.length, 0, "정상 결과에 alert 가 떴다");
  assert.equal(card.props.error, "", "오류 상태가 비워지지 않았다");
  assert.ok(card.props.summary, "요약이 없다");
  for (const message of absent) assert.equal(times(card.text, message), 0, `"${message}" 가 남았다`);
}

const isPlaying = () => render().some(named("PlayCard"));
const playError = () => render().find(named("PlayCard"))?.props.error;
const actions = () => sent.map((body) => body.action);

/* ---- 카드 갈래 ---- */

describe("결과 카드의 오류 갈래", () => {
  beforeEach(finishRound);

  const VARIANTS: [string, RoundSummary][] = [
    ["기록된 판", SUMMARY],
    ["0점·0문제인 판", { ...SUMMARY, score: 0, answered: 0, correct: 0 }],
    ["기록 안 된 게스트 판", { ...SUMMARY, recorded: false, guest: true }],
  ];

  for (const [name, summary] of VARIANTS) {
    it(`${name}: 결과와 오류가 있으면 alert 한 개에 문구가 그대로다`, () => {
      assertOneAlert(readCard({ summary, error: START_ERROR }), START_ERROR);
    });

    it(`${name}: 오류가 없으면 alert 가 없다`, () => {
      assert.equal(readCard({ summary, error: "" }).alerts.length, 0);
    });
  }

  it("결과가 없고 오류가 있으면 기존 갈래만 그리고 alert 문단이 없다", () => {
    const card = readCard({ summary: null, error: FINISH_ERROR });
    assert.equal(card.alerts.length, 0);
    assert.equal(times(card.text, FINISH_ERROR), 1, "문구가 겹치거나 빠졌다");
    assert.equal(times(card.text, "결과를 불러오지 못했습니다."), 0);
  });

  it("결과도 오류도 없으면 안내 문구만 있고 alert 가 없다", () => {
    const card = readCard({ summary: null, error: "" });
    assert.equal(card.alerts.length, 0);
    assert.equal(times(card.text, "결과를 불러오지 못했습니다."), 1);
  });

  it("오류가 있어도 다시 누를 버튼이 살아 있다", () => {
    const card = readCard({ summary: SUMMARY, error: START_ERROR, busy: false });
    assert.equal(card.button.props.disabled, false);
    assert.equal(card.button.props.children, "한 판 더");
  });
});

/* ---- 판 도중 실패가 결과로 새지 않는다 ---- */

describe("판을 정상으로 닫으면 판 도중의 실패 문구를 지운다", () => {
  it("답 전송이 실패한 뒤 시간이 다 되어 타이머가 닫으면 문구가 없다", async () => {
    await openRound();
    replies.push({ fail: 400, detail: GRADE_ERROR });
    await pick();
    assert.equal(playError(), GRADE_ERROR, "준비 실패: 판 도중 오류가 안 찼다");

    passDeadline();
    replies.push(SUMMARY);
    await tick();

    assertClean(readCard(), GRADE_ERROR);
    assert.deepEqual(actions(), ["start", "answer", "finish"]);
  });

  it("마감이 지난 뒤 답 전송이 실패해 곧바로 닫혀도 문구가 없다", async () => {
    await openRound();
    passDeadline();
    replies.push({ fail: 400, detail: GRADE_ERROR }, SUMMARY);
    await pick();
    await settle();

    assertClean(readCard(), GRADE_ERROR);
    assert.deepEqual(actions(), ["start", "answer", "finish"]);
    assert.equal(sent[2].token, "t0", "실패로 안 태워진 토큰으로 닫아야 한다");
  });

  it("마감 뒤 네트워크가 끊겨 답이 실패하면, 같은 답을 다시 보내 받은 새 토큰으로 닫고 문구가 없다", async () => {
    // 서버가 그 답을 이미 처리했을 수 있어, 들고 있는 토큰으로 닫으면 지난
    // 순번이라 거절된다. 같은 답을 다시 보내 새 토큰을 받은 뒤 닫는다.
    await openRound();
    passDeadline();
    replies.push({ throws: "Failed to fetch" });
    await pick();
    await settle();
    assert.deepEqual(actions(), ["start", "answer"], "끊긴 채로 바로 닫았다");

    replies.push(
      {
        token: "t1",
        result: { correct: false, skipped: false, in_time: true, score: -1, elapsed_ms: 100, answer_type: "word", answer_text: "a", answer_extra: "" },
        question: null,
        finished: true,
      },
      SUMMARY,
    );
    await tick();
    await settle();

    assertClean(readCard(), connectionLostMessage());
    assert.deepEqual(actions(), ["start", "answer", "answer", "finish"]);
    assert.equal(sent[2].choice_id, sent[1].choice_id, "다른 답을 보냈다");
    assert.equal(sent[2].token, "t0", "같은 토큰으로 다시 보내야 한다");
    assert.equal(sent[3].token, "t1", "새로 받은 토큰으로 닫아야 한다");
  });

  it("닫는 응답을 기다리는 사이 온 채점 실패도 닫힌 뒤에는 안 보인다", async () => {
    await openRound();
    passDeadline();
    const closing = later();
    replies.push(closing.promise, { fail: 400, detail: GRADE_ERROR });
    await tick();
    await pick();
    await settle();

    closing.resolve(SUMMARY);
    await settle();
    assertClean(readCard(), GRADE_ERROR);
    assert.deepEqual(actions(), ["start", "finish", "answer"], "닫기 요청이 두 번 나갔다");
  });

  it("닫기가 성공한 뒤에 도착한 채점 실패도 안 보인다", async () => {
    await openRound();
    passDeadline();
    const closing = later();
    const answering = later();
    replies.push(closing.promise, answering.promise);
    await tick();
    // 답 응답을 아직 안 풀었으므로 여기서 기다리면 끝나지 않는다.
    const picking = pick();
    await settle();

    closing.resolve(SUMMARY);
    await settle();
    answering.resolve({ fail: 400, detail: GRADE_ERROR });
    await picking;
    await settle();

    assertClean(readCard(), GRADE_ERROR);
    assert.deepEqual(actions(), ["start", "finish", "answer"]);
  });

  it("닫는 중에 타이머가 또 돌아도 요청은 하나고 문구가 없다", async () => {
    await openRound();
    replies.push({ fail: 400, detail: GRADE_ERROR });
    await pick();

    passDeadline();
    replies.push(SUMMARY);
    for (const run of [...intervals.values()]) {
      run();
      run();
    }
    await settle();

    assertClean(readCard(), GRADE_ERROR);
    assert.deepEqual(actions(), ["start", "answer", "finish"]);
  });

  it("마감 전의 답 실패는 지우지 않고 판을 이어 간다", async () => {
    await openRound();
    replies.push({ fail: 400, detail: GRADE_ERROR });
    await pick();
    assert.ok(isPlaying(), "마감 전인데 판이 끝났다");
    assert.equal(playError(), GRADE_ERROR);
    assert.deepEqual(actions(), ["start", "answer"]);
  });
});

describe("판을 닫지 못하면 오류 문구가 남는다", () => {
  it("타이머로 닫다가 실패하면 그 문구가 결과 없는 갈래에 나온다", async () => {
    await openRound();
    passDeadline();
    replies.push({ fail: 503, detail: FINISH_ERROR });
    await tick();

    const card = readCard();
    assert.equal(card.props.summary, null);
    assert.equal(card.props.error, FINISH_ERROR);
    assert.equal(times(card.text, FINISH_ERROR), 1);
    assert.equal(card.alerts.length, 0);
  });

  it("답도 닫기도 실패하면 닫기의 문구만 남는다", async () => {
    await openRound();
    passDeadline();
    replies.push({ fail: 400, detail: GRADE_ERROR }, { fail: 503, detail: FINISH_ERROR });
    await pick();
    await settle();

    const card = readCard();
    assert.equal(card.props.summary, null);
    assert.equal(times(card.text, FINISH_ERROR), 1);
    assert.equal(times(card.text, GRADE_ERROR), 0);
  });

  it("닫기 실패 뒤 한 판 더도 실패하면 새 문구 하나로 바뀌고, 다시 누르면 새 판이다", async () => {
    await openRound();
    passDeadline();
    replies.push({ fail: 503, detail: FINISH_ERROR });
    await tick();

    replies.push({ fail: 503, detail: START_ERROR });
    await press("onAgain");
    const card = readCard();
    assert.equal(card.props.summary, null);
    assert.equal(card.alerts.length, 0);
    assert.equal(times(card.text, START_ERROR), 1);
    assert.equal(times(card.text, FINISH_ERROR), 0);

    replies.push(started("t2"));
    await press("onAgain");
    assert.ok(isPlaying(), "다시 눌렀는데 새 판이 안 열렸다");
    assert.equal(playError(), "");
  });
});

/* ---- 한 판 더 ---- */

describe("한 판 더 실패", () => {
  beforeEach(finishRound);

  const FAILURES: [string, Reply, string][] = [
    ["서버가 거절", { fail: 503, detail: START_ERROR }, START_ERROR],
    ["본문이 JSON 이 아님", { fail: 502, noBody: true }, "요청이 실패했습니다."],
    // 브라우저의 영어 문구(Failed to fetch)가 아니라 사람이 읽을 문구로 알린다.
    ["네트워크 끊김", { throws: "Failed to fetch" }, connectionLostMessage()],
    [
      "문제가 빠진 응답",
      { token: "t1", question: null, round_seconds: 90, max_skips: 3 },
      "판을 여는 응답이 올바르지 않습니다. 다시 시도해주세요.",
    ],
  ];

  for (const [name, reply, message] of FAILURES) {
    it(`${name}: 결과를 그대로 두고 alert 한 개로 알린다`, async () => {
      replies.push(reply);
      await press("onAgain");

      const card = readCard();
      assertOneAlert(card, message);
      assert.equal(card.props.summary, SUMMARY, "실패했는데 지난 결과가 사라졌다");
      assert.match(card.text, /8문제 중 6개 정답/);
      assert.equal(card.button.props.disabled, false, "다시 누를 버튼이 잠겨 있다");
    });
  }

  it("다시 눌러 응답을 기다리는 동안은 지난 문구를 안 보이고 버튼이 잠긴다", async () => {
    replies.push({ fail: 503, detail: START_ERROR });
    await press("onAgain");

    const opening = later();
    replies.push(opening.promise);
    const pending = press("onAgain");
    await settle();
    const waiting = readCard();
    assert.equal(waiting.alerts.length, 0, "기다리는 중에 지난 오류가 남았다");
    assert.equal(waiting.button.props.disabled, true);

    opening.resolve(started("t2"));
    await pending;
    assert.ok(isPlaying());
  });

  it("다시 눌러 또 실패하면 새 문구 하나만 있다", async () => {
    replies.push({ fail: 503, detail: START_ERROR });
    await press("onAgain");
    replies.push({ fail: 503, detail: "두 번째 실패" });
    await press("onAgain");

    const card = readCard();
    assertOneAlert(card, "두 번째 실패");
    assert.equal(times(card.text, START_ERROR), 0);
  });

  it("다시 눌러 성공하면 오류 없이 새 판으로 가고, 그 판의 결과도 깨끗하다", async () => {
    replies.push({ fail: 503, detail: START_ERROR });
    await press("onAgain");

    replies.push(started("t2"));
    await press("onAgain");
    assert.ok(isPlaying(), "새 판이 안 열렸다");
    assert.equal(playError(), "", "지난 실패 문구가 새 판에 따라왔다");
    assert.equal(render().some(named("RoundResultCard")), false);

    render();
    passDeadline();
    const next = { ...SUMMARY, score: 7 };
    replies.push(next);
    await tick();
    const card = readCard();
    assert.equal(card.props.summary, next);
    assertClean(card, START_ERROR);
    assert.equal(sent.at(-1)?.token, "t2", "새 판의 토큰으로 닫아야 한다");
  });
});
