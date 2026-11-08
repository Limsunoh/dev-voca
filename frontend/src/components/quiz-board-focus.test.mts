/**
 * 문제풀기(QuizBoard)가 새 문제에서 안내문과 지문으로 초점을 옮기는지 눌러서 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 결함은 이렇다.
 *
 *   조건 뒤에 훅        가지가 바뀌는 렌더에서 훅 개수가 달라져 React 가 죽는다
 *   기존 effect 앞에 훅 채점 실패 때 두 effect 의 순서가 바뀌어 초점이 튄다
 *   지문이 감싸개 밖    화면 낭독기가 안내문만 읽고 지문을 건너뛴다
 *   보기가 다음 형제 아님 초점이 보기 안에 있어도 "보기 밖" 으로 쳐서 안 옮긴다
 *   로딩·오류 가지      옮길 카드가 없는 렌더에서 터진다
 *
 * 훅은 대역으로 바꾸지 않고 진짜를 돌린다. 훅의 순서와 기존 effect 와의 만남이
 * 보려는 것이기 때문이다. react 의 훅 대역은 quiz-board-item.test.mts 와 같은
 * 방식인데, 커밋을 흉내 내야 해서 두 가지를 더 했다. useEffect 와 useCallback 이
 * 의존성을 보고, 그린 ref 에 가짜 요소를 붙이며 사라진 요소의 초점은 body 로
 * 떨어뜨린다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

const realReact = await import("react");

type Run = () => void | (() => void);
type EffectSlot = { deps?: unknown[] };

let slots: unknown[] = [];
let cursor = 0;
let pending: Run[] = [];
/** 이번 렌더에서 불린 훅의 순서. */
let order: string[] = [];
/** 지금까지 등록된 의존성. 뒤에 불린 것이 뒤에 온다. */
let renderedDeps: unknown[][] = [];

function slot<T>(init: () => T): T {
  if (cursor >= slots.length) slots.push(init());
  return slots[cursor++] as T;
}

const sameDeps = (a: unknown[] | undefined, b: unknown[] | undefined) =>
  Boolean(a && b) && a!.length === b!.length && a!.every((dep, i) => Object.is(dep, b![i]));

mock.module("react", {
  defaultExport: realReact.default,
  namedExports: {
    ...realReact,
    useState<T>(init: T | (() => T)) {
      order.push("useState");
      const s = slot(() => ({
        value: typeof init === "function" ? (init as () => T)() : init,
      }));
      const set = (next: T | ((prev: T) => T)) => {
        s.value = typeof next === "function" ? (next as (prev: T) => T)(s.value) : next;
      };
      return [s.value, set];
    },
    useRef<T>(init: T) {
      order.push("useRef");
      return slot(() => ({ current: init }));
    },
    useCallback<T>(fn: T, deps: unknown[]) {
      order.push("useCallback");
      const s = slot(() => ({ fn, deps }));
      if (!sameDeps(s.deps, deps)) {
        s.fn = fn;
        s.deps = deps;
      }
      return s.fn;
    },
    useEffect(run: Run, deps?: unknown[]) {
      order.push("useEffect");
      const s = slot<EffectSlot>(() => ({}));
      if (deps) renderedDeps.push(deps);
      if (!sameDeps(s.deps, deps)) pending.push(run);
      s.deps = deps;
    },
  },
});

const { QuizBoard } = await import("./QuizBoard");

/* ---- 가짜 DOM ---- */

type FakeEl = {
  role: string;
  matches(selector: string): boolean;
  focus?(options: unknown): void;
  nextElementSibling?: unknown;
  getBoundingClientRect?(): { bottom: number };
};

function fake(role: string, disabled = false): FakeEl {
  return { role, matches: (selector) => selector === ":disabled" && disabled };
}

const body = fake("body");
const choice = fake("보기");
const lockedChoice = fake("잠긴 보기", true);
const select = fake("유형 고르개");
const list = { contains: (node: unknown) => node === choice || node === lockedChoice };

type Doc = { body: FakeEl; activeElement: unknown; querySelector(selector: string): null };
let doc: Doc;
let focusLog: { to: string; options: unknown }[] = [];

/** 그려진 ref 와 거기 붙은 가짜 요소. */
let mounted = new Map<{ current: unknown }, FakeEl>();

