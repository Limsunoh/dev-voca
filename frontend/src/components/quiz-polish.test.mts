/**
 * 문제풀기 다듬기를 깨뜨려 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 네 가지를 경계에서 본다.
 *   - 늦게 온 채점: 도착 순서가 뒤섞여도 점수·제외 목록은 맞고, 해설·연출·연속
 *     정답은 지금 문제의 것만 남는가. "처음부터 다시" 로 비운 판에는 안 들어가는가.
 *   - 새로고침 경고: 진짜 EventTarget 에 걸어, 푼 수가 0 으로 돌아가면 풀리는가.
 *   - 없는 분류: 두 페이지가 판과 고르개에 같은 값을 넘기는가.
 *   - picker: 어느 가지에서도 유형 고르개 앞에 있고, 안 넘겨도 괜찮은가.
 *
 * 훅·fetch 대역은 quiz-board-late-grade.test.mts 와 같은 방식이다. 푼 수를
 * 적는 effect 만 commit() 으로 직접 돌려 경고가 실제로 걸리는지 본다.
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

/** 페이지가 받을 분류 목록. 테스트마다 바꾼다. */
let categoryList: { value: string; label: string }[] = [];

mock.module("@/lib/api/vocab", {
  namedExports: { getCategories: async () => categoryList },
});
mock.module("@/lib/api/sentences", {
  namedExports: { getSentenceCategories: async () => categoryList },
});

const { QuizBoard } = await import("./QuizBoard");
const { CategoryPicker } = await import("./CategoryPicker");
const { clearSolved, markSolved, solvedNow } = await import("@/lib/quiz-progress");
const { renderToStaticMarkup } = await import("react-dom/server");
const wordsPage = (await import("@/app/test/words/page")).default;
const sentencesPage = (await import("@/app/test/sentences/page")).default;

type El = { type: unknown; props: Record<string, unknown>; key?: string | null };

/* ---- 대역 ---- */

const realFetch = globalThis.fetch;
const realWindow = (globalThis as { window?: unknown }).window;
const g = globalThis as unknown as Record<string, unknown>;

after(() => {
  globalThis.fetch = realFetch;
  (globalThis as { window?: unknown }).window = realWindow;
  delete g.addEventListener;
  delete g.removeEventListener;
});

/** 붙잡아 둔 채점 요청. 정답이면 어느 id 를 답으로 돌려줄지 고를 수 있다. */
type Held = {
  token: string;
  pass: (correct: boolean, answerId?: number) => void;
  fail: (status: number) => void;
  drop: () => void;
  garbled: () => void;
};

let held: Held[] = [];
let statuses: number[] = [];
let served = 0;
let asked: string[] = [];
/** 문제 응답에 덮어쓸 값. 차례로 쓴다. */
let questionOverrides: Record<string, unknown>[] = [];
/** 있으면 문제 응답을 이 약속이 풀릴 때까지 붙잡는다. */
let questionGate: Promise<void> | null = null;

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

/** beforeunload 를 받는 진짜 EventTarget. quiz-progress 는 globalThis 에 건다. */
let unloadTarget = new EventTarget();
/** 푼 수 effect 에 마지막으로 넘긴 값. 값이 바뀔 때만 돌린다. */
let lastCommitted: unknown;

beforeEach(() => {
  slots = [];
  held = [];
  statuses = [];
  served = 0;
  asked = [];
  questionOverrides = [];
  questionGate = null;
  lastCommitted = undefined;
  categoryList = [];
  props = { content: "words" };

  unloadTarget = new EventTarget();
  g.addEventListener = unloadTarget.addEventListener.bind(unloadTarget);
  g.removeEventListener = unloadTarget.removeEventListener.bind(unloadTarget);
  clearSolved();

  (globalThis as { window?: unknown }).window = { scrollTo() {} };
  globalThis.fetch = (async (input: string | URL, init?: RequestInit) => {
    if (init?.method === "POST") {
      const { token } = JSON.parse(String(init.body)) as { token: string };
      return new Promise<Response>((resolve, reject) => {
        held.push({
          token,
          pass: (correct, answerId = 12) =>
            resolve({
              ok: true,
              status: 200,
              json: async () => ({ correct, answer_id: answerId, explanation: "" }),
            } as Response),
          fail: (status) =>
            resolve({ ok: false, status, json: async () => ({ detail: "x" }) } as Response),
          drop: () => reject(new TypeError("Failed to fetch")),
          garbled: () =>
            resolve({
              ok: true,
              status: 200,
              json: async () => {
                throw new SyntaxError("Unexpected token <");
              },
            } as unknown as Response),
        });
      });
    }
    asked.push(String(input));
    if (questionGate) await questionGate;
    const status = statuses.shift() ?? 200;
    served += 1;
    const token = `t${served}`;
    const over = questionOverrides.shift() ?? {};
    return {
      ok: status < 400,
      status,
      json: async () => (status < 400 ? { ...QUESTION, ...over, token } : { detail: "x" }),
    } as Response;
  }) as typeof fetch;
});

