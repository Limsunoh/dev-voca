/**
 * 문제풀기(QuizBoard)에서 채점 응답이 "다음 문제" 보다 늦게 오면 버리는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * "다음 문제" 버튼은 보기를 고르자마자 뜬다. 채점이 느리면 그 버튼이 먼저
 * 눌리고, 늦게 온 옛 문제의 채점이 새 문제 위에 해설·점수·연출을 얹는다.
 * 실패 응답이면 새 문제에 "채점하지 못했습니다" 가 붙는다. 반대로 같은 문제
 * 에서 늦게 온 채점은 그대로 반영돼야 한다 - 너무 넓게 버리면 정상 흐름이
 * 깨진다.
 *
 * 훅 대역은 quiz-kind-picker.test.mts 와 같은 방식이다. 채점(POST)만 붙잡아
 * 두고 테스트가 원하는 순서로 풀어 준다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

const realReact = await import("react");

type Slot = { value: unknown };
type Effect = { run: () => void | (() => void); deps?: unknown[] };

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
    useCallback<T>(fn: T) {
      return fn;
    },
    useEffect(run: Effect["run"], deps?: unknown[]) {
      effects.push({ run, deps });
    },
  },
});

const { QuizBoard } = await import("./QuizBoard");
const { renderToStaticMarkup } = await import("react-dom/server");

type El = { type: unknown; props: Record<string, unknown> };

/* ---- 대역 ---- */

const realFetch = globalThis.fetch;
const realWindow = (globalThis as { window?: unknown }).window;
after(() => {
  globalThis.fetch = realFetch;
  (globalThis as { window?: unknown }).window = realWindow;
});

/** 붙잡아 둔 채점 요청. 보낸 토큰과 푸는 손잡이. */
type Held = {
  token: string;
  pass: (correct: boolean) => void;
  fail: (status: number) => void;
  drop: () => void;
};

let held: Held[] = [];
/** 문제 요청에 차례로 돌려줄 상태 코드. 비면 200. */
let statuses: number[] = [];
/** 지금까지 낸 문제 수. 토큰을 t1, t2 ... 로 붙인다. */
let served = 0;

const QUESTION = {
  kind: "meaning",
  kind_label: "뜻 고르기",
  question: "이 단어의 뜻은?",
  prompt: "commit",
  category: "git",
  category_label: "Git",
  choices: [
    { id: 12, text: "a" },
    { id: 13, text: "b" },
    { id: 14, text: "c" },
    { id: 15, text: "d" },
  ],
};

beforeEach(() => {
  slots = [];
  held = [];
  statuses = [];
  served = 0;
  (globalThis as { window?: unknown }).window = { scrollTo() {} };
  globalThis.fetch = (async (_input: string | URL, init?: RequestInit) => {
    if (init?.method === "POST") {
      const { token } = JSON.parse(String(init.body)) as { token: string };
      return new Promise<Response>((resolve, reject) => {
        held.push({
          token,
          pass: (correct) =>
            resolve({
              ok: true,
              status: 200,
              json: async () => ({ correct, answer_id: 12, explanation: "" }),
            } as Response),
          fail: (status) =>
            resolve({ ok: false, status, json: async () => ({ detail: "x" }) } as Response),
          drop: () => reject(new TypeError("Failed to fetch")),
        });
      });
    }
    const status = statuses.shift() ?? 200;
    served += 1;
    const token = `t${served}`;
    return {
      ok: status < 400,
      status,
      json: async () => (status < 400 ? { ...QUESTION, token } : { detail: "x" }),
    } as Response;
  }) as typeof fetch;
});

/* ---- 도구 ---- */

const PROPS = { content: "words" as const };

function render(): El {
  cursor = 0;
  effects = [];
  return QuizBoard(PROPS) as unknown as El;
}

async function settle() {
  for (let i = 0; i < 5; i++) await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
}

function findAll(node: unknown, test: (el: El) => boolean, out: El[] = []): El[] {
  if (Array.isArray(node)) {
    for (const one of node) findAll(one, test, out);
    return out;
  }
  if (!node || typeof node !== "object" || !("props" in node)) return out;
  const el = node as El;
  if (test(el)) out.push(el);
  findAll(el.props.children, test, out);
  return out;
}

const named = (name: string) => (el: El) =>
  typeof el.type === "function" && (el.type as { name: string }).name === name;

