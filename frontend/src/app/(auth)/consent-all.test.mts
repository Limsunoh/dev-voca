/**
 * "전체 동의" 칸을 깨뜨려 본다. consent-gate.test.mts 가 기본 흐름을 보고,
 * 여기서는 경계와 엇갈린 순서를 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - 처음에는 꺼져 있다. 미리 켜져 있으면 사용자가 하지 않은 동의가 된다.
 *   - 켜면 서버로 가는 숨은 값이 하나씩 다 켰을 때와 똑같다. 전체 동의 칸
 *     자체는 폼 값(name)으로 실리지 않는다.
 *   - 게스트는 두 항목만 켜고 끈다. 공개·해외 항목은 어디에도 나오지 않는다.
 *   - 일부만 켠 상태, 켰다가 하나 끈 상태, 빠르게 여러 번 누른 상태에서도
 *     칸 표시와 버튼 잠금이 어긋나지 않는다.
 *   - 잠긴 버튼의 안내와 포커스 이동은 항목 칸으로 간다(전체 동의 칸이 아니다).
 *   - 시트가 열린 직후(400ms 안)의 탭은 전체 동의 칸에 닿아도 버려진다.
 *   - 로그인 화면과, 버튼을 누르기 전의 시작 화면에는 없다.
 *
 * 하네스는 consent-gate.test.mts 와 같다. react 훅을 대역으로 바꿔 상태를
 * 이어 가고, jsx 런타임을 감싸 그려진 태그의 props 를 모은다. 시트의 열린
 * 시각을 재려고 useRef 도 칸에 담아 그리기 사이에 이어지게 했다.
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { afterEach, beforeEach, describe, it, mock } from "node:test";
import type { ReactElement } from "react";

const require = createRequire(import.meta.url);
const realReact = require("react") as typeof import("react");
const realJsx = require("react/jsx-runtime");

// ---- react 대역 --------------------------------------------------------------

type Slot = { value: unknown };
let slots: Slot[] = [];
let cursor = 0;
let effects: Array<() => void> = [];

function useState<T>(init: T | (() => T)) {
  const i = cursor++;
  if (!slots[i]) {
    slots[i] = { value: typeof init === "function" ? (init as () => T)() : init };
  }
  const slot = slots[i];
  const set = (next: T) => {
    slot.value = next;
  };
  return [slot.value as T, set] as const;
}

function useRef<T>(init: T) {
  const i = cursor++;
  if (!slots[i]) slots[i] = { value: { current: init } };
  return slots[i].value as { current: T };
}

mock.module("react", {
  defaultExport: realReact,
  namedExports: {
    ...realReact,
    useState,
    useRef,
    useActionState: () => [{}, () => {}] as const,
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

async function fakeGuestAction(): Promise<void> {}
Object.assign(fakeGuestAction, {
  $$FORM_ACTION: () => ({ name: undefined, action: "/__guest__", encType: undefined, method: "POST", data: null }),
});

mock.module("@/app/start/actions", {
  namedExports: { continueAsGuestAction: fakeGuestAction },
});

mock.module("next/link", {
  defaultExport: (props: { href: string; children: unknown }) =>
    realReact.createElement("a", { href: props.href }, props.children as never),
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { createElement } = realReact;
const { AuthForm } = await import("@/components/AuthForm");
const { StartChoices } = await import("../start/StartChoices");
const { ConsentSheet, GoogleStep, GuestStep } = await import("./ConsentSheet");

// ---- 도구 --------------------------------------------------------------------

let element: ReactElement;
let html = "";

function draw(): void {
  cursor = 0;
  hosts = [];
  effects = [];
  html = renderToStaticMarkup(element);
}

function mount(el: ReactElement): void {
  slots = [];
  element = el;
  draw();
}

const signup = () => createElement(AuthForm, { mode: "signup", action: async () => ({}) } as never);
const login = () => createElement(AuthForm, { mode: "login", action: async () => ({}) } as never);
const guestStep = () => createElement(GuestStep, { titleId: "t", onCancel: () => {} });
const googleStep = () => createElement(GoogleStep, { titleId: "t", onCancel: () => {} });

const ALL = "consent-all";
const TERMS = "consent-terms";
const DISCLOSURE = "consent-disclosure";
const AGE = "consent-age";
const G_ALL = "guest-consent-all";
const G_TERMS = "guest-consent-terms";
const G_AGE = "guest-consent-age";

const inputs = (id: string) => hosts.filter((h) => h.type === "input" && h.props.id === id);

function box(id: string): Record<string, unknown> {
  const found = inputs(id);
  assert.equal(found.length, 1, `#${id} 체크박스가 하나가 아니다`);
  return found[0].props;
}

function tick(id: string, checked = true): void {
  (box(id).onChange as (e: unknown) => void)({ target: { checked } });
  draw();
}

const checks = (...ids: string[]) => ids.map((id) => box(id).checked);

/** 폼으로 실리는 값 전부. name 이 있는 input 을 모은다(이메일·비밀번호 칸 포함). */
const named = () =>
  hosts.filter((h) => h.type === "input" && h.props.name !== undefined).map((h) => [h.props.name, h.props.value]);