function elementFor(el: El): FakeEl {
  const role = el.props.tabIndex === -1 ? "문제" : "다음 문제";
  const made = fake(role);
  made.nextElementSibling = list;
  made.getBoundingClientRect = () => ({ bottom: 100 });
  made.focus = (options) => {
    focusLog.push({ to: role, options });
    doc.activeElement = made;
  };
  return made;
}

/** React 의 커밋. 사라진 ref 는 비우고, 그 요소에 있던 초점은 body 로 떨어진다. */
function commit(tree: unknown) {
  const refs = findAll(tree, (el) => typeof el.props.ref === "object" && el.props.ref !== null);
  const seen = new Set(refs.map((el) => el.props.ref));
  for (const [ref, element] of mounted) {
    if (seen.has(ref)) continue;
    ref.current = null;
    mounted.delete(ref);
    if (doc.activeElement === element) doc.activeElement = body;
  }
  for (const el of refs) {
    const ref = el.props.ref as { current: unknown };
    if (!mounted.has(ref)) mounted.set(ref, elementFor(el));
    ref.current = mounted.get(ref);
  }
}

/* ---- 대역 ---- */

type G = { window?: unknown; document?: unknown };
const realFetch = globalThis.fetch;
const realWindow = (globalThis as G).window;
const realDocument = (globalThis as G).document;
const realNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");

after(() => {
  globalThis.fetch = realFetch;
  (globalThis as G).window = realWindow;
  (globalThis as G).document = realDocument;
  if (realNavigator) Object.defineProperty(globalThis, "navigator", realNavigator);
});

function setHasBeenActive(hasBeenActive: boolean) {
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { userActivation: { hasBeenActive } },
  });
}

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
  ],
};

/** 문제 요청에 차례로 돌려줄 상태 코드. 비면 200. */
let questionStatuses: number[] = [];
/** 채점 요청의 상태 코드. */
let gradeStatus = 200;
let served = 0;

beforeEach(() => {
  slots = [];
  pending = [];
  order = [];
  renderedDeps = [];
  mounted = new Map();
  focusLog = [];
  questionStatuses = [];
  gradeStatus = 200;
  served = 0;
  setHasBeenActive(true);
  doc = { body, activeElement: body, querySelector: () => null };
  (globalThis as G).document = doc;
  (globalThis as G).window = { scrollTo() {}, scrollY: 0, innerHeight: 800 };
  globalThis.fetch = (async (_input: string | URL, init?: RequestInit) => {
    const reply = (status: number, data: unknown) =>
      ({ ok: status < 400, status, json: async () => data }) as Response;
    if (init?.method === "POST") {
      return reply(gradeStatus, { correct: true, answer_id: 12, explanation: "" });
    }
    const status = questionStatuses.shift() ?? 200;
    served += 1;
    // 문제마다 새 객체다. 훅은 객체가 바뀐 것으로 새 문제를 안다.
    return reply(status, status < 400 ? { ...QUESTION, token: `t${served}` } : { detail: "x" });
  }) as typeof fetch;
});

/* ---- 도구 ---- */

type El = { type: unknown; props: Record<string, unknown> };

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

function draw(): El {
  cursor = 0;
  pending = [];
  order = [];
  renderedDeps = [];
  const tree = QuizBoard({ content: "words" }) as unknown as El;
  commit(tree);
  for (const run of pending) run();
  return tree;
}

async function settle() {
  for (let i = 0; i < 5; i++) await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
}

/** 첫 문제까지 띄운다. */
async function boot(): Promise<El> {
  draw();
  await settle();
  return draw();
}

const promptBoxes = (tree: unknown) => findAll(tree, (el) => el.props.tabIndex === -1);

function promptBox(tree: unknown): El {
  const boxes = promptBoxes(tree);
  assert.equal(boxes.length, 1, "초점을 받을 감싸개는 하나여야 한다");
  return boxes[0];
}

/** 훅의 의존성. [picked, result, error] 와 길이로 갈린다. */
const hookDeps = () => renderedDeps.filter((deps) => deps.length === 2);

function pressChoice(tree: unknown) {
  const [first] = findAll(tree, named("ChoiceButton"));
  assert.ok(first, "보기가 없다");
  (first.props.onClick as () => void)();
}