async function start() {
  render();
  const load = effects.filter((e) => e.deps?.length === 1 && typeof e.deps[0] === "function");
  assert.equal(load.length, 1, "첫 문제를 부르는 effect 를 못 찾았다");
  load[0].run();
  await settle();
}

/** 첫 보기를 고른다. 채점은 붙잡힌 채로 남는다. */
async function choose() {
  const choices = findAll(render(), named("ChoiceButton"));
  assert.equal(choices.length, 4, "보기가 없다 - 문제를 못 받았다");
  (choices[0].props.onClick as () => void)();
  await settle();
}

async function next() {
  const button = findAll(
    render(),
    (el) => el.type === "button" && el.props.children === "다음 문제",
  );
  assert.equal(button.length, 1, "다음 문제 버튼이 없다");
  (button[0].props.onClick as () => void)();
  await settle();
}

/** 화면에서 읽어 낸 지금 상태. */
function screen() {
  const tree = render();
  const burst = findAll(tree, named("Burst"))[0];
  const reaction = findAll(tree, named("Reaction"))[0];
  cursor = 0;
  const page = renderToStaticMarkup(tree as never);
  const score = /(\d+)문제 중 (\d+)개/.exec(page);
  return {
    burst: burst.props.fire as number,
    reaction: reaction.props.fire as number,
    explained: findAll(tree, named("Explanation")).length > 0,
    alert: findAll(tree, (el) => el.props.role === "alert").length > 0,
    score: score ? `${score[1]}/${score[2]}` : null,
    shaking: /class="[^"]*\bshake(-alt)?\b/.test(page),
    locked: findAll(tree, named("ChoiceButton")).some((c) => c.props.disabled === true),
    page,
  };
}

/** 아무것도 반영되지 않은 새 문제 화면. */
function assertUntouched() {
  const now = screen();
  assert.equal(now.explained, false, "새 문제에 옛 해설이 붙었다");
  assert.equal(now.alert, false, "새 문제에 옛 채점의 에러가 붙었다");
  assert.equal(now.score, null, "옛 채점이 점수에 들어갔다");
  assert.equal(now.burst, 0, "옛 정답으로 축포가 터졌다");
  assert.equal(now.reaction, 0, "옛 채점으로 연출이 돌았다");
  assert.equal(now.shaking, false, "옛 오답으로 보기가 흔들렸다");
  assert.equal(now.locked, false, "새 문제의 보기가 잠겼다");
  assert.doesNotMatch(now.page, /다음 문제/, "고르지도 않았는데 다음 문제 버튼이 떴다");
}

/* ---- 테스트 ---- */

describe("늦게 온 채점 - 같은 문제면 반영한다", () => {
  it("정답이 늦게 와도 해설·점수·축포·연출이 붙는다", async () => {
    await start();
    await choose();
    assert.equal(screen().explained, false, "채점 전에 해설이 떴다");
    for (let i = 0; i < 5; i++) await settle();
    held[0].pass(true);
    await settle();

    const now = screen();
    assert.equal(now.explained, true);
    assert.equal(now.score, "1/1");
    assert.equal(now.burst, 1);
    assert.equal(now.reaction, 1);
  });

  it("오답도 반영한다 - 흔들리고 축포는 없다", async () => {
    await start();
    await choose();
    held[0].pass(false);
    await settle();

    const now = screen();
    assert.equal(now.score, "1/0");
    assert.equal(now.burst, 0);
    assert.equal(now.reaction, 1);
    assert.equal(now.shaking, true);
  });

  it("채점 실패는 그 문제에 안내를 띄운다", async () => {
    await start();
    await choose();
    held[0].fail(500);
    await settle();

    const now = screen();
    assert.equal(now.alert, true);
    assert.match(now.page, /채점하지 못했습니다/);
    assert.equal(now.score, null);
  });

  it("기다리는 사이 유형을 바꿔도 버리지 않는다", async () => {
    // 답한 뒤 유형 변경은 새 문제를 받지 않는다. 그러니 문제 번호도 그대로다.
    await start();
    await choose();
    const picker = findAll(render(), named("KindPicker"))[0];
    (picker.props.onChange as (v: string) => void)("term");
    await settle();
    held[0].pass(true);
    await settle();

    assert.equal(served, 1, "답한 뒤 유형을 바꿨는데 새 문제를 받았다");
    assert.equal(screen().explained, true);
  });

  it("두 문제를 차례로 풀며 매번 늦게 와도 둘 다 센다", async () => {
    await start();
    await choose();
    held[0].pass(true);
    await settle();
    await next();
    await choose();
    held[1].pass(true);
    await settle();

    const now = screen();
    assert.equal(now.score, "2/2");
    assert.equal(now.burst, 2);
    assert.equal(now.reaction, 2);
  });
});

