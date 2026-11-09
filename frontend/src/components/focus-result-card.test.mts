/**
 * 판이 끝난 뒤 뜨는 결과 카드 셋이 초점 훅을 제대로 잇는지, 훅이 카드 안의 초점을
 * 건드리지 않는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 결함은 이렇다.
 *
 *   ref 를 안 붙임          훅이 돌아도 옮길 카드가 없어 초점이 body 에 남는다
 *   tabIndex 가 없음        div 는 focus() 를 받지 못해 조용히 아무 일도 안 일어난다
 *   error 를 안 넘김        다시 열기가 실패해도 훅이 다시 돌지 않는다
 *   화면을 덮는 링          일일공부·복습 카드는 화면 전체 크기라 링이 네모로 뜬다
 *   카드 안 초점을 뺏음     "한 판 더" 가 잠겼다 풀릴 때 다시 Tab 을 눌러야 한다
 *
 * 카드들은 내보내지 않으므로 보드가 돌려준 트리에서 꺼낸다. 대역 방식은
 * focus-new-question-boards.test.mts 와 같다. 훅의 진짜 구현은 훅을 대역으로
 * 바꾸기 전에 받아 둔다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

import type { DailyStatus, StudyProgress } from "@/lib/api/daily";
import type { RoundSummary } from "@/lib/api/rounds";

const realReact = await import("react");

type Slot = { value: unknown };
type Effect = () => void;

let slots: Slot[] = [];
let cursor = 0;

/** 한 판·복습의 phase 를 처음부터 done 으로 둔다. 끝까지 풀어 가려면 시계와 채점을 다 대역해야 한다. */
let startDone = false;

/** 훅 구현을 볼 때만 켠다. 보드의 effect 는 돌리지 않는다. */
let queueEffects = false;
let queued: Effect[] = [];

function slot<T>(init: () => T): Slot {
  if (cursor >= slots.length) slots.push({ value: init() });
  return slots[cursor++];
}

mock.module("react", {
  defaultExport: realReact.default,
  namedExports: {
    ...realReact,
    useState<T>(init: T | (() => T)) {
      const s = slot(() => {
        if (startDone && init === "idle") return "done";
        return typeof init === "function" ? (init as () => T)() : init;
      });
      return [s.value, () => {}];
    },
    useRef<T>(init: T) {
      return slot(() => ({ current: init })).value;
    },
    useCallback<T>(fn: T) {
      return fn;
    },
    useEffect(run: Effect, deps: unknown[]) {
      if (!queueEffects) return;
      const s = slot(() => null);
      const before = s.value as unknown[] | null;
      if (!before || deps.some((dep, i) => !Object.is(dep, before[i]))) queued.push(run);
      s.value = deps;
    },
  },
});

// use 로 시작하지 않는 이름으로 받는다. 대역 위에서 일반 함수처럼 부른다.
const { useFocusNewQuestion: callRealHook } = await import("./useFocusNewQuestion");

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

const SUMMARY: RoundSummary = {
  score: 120,
  answered: 8,
  correct: 6,
  skipped: 1,
  recorded: true,
  guest: false,
};

const STUDY: StudyProgress = {
  length: "5m",
  total: 10,
  answered: 10,
  correct: 7,
  score: 70,
  bonus: 5,
  done: true,
  chunk_size: 3,
  chunk_count: 2,
  chunk_index: 1,
};

const DAILY_DONE: DailyStatus = {
  lengths: [],
  today: STUDY,
  token: "",
  question: null,
  learning: [],
};

const DUE = { due: 5, round_size: 20, graduate_streak: 2 };

/* ---- 대역 ---- */

type G = { document?: unknown };
const realDocument = (globalThis as G).document;
const realNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");

function setActivation(hasBeenActive: boolean) {
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { userActivation: { hasBeenActive, isActive: false } },
  });
}

function setDocument(extra: Record<string, unknown> = {}) {
  (globalThis as G).document = {
    documentElement: { style: { setProperty() {}, removeProperty() {} } },
    ...extra,
  };
}

