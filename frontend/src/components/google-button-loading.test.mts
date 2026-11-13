/**
 * 구글 버튼(GoogleButton)을 기다리는 동안과, 신분 토큰을 보낸 뒤.
 *
 * 실행: cd frontend && npm test
 *
 * 지키는 것:
 *   - 기다리는 동안 예전 링크는 흐리고(opacity 0.5) inert 다. 보조기기에는
 *     "불러오는 중" 을 알린다. 그동안 누르면 예전 방식으로 구글 화면에 간다
 *     (11-13 폰, 동의를 켜자마자 누른 사람).
 *   - 그려진 때부터 6초가 지나면 누를 수 있다(5999ms 에는 아직 아니다).
 *   - 못 뜨는 것이 확실하면 6초를 기다리지 않는다: 스크립트 onError, 서버에
 *     클라이언트 ID 없음(prepare 가 null), 준비 실패(prepare 가 reject),
 *     스크립트가 떴는데 google.accounts.id 가 없음.
 *   - 구글 버튼이 크기를 가지면 예전 링크가 사라지고 6초 타이머도 풀린다.
 *     6초를 넘겨 링크를 연 뒤에 구글 버튼이 떠도 그 위로 바뀐다.
 *   - 화면을 떠난 뒤 늦게 끝난 준비는 상태를 건드리지 않는다.
 *   - 성공한 액션의 redirect(NEXT_REDIRECT)는 다시 던져 Next 에 돌려주고, 로그인
 *     화면으로 덮지 않는다(location.replace 를 부르지 않는다). 원인(cause)에
 *     감싼 redirect 도 같다.
 *   - 보통 오류와 { failed: true } 는 /login?error=google 로 바꿔치기한다.
 *     실패가 아니면 아무 데도 보내지 않는다. 토큰은 한 번만 보낸다.
 *
 * 하네스: 컴포넌트 함수를 직접 부르고 useState/useRef/useEffect/useTransition 을
 * 칸 배열 대역으로 돌린다(speak-button-dynamic 과 같은 방식). 효과는 의존값이
 * 바뀌면 뒷정리 후 다시 돈다. 시계는 node:test 의 mock.timers. 돌려준 요소
 * 트리는 renderToStaticMarkup 으로 마크업을 본다. next/navigation 의
 * unstable_rethrow·redirect 는 진짜를 쓴다(진짜 NEXT_REDIRECT 오류를 만든다).
 */
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it, mock } from "node:test";
import type { ReactElement } from "react";

const realReact = await import("react");

/* ---------- 훅 대역 ---------- */

let direct = false;
let cells: unknown[] = [];
let cursor = 0;
type Effect = { fn: () => void | (() => void); deps?: unknown[]; cleanup?: () => void };
let effects: Effect[] = [];
let pendingEffects: number[] = [];
let unmounted = false;
let setsAfterUnmount = 0;
/** startTransition 에 넘긴 비동기 함수가 돌려준 약속. */
let transitions: Promise<unknown>[] = [];

mock.module("react", {
  defaultExport: realReact.default,
  namedExports: {
    ...realReact,
    useState<T>(init: T) {
      if (!direct) return realReact.useState(init);
      const i = cursor++;
      if (!(i in cells)) cells[i] = init;
      const set = (next: T | ((prev: T) => T)) => {
        if (unmounted) setsAfterUnmount++;
        cells[i] = typeof next === "function" ? (next as (p: T) => T)(cells[i] as T) : next;
      };
      return [cells[i] as T, set];
    },
    useRef<T>(init: T) {
      if (!direct) return realReact.useRef(init);
      const i = cursor++;
      if (!(i in cells)) cells[i] = { current: init };
      return cells[i];
    },
    useEffect(fn: () => void | (() => void), deps?: unknown[]) {
      if (!direct) return realReact.useEffect(fn, deps);
      const i = cursor++;
      const prev = effects[i];
      const changed =
        !prev || !deps || !prev.deps || deps.some((d, k) => !Object.is(d, prev.deps![k]));
      if (prev && !changed) return;
      effects[i] = { fn, deps, cleanup: prev?.cleanup };
      pendingEffects.push(i);
    },
    useTransition() {
      if (!direct) return realReact.useTransition();
      const i = cursor++;
      if (!(i in cells)) cells[i] = false;
      const start = (fn: () => unknown) => {
        const p = Promise.resolve().then(fn);
        transitions.push(p);
        // 결과를 테스트가 따로 본다. 처리 안 된 거절로 러너가 멈추지 않게 한다.
        p.catch(() => {});
      };
      return [cells[i], start];
    },
  },
});