const consentValues = () =>
  named().filter(([n]) => ["terms_agreed", "disclosure_agreed", "age_confirmed"].includes(String(n)));

const submitButton = () =>
  hosts.find((h) => h.type === "button" && h.props.type === "submit" && h.props.children !== "로그인 없이 둘러보기")!
    .props;
const lockedButton = () => hosts.find((h) => h.type === "button" && h.props["aria-disabled"] === "true")?.props;
const googleLinks = () => html.match(/href="\/api\/auth\/google[^"]*"/g) ?? [];

let focused: string[] = [];
const realDocument = (globalThis as { document?: unknown }).document;

beforeEach(() => {
  focused = [];
  (globalThis as { document?: unknown }).document = {
    getElementById: (id: string) => ({ focus: () => void focused.push(id) }),
  };
});

afterEach(() => {
  (globalThis as { document?: unknown }).document = realDocument;
});

// ---- 처음 상태와 폼 값 --------------------------------------------------------

describe("전체 동의: 처음 상태", () => {
  for (const [label, el, all] of [
    ["가입 화면", signup, ALL],
    ["구글 시트", googleStep, ALL],
    ["게스트 시트", guestStep, G_ALL],
  ] as const) {
    it(`${label}: 꺼져 있고 체크박스다`, () => {
      mount(el());
      assert.equal(box(all).checked, false);
      assert.equal(box(all).type, "checkbox");
    });
  }

  it("가입 화면: 전체 동의 칸은 맨 위, 항목들보다 먼저 온다", () => {
    mount(signup());
    const order = hosts.filter((h) => h.type === "input" && String(h.props.id).startsWith("consent-")).map((h) => h.props.id);
    assert.deepEqual(order, [ALL, TERMS, DISCLOSURE, AGE]);
  });
});

describe("전체 동의: 서버로 가는 값", () => {
  it("전체 동의로 켠 값이 하나씩 켠 값과 똑같다", () => {
    mount(signup());
    tick(TERMS);
    tick(DISCLOSURE);
    tick(AGE);
    const oneByOne = named();
    const lockOneByOne = submitButton()["aria-disabled"];
    const linksOneByOne = googleLinks();

    mount(signup());
    tick(ALL);
    assert.deepEqual(named(), oneByOne);
    assert.equal(submitButton()["aria-disabled"], lockOneByOne);
    assert.deepEqual(googleLinks(), linksOneByOne);
    assert.deepEqual(consentValues(), [
      ["terms_agreed", "on"],
      ["disclosure_agreed", "on"],
      ["age_confirmed", "on"],
    ]);
  });

  it("전체 동의 칸 자체는 name 이 없어 폼 값으로 실리지 않는다", () => {
    mount(signup());
    tick(ALL);
    assert.equal(box(ALL).name, undefined);
    assert.ok(!named().some(([n]) => /all/i.test(String(n))), "all 이 들어간 폼 값이 있다");
  });

  it("뒤로 가기로 돌아왔을 때 체크 표시만 되살아나지 않게 autoComplete=off 다", () => {
    mount(signup());
    assert.equal(box(ALL).autoComplete, "off");
  });
});

