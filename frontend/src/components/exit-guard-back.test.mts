/**
 * 폰의 뒤로 가기(Navigation API 의 traverse)를 ExitGuard 가 언제 막고 언제
 * 그냥 보내는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 결함은 둘 갈래다.
 *
 *   잘못 묻는다     판이 끝난 화면·시작 전·한 문제도 안 푼 문제풀기에서 뒤로
 *                   가기를 막아 창을 띄운다. 링크·router.push 같은 다른 이동
 *                   까지 막으면 화면이 아예 안 넘어간다
 *   못 나간다       창에서 나가기를 골랐는데 다시 막혀 같은 창이 또 뜨거나,
 *                   한 번 나간 뒤(같은 경로에 남는 이동) 다음 뒤로 가기가
 *                   영영 안 막힌다(passRef 가 안 풀림)
 *
 * 브라우저 없이 본다. window.navigation 을 EventTarget 으로 만든 대역으로 두고
 * navigate 이벤트를 직접 쏜다. react 훅은 quiz-board-item.test.mts 와 같은 칸
 * 대역이고, effect 는 의존이 바뀔 때만 cleanup 뒤 다시 돌린다(React 와 같다).
 * 창(LeaveConfirm)은 그리지 않고 ExitGuard 가 넘긴 props 를 꺼내 쓴다 -
 * openRef 에 가짜 여는 함수를 넣어 "창이 열렸나" 를 세고, onConfirm 을 불러
 * "나가기" 를 고른 것으로 한다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

const realReact = await import("react");

// ---------------------------------------------------------------------------
// 훅 대역
// ---------------------------------------------------------------------------

type Slot = { value: unknown };
type EffectSlot = { deps?: unknown[]; cleanup?: void | (() => void) };

let slots: Slot[] = [];
let cursor = 0;
let pending: { s: EffectSlot; run: () => void | (() => void); deps?: unknown[] }[] = [];

function slot<T>(init: () => T): Slot {
  if (cursor >= slots.length) slots.push({ value: init() });
  return slots[cursor++];
}

const sameDeps = (a?: unknown[], b?: unknown[]) =>
  !!a && !!b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));

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
    useEffect(run: () => void | (() => void), deps?: unknown[]) {
      const s = slot(() => ({}) as EffectSlot).value as EffectSlot;
      pending.push({ s, run, deps });
    },
  },
});

const pushed: string[] = [];
mock.module("next/navigation", {
  namedExports: {
    useRouter: () => ({ push: (to: string) => pushed.push(to) }),
    usePathname: () => "/test/round",
  },
});

const { ExitGuard } = await import("./ExitGuard");
const { LeaveConfirm } = await import("./LeaveConfirm");
const { clearSolved, markSolved, leaveDetail } = await import("@/lib/quiz-progress");

// ---------------------------------------------------------------------------
// Navigation API 대역
// ---------------------------------------------------------------------------

type Deferred = {
  promise: Promise<unknown>;
  resolve: () => void;
  reject: (e: unknown) => void;
};

function deferred(): Deferred {
  let resolve!: () => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<unknown>((res, rej) => {
    resolve = () => res(undefined);
    reject = rej;
  });
  return { promise, resolve, reject };
}

class FakeNavigation extends EventTarget {
  /** traverseTo 로 간 기록 자리. */
  traversals: string[] = [];
  /** 마지막 traverseTo 의 finished. 테스트가 끝낸다. */
  finished: Deferred = deferred();
  /** 마지막 traverseTo 의 committed. 이동이 일어났는지. finished 와 따로 끝낸다. */
  committed: Deferred = deferred();
  listeners = 0;

  addEventListener(...args: Parameters<EventTarget["addEventListener"]>) {
    this.listeners += 1;
    super.addEventListener(...args);
  }

  removeEventListener(...args: Parameters<EventTarget["removeEventListener"]>) {
    this.listeners -= 1;
    super.removeEventListener(...args);
  }

  traverseTo(key: string) {
    this.traversals.push(key);
    this.finished = deferred();
    this.committed = deferred();
    return { committed: this.committed.promise, finished: this.finished.promise };
  }
}

let nav: FakeNavigation;

/**
 * navigate 이벤트를 쏜다. 막혔으면(preventDefault) true.
 * 기본은 사용자의 뒤로 가기(traverse, 막을 수 있음)다.
 */
function navigate(
  over: { type?: string; key?: string; cancelable?: boolean } = {},
): boolean {
  const event = new Event("navigate", { cancelable: over.cancelable ?? true });
  Object.assign(event, {
    navigationType: over.type ?? "traverse",
    destination: { key: over.key ?? "prev" },
  });
  nav.dispatchEvent(event);
  return event.defaultPrevented;
}

// ---------------------------------------------------------------------------
// 그리기
// ---------------------------------------------------------------------------

type Props = Parameters<typeof ExitGuard>[0];
type El = { type: unknown; props: Record<string, unknown> };

/** 창이 열린 횟수. LeaveConfirm 의 openRef 에 넣은 가짜가 센다. */
let opened = 0;

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

