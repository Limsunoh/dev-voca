/**
 * 한 판에서 답하기 응답을 못 받았을 때 "다시 시도" 로 같은 답만 다시 보내는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 서버는 같은 토큰·같은 답이 다시 오면 처음 응답을 돌려주고, 다른 답이면
 * "이미 처리한 답입니다" 로 거절한다(backend session._take_step). 화면이 지킬 것:
 *
 *   끊김·5xx 뒤       보기·넘기기를 잠그고 "다시 시도" 를 보인다. 고른 보기 표시는 남는다
 *   4xx 뒤            서버가 거절한 것이라 잠그지 않는다
 *   잠긴 동안 누름    다른 보기·넘기기를 눌러도 남긴 답만 나간다
 *   마감              끊긴 채로는 닫지 않는다. 다시 시도로 새 토큰을 받은 뒤 그 토큰으로 닫는다
 *   언마운트          떠난 뒤 도착한 응답으로 요청을 더 보내지 않는다
 *
 * 방식은 round-again-error.test.mts 와 같다. react 훅을 대역으로 바꾸고 보드가
 * 넘긴 콜백을 진짜로 부른다. Date.now 와 setInterval 도 대역이다.
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
let effects: EffectSlot[] = [];

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
      const state = slot<EffectSlot>(() => {
        const created: EffectSlot = { deps: null, cleanup: undefined };
        effects.push(created);
        return created;
      }).value as EffectSlot;
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

const named = (name: string) => (el: El) =>
  typeof el.type === "function" && (el.type as { name: string }).name === name;

/* ---- 자료 ---- */

const question = (n: number) => ({
  kind: "meaning",
  kind_label: "뜻 고르기",
  question: `문제 ${n}`,
  prompt: "commit",
  category: "git",
  category_label: "Git",
  choices: [
    { id: 1, text: "a" },
    { id: 2, text: "b" },
    { id: 3, text: "c" },
  ],
});

const SUMMARY: RoundSummary = {
  score: 1,
  answered: 1,
  correct: 1,
  skipped: 0,
  recorded: true,
  guest: false,
};

const started = (t: string) => ({
  token: t,
  question: question(0),
  round_seconds: 90,
  max_skips: 3,
  reaction_pause_ms: 0,
});

const answered = (t: string, opts: { finished?: boolean; skipped?: boolean } = {}) => ({
  token: t,
  result: {
    correct: !opts.skipped,
    skipped: !!opts.skipped,
    in_time: true,
    score: opts.skipped ? 0 : 1,
    elapsed_ms: 100,
    answer_type: "word",
    answer_text: "a",
    answer_extra: "",
  },
  question: opts.finished ? null : question(1),
  finished: !!opts.finished,
});

/* ---- 대역 ---- */