/* ---- 도구 ---- */

let props: Parameters<typeof QuizBoard>[0] = { content: "words" };

function render(): El {
  cursor = 0;
  effects = [];
  return QuizBoard(props) as unknown as El;
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

function clickButton(label: string) {
  const button = findAll(render(), (el) => el.type === "button" && el.props.children === label);
  assert.equal(button.length, 1, `${label} 버튼이 없다`);
  (button[0].props.onClick as () => void)();
}

async function next() {
  clickButton("다음 문제");
  await settle();
}

/** 화면에서 읽어 낸 지금 상태. */
function screen() {
  const tree = render();
  const burst = findAll(tree, named("Burst"))[0];
  const reaction = findAll(tree, named("Reaction"))[0];
  // 유형 고르개의 훅 칸이 판의 칸을 읽지 않게 뒤에 붙인다.
  cursor = slots.length;
  const page = renderToStaticMarkup(tree as never);
  const score = /(\d+)문제 중 (\d+)개/.exec(page);
  const combo = /연속<\/span>(\d+)/.exec(page);
  return {
    burst: burst.props.fire as number,
    reaction: reaction.props.fire as number,
    explained: findAll(tree, named("Explanation")).length > 0,
    alert: findAll(tree, (el) => el.props.role === "alert").length > 0,
    score: score ? `${score[1]}/${score[2]}` : null,
    combo: combo ? Number(combo[1]) : null,
    shaking: /class="[^"]*\bshake(-alt)?\b/.test(page),
    page,
  };
}

/** 푼 수 effect 를 값이 바뀌었을 때만 돌린다. React 가 커밋 뒤 하는 일이다. */
function commit() {
  render();
  const effect = effects.find((e) => e.deps?.length === 1 && typeof e.deps[0] === "number");
  assert.ok(effect, "푼 수를 적는 effect 를 못 찾았다");
  if (effect.deps?.[0] !== lastCommitted) {
    lastCommitted = effect.deps?.[0];
    effect.run();
  }
}

/** 판이 사라질 때 React 가 돌리는 정리. */
function unmount() {
  render();
  const effect = effects.find((e) => e.deps?.length === 0);
  assert.ok(effect, "판을 치우는 effect 를 못 찾았다");
  const cleanup = effect.run();
  assert.equal(typeof cleanup, "function");
  (cleanup as () => void)();
}

/** beforeunload 를 쏘아 확인 창이 뜰 상황인지 본다. */
function fireUnload() {
  const event = new Event("beforeunload", { cancelable: true });
  // Node 의 Event.returnValue 는 읽기 전용이다. 브라우저의 BeforeUnloadEvent 처럼 쓸 수 있게 편다.
  Object.defineProperty(event, "returnValue", { value: "처음 값", writable: true });
  unloadTarget.dispatchEvent(event);
  return { prompted: event.defaultPrevented, returnValue: (event as BeforeUnloadEvent).returnValue };
}

const excludeOf = (url: string | undefined) =>
  new URL(url ?? "", "http://x").searchParams.get("exclude")?.split(",") ?? [];

/** 세 문제를 고르기까지 해 둔다. 채점 셋이 모두 붙잡혀 있다. */
async function threeHeld() {
  await start();
  await choose();
  await next();
  await choose();
  await next();
  await choose();
  assert.deepEqual(held.map((h) => h.token), ["t1", "t2", "t3"]);
}

/* ---- 늦은 채점 ---- */