/** 한 번 그리고 effect 를 커밋한다. 창 props(없으면 undefined)와 나가기 버튼. */
function render(props: Props) {
  cursor = 0;
  pending = [];
  const tree = ExitGuard(props) as unknown as El;
  for (const { s, run, deps } of pending) {
    if (sameDeps(s.deps, deps)) continue;
    if (typeof s.cleanup === "function") s.cleanup();
    s.cleanup = run();
    s.deps = deps;
  }
  const [dialog] = findAll(tree, (el) => el.type === LeaveConfirm);
  if (dialog) {
    (dialog.props.openRef as { current: (() => void) | null }).current = () => {
      opened += 1;
    };
  }
  const [button] = findAll(tree, (el) => el.type === "button");
  return {
    dialog,
    /** 나가기 버튼을 누른다. */
    press: () => (button.props.onClick as () => void)(),
    /** 창에서 나가기를 고른다. */
    confirmLeave: () => {
      assert.ok(dialog, "창이 없는데 나가기를 골랐다");
      (dialog.props.onConfirm as () => void)();
    },
  };
}

/** 사라진다. 남은 effect 의 cleanup 을 모두 부른다. */
function unmount() {
  for (const s of slots) {
    const v = s.value as EffectSlot;
    if (v && typeof v === "object" && typeof v.cleanup === "function") v.cleanup();
  }
}

const flush = () => new Promise((r) => setTimeout(r, 0));

const realWindow = (globalThis as { window?: unknown }).window;
after(() => {
  (globalThis as { window?: unknown }).window = realWindow;
});

beforeEach(() => {
  slots = [];
  opened = 0;
  pushed.length = 0;
  clearSolved();
  nav = new FakeNavigation();
  // 움직임 줄이기를 켠 것으로 둔다. leave() 가 장막 타이머 없이 곧장 push 한다.
  (globalThis as { window?: unknown }).window = {
    navigation: nav,
    matchMedia: () => ({ matches: true }),
  };
});

const ROUND: Props = { to: "/test", label: "그만두기", confirm: true, score: 3, countdown: true };
const QUIZ: Props = { to: "/test", label: "문제풀기", confirmWhenSolved: true };

// ---------------------------------------------------------------------------
// 묻지 말아야 할 때
// ---------------------------------------------------------------------------

describe("뒤로 가기 - 묻지 않는 화면", () => {
  it("확인이 꺼진 출구(시작 전·판이 끝난 화면)는 리스너를 달지 않는다", () => {
    render({ to: "/test", label: "문제풀기" });
    assert.equal(nav.listeners, 0);
    assert.equal(navigate(), false);
    assert.equal(opened, 0);
  });

  it("문제풀기에서 한 문제도 안 풀었으면 뒤로 가기를 그냥 보낸다", () => {
    render(QUIZ);
    assert.equal(navigate(), false);
    assert.equal(opened, 0);
  });

  it("다 풀었다가 판이 비워졌으면(clearSolved) 다시 그냥 보낸다", () => {
    render(QUIZ);
    markSolved(2);
    assert.equal(navigate(), true);
    clearSolved();
    assert.equal(navigate(), false);
    assert.equal(opened, 1);
  });

  it("뒤로 가기가 아닌 이동(링크·push·replace·새로고침)은 막지 않는다", () => {
    markSolved(4);
    render(ROUND);
    for (const type of ["push", "replace", "reload"]) {
      assert.equal(navigate({ type }), false, `${type} 를 막았다`);
    }
    assert.equal(opened, 0);
  });

  it("막을 수 없는 뒤로 가기(cancelable false)는 창 없이 보낸다", () => {
    render(ROUND);
    assert.equal(navigate({ cancelable: false }), false);
    assert.equal(opened, 0);
  });

  it("Navigation API 가 없는 브라우저에서도 터지지 않고 버튼은 그대로다", () => {
    (globalThis as { window?: unknown }).window = { matchMedia: () => ({ matches: true }) };
    const guard = render(ROUND);
    guard.press();
    assert.equal(opened, 1);
    guard.confirmLeave();
    assert.deepEqual(pushed, ["/test"]);
  });

  it("사라지면 리스너를 뗀다", () => {
    render(ROUND);
    assert.equal(nav.listeners, 1);
    unmount();
    assert.equal(nav.listeners, 0);
    assert.equal(navigate(), false);
  });

  it("다시 그려도 리스너가 겹쳐 달리지 않는다", () => {
    render(ROUND);
    render(ROUND);
    render(ROUND);
    assert.equal(nav.listeners, 1);
    navigate();
    assert.equal(opened, 1, "한 번 눌렀는데 창이 여러 번 열렸다");
  });
});

// ---------------------------------------------------------------------------
// 물어야 할 때
// ---------------------------------------------------------------------------