describe("늦게 온 채점 - 다음 문제로 넘어갔으면 버린다", () => {
  it("정답 응답", async () => {
    await start();
    await choose();
    await next();
    held[0].pass(true);
    await settle();
    assertUntouched();
  });

  it("오답 응답", async () => {
    await start();
    await choose();
    await next();
    held[0].pass(false);
    await settle();
    assertUntouched();
  });

  it("서버가 실패로 답한 경우(500)", async () => {
    await start();
    await choose();
    await next();
    held[0].fail(500);
    await settle();
    assertUntouched();
  });

  it("연결이 끊긴 경우(reject)", async () => {
    await start();
    await choose();
    await next();
    held[0].drop();
    await settle();
    assertUntouched();
  });

  it("새 문제에 답하는 중에 옛 채점이 오면 새 채점만 반영한다", async () => {
    await start();
    await choose();
    await next();
    await choose();
    assert.deepEqual(held.map((h) => h.token), ["t1", "t2"]);

    // 옛 것이 먼저 온다. 새 문제는 아직 채점 대기다.
    held[0].pass(true);
    await settle();
    let now = screen();
    assert.equal(now.explained, false, "새 문제가 옛 해설로 채워졌다");
    assert.equal(now.score, null);
    assert.equal(now.burst, 0);

    held[1].pass(false);
    await settle();
    now = screen();
    assert.equal(now.explained, true);
    assert.equal(now.score, "1/0", "옛 정답이 같이 셌다");
    assert.equal(now.burst, 0);
    assert.equal(now.reaction, 1);
  });

  it("새 채점이 먼저 오고 옛 채점이 뒤에 와도 덮지 않는다", async () => {
    await start();
    await choose();
    await next();
    await choose();

    held[1].pass(false);
    await settle();
    held[0].pass(true);
    await settle();

    const now = screen();
    assert.equal(now.score, "1/0");
    assert.equal(now.burst, 0, "옛 정답으로 축포가 터졌다");
    assert.equal(now.reaction, 1);
    assert.equal(now.shaking, true, "옛 정답이 새 오답의 판정을 덮었다");
  });

  it("새 문제가 채점에 실패했을 때 옛 정답이 와도 에러가 그대로다", async () => {
    await start();
    await choose();
    await next();
    await choose();

    held[1].drop();
    await settle();
    held[0].pass(true);
    await settle();

    const now = screen();
    assert.equal(now.alert, true);
    assert.equal(now.explained, false);
    assert.equal(now.score, null);
  });

  it("두 문제를 건너뛴 뒤 둘 다 늦게 와도 세 번째 문제만 센다", async () => {
    await start();
    await choose();
    await next();
    await choose();
    await next();
    await choose();
    held[2].pass(true);
    await settle();
    held[0].pass(false);
    held[1].fail(503);
    await settle();

    const now = screen();
    assert.equal(now.score, "1/1");
    assert.equal(now.burst, 1);
    assert.equal(now.reaction, 1);
    assert.equal(now.alert, false);
  });

  it("다음 문제를 못 받은 안내 위에 옛 채점이 오지 않는다", async () => {
    // 404 안내 화면에서 늦게 온 실패가 "채점하지 못했습니다" 로 문구를 덮으면
    // "섞어서로 풀기"·"처음부터 다시" 중 맞는 버튼이 안 뜬다.
    statuses = [200, 404];
    await start();
    await choose();
    await next();
    const before = screen().page;
    assert.match(before, /다 풀었습니다/);

    held[0].drop();
    await settle();
    let now = screen();
    assert.match(now.page, /다 풀었습니다/);
    assert.doesNotMatch(now.page, /채점하지 못했습니다/);

    // 처음부터 다시 받은 문제의 채점은 그대로 센다.
    statuses = [];
    const again = findAll(
      render(),
      (el) => el.type === "button" && el.props.children === "처음부터 다시",
    );
    (again[0].props.onClick as () => void)();
    await settle();
    await choose();
    held[1].pass(true);
    await settle();
    now = screen();
    assert.equal(now.score, "1/1");
  });
});
