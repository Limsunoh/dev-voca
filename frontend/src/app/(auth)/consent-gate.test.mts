/**
 * 가입 동의 체크박스가 가입·구글 버튼을 잠그고 풀어 주는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - 처음에는 모두 꺼져 있고, 셋 다 켜야 잠금이 풀린다.
 *   - 잠긴 버튼을 누르면 제출·이동 없이 "세 항목을 모두 켜 주세요." 를 보여 주고
 *     아직 안 켠 칸으로 포커스를 옮긴다.
 *   - /login 에는 체크가 없다. 구글 링크에도 consent 가 붙지 않는다.
 *   - 시작 화면은 버튼을 누르기 전에는 체크가 없고, 게스트는 두 항목만 묻는다.
 *   - 제출에 실패하면 포커스가 오류 문구로 간다.
 *
 * 브라우저 없이 상태를 이어 가는 방법은 profile-cards-state.test.mts 와 같다.
 * react 의 useState·useActionState·useEffect 를 대역으로 바꾸고, jsx 런타임을
 * 감싸 그려진 태그의 props 를 모아 그 onChange·onClick 을 직접 부른다.
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
let actionState: unknown = {};
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

mock.module("react", {
  defaultExport: realReact,
  namedExports: {
    ...realReact,
    useState,
    useActionState: () => [actionState, () => {}] as const,
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

// 훅 칸이 호출 순서로 매겨지므로, useState 를 쓸 수 있는 next/link 는 단순한
// 링크로 바꾼다. 여기서 볼 것은 주소뿐이다.
mock.module("next/link", {
  defaultExport: (props: { href: string; children: unknown }) =>
    realReact.createElement("a", { href: props.href }, props.children as never),
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { createElement } = realReact;
const { AuthForm } = await import("@/components/AuthForm");
const { GoogleStep, GuestStep, StartChoices } = await import("../start/StartChoices");

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
  actionState = {};
  element = el;
  draw();
}

const signup = (props: Record<string, unknown> = {}) =>
  createElement(AuthForm, { mode: "signup", action: async () => ({}), ...props } as never);
const login = (props: Record<string, unknown> = {}) =>
  createElement(AuthForm, { mode: "login", action: async () => ({}), ...props } as never);

const TERMS = "consent-terms";
const DISCLOSURE = "consent-disclosure";
const AGE = "consent-age";

function box(id: string): Record<string, unknown> {
  const found = hosts.filter((h) => h.type === "input" && h.props.id === id);
  assert.equal(found.length, 1, `#${id} 체크박스가 하나가 아니다`);
  return found[0].props;
}

function tick(id: string, checked = true): void {
  (box(id).onChange as (e: unknown) => void)({ target: { checked } });
  draw();
}

/** 구글 버튼 자리. 잠겼으면 button, 풀렸으면 href 가 있는 a. */
function googleLock(): Record<string, unknown> | undefined {
  return hosts.find((h) => h.type === "button" && h.props["aria-disabled"] === "true")?.props;
}

function submitButton(): Record<string, unknown> {
  const found = hosts.filter(
    (h) => h.type === "button" && h.props.type === "submit" && h.props.children !== "로그인 없이 둘러보기",
  );
  assert.equal(found.length, 1, "제출 버튼이 하나가 아니다");
  return found[0].props;
}

const googleLinks = (markup: string) => markup.match(/href="\/api\/auth\/google[^"]*"/g) ?? [];
const hiddenConsent = () =>
  hosts
    .filter((h) => h.type === "input" && h.props.type === "hidden" && String(h.props.name).endsWith("ed"))
    .map((h) => [h.props.name, h.props.value]);

const GUIDE = "세 항목을 모두 켜 주세요.";

/** document.getElementById 대역. 어느 칸으로 포커스를 옮겼는지 남긴다. */
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

// ---- 가입 화면 ----------------------------------------------------------------