after(() => {
  (globalThis as G).document = realDocument;
  if (realNavigator) Object.defineProperty(globalThis, "navigator", realNavigator);
});

beforeEach(() => {
  slots = [];
  cursor = 0;
  hookArgs = [];
  queued = [];
  queueEffects = false;
  startDone = false;
  setDocument();
  setActivation(true);
});

function openCard(board: () => unknown, name: string): El {
  startDone = true;
  cursor = 0;
  const found = flatten(board()).find(named(name));
  assert.ok(found, `${name} 가 안 그려졌다`);
  return found;
}

const openRound = () => openCard(() => RoundBoard({ isGuest: false }), "RoundResultCard");
const openDaily = () => openCard(() => DailyStudyBoard({ status: DAILY_DONE }), "DoneCard");
const openReview = () => openCard(() => ReviewBoard({ due: DUE }), "DoneCard");

/** 카드를 한 번 그린다. 훅이 받은 인자는 hookArgs 에 남는다. */
function draw(card: El, override: Record<string, unknown> = {}): El {
  hookArgs = [];
  const root = (card.type as (props: unknown) => unknown)({ ...card.props, ...override });
  assert.ok(isElement(root), "카드 뿌리가 요소가 아니다");
  return root;
}

const classesOf = (el: El) => String(el.props.className).split(/\s+/);

const RING = [
  "focus-visible:outline",
  "focus-visible:outline-2",
  "focus-visible:outline-offset-2",
  "focus-visible:outline-focus",
];

const SCREENS = [
  ["한 판", openRound, { summary: SUMMARY, error: "", busy: false }],
  ["일일공부", openDaily, { study: STUDY }],
  ["복습", openReview, { answered: 8, error: "", busy: false }],
] as const;

/* ---- 카드 ---- */

for (const [name, open, props] of SCREENS) {
  describe(`${name} 결과 카드의 초점 자리`, () => {
    it("렌더 한 번에 훅을 한 번, 인자 둘로 부른다", () => {
      draw(open(), props);
      assert.equal(hookArgs.length, 1);
      assert.equal(hookArgs[0].length, 2);
    });

    it("뿌리 div 에 훅이 돌려준 ref 를 붙인다", () => {
      const root = draw(open(), props);
      assert.equal(root.type, "div");
      assert.equal(root.props.ref, SENTINEL_REF);
    });

    it("뿌리 div 만 tabIndex -1 이다", () => {
      // tabIndex 가 없으면 div 의 focus() 는 조용히 무시된다.
      const root = draw(open(), props);
      assert.equal(root.props.tabIndex, -1);
      const others = flatten(root).filter((el) => el !== root);
      assert.equal(others.some((el) => el.props.tabIndex !== undefined), false);
      assert.equal(others.some((el) => el.props.ref !== undefined), false);
    });

    it("마우스 초점에 링을 그리는 focus: 접두사를 쓰지 않는다", () => {
      const root = draw(open(), props);
      assert.equal(classesOf(root).some((c) => c.startsWith("focus:")), false);
    });
  });
}

describe("결과 카드가 훅에 넘기는 값", () => {
  it("한 판: 요약과 오류를 그대로 넘긴다", () => {
    const summary = { ...SUMMARY };
    draw(openRound(), { summary, error: "판을 열지 못했습니다." });
    assert.equal(hookArgs[0][0], summary);
    assert.equal(hookArgs[0][1], "판을 열지 못했습니다.");
  });

  it("한 판: 요약이 없어도(판을 못 닫음) 훅을 부르고 ref 를 붙인다", () => {
    const root = draw(openRound(), { summary: null, error: "판을 닫지 못했습니다." });
    assert.equal(hookArgs[0][0], null);
    assert.equal(hookArgs[0][1], "판을 닫지 못했습니다.");
    assert.equal(root.props.ref, SENTINEL_REF);
  });

  it("복습: 푼 개수와 오류를 그대로 넘긴다", () => {
    draw(openReview(), { answered: 8, error: "시작하지 못했습니다." });
    assert.deepEqual(hookArgs[0], [8, "시작하지 못했습니다."]);
  });

  it("일일공부: 진행 값을 넘기고 오류 자리는 null 이다", () => {
    const study = { ...STUDY };
    draw(openDaily(), { study });
    assert.equal(hookArgs[0][0], study);
    assert.equal(hookArgs[0][1], null);
  });

  it("일일공부: 진행 값이 없어도 훅을 부르고 ref 를 붙인다", () => {
    const root = draw(openDaily(), { study: null });
    assert.deepEqual(hookArgs[0], [null, null]);
    assert.equal(root.props.ref, SENTINEL_REF);
  });
});

