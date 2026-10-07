/**
 * 한 판(RoundBoard)을 시작한 첫 그림이 남은 시간 전부인지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 남은 시간은 타이머 effect 가 채우는데, effect 는 판이 그려진 뒤에야 돈다.
 * 시작이 left 를 채우지 않으면 첫 그림이 0 이다. 숫자 "0" 이 급할 때 색으로
 * 한 번 뜨고 막대가 0 에서 차오른다. 한 판 더를 누르면 지난 판의 남은 시간이
 * 첫 그림에 남는다.
 *
 * effect 를 일부러 안 돌린다. 이 테스트가 보려는 것이 "effect 가 돌기 전" 이다.
 * 훅 대역과 fetch 대역은 exit-destinations.test.mts 와 같은 방식이다. PlayCard
 * 는 훅이 없어 돌려받은 요소의 type 을 그대로 불러 안쪽 트리를 본다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

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

function ExitGuardStub() {
  return null;
}

mock.module("@/components/ExitGuard", {
  namedExports: { ExitGuard: ExitGuardStub },
});

const { RoundBoard } = await import("./RoundBoard");

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

/* ---- 대역 ---- */

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

/** 다음 시작 응답의 판 길이(초). */
let roundSeconds = 90;
/** 시작 요청이 실패하는가. */
let startFails = false;

const realFetch = globalThis.fetch;
const realDocument = (globalThis as { document?: unknown }).document;
after(() => {
  globalThis.fetch = realFetch;
  (globalThis as { document?: unknown }).document = realDocument;
});

beforeEach(() => {
  slots = [];
  roundSeconds = 90;
  startFails = false;
  (globalThis as { document?: unknown }).document = {
    documentElement: { style: { setProperty() {}, removeProperty() {} } },
  };
  globalThis.fetch = (async (_input: string, init: RequestInit) => {
    const body = JSON.parse(String(init.body)) as { action: string };
    const reply = (status: number, data: unknown) =>
      ({ ok: status < 400, status, json: async () => data }) as Response;

    if (body.action === "start") {
      if (startFails) return reply(503, { detail: "잠시 후" });
      return reply(200, {
        token: "t0",
        question: QUESTION,
        round_seconds: roundSeconds,
        max_skips: 3,
        reaction_pause_ms: 0,
      });
    }
    if (body.action === "answer") {
      return reply(200, {
        token: "t1",
        result: {
          correct: true,
          skipped: false,
          in_time: true,
          score: 1,
          elapsed_ms: 500,
          answer_type: "",
          answer_text: "a",
          answer_extra: "",
        },
        question: null,
        finished: true,
      });
    }
    return reply(200, { score: 1, answered: 1, correct: 1, skipped: 0, recorded: true });
  }) as typeof fetch;
});

/* ---- 도구 ---- */

function render() {
  cursor = 0;
  return RoundBoard({ isGuest: false });
}

const settle = () => new Promise((r) => setTimeout(r, 0));

function withProp(tree: unknown, name: string): El {
  const found = flatten(tree).find((e) => typeof e.props[name] === "function");
  assert.ok(found, `${name} 를 가진 요소가 없다`);
  return found;
}

/** 시작 버튼(또는 한 판 더)을 누르고, effect 가 돌기 전의 첫 그림을 돌려준다. */
async function press(name: "onStart" | "onAgain") {
  (withProp(render(), name).props[name] as () => Promise<void>)();
  await settle();
  return render();
}

/** 첫 그림의 시계. PlayCard 를 불러 숫자·막대를 읽는다. */
function clock(tree: unknown) {
  const card = flatten(tree).find(named("PlayCard"));
  assert.ok(card, "판이 안 열렸다 - PlayCard 가 없다");
  const inner = flatten((card.type as (p: unknown) => unknown)(card.props));
  const number = inner.find((e) => e.type === "span" && e.props["aria-hidden"] === true);
  const bar = inner.find((e) => e.props.role === "progressbar");
  assert.ok(number && bar, "숫자나 진행 막대를 못 찾았다");
  const fill = flatten(bar.props.children)[0];
  const fillStyle = fill.props.style as { width: string; background: string };
  return {
    left: card.props.left,
    total: card.props.total,
    seconds: number.props.children,
    color: (number.props.style as { color: string }).color,
    valueNow: bar.props["aria-valuenow"],
    valueMax: bar.props["aria-valuemax"],
    width: fillStyle.width,
    barColor: fillStyle.background,
  };
}

/* ---- 테스트 ---- */

describe("한 판 시작의 첫 그림", () => {
  it("90초 판은 90, 막대 100%, 경과 0, 평소 색으로 시작한다", async () => {
    assert.deepEqual(clock(await press("onStart")), {
      left: 90_000,
      total: 90,
      seconds: 90,
      color: "var(--foreground)",
      valueNow: 0,
      valueMax: 90,
      width: "100%",
      barColor: "var(--foreground)",
    });
  });

  it("서버가 정한 길이를 그대로 쓴다(60초)", async () => {
    roundSeconds = 60;
    const now = clock(await press("onStart"));
    assert.equal(now.left, 60_000);
    assert.equal(now.seconds, 60);
    assert.equal(now.width, "100%");
    assert.equal(now.valueNow, 0);
  });

  it("10초 이하 판도 시작은 꽉 찬 막대다", async () => {
    // 급할 때 색은 남은 시간이 정한다. 짧은 판은 처음부터 코랄이 맞다.
    roundSeconds = 10;
    const now = clock(await press("onStart"));
    assert.equal(now.seconds, 10);
    assert.equal(now.width, "100%");
    assert.equal(now.color, "var(--coral)");
  });

  it("한 판 더는 지난 판의 시계가 아니라 새 판 길이로 시작한다", async () => {
    const first = await press("onStart");
    assert.equal(clock(first).left, 90_000);
    (withProp(first, "onPick").props.onPick as (id: number) => void)(1);
    await settle();
    await settle();
    assert.ok(flatten(render()).some(named("RoundResultCard")), "판이 안 끝났다");

    roundSeconds = 45;
    const again = clock(await press("onAgain"));
    assert.equal(again.left, 45_000);
    assert.equal(again.seconds, 45);
    assert.equal(again.width, "100%");
  });

  it("시작이 실패하면 판이 안 열린다", async () => {
    startFails = true;
    const tree = await press("onStart");
    assert.equal(flatten(tree).some(named("PlayCard")), false);
    assert.ok(flatten(tree).some(named("StartCard")));
  });
});