describe("늦은 채점 - 도착 순서가 뒤섞일 때", () => {
  it("셋이 거꾸로 와도 점수는 다 들어가고 연출은 지금 문제 것 하나다", async () => {
    await threeHeld();
    held[2].pass(true);
    await settle();
    held[1].pass(false);
    await settle();
    held[0].pass(true);
    await settle();

    const now = screen();
    assert.equal(now.score, "3/2");
    assert.equal(now.explained, true);
    assert.equal(now.burst, 1);
    assert.equal(now.reaction, 1);
    assert.equal(now.shaking, false, "옛 오답이 지금 정답 화면을 흔들었다");
  });

  it("지금 문제가 가운데 끼어 와도 옛 응답이 앞뒤를 덮지 않는다", async () => {
    await threeHeld();
    held[1].pass(true);
    await settle();
    held[2].pass(false);
    await settle();
    held[0].pass(true);
    await settle();

    const now = screen();
    assert.equal(now.score, "3/2");
    assert.equal(now.burst, 0, "옛 정답으로 축포가 터졌다");
    assert.equal(now.reaction, 1);
    assert.equal(now.shaking, true);
  });

  it("같은 틱에 한꺼번에 풀려도 하나도 빠지지 않는다", async () => {
    await threeHeld();
    held[0].pass(true);
    held[1].pass(true);
    held[2].pass(true);
    await settle();
    assert.equal(screen().score, "3/3");
    assert.equal(screen().burst, 1);
  });

  it("문제를 받아 오는 중에 온 채점도 세고 화면은 가져오는 중 그대로다", async () => {
    await start();
    await choose();
    let open = () => {};
    questionGate = new Promise((r) => (open = r));
    clickButton("다음 문제");
    await settle();
    held[0].pass(true);
    await settle();

    let now = screen();
    assert.match(now.page, /문제를 가져오는 중/);
    assert.equal(now.score, "1/1");
    assert.equal(now.burst, 0);

    open();
    await settle();
    now = screen();
    assert.equal(now.explained, false);
    assert.equal(now.alert, false);
    assert.equal(findAll(render(), named("ChoiceButton")).length, 4);
  });

  it("유형을 바꿔 새 문제를 받은 뒤 와도 해설을 얹지 않는다", async () => {
    await start();
    await choose();
    await next();
    (findAll(render(), named("KindPicker"))[0].props.onChange as (v: string) => void)("term");
    await settle();
    held[0].pass(true);
    await settle();

    const now = screen();
    assert.equal(now.score, "1/1");
    assert.equal(now.explained, false);
    assert.equal(now.burst, 0);
  });
});

describe("늦은 채점 - 연속 정답", () => {
  /** 두 문제를 제때 맞혀 연속 2 를 만든다. */
  async function twoInARow() {
    await start();
    await choose();
    held[0].pass(true);
    await settle();
    await next();
    await choose();
    held[1].pass(true);
    await settle();
    assert.equal(screen().combo, 2);
  }

  it("늦은 오답은 지금 연속을 끊지 않는다", async () => {
    await twoInARow();
    await next();
    await choose();
    await next();
    held[2].pass(false);
    await settle();
    const now = screen();
    assert.equal(now.combo, 2, "옛 오답이 연속을 끊었다");
    assert.equal(now.score, "3/2");
  });

  it("늦은 정답은 연속을 올리지 않는다", async () => {
    await twoInARow();
    await next();
    await choose();
    await next();
    held[2].pass(true);
    await settle();
    const now = screen();
    assert.equal(now.combo, 2, "옛 정답이 연속을 올렸다");
    assert.equal(now.score, "3/3");
  });
});

describe("늦은 채점 - 실패와 성공의 조합", () => {
  it("옛 실패 뒤 지금 성공: 안내 없이 정상 반영", async () => {
    await start();
    await choose();
    await next();
    await choose();
    held[0].drop();
    await settle();
    held[1].pass(true);
    await settle();
    const now = screen();
    assert.equal(now.alert, false);
    assert.equal(now.explained, true);
    assert.equal(now.score, "1/1");
  });

  it("지금 성공 뒤 옛 실패: 해설이 그대로고 안내가 안 붙는다", async () => {
    await start();
    await choose();
    await next();
    await choose();
    held[1].pass(true);
    await settle();
    held[0].fail(500);
    await settle();
    const now = screen();
    assert.equal(now.alert, false, "옛 실패가 지금 문제에 안내를 붙였다");
    assert.equal(now.explained, true);
    assert.equal(now.score, "1/1");
  });

  it("옛 성공 뒤 지금 실패: 안내는 뜨고 옛 성공은 세어져 있다", async () => {
    await start();
    await choose();
    await next();
    await choose();
    held[0].pass(true);
    await settle();
    held[1].drop();
    await settle();
    const now = screen();
    assert.equal(now.alert, true);
    assert.equal(now.explained, false);
    assert.equal(now.score, "1/1");
  });

  it("옛 응답의 본문이 깨져 있어도 조용히 버리고 세지 않는다", async () => {
    await start();
    await choose();
    await next();
    held[0].garbled();
    await settle();
    const now = screen();
    assert.equal(now.alert, false);
    assert.equal(now.score, null);
  });

  it("옛 응답이 전부 실패면 점수도 경고도 없다", async () => {
    await threeHeld();
    held[0].fail(500);
    held[1].drop();
    await settle();
    commit();
    assert.equal(screen().score, null);
    assert.equal(fireUnload().prompted, false);
  });
});