describe("결과 카드의 초점 링", () => {
  it("한 판 카드는 focus-visible 링이 있고 outline-none 이 없다", () => {
    const classes = classesOf(draw(openRound(), { summary: SUMMARY, error: "", busy: false }));
    for (const name of RING) assert.ok(classes.includes(name), `${name} 가 없다`);
    assert.equal(classes.includes("outline-none"), false);
  });

  for (const [name, open, props] of [SCREENS[1], SCREENS[2]]) {
    it(`${name} 카드는 outline-none 이고 링 클래스가 없다`, () => {
      const classes = classesOf(draw(open(), props));
      assert.ok(classes.includes("outline-none"));
      assert.equal(classes.some((c) => c.startsWith("focus-visible:")), false);
    });
  }
});

describe("다시 여는 버튼은 카드 안에 있다", () => {
  // 훅의 "카드 안이면 안 옮긴다" 가 이 구조에 기댄다.
  for (const [name, open, props, label] of [
    ["한 판", openRound, { summary: SUMMARY, error: "" }, "여는 중..."],
    ["복습", openReview, { answered: 8, error: "" }, "여는 중"],
  ] as const) {
    it(`${name}: busy 면 카드 안 버튼이 잠긴다`, () => {
      const buttons = flatten(draw(open(), { ...props, busy: true })).filter(
        (el) => el.type === "button",
      );
      assert.equal(buttons.length, 1);
      assert.equal(buttons[0].props.disabled, true);
      assert.equal(buttons[0].props.children, label);
    });
  }
});

/* ---- 훅 ---- */

type FakeNode = {
  parent: FakeNode | null;
  disabled: boolean;
  matches(selector: string): boolean;
  contains(other: unknown): boolean;
};

function fakeNode(parent: FakeNode | null = null, disabled = false): FakeNode {
  const self: FakeNode = {
    parent,
    disabled,
    matches: (selector) => selector === ":disabled" && self.disabled,
    contains(other) {
      for (let at = other as FakeNode | null; at; at = at.parent) {
        if (at === self) return true;
      }
      return false;
    },
  };
  return self;
}

let focusCalls: unknown[] = [];

/** 결과 카드는 다음 형제가 없다. 보기 목록을 기대면 안 되는 자리다. */
function makeCard(page: FakeNode) {
  return Object.assign(fakeNode(page), {
    nextElementSibling: null,
    focus(options: unknown) {
      focusCalls.push(options);
    },
  });
}

function setup() {
  const page = fakeNode();
  const body = fakeNode(page);
  const card = makeCard(page);
  return {
    body,
    card,
    againEnabled: fakeNode(card),
    againLocked: fakeNode(card, true),
    insideLink: fakeNode(fakeNode(card)),
    exitLink: fakeNode(page),
    lockedOutside: fakeNode(page, true),
  };
}

type World = ReturnType<typeof setup>;

function focusOn(world: World, active: unknown) {
  setDocument({ body: world.body, activeElement: active });
}

