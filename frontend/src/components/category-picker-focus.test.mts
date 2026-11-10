/**
 * 분류 고르개가 메뉴를 닫은 뒤 초점을 어디에 두는지 눌러서 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 메뉴를 닫으면 초점이 있던 항목이 함께 사라져 초점이 body 로 떨어진다. 다른
 * 분류로 옮기면 호출부의 key 때문에 고르개가 통째로 새로 만들어져 버튼도
 * 바뀐다. 그래서 값 하나를 모듈에 두고 다음 마운트가 한 번 쓰고 지운다.
 *
 * 잡으려는 결함은 이렇다.
 *
 *   값이 안 지워짐           다음에 고르개가 뜰 때마다 초점을 가로챈다
 *   새 탭 클릭에 값을 남김   이 탭은 그대로라 값이 남아 엉뚱한 때 초점이 온다
 *   고른 항목에 값을 남김    주소가 그대로라 새로 안 만들어져 값이 남는다
 *   확인 창 안의 Esc 를 먹음 창이 초점을 돌려줄 링크가 메뉴와 함께 사라진다
 *
 * leave-exits.test.mts 머리말대로 항목은 메뉴를 열어야 그려져서 서버 렌더로는 못
 * 누른다. 여기서는 react 의 훅을 대역으로 바꿔 메뉴를 진짜로 연다. 대역은 고르개
 * 하나마다 칸을 따로 둬서 "옛 고르개" 와 "새 고르개" 를 가른다.
 */
import assert from "node:assert/strict";
import { after, afterEach, beforeEach, describe, it, mock } from "node:test";
import type { ReactNode } from "react";

const realReact = await import("react");

type Effect = () => void | (() => void);
type EffectSlot = { deps: unknown[]; cleanup?: void | (() => void) };

type Instance = {
  props: { options: { value: string; label: string }[]; basePath: string; selected?: string };
  slots: unknown[];
  cursor: number;
  queued: (() => void)[];
  buttonFocus: number;
  attachButton: boolean;
  tree?: unknown;
};

let current: Instance;

mock.module("react", {
  defaultExport: realReact.default,
  namedExports: {
    ...realReact,
    useState<T>(init: T | (() => T)) {
      const inst = current;
      const at = inst.cursor++;
      if (at >= inst.slots.length) {
        inst.slots.push({ value: typeof init === "function" ? (init as () => T)() : init });
      }
      const s = inst.slots[at] as { value: T };
      const set = (next: T | ((prev: T) => T)) => {
        s.value = typeof next === "function" ? (next as (prev: T) => T)(s.value) : next;
      };
      return [s.value, set];
    },
    useRef<T>(init: T) {
      const inst = current;
      const at = inst.cursor++;
      if (at >= inst.slots.length) inst.slots.push({ current: init });
      return inst.slots[at];
    },
    useEffect(run: Effect, deps: unknown[]) {
      const inst = current;
      const at = inst.cursor++;
      const before = inst.slots[at] as EffectSlot | undefined;
      const changed = !before || deps.some((dep, i) => !Object.is(dep, before.deps[i]));
      if (at >= inst.slots.length) inst.slots.push({ deps });
      const self = inst.slots[at] as EffectSlot;
      if (!changed) return;
      self.deps = deps;
      inst.queued.push(() => {
        if (typeof self.cleanup === "function") self.cleanup();
        self.cleanup = run();
      });
    },
  },
});

const pushed: string[] = [];

mock.module("next/navigation", {
  namedExports: {
    useRouter: () => ({ push: (to: string) => pushed.push(to) }),
  },
});

mock.module("next/link", {
  defaultExport: function LinkStub(props: { children?: ReactNode }) {
    return props.children;
  },
});

const { CategoryPicker } = await import("./CategoryPicker");
const { clearSolved, markSolved } = await import("@/lib/quiz-progress");

/* ---- 가짜 DOM ---- */

type Listener = (event: unknown) => void;

let listeners: Record<string, Listener[]> = {};

type G = { document?: unknown; window?: unknown };
const realDocument = (globalThis as G).document;
const realWindow = (globalThis as G).window;

after(() => {
  (globalThis as G).document = realDocument;
  (globalThis as G).window = realWindow;
});

beforeEach(() => {
  listeners = {};
  pushed.length = 0;
  clearSolved();
  (globalThis as G).document = {
    addEventListener(type: string, fn: Listener) {
      (listeners[type] ??= []).push(fn);
    },
    removeEventListener(type: string, fn: Listener) {
      listeners[type] = (listeners[type] ?? []).filter((f) => f !== fn);
    },
  };
  (globalThis as G).window = {
    innerHeight: 800,
    addEventListener() {},
    removeEventListener() {},
  };
});