/* ---------- 바깥 모듈 대역 ---------- */

mock.module("next/script", { defaultExport: () => null });

let prepareImpl: () => Promise<unknown> = async () => ({ clientId: "cid", nonce: "n" });
let actionImpl: (arg: unknown) => Promise<unknown> = async () => undefined;
const actionCalls: unknown[] = [];
mock.module("@/app/(auth)/google-actions", {
  namedExports: {
    prepareGoogleButton: () => prepareImpl(),
    googleCredentialAction: (arg: unknown) => {
      actionCalls.push(arg);
      return actionImpl(arg);
    },
  },
});

const { createElement } = realReact;
const { renderToStaticMarkup } = await import("react-dom/server");
const { redirect, notFound } = await import("next/navigation");
const { GoogleButton } = await import("./GoogleButton");

/* ---------- 브라우저 대역 ---------- */

let replaced: string[] = [];
let googleCallback: ((r: { credential?: unknown }) => void) | undefined;
let frameSize = { offsetWidth: 0, offsetHeight: 0 };
let googlePresent = true;

const fakeEl = {
  offsetWidth: 360,
  querySelector: (sel: string) => (sel === "iframe" ? frameSize : null),
};

class FakeResizeObserver {
  observe() {}
  disconnect() {}
}

function installWindow() {
  (globalThis as Record<string, unknown>).ResizeObserver = FakeResizeObserver;
  (globalThis as Record<string, unknown>).window = {
    get google() {
      if (!googlePresent) return undefined;
      return {
        accounts: {
          id: {
            initialize: (config: { callback: (r: { credential?: unknown }) => void }) => {
              googleCallback = config.callback;
            },
            renderButton: () => {},
          },
        },
      };
    },
    location: { replace: (to: string) => replaced.push(to) },
  };
}

/* ---------- 그리기 ---------- */

const props = {
  context: "signin" as const,
  next: "/board",
  fallback: createElement("a", { href: "/api/auth/google" }, "구글로 계속하기"),
};
let tree: ReactElement | null = null;

/** 컴포넌트를 한 번 부르고, 바뀐 효과를 뒷정리 후 돌린다. */
function render() {
  direct = true;
  cursor = 0;
  try {
    tree = (GoogleButton as (p: typeof props) => ReactElement)(props);
  } finally {
    direct = false;
  }
  // 첫 그림 뒤 ref 가 box 에 붙은 것처럼 한다. box 는 첫 useRef 다.
  const boxRef = cells.find((c) => c && typeof c === "object" && "current" in c) as {
    current: unknown;
  };
  if (boxRef && boxRef.current === null) boxRef.current = fakeEl;
  const run = pendingEffects;
  pendingEffects = [];
  for (const i of run) {
    effects[i].cleanup?.();
    const out = effects[i].fn();
    effects[i].cleanup = typeof out === "function" ? out : undefined;
  }
}

function unmount() {
  for (const e of effects) e?.cleanup?.();
  unmounted = true;
}

function html(): string {
  return renderToStaticMarkup(tree!);
}

/** 예전 링크를 감싼 덮개의 여는 태그. 없으면 null. */
function overlayTag(): string | null {
  const h = html();
  const at = h.indexOf('<a href="/api/auth/google"');
  if (at < 0) return null;
  return h.slice(0, at).match(/<div[^>]*>$/)?.[0] ?? "";
}

function assertWaiting() {
  const tag = overlayTag();
  assert.ok(tag, "예전 링크가 있어야 한다");
  assert.match(tag, /\sinert=""/, "기다리는 동안 예전 링크는 inert");
  assert.match(tag, /opacity:0\.5/, "기다리는 동안 예전 링크는 흐리다");
  assert.match(html(), /role="status"[^>]*>구글 로그인 버튼을 불러오는 중입니다/);
}

function assertGaveUp() {
  const tag = overlayTag();
  assert.ok(tag, "예전 링크가 있어야 한다");
  assert.doesNotMatch(tag, /inert/, "포기한 뒤 예전 링크는 누를 수 있다");
  assert.doesNotMatch(tag, /opacity/, "포기한 뒤 예전 링크는 흐리지 않다");
  assert.doesNotMatch(html(), /불러오는 중입니다/);
}