const nextButton = (tree: unknown) => {
  const found = findAll(tree, (el) => el.type === "button" && el.props.children === "다음 문제");
  assert.equal(found.length, 1, "다음 문제 버튼이 없다");
  return found[0];
};

/* ---- 테스트 ---- */

describe("QuizBoard 가 훅에 넘기는 것", () => {
  it("지금 문제와 error 를 그대로 넘긴다", async () => {
    await boot();
    const shown = (slots[0] as { value: unknown }).value;
    assert.ok(shown, "문제를 못 받았다");
    assert.equal(hookDeps().length, 1, "2개짜리 의존성은 훅 하나뿐이어야 한다");
    assert.equal(hookDeps()[0][0], shown);
    assert.equal(hookDeps()[0][1], null);
  });

  it("문제를 못 받으면 null 문제와 안내 문구를 넘긴다", async () => {
    questionStatuses = [503];
    await boot();
    assert.equal(hookDeps()[0][0], null);
    assert.match(String(hookDeps()[0][1]), /불러오지 못했습니다/);
  });

  it("채점이 실패하면 그 문구가 error 로 들어간다", async () => {
    gradeStatus = 503;
    pressChoice(await boot());
    await settle();
    draw();
    assert.match(String(hookDeps()[0][1]), /채점하지 못했습니다/);
  });
});

describe("QuizBoard 의 훅 순서", () => {
  it("로딩·문제·오류 가지에서 훅 순서가 같다", async () => {
    questionStatuses = [200, 503];
    draw();
    const loading = [...order];
    await settle();
    const tree = draw();
    const playing = [...order];
    (nextButtonAfterPick(tree).props.onClick as () => void)();
    await settle();
    draw();
    assert.ok(loading.length > 0);
    assert.deepEqual(playing, loading, "문제 가지에서 훅이 달라졌다");
    assert.deepEqual([...order], loading, "오류 가지에서 훅이 달라졌다");
  });

  function nextButtonAfterPick(tree: unknown): El {
    pressChoice(tree);
    return nextButton(draw());
  }

  it("초점 훅은 맨 뒤에서 불린다", async () => {
    await boot();
    assert.deepEqual(order.slice(-2), ["useRef", "useEffect"]);
  });

  it("초점 훅의 effect 는 채점 뒤 버튼으로 옮기는 effect 보다 뒤다", async () => {
    await boot();
    const scrollAt = renderedDeps.findIndex((deps) => deps.length === 3);
    const hookAt = renderedDeps.findIndex((deps) => deps.length === 2);
    assert.notEqual(scrollAt, -1, "채점 뒤 effect 를 못 찾았다");
    assert.ok(scrollAt < hookAt, "훅이 기존 effect 앞에서 돈다");
  });
});

describe("QuizBoard 의 감싸개 모양", () => {
  it("안내문과 지문이 둘 다 감싸개 안에 있다", async () => {
    const box = promptBox(await boot());
    const [heading] = findAll(box.props.children, (el) => el.type === "h2");
    assert.ok(heading, "안내문이 감싸개 밖이다");
    assert.equal(heading.props.children, QUESTION.question);
    const [prompt] = findAll(box.props.children, named("Prompt"));
    assert.ok(prompt, "지문이 감싸개 밖이다");
    assert.equal(prompt.props.text, QUESTION.prompt);
  });

  it("감싸개 바로 다음 형제가 보기 ul 이다", async () => {
    const tree = await boot();
    const box = promptBox(tree);
    const [parent] = findAll(tree, (el) => {
      const children = el.props.children;
      return Array.isArray(children) && children.includes(box);
    });
    assert.ok(parent, "감싸개의 부모를 못 찾았다");
    const siblings = (parent.props.children as unknown[]).filter(Boolean);
    const next = siblings[siblings.indexOf(box) + 1] as El;
    assert.equal(next.type, "ul");
    assert.equal(findAll(next.props.children, named("ChoiceButton")).length, 2);
  });

  it("div 이고 tabIndex 가 -1 이며 focus-visible 링만 쓴다", async () => {
    const box = promptBox(await boot());
    assert.equal(box.type, "div");
    const classes = String(box.props.className).split(/\s+/);
    for (const name of [
      "focus-visible:outline",
      "focus-visible:outline-2",
      "focus-visible:outline-offset-2",
      "focus-visible:outline-focus",
    ]) {
      assert.ok(classes.includes(name), `${name} 가 없다`);
    }
    assert.equal(
      classes.some((name) => name.startsWith("focus:")),
      false,
    );
  });
});