// ---- 게스트 ------------------------------------------------------------------

describe("전체 동의: 게스트 시트", () => {
  it("켜고 꺼도 공개·해외 항목은 어디에도 나오지 않는다", () => {
    mount(guestStep());
    for (const on of [true, false, true]) {
      tick(G_ALL, on);
      assert.equal(inputs("guest-consent-disclosure").length, 0);
      assert.doesNotMatch(html, /순위표에 이름과 사진이 공개/);
      assert.doesNotMatch(html, /disclosure/);
      assert.doesNotMatch(html, /세 항목/);
    }
  });

  it("켜면 두 항목과 들어가기가 열리고, 끄면 다시 잠긴다", () => {
    mount(guestStep());
    tick(G_ALL);
    assert.deepEqual(checks(G_ALL, G_TERMS, G_AGE), [true, true, true]);
    assert.match(html, /action="\/__guest__"/);
    assert.equal(lockedButton(), undefined);

    tick(G_ALL, false);
    assert.deepEqual(checks(G_ALL, G_TERMS, G_AGE), [false, false, false]);
    assert.doesNotMatch(html, /action="\/__guest__"/);
    assert.ok(lockedButton());
  });

  it("두 항목을 하나씩 켜면 전체 동의도 켜진다(공개·해외를 기다리지 않는다)", () => {
    mount(guestStep());
    tick(G_TERMS);
    assert.equal(box(G_ALL).checked, false);
    tick(G_AGE);
    assert.equal(box(G_ALL).checked, true);
  });

  it("가입 화면에서 연 게스트 시트의 전체 동의는 가입 화면 칸을 건드리지 않는다", () => {
    mount(signup());
    const open = hosts.find((h) => h.type === "button" && h.props.children === "로그인 없이 둘러보기")!;
    (open.props.onClick as () => void)();
    draw();

    tick(G_ALL);
    assert.deepEqual(checks(G_TERMS, G_AGE), [true, true]);
    assert.deepEqual(checks(ALL, TERMS, DISCLOSURE, AGE), [false, false, false, false]);
    assert.deepEqual(consentValues(), []);
    assert.equal(submitButton()["aria-disabled"], true);

    tick(ALL);
    tick(G_ALL, false);
    assert.deepEqual(checks(ALL, TERMS, DISCLOSURE, AGE), [true, true, true, true]);
    assert.deepEqual(checks(G_ALL, G_TERMS, G_AGE), [false, false, false]);
  });
});

// ---- 엇갈린 순서 -------------------------------------------------------------

describe("전체 동의: 일부만 켠 상태", () => {
  for (const [label, first] of [
    ["약관만", TERMS],
    ["공개·해외만", DISCLOSURE],
    ["나이만", AGE],
  ] as const) {
    it(`${label} 켠 상태에서 전체 동의 칸은 꺼져 있고, 누르면 셋 다 켜진다`, () => {
      mount(signup());
      tick(first);
      assert.equal(box(ALL).checked, false);
      assert.equal(submitButton()["aria-disabled"], true);

      tick(ALL);
      assert.deepEqual(checks(ALL, TERMS, DISCLOSURE, AGE), [true, true, true, true]);
      assert.equal(submitButton()["aria-disabled"], undefined);
    });
  }

  it("두 개 켠 상태에서도 칸은 꺼져 있고 잠겨 있다", () => {
    mount(signup());
    tick(TERMS);
    tick(AGE);
    assert.equal(box(ALL).checked, false);
    assert.deepEqual(googleLinks(), []);
    assert.equal(submitButton()["aria-disabled"], true);
  });
});

