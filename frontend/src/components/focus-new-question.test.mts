/**
 * 새 문제가 뜰 때 초점을 카드로 옮기는 훅과, 훅이 기대는 QuestionCard 의 모양을 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 결함은 이렇다.
 *
 *   아직 아무것도 안 눌렀는데 옮김   새로고침한 화면에서 초점을 가로챈다
 *   보기 밖 초점을 뺏음             나가기 버튼에 서 있던 사람이 튕겨 나간다
 *   초점을 잃었는데 안 옮김         문제마다 맨 위에서 다시 Tab 을 눌러야 한다
 *   스크롤이 끌려 올라감            보기를 누르려고 내린 화면이 위로 튄다
 *   타이머 재렌더마다 돎            한 판은 시계 때문에 수시로 다시 그려진다
 *
 * DOM 라이브러리 없이 react 의 useRef·useEffect 만 대역으로 바꾸고, document 와
 * navigator 는 훅이 읽는 몫만 작은 가짜로 둔다. 가짜 useEffect 는 진짜처럼 의존성이
 * 바뀐 렌더에서만 돈다. 그래야 "다시 안 돈다" 를 볼 수 있다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

import type { RoundQuestion } from "@/lib/api/rounds";

const realReact = await import("react");

type Effect = () => void;

let slots: unknown[] = [];
let cursor = 0;
let queued: Effect[] = [];
let lastDeps: unknown[] = [];
/** 훅이 불린 횟수. QuestionCard 가 훅 없이 그려지는지 본다. */
let hookCalls = 0;