// 테스트가 값을 남기면 다음 테스트로 샌다. 마운트 하나로 비운다.
afterEach(() => {
  mount();
});

/* ---- 도구 ---- */

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

const OPTIONS = [
  { value: "git", label: "Git" },
  { value: "db", label: "DB" },
];

function draw(inst: Instance) {
  current = inst;
  inst.cursor = 0;
  inst.queued = [];
  inst.tree = CategoryPicker(inst.props as never);
  const root = inst.tree as El;
  (root.props.ref as { current: unknown }).current = {
    contains: () => true,
    getBoundingClientRect: () => ({ bottom: 100 }),
  };
  const button = flatten(root).find((el) => el.type === "button");
  assert.ok(button, "여는 버튼이 없다");
  if (inst.attachButton) {
    (button.props.ref as { current: unknown }).current = {
      focus() {
        inst.buttonFocus += 1;
      },
    };
  }
  for (const run of inst.queued) run();
  return inst;
}

/** 새 고르개를 만든다. key 가 바뀐 리마운트와 같다. */
function mount(selected?: string, attachButton = true): Instance {
  return draw({
    props: { options: OPTIONS, basePath: "/test/words", selected },
    slots: [],
    cursor: 0,
    queued: [],
    buttonFocus: 0,
    attachButton,
  });
}

function toggle(inst: Instance) {
  const button = flatten(inst.tree).find((el) => el.type === "button") as El;
  (button.props.onClick as () => void)();
  draw(inst);
}

function openPicker(selected?: string): Instance {
  const inst = mount(selected);
  toggle(inst);
  assert.ok(isOpen(inst), "메뉴가 안 열렸다");
  return inst;
}

const isOpen = (inst: Instance) => flatten(inst.tree).some((el) => el.type === "nav");

/** 메뉴의 항목. PickerItem 을 불러 Link 요소를 돌려준다. */
function item(inst: Instance, text: string): El {
  const found = flatten(inst.tree)
    .filter(named("PickerItem"))
    .find((el) => el.props.children === text);
  assert.ok(found, `${text} 항목이 없다`);
  return (found.type as (props: unknown) => El)(found.props);
}

type Mods = Partial<Record<"metaKey" | "ctrlKey" | "shiftKey" | "altKey", boolean>>;

/** 항목을 누른다. 이동이 막혔으면 true. */
function click(inst: Instance, text: string, mods: Mods = {}): boolean {
  let prevented = false;
  (item(inst, text).props.onClick as (event: unknown) => void)({
    metaKey: false,
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
    button: 0,
    preventDefault() {
      prevented = true;
    },
    ...mods,
  });
  draw(inst);
  return prevented;
}

function press(key: string, target: unknown) {
  for (const fn of listeners.keydown ?? []) fn({ key, target });
}

const plainTarget = { closest: () => null };

/** 다음 마운트가 버튼에 초점을 뒀는가. */
const nextMountFocused = () => mount().buttonFocus === 1;

/* ---- 테스트 ---- */

describe("분류 고르개 Esc", () => {
  it("Esc 로 닫으면 여는 버튼에 초점이 온다", () => {
    const inst = openPicker();
    press("Escape", plainTarget);
    draw(inst);
    assert.equal(isOpen(inst), false);
    assert.equal(inst.buttonFocus, 1);
  });

  it("closest 가 없는 대상(document)에서도 닫힌다", () => {
    const inst = openPicker();
    press("Escape", {});
    draw(inst);
    assert.equal(isOpen(inst), false);
    assert.equal(inst.buttonFocus, 1);
  });

  it("다른 키는 메뉴도 초점도 건드리지 않는다", () => {
    const inst = openPicker();
    press("Enter", plainTarget);
    draw(inst);
    assert.equal(isOpen(inst), true);
    assert.equal(inst.buttonFocus, 0);
  });

  it("확인 창 안의 Esc 는 메뉴도 초점도 건드리지 않는다", () => {
    const inst = openPicker();
    const asked: string[] = [];
    press("Escape", {
      closest(selector: string) {
        asked.push(selector);
        return {};
      },
    });
    draw(inst);
    assert.deepEqual(asked, ["dialog"]);
    assert.equal(isOpen(inst), true);
    assert.equal(inst.buttonFocus, 0);
  });

  it("Esc 로 닫아도 다음 마운트는 초점을 안 가져간다", () => {
    openPicker();
    press("Escape", plainTarget);
    assert.equal(nextMountFocused(), false);
  });
});