/** 대기 중인 약속(마이크로태스크)을 흘려보낸다. 가짜 시계와 무관하다. */
async function flush() {
  for (let k = 0; k < 10; k++) await Promise.resolve();
}

/** 그린 트리에서 구글 스크립트(next/script) 요소의 props. */
function script(): Record<string, unknown> {
  const kids = (tree!.props as { children: unknown[] }).children.flat();
  const el = kids.find(
    (k) => (k as ReactElement<{ src?: string }>)?.props?.src?.includes("gsi/client"),
  ) as ReactElement<Record<string, unknown>>;
  assert.ok(el, "구글 스크립트 요소가 있어야 한다");
  return el.props;
}

function scriptReady() {
  (script().onReady as () => void)();
  render();
}

/** 스크립트가 뜨고 준비가 끝나 구글 버튼이 크기를 갖고 나타나게 한다. */
async function showButton() {
  scriptReady();
  await flush();
  frameSize = { offsetWidth: 300, offsetHeight: 44 };
  mock.timers.tick(200);
  render();
}

beforeEach(() => {
  mock.timers.enable({ apis: ["setTimeout", "setInterval"] });
  cells = [];
  effects = [];
  pendingEffects = [];
  transitions = [];
  unmounted = false;
  setsAfterUnmount = 0;
  replaced = [];
  actionCalls.length = 0;
  googleCallback = undefined;
  frameSize = { offsetWidth: 0, offsetHeight: 0 };
  googlePresent = true;
  prepareImpl = async () => ({ clientId: "cid", nonce: "n" });
  actionImpl = async () => undefined;
  installWindow();
  render();
});

afterEach(() => {
  mock.timers.reset();
});

/* ---------- 기다리는 동안 ---------- */

describe("구글 버튼 - 기다리는 동안", () => {
  it("처음 그림에서 예전 링크는 흐리고 누를 수 없고, 불러오는 중이라고 알린다", () => {
    assertWaiting();
  });

  it("5999ms 에는 아직 누를 수 없고 6000ms 에 누를 수 있다", () => {
    mock.timers.tick(5999);
    render();
    assertWaiting();
    mock.timers.tick(1);
    render();
    assertGaveUp();
  });

  it("스크립트가 떴지만 버튼이 0x0 이면 6초 뒤 누를 수 있다", async () => {
    scriptReady();
    await flush();
    assert.ok(googleCallback, "구글 스크립트에 설정이 넘어가야 한다");
    mock.timers.tick(2000);
    render();
    assertWaiting();
    mock.timers.tick(4000);
    render();
    assertGaveUp();
  });
});

describe("구글 버튼 - 못 뜨는 것이 확실하면 바로", () => {
  it("스크립트 onError", () => {
    (script().onError as () => void)();
    render();
    assertGaveUp();
  });

  it("서버에 클라이언트 ID 가 없음(prepare 가 null)", async () => {
    prepareImpl = async () => null;
    scriptReady();
    await flush();
    render();
    assertGaveUp();
  });

  it("준비 실패(prepare 가 reject)", async () => {
    const warn = mock.method(console, "warn", () => {});
    prepareImpl = async () => {
      throw new Error("action not found");
    };
    scriptReady();
    await flush();
    render();
    assertGaveUp();
    assert.equal(warn.mock.callCount(), 1);
    warn.mock.restore();
  });

  it("스크립트가 떴는데 google.accounts.id 가 없음", async () => {
    googlePresent = false;
    scriptReady();
    await flush();
    render();
    assertGaveUp();
  });
});

describe("구글 버튼 - 나타난 뒤", () => {
  it("크기를 가지면 예전 링크가 사라지고, 6초가 지나도 돌아오지 않는다", async () => {
    await showButton();
    assert.equal(overlayTag(), null);
    assert.doesNotMatch(html(), /불러오는 중입니다/);
    mock.timers.tick(10_000);
    render();
    assert.equal(overlayTag(), null);
  });

  it("6초가 지나 예전 링크를 연 뒤에 구글 버튼이 떠도 그 위로 바뀐다", async () => {
    scriptReady();
    await flush();
    mock.timers.tick(6000);
    render();
    assertGaveUp();
    frameSize = { offsetWidth: 300, offsetHeight: 44 };
    mock.timers.tick(200);
    render();
    assert.equal(overlayTag(), null);
  });

  it("화면을 떠난 뒤 늦게 끝난 준비는 상태를 건드리지 않는다", async () => {
    let finish: (v: unknown) => void = () => {};
    prepareImpl = () => new Promise((r) => (finish = r));
    scriptReady();
    unmount();
    finish(null);
    await flush();
    mock.timers.tick(10_000);
    assert.equal(setsAfterUnmount, 0);
  });
});