describe("가입 화면: 처음 상태", () => {
  beforeEach(() => mount(signup()));

  it("세 칸 모두 꺼져 있다", () => {
    assert.equal(box(TERMS).checked, false);
    assert.equal(box(DISCLOSURE).checked, false);
    assert.equal(box(AGE).checked, false);
    assert.equal(box(TERMS).type, "checkbox");
  });

  it("구글은 링크가 아니라 잠긴 버튼이다", () => {
    assert.deepEqual(googleLinks(html), []);
    assert.ok(googleLock(), "aria-disabled 버튼이 없다");
    assert.equal(googleLock()?.disabled, undefined);
  });

  it("제출 버튼은 잠겼지만 disabled 는 아니다(눌러야 이유를 안다)", () => {
    assert.equal(submitButton()["aria-disabled"], true);
    assert.equal(submitButton().disabled, false);
  });

  it("동의 값을 실은 숨은 칸이 없다", () => {
    assert.deepEqual(hiddenConsent(), []);
  });

  it("안내 문구는 아직 없다", () => {
    assert.doesNotMatch(html, new RegExp(GUIDE));
  });

  it("문서 링크는 새 탭으로 연다", () => {
    assert.match(html, /<a href="\/terms" target="_blank" rel="noreferrer"/);
    assert.match(html, /<a href="\/privacy" target="_blank" rel="noreferrer"/);
  });
});

for (const [label, id, hidden] of [
  ["약관만", TERMS, [["terms_agreed", "on"]]],
  ["공개·해외만", DISCLOSURE, [["disclosure_agreed", "on"]]],
  ["나이만", AGE, [["age_confirmed", "on"]]],
] as const) {
  describe(`가입 화면: ${label} 켠 경우`, () => {
    beforeEach(() => {
      mount(signup());
      tick(id);
    });

    it("구글·제출 모두 잠겨 있다", () => {
      assert.deepEqual(googleLinks(html), []);
      assert.ok(googleLock());
      assert.equal(submitButton()["aria-disabled"], true);
    });

    it("켠 칸의 값만 숨은 칸으로 실린다", () => {
      assert.deepEqual(hiddenConsent(), hidden);
    });
  });
}

describe("가입 화면: 셋 다 켠 경우", () => {
  beforeEach(() => {
    mount(signup());
    tick(TERMS);
    tick(DISCLOSURE);
    tick(AGE);
  });

  it("구글이 consent=1 링크가 된다", () => {
    assert.deepEqual(googleLinks(html), ['href="/api/auth/google?consent=1"']);
    assert.equal(googleLock(), undefined);
  });

  it("제출 잠금이 풀린다", () => {
    assert.equal(submitButton()["aria-disabled"], undefined);
    assert.equal(submitButton().onClick, undefined);
  });

  it("세 값이 숨은 칸으로 실린다", () => {
    assert.deepEqual(hiddenConsent(), [
      ["terms_agreed", "on"],
      ["disclosure_agreed", "on"],
      ["age_confirmed", "on"],
    ]);
  });

  it("하나를 끄면 다시 잠긴다", () => {
    tick(AGE, false);

    assert.deepEqual(googleLinks(html), []);
    assert.ok(googleLock());
    assert.equal(submitButton()["aria-disabled"], true);
    assert.deepEqual(hiddenConsent(), [
      ["terms_agreed", "on"],
      ["disclosure_agreed", "on"],
    ]);
  });

  it("돌아갈 곳이 있으면 구글 링크에 같이 싣는다", () => {
    mount(signup({ next: "/board" }));
    tick(TERMS);
    tick(DISCLOSURE);
    tick(AGE);

    assert.deepEqual(googleLinks(html), ['href="/api/auth/google?consent=1&amp;next=%2Fboard"']);
  });
});