mock.module("react", {
  defaultExport: realReact.default,
  namedExports: {
    ...realReact,
    useRef<T>(init: T) {
      hookCalls += 1;
      if (cursor >= slots.length) slots.push({ current: init });
      return slots[cursor++];
    },
    useEffect(run: Effect, deps: unknown[]) {
      hookCalls += 1;
      const at = cursor++;
      const before = slots[at] as unknown[] | undefined;
      if (!before || deps.some((dep, i) => !Object.is(dep, before[i]))) queued.push(run);
      slots[at] = deps;
      lastDeps = deps;
    },
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
// use 로 시작하지 않는 이름으로 받는다. 대역 위에서 일반 함수처럼 부르므로 훅 규칙 검사 대상이 아니다.
const { useFocusNewQuestion: callFocusHook } = await import("./useFocusNewQuestion");
const { QuestionCard } = await import("./QuestionCard");

/* ---- 가짜 DOM ---- */

type FakeElement = { matches(selector: string): boolean };

const element = (disabled = false): FakeElement => ({
  // 선택자가 ":disabled" 가 아니면 잠긴 것으로 답하지 않는다.
  matches: (selector) => selector === ":disabled" && disabled,
});

const body = element();
const insideList = element();
const lockedInsideList = element(true);
const outside = element();
const lockedOutside = element(true);

const list = { contains: (node: unknown) => node === insideList || node === lockedInsideList };

let focusCalls: unknown[] = [];

/** 다음 형제로 보기 목록을 가진 카드. */
const card = {
  nextElementSibling: list,
  contains: () => false,
  focus(options: unknown) {
    focusCalls.push(options);
  },
};

type G = { document?: unknown };
const realDocument = (globalThis as G).document;
const realNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");

function setActivation(userActivation: unknown) {
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: userActivation === undefined ? {} : { userActivation },
  });
}

function setFocused(active: unknown) {
  (globalThis as G).document = { body, activeElement: active };
}

after(() => {
  (globalThis as G).document = realDocument;
  if (realNavigator) Object.defineProperty(globalThis, "navigator", realNavigator);
});

beforeEach(() => {
  slots = [];
  queued = [];
  focusCalls = [];
  hookCalls = 0;
  setActivation({ hasBeenActive: true, isActive: false });
  setFocused(body);
});

/** 훅을 한 번 부르고, 카드를 ref 에 붙인 뒤 effect 를 돌린다(React 의 순서). */
function render(question: unknown, error: string, target: unknown = card) {
  cursor = 0;
  queued = [];
  const ref = callFocusHook(question, error) as { current: unknown };
  ref.current = target;
  for (const run of queued) run();
  return ref;
}

/* ---- 훅 ---- */

describe("useFocusNewQuestion 언제 옮기나", () => {
  it("아직 아무것도 안 눌렀으면(hasBeenActive false) 옮기지 않는다", () => {
    setActivation({ hasBeenActive: false, isActive: false });
    render({}, "");
    assert.equal(focusCalls.length, 0);
  });

  it("userActivation 이 없는 브라우저는 옮기지 않는다", () => {
    setActivation(undefined);
    render({}, "");
    assert.equal(focusCalls.length, 0);
  });

  it("지금 활성이 아니어도 한 번이라도 눌렀으면 옮긴다", () => {
    // isActive 는 누른 직후 몇 초만 true 다. 채점 응답을 기다린 뒤에는 false 다.
    setActivation({ hasBeenActive: true, isActive: false });
    render({}, "");
    assert.equal(focusCalls.length, 1);
  });

  for (const [name, active] of [
    ["초점이 body 에 있으면", body],
    ["activeElement 가 null 이면", null],
    ["초점이 보기 목록 안에 있으면", insideList],
    ["보기 목록 안의 잠긴 버튼이면", lockedInsideList],
    ["보기 밖이라도 잠긴 요소면", lockedOutside],
  ] as const) {
    it(`${name} 옮긴다`, () => {
      setFocused(active);
      render({}, "");
      assert.deepEqual(focusCalls, [{ preventScroll: true }]);
    });
  }

  it("보기 밖의 다른 요소에 초점이 있으면 뺏지 않는다", () => {
    setFocused(outside);
    render({}, "");
    assert.equal(focusCalls.length, 0);
  });

  it("보기 밖 요소를 잠겼는지 물을 때 :disabled 로 묻는다", () => {
    const asked: string[] = [];
    setFocused({
      matches(selector: string) {
        asked.push(selector);
        return false;
      },
    });
    render({}, "");
    assert.deepEqual(asked, [":disabled"]);
  });
});

describe("useFocusNewQuestion 의존성", () => {
  it("의존성은 question 과 error 둘이다", () => {
    const question = { id: 1 };
    render(question, "실패");
    assert.equal(lastDeps.length, 2);
    assert.equal(lastDeps[0], question);
    assert.equal(lastDeps[1], "실패");
  });

  it("같은 문제 객체로 다시 그려지면(타이머) 다시 돌지 않는다", () => {
    const question = { id: 1 };
    render(question, "");
    render(question, "");
    render(question, "");
    assert.equal(focusCalls.length, 1);
  });

  it("문제 객체가 바뀌면 다시 돈다", () => {
    render({ id: 1 }, "");
    render({ id: 2 }, "");
    assert.equal(focusCalls.length, 2);
  });

  it("문제가 그대로여도 error 가 바뀌면 다시 돈다", () => {
    const question = { id: 1 };
    render(question, "");
    render(question, "채점하지 못했습니다.");
    assert.equal(focusCalls.length, 2);
  });

  it("돌려주는 ref 는 렌더가 바뀌어도 같은 객체다", () => {
    const question = { id: 1 };
    assert.equal(render(question, ""), render(question, ""));
  });
});

describe("useFocusNewQuestion 카드가 없을 때", () => {
  // 일일공부·복습은 ending 일 때, 일일공부는 익히기를 기다릴 때 카드를 안 그린다.
  for (const [name, active] of [
    ["body", body],
    ["보기 안", insideList],
    ["보기 밖", outside],
    ["잠긴 요소", lockedOutside],
  ] as const) {
    it(`카드가 null 이고 초점이 ${name} 이어도 안 터진다`, () => {
      setFocused(active);
      assert.doesNotThrow(() => render({}, "", null));
    });
  }

  it("다음 형제가 없는 카드면 보기 안으로 치지 않는다", () => {
    const lone = {
      nextElementSibling: null,
      contains: () => false,
      focus(options: unknown) {
        focusCalls.push(options);
      },
    };
    setFocused(outside);
    render({}, "", lone);
    assert.equal(focusCalls.length, 0);
  });
});

/* ---- QuestionCard ---- */

type El = { type: unknown; props: Record<string, unknown> };

const QUESTION: RoundQuestion = {
  kind: "meaning",
  kind_label: "뜻 고르기",
  question: "이 단어의 뜻은?",
  prompt: "rebase",
  choices: [
    { id: 1, text: "기준을 옮기다" },
    { id: 2, text: "합치다" },
  ],
  category: "git",
  category_label: "git",
};

describe("QuestionCard 의 초점 자리", () => {
  const cardRef = { current: null };
  const draw = (ref?: typeof cardRef) =>
    QuestionCard({ question: QUESTION, busy: false, onPick: () => {}, cardRef: ref });

  /** 카드 div 와 그 다음 형제. Fragment 의 자식 둘이다. */
  function parts(ref?: typeof cardRef): [El, El] {
    const tree = draw(ref) as unknown as { props: { children: El[] } };
    assert.equal(tree.props.children.length, 2, "카드와 보기 목록 사이에 다른 것이 끼었다");
    return [tree.props.children[0], tree.props.children[1]];
  }

  it("훅 없이 그려진다", () => {
    // 훅을 쓰면 카드가 클라이언트 전용이 되고, 화면 셋이 부르는 순서가 묶인다.
    draw(cardRef);
    assert.equal(hookCalls, 0);
  });

  it("cardRef 를 안 줘도 그려진다", () => {
    assert.doesNotThrow(() =>
      renderToStaticMarkup(draw() as never),
    );
  });

  it("cardRef 가 카드 div 에 붙는다", () => {
    const [box] = parts(cardRef);
    assert.equal(box.type, "div");
    assert.equal(box.props.ref, cardRef);
  });

  it("카드 바로 다음 형제가 보기 목록 ul 이다", () => {
    // 훅이 nextElementSibling 을 보기 목록으로 읽는다.
    const [, next] = parts(cardRef);
    assert.equal(next.type, "ul");
  });

  it('문제 카드에만 tabindex="-1" 이 있다', () => {
    const html = renderToStaticMarkup(draw(cardRef) as never);
    assert.match(html, /^<div[^>]*tabindex="-1"/);
    assert.equal(html.match(/tabindex=/g)?.length, 1);
  });

  it("초점 링 클래스가 focus-visible 로 걸려 있다", () => {
    const [box] = parts(cardRef);
    const classes = String(box.props.className).split(/\s+/);
    for (const name of [
      "focus-visible:outline",
      "focus-visible:outline-2",
      "focus-visible:outline-offset-2",
      "focus-visible:outline-focus",
    ]) {
      assert.ok(classes.includes(name), `${name} 가 없다`);
    }
    // 마우스로 푸는 사람에게 링이 뜨면 안 된다.
    assert.equal(
      classes.some((name) => name.startsWith("focus:")),
      false,
    );
  });
});