describe("늦은 채점 - 제외 목록", () => {
  it("늦은 오답은 넣지 않는다", async () => {
    await start();
    await choose();
    await next();
    held[0].pass(false);
    await settle();
    await choose();
    await next();
    assert.deepEqual(excludeOf(asked.at(-1)), []);
  });

  it("뒤섞여 와도 맞힌 것만 전부 넣는다", async () => {
    await threeHeld();
    held[2].pass(true, 33);
    held[0].pass(true, 11);
    held[1].pass(false, 22);
    await settle();
    await next();
    assert.deepEqual([...excludeOf(asked.at(-1))].sort(), ["11", "33"]);
  });

  it("빈칸 문제는 응답이 늦어도 그 문제의 문장 id 를 넣는다", async () => {
    // 늦게 왔을 때 지금 문제의 문장을 쓰면 엉뚱한 문장이 빠지고 푼 문장은 또 나온다.
    props = { content: "sentences" };
    questionOverrides = [
      { kind: "blank", answer_type: "word", source_sentence_id: 77 },
      { kind: "blank", answer_type: "word", source_sentence_id: 88 },
    ];
    await start();
    await choose();
    await next();
    held[0].pass(true, 5);
    await settle();
    await choose();
    await next();
    assert.deepEqual(excludeOf(asked.at(-1)), ["77"]);
  });

  it("같은 문제가 또 나와 둘 다 맞혀도 제외 목록에는 한 번만 든다", async () => {
    // 첫 채점이 늦으면 서버가 아직 모르니 같은 단어가 곧바로 다시 나올 수 있다.
    // 상한(RECENT_LIMIT)이 백엔드와 같은 100 이라 중복은 그만큼 다른 단어를 밀어낸다.
    await start();
    await choose();
    await next();
    await choose();
    held[0].pass(true, 12);
    held[1].pass(true, 12);
    await settle();
    await next();
    assert.deepEqual(excludeOf(asked.at(-1)), ["12"]);
  });
});

describe("늦은 채점 - 처음부터 다시로 비운 판", () => {
  /** 첫 문제 채점이 붙잡힌 채 다음 문제를 못 받아 "처음부터 다시" 를 누른다. */
  async function restartWhileHeld() {
    statuses = [200, 404];
    await start();
    await choose();
    await next();
    clickButton("처음부터 다시");
    await settle();
  }

  it("지난 판의 늦은 채점은 새 판 점수와 제외 목록에 안 들어간다", async () => {
    await restartWhileHeld();
    held[0].pass(true);
    await settle();
    assert.equal(screen().score, null, "비운 판에 지난 판 점수가 들어왔다");
    await choose();
    await next();
    assert.deepEqual(excludeOf(asked.at(-1)), [], "비운 제외 목록에 지난 판 단어가 들어왔다");
  });

  it("지난 판의 늦은 채점이 새 판에 새로고침 경고를 걸지 않는다", async () => {
    await restartWhileHeld();
    commit();
    assert.equal(fireUnload().prompted, false);
    held[0].pass(false);
    await settle();
    commit();
    assert.equal(fireUnload().prompted, false, "한 문제도 안 푼 새 판에 경고가 걸렸다");
  });
});

/* ---- 새로고침 경고 ---- */