describe("가입 화면: 잠긴 버튼을 눌렀을 때", () => {
  const presses = {
    제출: () => {
      const event = { preventDefault: mock.fn() };
      (submitButton().onClick as (e: unknown) => void)(event);
      assert.equal(event.preventDefault.mock.callCount(), 1, "제출을 막지 않았다");
    },
    구글: () => (googleLock()?.onClick as () => void)(),
  };

  for (const [name, press] of Object.entries(presses)) {
    it(`${name}: 아무것도 안 켰으면 약관 칸으로 포커스를 옮기고 안내를 띄운다`, () => {
      mount(signup());

      press();
      draw();

      assert.deepEqual(focused, [TERMS]);
      assert.match(html, new RegExp(GUIDE));
    });

    it(`${name}: 약관만 켰으면 공개·해외 칸으로 포커스를 옮긴다`, () => {
      mount(signup());
      tick(TERMS);

      press();
      draw();

      assert.deepEqual(focused, [DISCLOSURE]);
      assert.match(html, new RegExp(GUIDE));
    });

    it(`${name}: 약관과 공개·해외를 켰으면 나이 칸으로 포커스를 옮긴다`, () => {
      mount(signup());
      tick(TERMS);
      tick(DISCLOSURE);

      press();
      draw();

      assert.deepEqual(focused, [AGE]);
      assert.match(html, new RegExp(GUIDE));
    });

    it(`${name}: 나이만 켰으면 약관 칸으로 포커스를 옮긴다`, () => {
      mount(signup());
      tick(AGE);

      press();
      draw();

      assert.deepEqual(focused, [TERMS]);
    });

    it(`${name}: 셋 다 켜면 안내가 사라진다`, () => {
      mount(signup());
      press();
      draw();

      tick(TERMS);
      tick(DISCLOSURE);
      tick(AGE);

      assert.doesNotMatch(html, new RegExp(GUIDE));
    });
  }
});

describe("가입 화면: 구글에서 되돌아온 안내", () => {
  const NOTICE = "처음 오셨습니다. 아래 세 항목을 확인한 뒤 구글 버튼을 다시";

  it("consentRequired 면 안내를 보여 준다", () => {
    mount(signup({ consentRequired: true }));
    assert.match(html, new RegExp(NOTICE));
  });

  it("보통 가입에는 안 보인다", () => {
    mount(signup());
    assert.doesNotMatch(html, new RegExp(NOTICE));
  });
});

describe("구글 이름·사진 안내", () => {
  const NOTE = /순위표에 오르면 구글 이름과 사진이 보입니다\. 내정보에서 이름이나 아바타를\s+바꿀 수 있습니다\./;

  it("가입 화면에 있다", () => {
    mount(signup());
    assert.match(html, NOTE);
  });

  it("시작 화면에 있다", () => {
    mount(createElement(GoogleStep, { titleId: "t", onCancel: () => {} }));
    assert.match(html, NOTE);
  });
});

// ---- 로그인 화면 --------------------------------------------------------------

describe("로그인 화면", () => {
  it("체크박스가 없고 구글은 바로 눌린다", () => {
    mount(login());

    assert.doesNotMatch(html, /type="checkbox"/);
    assert.deepEqual(googleLinks(html), ['href="/api/auth/google"']);
    assert.equal(googleLock(), undefined);
    assert.equal(submitButton()["aria-disabled"], undefined);
  });

  it("돌아갈 곳이 있어도 consent 는 붙지 않는다", () => {
    mount(login({ next: "/board" }));

    assert.deepEqual(googleLinks(html), ['href="/api/auth/google?next=%2Fboard"']);
  });
});

// ---- 시작 화면 ----------------------------------------------------------------

describe("시작 화면: 구글로 시작하기", () => {
  beforeEach(() => mount(createElement(GoogleStep, { titleId: "t", onCancel: () => {} })));

  it("처음에는 잠긴 버튼이다", () => {
    assert.equal(box(TERMS).checked, false);
    assert.equal(box(DISCLOSURE).checked, false);
    assert.equal(box(AGE).checked, false);
    assert.deepEqual(googleLinks(html), []);
    assert.ok(googleLock());
  });

  for (const [label, id] of [
    ["약관만", TERMS],
    ["공개·해외만", DISCLOSURE],
    ["나이만", AGE],
  ] as const) {
    it(`${label} 켜면 아직 잠겨 있다`, () => {
      tick(id);

      assert.deepEqual(googleLinks(html), []);
      assert.ok(googleLock());
    });
  }

  it("셋 다 켜면 consent=1 링크가 된다", () => {
    tick(TERMS);
    tick(DISCLOSURE);
    tick(AGE);

    assert.deepEqual(googleLinks(html), ['href="/api/auth/google?consent=1"']);
    assert.equal(googleLock(), undefined);
  });

  it("잠긴 버튼을 누르면 이동 없이 안내하고 안 켠 칸으로 포커스를 옮긴다", () => {
    tick(TERMS);

    (googleLock()?.onClick as () => void)();
    draw();

    assert.deepEqual(focused, [DISCLOSURE]);
    assert.match(html, new RegExp(GUIDE));
    assert.deepEqual(googleLinks(html), []);
  });
});