describe("전체 동의: 켰다가 하나 끄고 다시", () => {
  for (const off of [TERMS, DISCLOSURE, AGE]) {
    it(`${off} 를 끄면 칸이 꺼지고 그 값만 빠지며, 다시 누르면 셋이 돌아온다`, () => {
      mount(signup());
      tick(ALL);
      tick(off, false);

      assert.equal(box(ALL).checked, false);
      assert.equal(submitButton()["aria-disabled"], true);
      assert.deepEqual(googleLinks(), []);
      assert.equal(consentValues().length, 2);
      assert.ok(!consentValues().some(([n]) => String(n).startsWith(off.replace("consent-", ""))));

      tick(ALL);
      assert.deepEqual(checks(ALL, TERMS, DISCLOSURE, AGE), [true, true, true, true]);
      assert.equal(consentValues().length, 3);
    });
  }

  it("하나를 끈 뒤 꺼져 보이는 전체 동의를 누르면 남은 둘이 꺼지지 않고 셋 다 켜진다", () => {
    // 칸 표시가 꺼져 있으므로 브라우저가 보내는 값은 true 다. 꺼져 보이는
    // 칸을 눌렀는데 남은 항목이 꺼지면 사용자는 무엇이 일어났는지 모른다.
    mount(signup());
    tick(ALL);
    tick(AGE, false);
    tick(ALL, !box(ALL).checked);
    assert.deepEqual(checks(TERMS, DISCLOSURE, AGE), [true, true, true]);
  });
});

describe("전체 동의: 빠르게 여러 번 누르기", () => {
  it("켜기·끄기를 번갈아 다섯 번 누르면 마지막(켜기) 상태로 끝난다", () => {
    mount(signup());
    for (let i = 0; i < 5; i++) tick(ALL, !box(ALL).checked);
    assert.deepEqual(checks(ALL, TERMS, DISCLOSURE, AGE), [true, true, true, true]);
    assert.equal(consentValues().length, 3);
  });

  it("여섯 번이면 꺼진 상태로 끝나고 숨은 값이 하나도 남지 않는다", () => {
    mount(signup());
    for (let i = 0; i < 6; i++) tick(ALL, !box(ALL).checked);
    assert.deepEqual(checks(ALL, TERMS, DISCLOSURE, AGE), [false, false, false, false]);
    assert.deepEqual(consentValues(), []);
    assert.ok(lockedButton());
  });

  it("같은 값이 두 번 와도(이벤트 중복) 상태가 뒤집히지 않는다", () => {
    mount(signup());
    tick(ALL, true);
    tick(ALL, true);
    assert.deepEqual(checks(TERMS, DISCLOSURE, AGE), [true, true, true]);
    tick(ALL, false);
    tick(ALL, false);
    assert.deepEqual(checks(TERMS, DISCLOSURE, AGE), [false, false, false]);
  });

  it("그리기 없이 연달아 와도(같은 렌더의 handler 두 번) 마지막 값이 이긴다", () => {
    mount(signup());
    const onChange = box(ALL).onChange as (e: unknown) => void;
    onChange({ target: { checked: true } });
    onChange({ target: { checked: false } });
    draw();
    assert.deepEqual(checks(ALL, TERMS, DISCLOSURE, AGE), [false, false, false, false]);
  });
});

// ---- 잠긴 버튼 안내 ----------------------------------------------------------