/* ---------- 신분 토큰을 보낸 뒤 ---------- */

describe("구글 버튼 - 신분 토큰을 보낸 뒤", () => {
  beforeEach(async () => {
    await showButton();
    assert.ok(googleCallback);
  });

  it("성공한 액션의 redirect 는 다시 던지고 로그인 화면으로 덮지 않는다", async () => {
    let thrown: unknown;
    actionImpl = async () => {
      try {
        redirect("/board");
      } catch (e) {
        thrown = e;
        throw e;
      }
    };
    const err = mock.method(console, "error", () => {});
    googleCallback!({ credential: "x.y.z" });
    await assert.rejects(transitions[0], (e) => e === thrown);
    assert.match(String((thrown as { digest?: string }).digest), /^NEXT_REDIRECT;/);
    assert.deepEqual(replaced, []);
    assert.equal(err.mock.callCount(), 0, "redirect 를 실패로 기록하지 않는다");
    err.mock.restore();
    assert.deepEqual(actionCalls, [{ credential: "x.y.z", next: "/board", consent: false }]);
  });

  it("cause 에 감싼 redirect 도 다시 던진다", async () => {
    actionImpl = async () => {
      try {
        redirect("/board");
      } catch (e) {
        throw new Error("감쌈", { cause: e });
      }
    };
    googleCallback!({ credential: "x.y.z" });
    await assert.rejects(transitions[0], /NEXT_REDIRECT/);
    assert.deepEqual(replaced, []);
  });

  it("notFound 같은 다른 라우터 신호도 로그인 화면으로 덮지 않는다", async () => {
    actionImpl = async () => notFound();
    googleCallback!({ credential: "x.y.z" });
    await assert.rejects(transitions[0]);
    assert.deepEqual(replaced, []);
  });

  it("보통 오류는 /login?error=google 로 바꿔치기한다", async () => {
    const err = mock.method(console, "error", () => {});
    actionImpl = async () => {
      throw new TypeError("Failed to fetch");
    };
    googleCallback!({ credential: "x.y.z" });
    await transitions[0];
    assert.deepEqual(replaced, ["/login?error=google"]);
    assert.equal(err.mock.callCount(), 1);
    err.mock.restore();
  });

  it("digest 만 비슷한 보통 오류는 redirect 로 보지 않는다", async () => {
    const err = mock.method(console, "error", () => {});
    actionImpl = async () => {
      throw Object.assign(new Error("x"), { digest: "NEXT_REDIRECT" });
    };
    googleCallback!({ credential: "x.y.z" });
    await transitions[0];
    assert.deepEqual(replaced, ["/login?error=google"]);
    err.mock.restore();
  });

  it("{ failed: true } 는 /login?error=google 로 바꿔치기한다", async () => {
    actionImpl = async () => ({ failed: true });
    googleCallback!({ credential: "x.y.z" });
    await transitions[0];
    assert.deepEqual(replaced, ["/login?error=google"]);
  });

  it("실패 없이 끝나면(undefined) 바꿔치기하지 않는다", async () => {
    actionImpl = async () => undefined;
    googleCallback!({ credential: "x.y.z" });
    await transitions[0];
    assert.deepEqual(replaced, []);
  });

  it("토큰은 한 번만 보낸다", async () => {
    actionImpl = () => new Promise(() => {});
    googleCallback!({ credential: "a.b.c" });
    googleCallback!({ credential: "d.e.f" });
    await flush();
    assert.equal(actionCalls.length, 1);
    assert.equal(transitions.length, 1);
  });

  it("빈 토큰·글자가 아닌 토큰은 보내지 않는다", async () => {
    googleCallback!({ credential: "" });
    googleCallback!({ credential: 123 });
    googleCallback!({});
    await flush();
    assert.equal(actionCalls.length, 0);
  });
});