describe("시작 화면: 버튼을 누르기 전", () => {
  const press = (label: string) => {
    const button = hosts.find((h) => h.type === "button" && h.props.children === label);
    assert.ok(button, `${label} 버튼이 없다`);
    (button.props.onClick as () => void)();
    draw();
  };

  beforeEach(() => mount(createElement(StartChoices)));

  it("체크박스도 구글 링크도 없다", () => {
    assert.doesNotMatch(html, /type="checkbox"/);
    assert.deepEqual(googleLinks(html), []);
  });

  it("구글을 누르면 세 항목이 나온다", () => {
    press("구글로 시작하기");

    assert.equal(box(TERMS).checked, false);
    assert.equal(box(DISCLOSURE).checked, false);
    assert.equal(box(AGE).checked, false);
  });

  it("게스트를 누르면 공개·해외 항목 없이 두 항목이 나온다", () => {
    press("게스트로 둘러보기");

    assert.equal(box(TERMS).checked, false);
    assert.equal(box(AGE).checked, false);
    assert.doesNotMatch(html, new RegExp(DISCLOSURE));
  });
});

describe("시작 화면: 게스트로 둘러보기", () => {
  const GUEST_FORM = /action="\/__guest__"/;

  beforeEach(() => mount(createElement(GuestStep, { titleId: "t", onCancel: () => {} })));

  it("처음에는 잠겨 있어 들어갈 수 없다", () => {
    assert.doesNotMatch(html, GUEST_FORM);
    assert.ok(googleLock());
  });

  for (const [label, id] of [
    ["약관만", TERMS],
    ["나이만", AGE],
  ] as const) {
    it(`${label} 켜면 아직 잠겨 있다`, () => {
      tick(id);

      assert.doesNotMatch(html, GUEST_FORM);
    });
  }

  it("둘 다 켜면 들어갈 수 있다", () => {
    tick(TERMS);
    tick(AGE);

    assert.match(html, GUEST_FORM);
    assert.equal(googleLock(), undefined);
  });

  it("잠긴 버튼을 누르면 두 항목을 안내하고 안 켠 칸으로 포커스를 옮긴다", () => {
    tick(TERMS);

    (googleLock()?.onClick as () => void)();
    draw();

    assert.deepEqual(focused, [AGE]);
    assert.match(html, /두 항목을 모두 켜 주세요\./);
  });
});

// ---- 제출 실패 뒤 포커스 --------------------------------------------------------

describe("제출 실패 뒤 포커스", () => {
  for (const [name, make] of [
    ["로그인", login],
    ["가입", signup],
  ] as const) {
    it(`${name}: 오류 문구로 포커스가 간다`, () => {
      mount(make());
      actionState = { error: "비밀번호가 틀렸습니다." };
      draw();

      const alert = hosts.find((h) => h.type === "p" && h.props.role === "alert");
      assert.ok(alert, "오류 문구가 없다");
      assert.equal(alert.props.tabIndex, -1);
      const focus = mock.fn();
      (alert.props.ref as { current: unknown }).current = { focus };

      for (const run of effects) run();

      assert.equal(focus.mock.callCount(), 1);
    });
  }

  it("오류가 없으면 포커스를 옮기지 않는다", () => {
    mount(login());
    for (const run of effects) run();

    assert.deepEqual(focused, []);
    assert.equal(hosts.find((h) => h.type === "p" && h.props.role === "alert"), undefined);
  });
});

// ---- 입력칸 테두리 ------------------------------------------------------------

describe("입력칸 테두리", () => {
  for (const name of ["email", "password"]) {
    it(`${name} 칸에 1px 테두리가 있다`, () => {
      mount(login());

      const input = hosts.find((h) => h.type === "input" && h.props.name === name);
      assert.equal((input?.props.style as { border: string }).border, "1px solid var(--text-muted)");
    });
  }
});