describe("새로고침 경고 - 함수", () => {
  it("푼 것이 없으면 안 묻고, 있으면 묻는다", () => {
    markSolved(0);
    assert.equal(fireUnload().prompted, false);
    markSolved(1);
    const fired = fireUnload();
    assert.equal(fired.prompted, true);
    assert.equal(fired.returnValue, "");
  });

  it("여러 번 적어도 0 한 번에 풀린다", () => {
    for (const n of [1, 2, 3, 4]) markSolved(n);
    markSolved(0);
    assert.equal(fireUnload().prompted, false);
  });

  it("clearSolved 도 푼다", () => {
    markSolved(5);
    clearSolved();
    assert.equal(fireUnload().prompted, false);
    assert.equal(solvedNow(), 0);
  });

  it("음수·NaN 은 걸지 않고, 걸려 있었으면 푼다", () => {
    for (const bad of [-1, Number.NaN]) {
      markSolved(3);
      markSolved(bad);
      assert.equal(fireUnload().prompted, false, String(bad));
    }
  });

  it("window 가 없는 서버에서 불러도 터지지 않는다", () => {
    delete g.addEventListener;
    delete g.removeEventListener;
    assert.doesNotThrow(() => {
      markSolved(2);
      clearSolved();
    });
  });
});

describe("새로고침 경고 - 판", () => {
  it("늦은 채점으로 푼 수가 생겨도 걸린다", async () => {
    await start();
    commit();
    await choose();
    await next();
    commit();
    assert.equal(fireUnload().prompted, false, "채점 전에 걸렸다");
    held[0].pass(false);
    await settle();
    commit();
    assert.equal(fireUnload().prompted, true);
  });

  it("처음부터 다시로 0 이 되면 풀린다", async () => {
    statuses = [200, 200, 404];
    await start();
    await choose();
    held[0].pass(true);
    await settle();
    commit();
    assert.equal(fireUnload().prompted, true);

    await next();
    await choose();
    held[1].pass(true);
    await settle();
    await next();
    assert.match(screen().page, /다 풀었습니다/);
    clickButton("처음부터 다시");
    await settle();
    commit();
    assert.equal(fireUnload().prompted, false);
  });

  it("판이 사라지면 풀린다", async () => {
    await start();
    await choose();
    held[0].pass(true);
    await settle();
    commit();
    assert.equal(fireUnload().prompted, true);
    unmount();
    assert.equal(fireUnload().prompted, false);
  });
});

/* ---- 없는 분류 ---- */

type Page = (p: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) => Promise<unknown>;

const PAGES: [string, Page, string][] = [
  ["단어", wordsPage as Page, "/test/words"],
  ["문장", sentencesPage as Page, "/test/sentences"],
];

const GIT = { value: "git", label: "Git" };
const NET = { value: "network", label: "네트워크" };

describe("없는 분류는 전체로 낸다", () => {
  for (const [name, page, path] of PAGES) {
    async function board(query: { [key: string]: string | string[] | undefined }) {
      const tree = await page({ searchParams: Promise.resolve(query) });
      const found = findAll(tree, (el) => el.type === QuizBoard);
      assert.equal(found.length, 1, "판이 하나가 아니다");
      const picker = found[0].props.picker as El;
      assert.equal(picker.type, CategoryPicker);
      assert.equal(
        findAll(tree, (el) => el.type === CategoryPicker).length,
        0,
        "판 밖에도 분류 고르개가 남았다",
      );
      assert.equal(found[0].key, picker.key, "판과 고르개의 key 가 어긋난다");
      assert.equal(found[0].props.category, picker.props.selected, "판과 고르개가 다른 분류를 본다");
      assert.equal(picker.props.basePath, path);
      return found[0];
    }

    describe(name, () => {
      it("있는 분류는 그대로", async () => {
        categoryList = [GIT, NET];
        const el = await board({ category: "network" });
        assert.equal(el.props.category, "network");
        assert.equal(el.key, "network");
      });

      it("분류를 안 주면 전체", async () => {
        categoryList = [GIT];
        const el = await board({});
        assert.equal(el.props.category, undefined);
        assert.equal(el.key, "all");
      });

      for (const bad of ["없는분류", "GIT", " git", "", "constructor", "__proto__", "all"]) {
        it(`목록에 없는 값 ${JSON.stringify(bad)} 은 전체`, async () => {
          categoryList = [GIT];
          const el = await board({ category: bad });
          assert.equal(el.props.category, undefined);
          assert.equal(el.key, "all");
        });
      }

      it("목록을 못 받으면 판단하지 않고 그대로 보낸다", async () => {
        categoryList = [];
        const el = await board({ category: "없는분류" });
        assert.equal(el.props.category, "없는분류");
      });

      it("목록을 못 받았고 분류도 없으면 전체", async () => {
        categoryList = [];
        const el = await board({});
        assert.equal(el.props.category, undefined);
        assert.equal(el.key, "all");
      });

      it("배열이면 첫 값으로 판단한다", async () => {
        categoryList = [GIT];
        assert.equal((await board({ category: ["git", "없는분류"] })).props.category, "git");
        assert.equal((await board({ category: ["없는분류", "git"] })).props.category, undefined);
      });

      it("빈 배열은 전체", async () => {
        categoryList = [GIT];
        assert.equal((await board({ category: [] })).props.category, undefined);
      });

      it("없는 분류여도 항목은 남긴다", async () => {
        categoryList = [GIT];
        const el = await board({ category: "없는분류", item: "7" });
        assert.equal(el.props.item, "7");
      });
    });
  }

  it("문장 페이지만 판에 sentences 를 넘긴다", async () => {
    categoryList = [GIT];
    const [words, sentences] = await Promise.all(
      PAGES.map(([, page]) => page({ searchParams: Promise.resolve({}) })),
    );
    assert.equal(findAll(words, (el) => el.type === QuizBoard)[0].props.content, undefined);
    assert.equal(findAll(sentences, (el) => el.type === QuizBoard)[0].props.content, "sentences");
  });

  it("빈 분류가 판까지 와도 요청에 category 를 싣지 않는다", async () => {
    // 목록을 못 받은 ?category= 는 빈 문자열로 판에 그대로 온다.
    props = { content: "words", category: "" };
    await start();
    assert.doesNotMatch(asked[0], /category=/);
  });
});