describe("분류 고르개 항목 고르기", () => {
  it("처음 뜬 고르개는 초점을 가져가지 않는다", () => {
    assert.equal(mount().buttonFocus, 0);
  });

  it("다른 분류를 고르면 닫히고 버튼에 초점이 온다", () => {
    const inst = openPicker("git");
    assert.equal(click(inst, "DB"), false);
    assert.equal(isOpen(inst), false);
    assert.equal(inst.buttonFocus, 1);
  });

  it("다른 분류로 옮기면 다음 마운트가 초점을 되찾고 값은 한 번 쓰면 사라진다", () => {
    click(openPicker("git"), "DB");
    assert.equal(mount("db").buttonFocus, 1, "새 고르개가 초점을 못 찾았다");
    assert.equal(mount("db").buttonFocus, 0, "값이 안 지워졌다");
  });

  it("분류가 있을 때 전체를 고르는 것도 다른 분류로 친다", () => {
    click(openPicker("git"), "전체");
    assert.equal(nextMountFocused(), true);
  });

  it("전체에서 분류를 고르는 것도 다른 분류로 친다", () => {
    click(openPicker(), "Git");
    assert.equal(nextMountFocused(), true);
  });

  it("이미 고른 항목을 누르면 버튼에 초점이 오고 값은 안 남는다", () => {
    const inst = openPicker("git");
    click(inst, "Git");
    assert.equal(isOpen(inst), false);
    assert.equal(inst.buttonFocus, 1);
    assert.equal(nextMountFocused(), false);
  });

  it("전체인 상태에서 전체를 눌러도 값은 안 남는다", () => {
    click(openPicker(), "전체");
    assert.equal(nextMountFocused(), false);
  });

  for (const mod of ["ctrlKey", "metaKey", "shiftKey", "altKey"] as const) {
    it(`${mod} 클릭은 새 탭이라 값을 안 남긴다`, () => {
      const inst = openPicker("git");
      assert.equal(click(inst, "DB", { [mod]: true }), false, "새 탭 열기를 막으면 안 된다");
      assert.equal(nextMountFocused(), false);
    });
  }

  it("새 마운트의 버튼이 아직 없어도 안 터지고 값은 지워진다", () => {
    click(openPicker("git"), "DB");
    assert.doesNotThrow(() => mount("db", false));
    assert.equal(nextMountFocused(), false);
  });
});

describe("분류 고르개 확인 창", () => {
  it("푼 것이 있으면 막고 창을 띄운다. 아직 메뉴도 값도 그대로다", () => {
    markSolved(3);
    const inst = openPicker("git");
    assert.equal(click(inst, "DB"), true);
    assert.equal(isOpen(inst), true);
    assert.equal(inst.buttonFocus, 0);
    assert.equal(nextMountFocused(), false, "확인 전인데 값이 남았다");
  });

  it("확인 창을 거쳐 옮기면 값이 남아 다음 마운트가 초점을 되찾는다", () => {
    markSolved(3);
    const inst = openPicker("git");
    click(inst, "DB");
    const dialog = flatten(inst.tree).find(named("LeaveConfirm"));
    assert.ok(dialog, "확인 창이 없다");
    (dialog.props.onConfirm as () => void)();
    draw(inst);
    assert.deepEqual(pushed, ["/test/words?category=db"]);
    assert.equal(isOpen(inst), false);
    assert.equal(mount("db").buttonFocus, 1);
    assert.equal(mount("db").buttonFocus, 0);
  });

  it("푼 것이 있어도 Ctrl 클릭은 안 막고 값도 안 남긴다", () => {
    markSolved(3);
    const inst = openPicker("git");
    assert.equal(click(inst, "DB", { ctrlKey: true }), false);
    assert.equal(nextMountFocused(), false);
  });

  it("푼 것이 있어도 이미 고른 항목은 안 막고 값도 안 남긴다", () => {
    markSolved(3);
    const inst = openPicker("git");
    assert.equal(click(inst, "Git"), false);
    assert.equal(nextMountFocused(), false);
  });
});

describe("분류 고르개 고른 항목의 색", () => {
  it("고른 항목은 --brand-soft 바탕에 --brand 글자다", () => {
    const style = item(openPicker("git"), "Git").props.style as Record<string, string>;
    assert.equal(style.background, "var(--brand-soft)");
    assert.equal(style.color, "var(--brand)");
  });

  it("안 고른 항목은 그 색을 쓰지 않는다", () => {
    const style = item(openPicker("git"), "DB").props.style as Record<string, string>;
    assert.equal(style.background, "transparent");
    assert.equal(style.color, "var(--text-body)");
  });
});