type Reply =
  | { fail: number; detail?: string }
  | { throws: string }
  | Record<string, unknown>;

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
  effects = [];
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
      const { detail } = reply as { detail?: string };
      return {
        ok: false,
        status: reply.fail,
        json: async () => ({ detail }),
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

/** 화면을 떠난다. React 처럼 모든 effect 의 정리를 돌린다. */
function unmount() {
  for (const state of effects) {
    if (typeof state.cleanup === "function") state.cleanup();
    state.cleanup = undefined;
  }
}

function playProps(): Record<string, unknown> {
  const card = render().find(named("PlayCard"));
  assert.ok(card, "판 화면이 안 그려졌다");
  return card.props;
}

/** PlayCard 안쪽을 그려 보기 묶음·넘기기·다시 시도 버튼을 꺼낸다. */
function readPlay() {
  // 콜백은 렌더마다 새로 만들어지므로 같은 렌더의 props 로 버튼을 찾는다.
  const card = render().find(named("PlayCard"));
  assert.ok(card, "판 화면이 안 그려졌다");
  const props = card.props;
  const tree = flatten((card.type as (p: unknown) => unknown)(props));
  const buttons = tree.filter((el) => el.type === "button");
  return {
    props,
    choices: tree.find(named("QuestionCard")) as El,
    skip: buttons.find((b) => b.props.onClick === props.onSkip) as El | undefined,
    retry: buttons.find((b) => b.props.onClick === props.onRetry) as El | undefined,
  };
}

const pick = (id: number) => (playProps().onPick as (id: number) => Promise<void>)(id);
const skipNow = () => (playProps().onSkip as () => Promise<void>)();
const retry = () => (playProps().onRetry as () => Promise<void>)();

async function openRound() {
  replies.push(started("t0"));
  const start = render().find((e) => typeof e.props.onStart === "function");
  assert.ok(start, "시작 버튼이 없다");
  await (start.props.onStart as () => Promise<void>)();
  render();
}

const passDeadline = () => {
  clock += 90_001;
};

async function tick() {
  for (const run of [...intervals.values()]) run();
  await settle();
}

const answers = () => sent.filter((b) => b.action === "answer");
const actions = () => sent.map((b) => b.action);

function assertLost(lostChoice: number | null) {
  const play = readPlay();
  assert.equal(play.props.lost, true, "끊겼는데 lost 가 아니다");
  assert.equal(play.choices.props.busy, true, "끊긴 동안 보기가 잠기지 않았다");
  assert.equal(play.skip?.props.disabled, true, "끊긴 동안 넘기기가 잠기지 않았다");
  assert.ok(play.retry, "다시 시도 버튼이 없다");
  assert.equal(play.retry.props.disabled, false);
  assert.equal(play.retry.props.children, "다시 시도");
  assert.equal(play.props.pickedId, lostChoice, "고른 보기 표시가 사라졌다");
}

function assertNotLost() {
  const play = readPlay();
  assert.equal(play.props.lost, false);
  assert.equal(play.retry, undefined, "다시 시도 버튼이 남았다");
  assert.equal(play.choices.props.busy, false, "보기가 잠긴 채다");
}

/* ---- 끊김과 거절 ---- */

describe("답하기 응답을 못 받으면 잠그고 다시 시도를 둔다", () => {
  const UNSURE: [string, Reply][] = [
    ["연결 끊김", { throws: "Failed to fetch" }],
    ["500", { fail: 500, detail: "서버 오류" }],
    ["502 본문 없음", { fail: 502 }],
    ["503", { fail: 503, detail: "잠시 뒤" }],
  ];

  for (const [name, reply] of UNSURE) {
    it(`${name}: lost, 보기·넘기기 잠김, 고른 보기 표시 유지`, async () => {
      await openRound();
      replies.push(reply);
      await pick(2);
      assertLost(2);
      assert.notEqual(readPlay().props.error, "", "끊겼다는 안내가 없다");
    });
  }

  it("끊김 안내는 사람이 읽을 문구다", async () => {
    await openRound();
    replies.push({ throws: "Failed to fetch" });
    await pick(1);
    assert.equal(readPlay().props.error, connectionLostMessage());
  });

  it("400 은 서버가 거절한 것이라 잠그지 않는다", async () => {
    await openRound();
    replies.push({ fail: 400, detail: "이미 처리한 답입니다." });
    await pick(2);
    assertNotLost();
    assert.equal(readPlay().props.pickedId, null);
    assert.equal(readPlay().props.error, "이미 처리한 답입니다.");
  });

  for (const status of [401, 403, 429]) {
    it(`${status} 는 이 답이 처리됐는지 알려 주지 않아 잠근다`, async () => {
      await openRound();
      replies.push({ fail: status, detail: "잠시 뒤 다시 시도해주세요." });
      await pick(2);
      assertLost(2);
    });
  }

  it("다시 시도가 429 를 받아도 남긴 답을 버리지 않는다", async () => {
    // 처음 답은 서버가 이미 처리했을 수 있다. 여기서 풀면 다른 보기도, 들고
    // 있는 토큰으로 닫기도 거절돼 판 전체를 잃는다.
    await openRound();
    replies.push({ throws: "Failed to fetch" });
    await pick(2);
    replies.push({ fail: 429, detail: "요청이 많습니다." });
    await retry();
    assertLost(2);

    replies.push(answered("t1"));
    await retry();
    assertNotLost();
    assert.deepEqual(
      answers().map((a) => a.choice_id),
      [2, 2, 2],
    );
  });

  it("넘기기가 끊겨도 잠기고, 다시 시도는 넘기기로 나간다", async () => {
    await openRound();
    replies.push({ throws: "Failed to fetch" });
    await skipNow();
    assertLost(null);

    replies.push(answered("t1", { skipped: true }));
    await retry();
    assert.deepEqual(
      answers().map((b) => [b.token, b.skip, b.choice_id]),
      [
        ["t0", true, null],
        ["t0", true, null],
      ],
    );
    assertNotLost();
  });
});

describe("잠긴 동안에는 남긴 답만 나간다", () => {
  it("다른 보기·넘기기를 눌러도 처음 답이 같은 토큰으로 나간다", async () => {
    await openRound();
    replies.push({ throws: "Failed to fetch" });
    await pick(2);

    replies.push({ throws: "Failed to fetch" }, { throws: "Failed to fetch" });
    await pick(3);
    await skipNow();

    for (const body of answers()) {
      assert.equal(body.token, "t0");
      assert.equal(body.choice_id, 2, "잠긴 동안 다른 답이 나갔다");
      assert.equal(body.skip, false);
    }
    assertLost(2);
  });

  it("다시 시도도 또 끊기면 계속 잠겨 있고 표시가 남는다", async () => {
    await openRound();
    replies.push({ fail: 500 }, { throws: "Failed to fetch" }, { fail: 504 });
    await pick(3);
    await retry();
    await retry();
    assertLost(3);
    assert.equal(answers().length, 3);
  });

  it("다시 시도를 기다리는 동안 버튼이 잠기고 문구가 바뀐다", async () => {
    await openRound();
    replies.push({ throws: "Failed to fetch" });
    await pick(1);

    const waiting = later();
    replies.push(waiting.promise);
    const pending = retry();
    await settle();
    const play = readPlay();
    assert.equal(play.retry?.props.disabled, true);
    assert.equal(play.retry?.props.children, "보내는 중...");
    // 기다리는 동안 또 눌러도 요청은 하나다.
    await retry();
    assert.equal(answers().length, 2);

    waiting.resolve(answered("t1"));
    await pending;
    assertNotLost();
  });

  it("다시 시도가 4xx 로 거절되면 잠금을 풀어 다른 답을 고를 수 있다", async () => {
    await openRound();
    replies.push({ throws: "Failed to fetch" });
    await pick(1);
    replies.push({ fail: 400, detail: "판 정보가 올바르지 않습니다." });
    await retry();
    assertNotLost();

    replies.push(answered("t1"));
    await pick(2);
    assert.equal(answers().at(-1)?.choice_id, 2);
  });
});

describe("다시 시도가 성공하면 새 토큰으로 이어간다", () => {
  it("다음 답은 새 토큰으로 나가고 점수는 한 번만 센다", async () => {
    await openRound();
    replies.push({ throws: "Failed to fetch" });
    await pick(1);
    replies.push(answered("t1"));
    await retry();

    assertNotLost();
    assert.equal(readPlay().props.pickedId, null);
    assert.deepEqual(readPlay().props.tally, { answered: 1, correct: 1, score: 1, late: 0 });

    replies.push(answered("t2"));
    await pick(2);
    assert.equal(answers().at(-1)?.token, "t1");
  });

  it("마지막 답이었으면 다시 시도 성공 뒤 새 토큰으로 닫는다", async () => {
    await openRound();
    replies.push({ throws: "Failed to fetch" });
    await pick(1);
    replies.push(answered("t1", { finished: true }), SUMMARY);
    await retry();
    await settle();

    assert.deepEqual(actions(), ["start", "answer", "answer", "finish"]);
    assert.equal(sent.at(-1)?.token, "t1");
    assert.ok(render().some(named("RoundResultCard")), "결과 화면으로 안 갔다");
  });
});

describe("마감", () => {
  it("끊긴 채 마감이 지나면 타이머가 그 답을 다시 보내고 새 토큰으로 닫는다", async () => {
    // 들고 있는 토큰으로 바로 닫으면, 서버가 그 답을 처리했을 때 지난 순번이라
    // 거절되고 판 전체가 안 남는다.
    await openRound();
    replies.push({ throws: "Failed to fetch" });
    await pick(1);

    passDeadline();
    replies.push(answered("t1"), SUMMARY);
    await tick();
    await settle();
    assert.deepEqual(actions(), ["start", "answer", "answer", "finish"]);
    assert.equal(answers()[1].choice_id, 1, "다른 답을 보냈다");
    assert.equal(answers()[1].token, "t0", "같은 토큰으로 다시 보내야 한다");
    assert.equal(sent.at(-1)?.token, "t1", "옛 토큰으로 닫았다");
  });

  it("마감에 다시 보내기도 실패하면 들고 있던 토큰으로 닫아 본다", async () => {
    // 서버 오류가 계속되면 다시 보내기만 기다리다 판이 영영 안 닫힌다. 서버가
    // 그 답을 처리하지 못했으면 들고 있던 토큰이 아직 살아 있어 닫힌다.
    await openRound();
    replies.push({ fail: 500 });
    await pick(1);

    passDeadline();
    replies.push({ fail: 500 }, SUMMARY);
    await tick();
    await settle();
    assert.deepEqual(actions(), ["start", "answer", "answer", "finish"]);
    assert.equal(sent.at(-1)?.token, "t0");
  });

  it("타이머가 다시 보내는 동안 또 돌아도 요청은 한 번이다", async () => {
    await openRound();
    replies.push({ throws: "Failed to fetch" });
    await pick(1);

    passDeadline();
    const resend = later();
    replies.push(resend.promise, SUMMARY);
    await tick();
    await tick();
    await tick();
    assert.deepEqual(actions(), ["start", "answer", "answer"], "다시 보내기가 겹쳐 나갔다");
    resend.resolve(answered("t1"));
    await settle();
    await settle();
    assert.deepEqual(actions(), ["start", "answer", "answer", "finish"]);
  });

  it("마감 뒤 끊기면 그 자리에서 옛 토큰으로 닫지 않는다", async () => {
    // 답하기가 끝난 자리(catch)에서는 닫지 않고, 타이머의 다음 틱이 그 답을
    // 다시 보낸 뒤 닫는다(위 테스트).
    await openRound();
    passDeadline();
    replies.push({ fail: 500 });
    await pick(1);
    assert.deepEqual(actions(), ["start", "answer"]);
    assertLost(1);
  });

  it("마감 전 다시 시도가 성공한 뒤 마감이 지나면 그 새 토큰으로 닫는다", async () => {
    await openRound();
    replies.push({ throws: "Failed to fetch" });
    await pick(1);

    replies.push(answered("t1"));
    await retry();
    passDeadline();
    replies.push(SUMMARY);
    await tick();
    assert.deepEqual(actions(), ["start", "answer", "answer", "finish"]);
    assert.equal(sent.at(-1)?.token, "t1", "옛 토큰으로 닫았다");
  });

  it("마감 뒤 4xx 거절이면 예전처럼 들고 있던 토큰으로 곧바로 닫는다", async () => {
    await openRound();
    passDeadline();
    replies.push({ fail: 400, detail: "거절" }, SUMMARY);
    await pick(1);
    await settle();
    assert.deepEqual(actions(), ["start", "answer", "finish"]);
    assert.equal(sent.at(-1)?.token, "t0");
  });
});

describe("화면을 떠난 뒤", () => {
  it("다시 시도 응답이 떠난 뒤 오면 닫기를 보내지 않는다", async () => {
    await openRound();
    replies.push({ throws: "Failed to fetch" });
    await pick(1);
    passDeadline();

    const waiting = later();
    replies.push(waiting.promise);
    const pending = retry();
    await settle();
    unmount();
    waiting.resolve(answered("t1"));
    await pending;
    await settle();
    assert.deepEqual(actions(), ["start", "answer", "answer"]);
  });

  it("처음 답이 떠난 뒤 끊김으로 끝나도 아무것도 더 보내지 않는다", async () => {
    await openRound();
    const waiting = later();
    replies.push(waiting.promise);
    const pending = pick(1);
    await settle();
    unmount();
    waiting.resolve({ throws: "Failed to fetch" });
    await pending;
    await settle();
    assert.deepEqual(actions(), ["start", "answer"]);
  });
});


describe("다음 판으로 새지 않는다", () => {
  it("닫는 중에 보낸 답이 끊기고 닫기가 성공하면, 한 판 더의 새 판은 잠겨 있지 않다", async () => {
    await openRound();
    passDeadline();
    const closing = later();
    const answering = later();
    replies.push(closing.promise, answering.promise);
    await tick();
    const picking = pick(2);
    await settle();
    closing.resolve(SUMMARY);
    await settle();
    answering.resolve({ fail: 500 });
    await picking;
    await settle();
    assert.ok(render().some(named("RoundResultCard")));

    replies.push(started("t9"));
    const again = render().find((e) => typeof e.props.onAgain === "function") as El;
    await (again.props.onAgain as () => Promise<void>)();
    render();
    const play = readPlay();
    assert.equal(play.props.lost, false, "지난 판의 lost 가 새 판으로 넘어왔다");
    assert.equal(play.props.pickedId, null);
    replies.push(answered("t10"));
    await pick(3);
    assert.equal(answers().at(-1)?.choice_id, 3, "새 판에서 지난 판의 답이 나갔다");
  });
});
