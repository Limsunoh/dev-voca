/**
 * 시작 화면 시트가 열고 닫히는 길을 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 켠 칸이 다음에 열 때 남지 않는 것은, 닫힘 이벤트가 choice 를 비워 내용을
 * 내리기 때문이다. consent-gate.test.mts 는 체크와 잠금만 보고 닫는 길은
 * 부르지 않으므로 여기서 본다. 그 밖의 대역 방식은 그 파일과 같다.
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { afterEach, beforeEach, describe, it, mock } from "node:test";

const require = createRequire(import.meta.url);
const realReact = require("react") as typeof import("react");
const realJsx = require("react/jsx-runtime");

let slots: Array<{ value: unknown }> = [];
let cursor = 0;
let effects: Array<() => void | (() => void)> = [];

function slot<T>(init: () => T): { value: T } {
  const i = cursor++;
  slots[i] ??= { value: init() };
  return slots[i] as { value: T };
}

mock.module("react", {
  defaultExport: realReact,
  namedExports: {
    ...realReact,
    useState: <T,>(init: T) => {
      const s = slot(() => init);
      return [s.value, (next: T) => void (s.value = next)] as const;
    },
    useRef: <T,>(init: T) => slot(() => ({ current: init })).value,
    useEffect: (fn: () => void) => void effects.push(fn),
  },
});

type Host = { type: string; props: Record<string, unknown> };
let hosts: Host[] = [];

const record =
  (fn: (...args: unknown[]) => unknown) =>
  (type: unknown, props: Record<string, unknown>, key?: unknown) => {
    if (typeof type === "string") hosts.push({ type, props });
    return fn(type, props, key);
  };

mock.module("react/jsx-runtime", {
  namedExports: { ...realJsx, jsx: record(realJsx.jsx), jsxs: record(realJsx.jsxs) },
});

mock.module("@/app/start/actions", {
  namedExports: { continueAsGuestAction: async () => {} },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { createElement } = realReact;
const { StartChoices } = await import("./StartChoices");

const dialog = () => hosts.find((h) => h.type === "dialog")!.props;

/** 브라우저의 dialog 대역. React 를 거치지 않으므로 호출 횟수만 센다. */
let sheet = { open: false, showModal: mock.fn(), close: mock.fn() };
let html = "";

function draw(): void {
  cursor = 0;
  hosts = [];
  effects = [];
  html = renderToStaticMarkup(createElement(StartChoices));
  (dialog().ref as { current: unknown }).current = sheet;
}

const runEffects = () => effects.map((run) => run());

function press(label: string): void {
  const button = hosts.find((h) => h.type === "button" && h.props.children === label);
  assert.ok(button, `${label} 버튼이 없다`);
  (button.props.onClick as () => void)();
  draw();
}

const G = "구글로 시작하기";
const V = "게스트로 둘러보기";

beforeEach(() => {
  slots = [];
  sheet = {
    open: false,
    showModal: mock.fn(() => void (sheet.open = true)),
    close: mock.fn(() => void (sheet.open = false)),
  };
  draw();
});

describe("시트 열기", () => {
  it("누르기 전에는 열지 않는다", () => {
    runEffects();
    assert.equal(sheet.showModal.mock.callCount(), 0);
  });

  it("누르면 내용을 그린 뒤 한 번만 연다", () => {
    press(G);
    assert.match(html, /consent-terms/);

    runEffects();
    runEffects();

    assert.equal(sheet.showModal.mock.callCount(), 1);
  });
});

describe("시트 이름", () => {
  for (const [name, label] of [
    ["구글", G],
    ["게스트", V],
  ] as const) {
    it(`${name}: 화면의 제목을 가리킨다`, () => {
      press(label);

      assert.ok(html.includes(`<h2 id="${dialog()["aria-labelledby"]}"`));
    });
  }
});

describe("열린 직후의 탭", () => {
  let clock = 0;
  let now: { mock: { restore: () => void } };

  beforeEach(() => {
    clock = 1000;
    now = mock.method(performance, "now", () => clock);
    press(G);
    runEffects();
  });

  afterEach(() => now.mock.restore());

  const tap = (timeStamp = clock) => {
    const event = { timeStamp, preventDefault: mock.fn(), stopPropagation: mock.fn() };
    (dialog().onClickCapture as (e: unknown) => void)(event);
    return event;
  };

  it("이중탭의 둘째 탭(399ms 까지)을 버린다", () => {
    clock += 399;

    const event = tap();

    assert.equal(event.preventDefault.mock.callCount(), 1);
    assert.equal(event.stopPropagation.mock.callCount(), 1);
  });

  it("처리가 밀려도 누른 시각으로 잰다", () => {
    const pressed = clock + 150;
    clock += 900;

    assert.equal(tap(pressed).preventDefault.mock.callCount(), 1);
  });

  it("닫고 다시 열면 그때부터 다시 잰다", () => {
    (dialog().onClose as () => void)();
    sheet.open = false;
    draw();
    clock += 10000;
    press(G);
    runEffects();
    clock += 100;

    assert.equal(tap().preventDefault.mock.callCount(), 1);
  });

  it("400ms 부터는 그대로 통과시킨다", () => {
    clock += 400;

    const event = tap();

    assert.equal(event.preventDefault.mock.callCount(), 0);
    assert.equal(event.stopPropagation.mock.callCount(), 0);
  });
});

describe("시트 닫기", () => {
  for (const [name, label] of [
    ["구글", G],
    ["게스트", V],
  ] as const) {
    it(`${name}: 닫힘 이벤트가 오면 체크칸을 내려 다음에 새로 그린다`, () => {
      press(label);
      assert.match(html, /consent-terms/);

      (dialog().onClose as () => void)();
      draw();

      assert.doesNotMatch(html, /type="checkbox"/);
    });
  }

  it("취소는 시트를 닫는다", () => {
    press(G);
    const cancel = hosts.find((h) => h.type === "button" && h.props.children === "취소");

    (cancel?.props.onClick as () => void)();

    assert.equal(sheet.close.mock.callCount(), 1);
  });

  it("바깥(dialog 자신)을 누르면 닫는다", () => {
    press(G);
    const target = {};

    (dialog().onClick as (e: unknown) => void)({ target, currentTarget: target });

    assert.equal(sheet.close.mock.callCount(), 1);
  });

  it("시트 안을 누르면 닫지 않는다", () => {
    press(G);

    (dialog().onClick as (e: unknown) => void)({ target: {}, currentTarget: {} });

    assert.equal(sheet.close.mock.callCount(), 0);
  });

  it("열린 채 화면을 떠나면 닫는다", () => {
    press(G);
    const cleanups = runEffects().filter((c) => typeof c === "function") as Array<() => void>;
    assert.equal(cleanups.length, 1);

    cleanups[0]();

    assert.equal(sheet.close.mock.callCount(), 1);
  });
});