describe("뒤로 가기 - 막고 묻는다", () => {
  it("한 판 도중이면 푼 것이 없어도 막고 창을 연다", () => {
    render(ROUND);
    assert.equal(navigate(), true);
    assert.equal(opened, 1);
    assert.equal(pushed.length, 0);
  });

  it("문제풀기에서 푼 것이 생기면 다시 그리지 않아도 막는다(그 순간의 값을 본다)", () => {
    render(QUIZ);
    markSolved(3);
    assert.equal(navigate(), true);
    assert.equal(opened, 1);
    // 창의 문구는 막은 그 순간의 푼 수를 말한다.
    const { dialog } = render(QUIZ);
    assert.equal(dialog.props.detail, leaveDetail(3));
  });

  it("앞으로 가기(traverse)도 같은 판을 떠나는 것이라 막는다", () => {
    render(ROUND);
    assert.equal(navigate({ key: "forward" }), true);
  });
});

// ---------------------------------------------------------------------------
// 창에서 나가기를 고른 뒤
// ---------------------------------------------------------------------------

describe("뒤로 가기 - 나가기를 고른 뒤", () => {
  it("뒤로 가기로 연 창이면 막았던 그 자리로 간다(버튼의 목적지가 아니다)", () => {
    const guard = render(ROUND);
    navigate({ key: "hub" });
    guard.confirmLeave();
    assert.deepEqual(nav.traversals, ["hub"]);
    assert.deepEqual(pushed, []);
  });

  it("그 이동이 일으킨 navigate 는 다시 막지 않는다", () => {
    const guard = render(ROUND);
    navigate({ key: "hub" });
    guard.confirmLeave();
    assert.equal(navigate({ key: "hub" }), false, "나가기를 골랐는데 또 막혔다");
    assert.equal(opened, 1, "같은 창이 또 열렸다");
  });

  it("같은 경로에 남는 이동이 끝나면 다음 뒤로 가기를 다시 막는다", async () => {
    const guard = render(ROUND);
    navigate({ key: "same-path" });
    guard.confirmLeave();
    nav.finished.resolve();
    await flush();
    assert.equal(navigate({ key: "older" }), true, "passRef 가 안 풀렸다");
    assert.equal(opened, 2);
  });

  it("그 기록이 사라져 이동이 실패하면 버튼의 목적지로 간다", async () => {
    const guard = render(ROUND);
    navigate({ key: "gone" });
    guard.confirmLeave();
    // 진짜와 같이 이동이 아예 안 일어나면 committed 와 finished 가 같이 실패한다.
    nav.committed.reject(new Error("InvalidStateError"));
    nav.finished.reject(new Error("InvalidStateError"));
    await flush();
    assert.deepEqual(pushed, ["/test"]);
    // 이제 나가는 중이라 그 사이 뒤로 가기는 막지 않는다(아래 테스트).
    assert.equal(navigate(), false, "나가는 중인데 뒤로 가기를 또 막았다");
  });

  it("이동은 됐는데 뒤이은 이동에 끊겨 finished 만 실패하면 다시 밀어내지 않는다", async () => {
    const guard = render(ROUND);
    navigate({ key: "hub" });
    guard.confirmLeave();
    nav.committed.resolve();
    nav.finished.reject(new Error("AbortError"));
    await flush();
    assert.deepEqual(pushed, [], "이미 도착한 사람을 버튼의 목적지로 다시 밀었다");
    assert.equal(navigate({ key: "older" }), true, "finished 가 실패한 뒤 passRef 가 안 풀렸다");
  });

  it("버튼으로 나가기를 고른 뒤(나가는 중) 뒤로 가기는 막지 않고 창도 다시 안 연다", () => {
    const guard = render(ROUND);
    guard.press();
    guard.confirmLeave();
    const before = opened;
    assert.equal(navigate({ key: "hub" }), false, "나가는 중인데 뒤로 가기를 막았다");
    assert.equal(opened, before, "나가는 중인데 창이 또 열렸다");
  });

  it("뒤로 가기로 연 창을 닫은 뒤 버튼으로 다시 열면 버튼의 목적지로 간다", () => {
    const guard = render(ROUND);
    navigate({ key: "hub" });
    // 계속 풀기(창만 닫힘). 그 뒤 버튼으로 나가기.
    guard.press();
    guard.confirmLeave();
    assert.deepEqual(nav.traversals, [], "버튼으로 열었는데 옛 뒤로 가기 자리로 갔다");
    assert.deepEqual(pushed, ["/test"]);
  });

  it("창을 닫고 다시 뒤로 가기를 누르면 마지막에 막은 자리로 간다", () => {
    const guard = render(ROUND);
    navigate({ key: "first" });
    navigate({ key: "second" });
    guard.confirmLeave();
    assert.deepEqual(nav.traversals, ["second"]);
  });

  it("버튼으로 연 창에서 나가기는 기록을 건드리지 않는다", () => {
    markSolved(1);
    const guard = render(QUIZ);
    guard.press();
    assert.equal(opened, 1);
    guard.confirmLeave();
    assert.deepEqual(nav.traversals, []);
    assert.deepEqual(pushed, ["/test"]);
  });
});