describe("전체 동의: 잠긴 버튼의 안내와 포커스", () => {
  const pressSubmit = () => {
    const event = { preventDefault: mock.fn() };
    (submitButton().onClick as (e: unknown) => void)(event);
    assert.equal(event.preventDefault.mock.callCount(), 1, "제출을 막지 않았다");
  };
  const pressGoogle = () => (lockedButton()!.onClick as () => void)();

  for (const [name, press] of [
    ["제출", pressSubmit],
    ["구글", pressGoogle],
  ] as const) {
    it(`${name}: 아무것도 안 켰으면 전체 동의가 아니라 약관 칸으로 간다`, () => {
      mount(signup());
      press();
      draw();
      assert.deepEqual(focused, [TERMS]);
      assert.match(html, /세 항목을 모두 켜 주세요\./);
    });

    it(`${name}: 전체 동의 뒤 공개·해외를 끄면 그 칸으로 간다`, () => {
      mount(signup());
      tick(ALL);
      tick(DISCLOSURE, false);
      press();
      draw();
      assert.deepEqual(focused, [DISCLOSURE]);
      assert.match(html, /세 항목을 모두 켜 주세요\./);
    });

    it(`${name}: 전체 동의를 켰다 끄면 약관 칸으로 간다`, () => {
      mount(signup());
      tick(ALL);
      tick(ALL, false);
      press();
      draw();
      assert.deepEqual(focused, [TERMS]);
    });
  }

  it("안내가 뜬 뒤 전체 동의를 켜면 안내가 사라지고 잠금이 풀린다", () => {
    mount(signup());
    pressSubmit();
    draw();
    assert.match(html, /세 항목을 모두 켜 주세요\./);
    tick(ALL);
    assert.doesNotMatch(html, /항목을 모두 켜 주세요/);
    assert.equal(submitButton()["aria-disabled"], undefined);
    assert.equal(submitButton().onClick, undefined);
  });

  it("게스트: 전체 동의 뒤 나이를 끄면 나이 칸으로 가고 두 항목 안내가 뜬다", () => {
    mount(guestStep());
    tick(G_ALL);
    tick(G_AGE, false);
    (lockedButton()!.onClick as () => void)();
    draw();
    assert.deepEqual(focused, [G_AGE]);
    assert.match(html, /두 항목을 모두 켜 주세요\./);
    assert.doesNotMatch(html, /세 항목을 모두 켜 주세요/);
  });
});

// ---- 시트가 열린 직후의 탭 ---------------------------------------------------

describe("전체 동의: 시트가 열린 직후의 탭", () => {
  const OPENED = 1000;
  let restoreNow: (() => void) | undefined;

  beforeEach(() => {
    const now = mock.method(performance, "now", () => OPENED);
    restoreNow = () => now.mock.restore();
  });
  afterEach(() => restoreNow?.());

  /** 시트를 그리고, 브라우저 대신 dialog 를 붙여 열기 효과를 돌린다. */
  function openSheet(choice: "google" | "guest"): void {
    mount(createElement(ConsentSheet, { choice, onClose: () => {} }));
    const dialog = hosts.find((h) => h.type === "dialog")!;
    const fake = { open: false, showModal: () => void (fake.open = true), close: () => {} };
    (dialog.props.ref as { current: unknown }).current = fake;
    for (const fn of effects) fn();
    draw();
  }

  /**
   * 시트 안의 칸을 누른다. dialog 의 capture 처리기가 먼저 받고, 전파를 막지
   * 않았을 때만 칸의 onChange 까지 내려간다(React 의 캡처 순서와 같다).
   */
  function tapInSheet(id: string, timeStamp: number): { stopped: boolean; prevented: boolean } {
    const event = {
      timeStamp,
      stopped: false,
      prevented: false,
      stopPropagation() {
        this.stopped = true;
      },
      preventDefault() {
        this.prevented = true;
      },
    };
    const dialog = hosts.find((h) => h.type === "dialog")!;
    (dialog.props.onClickCapture as (e: unknown) => void)(event);
    if (!event.stopped) tick(id, !box(id).checked);
    else draw();
    return event;
  }

  const inDialog = (id: string) => {
    const body = html.slice(html.indexOf("<dialog"), html.indexOf("</dialog>"));
    return body.includes(`id="${id}"`);
  };

  for (const [choice, all, items] of [
    ["google", ALL, [TERMS, DISCLOSURE, AGE]],
    ["guest", G_ALL, [G_TERMS, G_AGE]],
  ] as const) {
    it(`${choice}: 전체 동의 칸이 dialog 안에 있다(가드가 덮는 자리)`, () => {
      openSheet(choice);
      assert.ok(inDialog(all), "전체 동의 칸이 dialog 밖에 있다");
    });

    for (const dt of [0, 1, 399]) {
      it(`${choice}: 열린 지 ${dt}ms 에 전체 동의를 누르면 버려지고 아무것도 안 켜진다`, () => {
        openSheet(choice);
        const event = tapInSheet(all, OPENED + dt);
        assert.ok(event.stopped && event.prevented, "탭을 막지 않았다");
        assert.deepEqual(checks(all, ...items), [false, ...items.map(() => false)]);
        assert.deepEqual(googleLinks(), []);
        assert.doesNotMatch(html, /action="\/__guest__"/);
      });
    }

    it(`${choice}: 400ms 가 지나면 전체 동의가 먹는다`, () => {
      openSheet(choice);
      const event = tapInSheet(all, OPENED + 400);
      assert.ok(!event.stopped && !event.prevented);
      assert.deepEqual(checks(all, ...items), [true, ...items.map(() => true)]);
    });
  }

  it("열린 직후 막힌 탭 뒤 정상 탭 한 번이면 켜진다(막힌 탭이 상태를 남기지 않는다)", () => {
    openSheet("google");
    tapInSheet(ALL, OPENED + 50);
    tapInSheet(ALL, OPENED + 800);
    assert.deepEqual(checks(ALL, TERMS, DISCLOSURE, AGE), [true, true, true, true]);
    assert.equal(googleLinks().length, 1);
  });
});

