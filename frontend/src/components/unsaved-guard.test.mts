/**
 * useUnsavedGuard 가 **어떤 클릭을 막고 어떤 클릭을 흘려보내는지** 실제
 * 처리기를 불러서 본다. LeaveConfirm 의 cancelLabel 도 같이 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - dirty 일 때만 beforeunload 와 문서 캡처 click 리스너를 건다.
 *   - 같은 출처·다른 경로 링크의 왼쪽 클릭(수정키 없음, target 없음/_self,
 *     download 없음)을 막고 확인 창을 연다. 진행하면 그 경로로 간다.
 *   - 같은 경로(#)·바깥 출처·새 탭 클릭은 안 막는다.
 *
 * 브라우저 없이 도는 방법: 서버 렌더에서는 useEffect 가 안 돈다. 그래서
 * react 모듈을 대역으로 바꿔 useEffect 만 "그 자리에서 바로 실행" 으로
 * 갈아끼운다(나머지는 진짜 react). 그러면 렌더하는 순간 리스너가 걸리고,
 * 가짜 window·document 가 그것을 받아 둔다. 받아 둔 click 처리기에 가짜
 * 이벤트를 넣어 preventDefault 가 불렸는지·창이 열렸는지를 본다.
 *
 * 창을 여는 openRef 는 서버 렌더에서 LeaveConfirm 이 채워주지 않는다
 * (useImperativeHandle 이 안 돈다). 훅이 돌려준 LeaveConfirm 요소의 props
 * 에서 openRef 를 꺼내 직접 채우고, onConfirm 을 직접 불러 이동을 본다.
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { beforeEach, describe, it, mock } from "node:test";
import type { ReactElement } from "react";

const require = createRequire(import.meta.url);
const realReact = require("react") as typeof import("react");

/** 렌더 중에 걸린 effect 의 정리 함수. */
const cleanups: Array<() => void> = [];

mock.module("react", {
  defaultExport: realReact,
  namedExports: {
    ...realReact,
    useEffect(effect: () => void | (() => void)) {
      const cleanup = effect();
      if (typeof cleanup === "function") cleanups.push(cleanup);
    },
  },
});

/** router.push 로 간 곳. */
const pushed: string[] = [];

mock.module("next/navigation", {
  namedExports: {
    useRouter: () => ({ push: (to: string) => pushed.push(to) }),
  },
});

// ---------------------------------------------------------------------------
// 가짜 DOM. 훅이 쓰는 것만 흉내 낸다.
// ---------------------------------------------------------------------------

type Listener = (event: never) => void;
type Registered = { type: string; fn: Listener; capture: boolean };

const windowListeners: Registered[] = [];
const documentListeners: Registered[] = [];

const listenerApi = (bag: Registered[]) => ({
  addEventListener(type: string, fn: Listener, capture?: boolean) {
    bag.push({ type, fn, capture: Boolean(capture) });
  },
  removeEventListener(type: string, fn: Listener, capture?: boolean) {
    const i = bag.findIndex(
      (r) => r.type === type && r.fn === fn && r.capture === Boolean(capture),
    );
    if (i >= 0) bag.splice(i, 1);
  },
});

const PAGE = "http://localhost:3001/profile";

class FakeElement {
  constructor(readonly parent: FakeElement | null = null) {}
  closest(selector: string): FakeElement | null {
    assert.equal(selector, "a[href]");
    if (this instanceof FakeAnchor && this.rawHref !== null) return this;
    return this.parent ? this.parent.closest(selector) : null;
  }
}

class FakeAnchor extends FakeElement {
  target = "";
  attrs: Record<string, string> = {};
  constructor(
    readonly rawHref: string | null,
    options: { target?: string; download?: boolean } = {},
  ) {
    super(null);
    if (options.target !== undefined) this.target = options.target;
    if (options.download) this.attrs.download = "";
  }
  get href(): string {
    return new URL(this.rawHref ?? "", PAGE).href;
  }
  hasAttribute(name: string): boolean {
    return name in this.attrs;
  }
}

const location = new URL(PAGE);