/* ---- picker ---- */

describe("picker", () => {
  const PICKER = realReact.createElement("span", { "data-test": "cat-picker" }, "분류칸");

  /** 유형 고르개가 든 줄의 자식들. 빈 자리(false·undefined)는 뺀다. */
  function row(): El[] {
    const rows = findAll(
      render(),
      (el) =>
        Array.isArray(el.props.children) &&
        (el.props.children as unknown[]).some((c) => Boolean(c) && named("KindPicker")(c as El)),
    );
    assert.equal(rows.length, 1, "유형 고르개 줄이 하나가 아니다");
    return (rows[0].props.children as unknown[]).filter(Boolean) as El[];
  }

  function assertPickerFirst() {
    const kids = row();
    assert.equal(kids[0], PICKER, "분류 고르개가 줄의 맨 앞이 아니다");
    assert.ok(named("KindPicker")(kids[1]), "유형 고르개가 바로 뒤에 없다");
  }

  it("가져오는 중에도 유형 고르개 앞에 있다", () => {
    props = { content: "words", picker: PICKER };
    assertPickerFirst();
    assert.match(screen().page, /문제를 가져오는 중/);
    assert.match(screen().page, /분류칸/);
  });

  it("문제 화면에서도 있다", async () => {
    props = { content: "words", picker: PICKER };
    await start();
    assertPickerFirst();
    assert.equal(findAll(render(), named("ChoiceButton")).length, 4);
  });

  it("문제를 못 받은 안내 화면에서도 있다 - 분류를 넓히라고 안내하는 자리다", async () => {
    props = { content: "words", picker: PICKER };
    statuses = [404];
    await start();
    assert.match(screen().page, /다 풀었습니다/);
    assertPickerFirst();
    assert.match(screen().page, /분류칸/);
  });

  it("점수가 붙어도 앞자리를 지키고 점수는 맨 뒤다", async () => {
    props = { content: "words", picker: PICKER };
    await start();
    await choose();
    held[0].pass(true);
    await settle();
    assertPickerFirst();
    const kids = row();
    assert.equal(kids.length, 3);
    assert.match(String(kids[2].props.className), /ml-auto/);
  });

  it("안 넘기면 유형 고르개만 있고 판은 그대로 돈다", async () => {
    props = { content: "words" };
    await start();
    assert.ok(named("KindPicker")(row()[0]));
    await choose();
    held[0].pass(true);
    await settle();
    const now = screen();
    assert.equal(now.score, "1/1");
    assert.doesNotMatch(now.page, /undefined|null/);
  });

  it("null 을 넘겨도 안 넘긴 것과 같다", async () => {
    props = { content: "words", picker: null };
    await start();
    assert.ok(named("KindPicker")(row()[0]));
  });
});