// ---- 없어야 하는 곳 ----------------------------------------------------------

describe("전체 동의: 없어야 하는 곳", () => {
  it("로그인 화면에는 없다(낭독기 설명도 없다)", () => {
    mount(login());
    assert.equal(inputs(ALL).length, 0);
    assert.equal(inputs(G_ALL).length, 0);
    assert.doesNotMatch(html, /전체 동의/);
  });

  it("로그인 화면에서 게스트 시트를 열면 게스트 전체 동의만 생긴다", () => {
    mount(login());
    const open = hosts.find((h) => h.type === "button" && h.props.children === "로그인 없이 둘러보기")!;
    (open.props.onClick as () => void)();
    draw();
    assert.equal(inputs(ALL).length, 0);
    assert.equal(inputs(G_ALL).length, 1);
    assert.match(html, /아래 필수 두 항목에 모두 동의/);
  });

  it("시작 화면은 버튼을 누르기 전에는 없다", () => {
    mount(createElement(StartChoices));
    assert.equal(inputs(ALL).length, 0);
    assert.equal(inputs(G_ALL).length, 0);
  });
});

// ---- 화면 낭독기 -------------------------------------------------------------

describe("전체 동의: 화면 낭독기 설명", () => {
  it("설명은 sr-only 안에 있고 칸의 label 안에 들어 있다", () => {
    mount(signup());
    const label = html.match(/<label[^>]*>(?:(?!<\/label>)[\s\S])*id="consent-all"(?:(?!<\/label>)[\s\S])*<\/label>/)?.[0] ?? "";
    assert.match(label, /전체 동의/);
    assert.match(label, /<span class="sr-only"> \(아래 필수 세 항목에 모두 동의\)<\/span>/);
  });

  it("구글 시트는 세, 게스트 시트는 두 항목이라고 읽는다", () => {
    mount(googleStep());
    assert.match(html, /아래 필수 세 항목에 모두 동의/);
    mount(guestStep());
    assert.match(html, /아래 필수 두 항목에 모두 동의/);
    assert.doesNotMatch(html, /아래 필수 세 항목/);
  });
});