Object.assign(globalThis, {
  window: { location, ...listenerApi(windowListeners) },
  document: listenerApi(documentListeners),
  Element: FakeElement,
  HTMLAnchorElement: FakeAnchor,
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { createElement } = realReact;
const { useUnsavedGuard } = await import("./useUnsavedGuard");
const { LeaveConfirm } = await import("./LeaveConfirm");

// ---------------------------------------------------------------------------
// 도구
// ---------------------------------------------------------------------------

type GuardElement = ReactElement<{
  openRef: { current: (() => void) | null };
  onConfirm: () => void;
  cancelLabel?: string;
  confirmLabel: string;
  detail: string;
}>;

let dialog: GuardElement;
let opened = 0;

function Host({ dirty }: { dirty: boolean }) {
  dialog = useUnsavedGuard({
    dirty,
    title: "저장하지 않고 나갈까요?",
    detail: "고른 사진이 저장되지 않습니다.",
    confirmLabel: "나가기",
    cancelLabel: "계속 고치기",
  }) as GuardElement;
  return null;
}

/** 훅을 한 번 그린다. 이전 렌더의 리스너는 정리한다(언마운트 흉내). */
function mount(dirty: boolean): void {
  for (const c of cleanups.splice(0)) c();
  renderToStaticMarkup(createElement(Host, { dirty }));
  opened = 0;
  dialog.props.openRef.current = () => {
    opened += 1;
  };
}

const clickHandler = (): Listener => {
  const found = documentListeners.filter((r) => r.type === "click");
  assert.equal(found.length, 1, "click 리스너가 하나가 아니다");
  assert.equal(found[0].capture, true, "캡처 단계가 아니다 - Link 의 onClick 이 먼저 돈다");
  return found[0].fn;
};

type FakeClick = {
  target: unknown;
  button: number;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
  defaultPrevented: boolean;
  preventDefault: () => void;
};

function click(target: unknown, over: Partial<FakeClick> = {}): FakeClick {
  const event: FakeClick = {
    target,
    button: 0,
    metaKey: false,
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
    defaultPrevented: false,
    preventDefault() {
      event.defaultPrevented = true;
    },
    ...over,
  };
  clickHandler()(event as never);
  return event;
}

beforeEach(() => {
  pushed.length = 0;
});

// ---------------------------------------------------------------------------

describe("dirty 가 아니면 아무것도 걸지 않는다", () => {
  it("리스너가 없다", () => {
    mount(false);
    assert.equal(windowListeners.length, 0);
    assert.equal(documentListeners.length, 0);
  });
});

describe("dirty 일 때", () => {
  it("beforeunload 를 걸고, 불리면 떠나기를 막는다", () => {
    mount(true);
    const found = windowListeners.filter((r) => r.type === "beforeunload");
    assert.equal(found.length, 1);
    let prevented = false;
    const event = {
      returnValue: undefined as unknown,
      preventDefault() {
        prevented = true;
      },
    };
    found[0].fn(event as never);
    assert.ok(prevented);
    assert.equal(event.returnValue, "");
  });

  it("정리하면 두 리스너가 다 빠진다", () => {
    mount(true);
    for (const c of cleanups.splice(0)) c();
    assert.equal(windowListeners.length, 0);
    assert.equal(documentListeners.length, 0);
  });

  it("앱 안 다른 경로 링크는 막고 창을 연다", () => {
    mount(true);
    const e = click(new FakeAnchor("/board"));
    assert.equal(e.defaultPrevented, true);
    assert.equal(opened, 1);
    assert.deepEqual(pushed, [], "확인 전에 옮겼다");
  });

  it("링크 안쪽 글자(자식 요소)를 눌러도 막는다", () => {
    mount(true);
    const a = new FakeAnchor("/learn/words");
    const span = new FakeElement(a);
    const e = click(span);
    assert.equal(e.defaultPrevented, true);
    assert.equal(opened, 1);
  });

  it("진행하면 누른 링크의 경로(쿼리·# 포함)로 간다", () => {
    mount(true);
    click(new FakeAnchor("/learn/words?page=2#top"));
    dialog.props.onConfirm();
    assert.deepEqual(pushed, ["/learn/words?page=2#top"]);
  });

  it("두 번째로 누른 링크로 간다(앞 클릭이 남지 않는다)", () => {
    mount(true);
    click(new FakeAnchor("/board"));
    click(new FakeAnchor("/"));
    dialog.props.onConfirm();
    assert.deepEqual(pushed, ["/"]);
  });

  it("같은 출처 절대 주소도 막는다", () => {
    mount(true);
    const e = click(new FakeAnchor("http://localhost:3001/board"));
    assert.equal(e.defaultPrevented, true);
  });

  it("같은 경로·다른 쿼리는 떠나는 것이라 막는다", () => {
    mount(true);
    const e = click(new FakeAnchor("/profile?tab=x"));
    assert.equal(e.defaultPrevented, true);
  });

  for (const [label, anchor] of [
    ["같은 경로의 #", new FakeAnchor("#photo")],
    ["같은 경로 그대로", new FakeAnchor("/profile")],
    ["바깥 출처", new FakeAnchor("https://example.com/board")],
    ["다른 포트", new FakeAnchor("http://localhost:3000/board")],
    ["target=_blank", new FakeAnchor("/board", { target: "_blank" })],
    ["target=다른 창 이름", new FakeAnchor("/board", { target: "other" })],
    ["download", new FakeAnchor("/board", { download: true })],
    ["href 없는 a", new FakeAnchor(null)],
  ] as const) {
    it(`${label} 는 안 막는다`, () => {
      mount(true);
      const e = click(anchor);
      assert.equal(e.defaultPrevented, false);
      assert.equal(opened, 0);
    });
  }

  it("target=_self 는 막는다", () => {
    mount(true);
    const e = click(new FakeAnchor("/board", { target: "_self" }));
    assert.equal(e.defaultPrevented, true);
  });

  for (const key of ["metaKey", "ctrlKey", "shiftKey", "altKey"] as const) {
    it(`${key} 를 누른 클릭은 안 막는다(새 탭·새 창)`, () => {
      mount(true);
      const e = click(new FakeAnchor("/board"), { [key]: true });
      assert.equal(e.defaultPrevented, false);
      assert.equal(opened, 0);
    });
  }

  it("가운데 버튼 클릭은 안 막는다", () => {
    mount(true);
    const e = click(new FakeAnchor("/board"), { button: 1 });
    assert.equal(e.defaultPrevented, false);
  });

  it("이미 막힌 클릭은 건드리지 않는다", () => {
    mount(true);
    const e = click(new FakeAnchor("/board"), { defaultPrevented: true });
    assert.equal(opened, 0);
    assert.equal(e.defaultPrevented, true);
  });

  it("링크가 아닌 곳의 클릭은 안 막는다", () => {
    mount(true);
    const e = click(new FakeElement(null));
    assert.equal(e.defaultPrevented, false);
    assert.equal(opened, 0);
  });

  it("Element 가 아닌 대상(text 노드 등)은 안 막는다", () => {
    mount(true);
    const e = click({});
    assert.equal(e.defaultPrevented, false);
  });

  it("창 버튼은 '계속 고치기' / '나가기' 다", () => {
    mount(true);
    assert.equal(dialog.props.cancelLabel, "계속 고치기");
    assert.equal(dialog.props.confirmLabel, "나가기");
  });
});

describe("LeaveConfirm 의 되돌아가는 버튼 글자", () => {
  const draw = (cancelLabel?: string) =>
    renderToStaticMarkup(
      createElement(LeaveConfirm, {
        openRef: { current: null },
        title: "t",
        detail: "d",
        confirmLabel: "나가기",
        onConfirm: () => {},
        ...(cancelLabel === undefined ? {} : { cancelLabel }),
      }),
    );

  it("안 주면 '계속 풀기' (문제풀기 화면은 그대로)", () => {
    assert.match(draw(), />계속 풀기</);
  });

  it("주면 그 글자이고 '계속 풀기' 는 없다", () => {
    const html = draw("계속 고치기");
    assert.match(html, />계속 고치기</);
    assert.doesNotMatch(html, /계속 풀기/);
    assert.ok(html.indexOf("계속 고치기") < html.indexOf("나가기"), "되돌아가는 쪽이 먼저다");
  });
});