/** 훅을 부르고 ref 에 카드를 붙인 뒤 effect 를 돌린다(React 의 순서). */
function renderHook(question: unknown, error: string | null, target: unknown) {
  queueEffects = true;
  cursor = 0;
  queued = [];
  const ref = callRealHook(question, error) as { current: unknown };
  ref.current = target;
  for (const run of queued) run();
}

describe("useFocusNewQuestion 결과 카드에서", () => {
  beforeEach(() => {
    focusCalls = [];
  });

  for (const [name, pick] of [
    ["카드 안 버튼", (w: World) => w.againEnabled],
    ["카드 안의 잠긴 버튼", (w: World) => w.againLocked],
    ["카드 안 깊은 곳의 링크", (w: World) => w.insideLink],
    ["카드 자신", (w: World) => w.card],
  ] as const) {
    it(`초점이 ${name} 이면 옮기지 않는다`, () => {
      const world = setup();
      focusOn(world, pick(world));
      renderHook(SUMMARY, "", world.card);
      assert.equal(focusCalls.length, 0);
    });
  }

  it("카드 밖에서 잠긴 버튼에 초점이 있으면 옮긴다", () => {
    const world = setup();
    focusOn(world, world.lockedOutside);
    renderHook(SUMMARY, "", world.card);
    assert.deepEqual(focusCalls, [{ preventScroll: true }]);
  });

  it("초점이 body 면 옮긴다", () => {
    const world = setup();
    focusOn(world, world.body);
    renderHook(SUMMARY, "", world.card);
    assert.deepEqual(focusCalls, [{ preventScroll: true }]);
  });

  it("activeElement 가 null 이면 옮긴다", () => {
    const world = setup();
    focusOn(world, null);
    renderHook(SUMMARY, "", world.card);
    assert.deepEqual(focusCalls, [{ preventScroll: true }]);
  });

  it("카드 밖의 살아 있는 링크(내 기록)에 초점이 있으면 뺏지 않는다", () => {
    const world = setup();
    focusOn(world, world.exitLink);
    renderHook(SUMMARY, "", world.card);
    assert.equal(focusCalls.length, 0);
  });

  it("아직 아무것도 안 눌렀으면 카드 밖이어도 옮기지 않는다", () => {
    setActivation(false);
    const world = setup();
    focusOn(world, world.body);
    renderHook(SUMMARY, "", world.card);
    assert.equal(focusCalls.length, 0);
  });

  it("다시 열기가 실패해 오류만 바뀌면 잠겼던 버튼의 초점을 뺏지 않는다", () => {
    const world = setup();
    focusOn(world, world.body);
    renderHook(SUMMARY, "", world.card);
    assert.equal(focusCalls.length, 1, "처음 뜰 때는 카드로 옮긴다");

    world.againEnabled.disabled = true;
    focusOn(world, world.againEnabled);
    renderHook(SUMMARY, "판을 열지 못했습니다.", world.card);
    assert.equal(focusCalls.length, 1);
  });

  it("초점을 잃은 뒤 오류가 바뀌면 다시 카드로 옮긴다", () => {
    // 잠긴 버튼에서 초점을 빼 버리는 브라우저에서는 body 로 떨어진다.
    const world = setup();
    focusOn(world, world.body);
    renderHook(SUMMARY, "", world.card);
    renderHook(SUMMARY, "판을 열지 못했습니다.", world.card);
    assert.equal(focusCalls.length, 2);
  });

  it("같은 값으로 다시 그려지면 다시 돌지 않는다", () => {
    const world = setup();
    focusOn(world, world.body);
    renderHook(SUMMARY, "", world.card);
    renderHook(SUMMARY, "", world.card);
    assert.equal(focusCalls.length, 1);
  });

  it("카드가 아직 안 붙었어도 어느 초점에서든 터지지 않는다", () => {
    const world = setup();
    for (const active of [world.body, world.againLocked, world.lockedOutside, null]) {
      slots = [];
      focusOn(world, active);
      assert.doesNotThrow(() => renderHook(SUMMARY, "", null));
    }
    assert.equal(focusCalls.length, 0);
  });
});