describe("QuizBoard 의 초점 이동", () => {
  it("새 문제가 뜨면 감싸개로 옮기고 스크롤은 건드리지 않는다", async () => {
    await boot();
    assert.deepEqual(focusLog, [{ to: "문제", options: { preventScroll: true } }]);
  });

  it("같은 문제로 다시 그려지면 또 옮기지 않는다", async () => {
    await boot();
    draw();
    draw();
    assert.equal(focusLog.length, 1);
  });

  it("주소로 바로 열어 아직 안 눌렀으면 옮기지 않는다", async () => {
    setHasBeenActive(false);
    await boot();
    assert.equal(focusLog.length, 0);
  });

  it("다음 문제를 누르면 버튼이 사라진 뒤 새 문제의 감싸개로 옮긴다", async () => {
    const tree = await boot();
    pressChoice(tree);
    await settle();
    const graded = draw();
    assert.deepEqual(focusLog.at(-1)?.to, "다음 문제");

    focusLog = [];
    (nextButton(graded).props.onClick as () => void)();
    draw();
    assert.equal(doc.activeElement, body, "버튼이 사라졌는데 초점이 남았다");
    assert.equal(focusLog.length, 0, "로딩 중에는 옮길 곳이 없다");
    await settle();
    draw();
    assert.deepEqual(focusLog, [{ to: "문제", options: { preventScroll: true } }]);
  });

  it("채점이 끝나면 다음 문제 버튼에 초점이 남는다", async () => {
    const tree = await boot();
    focusLog = [];
    doc.activeElement = lockedChoice;
    pressChoice(tree);
    await settle();
    draw();
    assert.deepEqual(
      focusLog.map((entry) => entry.to),
      ["다음 문제"],
    );
  });

  it("채점이 실패해도 초점은 다음 문제 버튼에 남고 지문으로 끌려가지 않는다", async () => {
    gradeStatus = 503;
    const tree = await boot();
    focusLog = [];
    doc.activeElement = lockedChoice;
    pressChoice(tree);
    await settle();
    draw();
    assert.deepEqual(
      focusLog.map((entry) => entry.to),
      ["다음 문제"],
    );
    assert.equal((doc.activeElement as FakeEl).role, "다음 문제");
  });

  it("유형 고르개에 서 있으면 새 문제가 떠도 초점을 뺏지 않는다", async () => {
    const tree = await boot();
    focusLog = [];
    doc.activeElement = select;
    const [picker] = findAll(tree, named("KindPicker"));
    assert.ok(picker, "유형 고르개가 없다");
    (picker.props.onChange as (next: string) => void)("term");
    draw();
    await settle();
    draw();
    assert.equal(focusLog.length, 0);
    assert.equal(doc.activeElement, select);
  });
});

describe("QuizBoard 의 로딩·오류 가지", () => {
  it("로딩 가지에는 감싸개가 없고 훅이 돌아도 안 터진다", () => {
    const tree = draw();
    assert.equal(promptBoxes(tree).length, 0);
    assert.equal(hookDeps().length, 1);
    assert.equal(focusLog.length, 0);
  });

  it("오류 가지에는 감싸개가 없고 안 터진다", async () => {
    questionStatuses = [503];
    const tree = await boot();
    assert.equal(promptBoxes(tree).length, 0);
    assert.ok(findAll(tree, (el) => el.type === "button").length >= 1, "다시 시도 버튼이 없다");
    assert.equal(focusLog.length, 0);
  });

  it("초점이 보기 밖에 있어도 오류 가지에서 안 터진다", async () => {
    questionStatuses = [503];
    doc.activeElement = select;
    await assert.doesNotReject(boot());
    assert.equal(focusLog.length, 0);
  });

  it("오류에서 다시 받으면 새 문제의 감싸개로 옮긴다", async () => {
    questionStatuses = [503];
    const tree = await boot();
    const [again] = findAll(tree, (el) => el.type === "button");
    (again.props.onClick as () => void)();
    draw();
    await settle();
    const retried = draw();
    assert.equal(promptBoxes(retried).length, 1);
    assert.deepEqual(focusLog, [{ to: "문제", options: { preventScroll: true } }]);
  });
});
