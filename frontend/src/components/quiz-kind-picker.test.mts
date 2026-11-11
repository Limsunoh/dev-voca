/**
 * 문제풀기(QuizBoard)의 유형 고르개가 다음 요청에 실제로 실리는지,
 * 언제 곧바로 새 문제를 받고 언제 다음 문제까지 미루는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 결함 넷이다.
 *
 *   유형이 안 실림        고르개는 바뀌는데 요청에 kind 가 빠져 계속 섞여 나온다
 *   해설 도중 문제 교체   답한 뒤 유형을 바꿨는데 곧바로 새 문제를 받아, 읽던
 *                        해설이 사라진다
 *   고르개가 사라짐       "가져오는 중"·안내 가지에서 고르개가 없어져, 유형을
 *                        바꾸라는 안내를 보고도 바꿀 곳이 없다
 *   안내가 유형을 모름    유형 하나로 바닥난 것을 "분류를 넓히라" 로만 말한다
 *
 * 전부 눈으로는 "고르개가 잘 바뀐다" 로 보여서 화면만 봐서는 안 잡힌다.
 * quiz-board-item.test.mts 와 같은 방식으로 react 의 훅 넷만 대역으로 바꾸고
 * QuizBoard 를 함수로 부른다. 돌려받은 트리에서 KindPicker 의 onChange·보기
 * 버튼의 onClick 을 꺼내 진짜로 불러 사용자의 동작을 흉내 낸다. 클로저는
 * 그린 시점의 값을 잡으므로, 상태가 바뀌면 다시 그린 뒤 꺼낸다(React 도 그렇다).
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

const realReact = await import("react");

type Slot = { value: unknown };
type Effect = { run: () => void | (() => void); deps?: unknown[] };

let slots: Slot[] = [];
let cursor = 0;
let effects: Effect[] = [];

function slot<T>(init: () => T): Slot {
  if (cursor >= slots.length) slots.push({ value: init() });
  return slots[cursor++];
}

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
    useCallback<T>(fn: T) {
      return fn;
    },
    useEffect(run: Effect["run"], deps?: unknown[]) {
      effects.push({ run, deps });
    },
  },
});

const { QuizBoard } = await import("./QuizBoard");
const { renderToStaticMarkup } = await import("react-dom/server");

type Props = Parameters<typeof QuizBoard>[0];
type El = { type: unknown; props: Record<string, unknown> };

/* ---- 대역 ---- */

const realFetch = globalThis.fetch;
const realWindow = (globalThis as { window?: unknown }).window;
after(() => {
  globalThis.fetch = realFetch;
  (globalThis as { window?: unknown }).window = realWindow;
});

/** 문제 요청의 쿼리. 채점(POST)은 세지 않는다. */
let requested: URLSearchParams[] = [];
/** 문제 요청에 차례로 돌려줄 상태 코드. 비면 200. */
let statuses: number[] = [];
/** 채점에 차례로 돌려줄 정답 여부. 비면 맞음. */
let grades: boolean[] = [];

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
    { id: 14, text: "c" },
    { id: 15, text: "d" },
  ],
  token: "t",
};

beforeEach(() => {
  slots = [];
  requested = [];
  statuses = [];
  grades = [];
  (globalThis as { window?: unknown }).window = { scrollTo() {}, innerWidth: 390 };
  globalThis.fetch = (async (input: string | URL, init?: RequestInit) => {
    if (init?.method === "POST") {
      const correct = grades.shift() ?? true;
      return {
        ok: true,
        status: 200,
        json: async () => ({ correct, answer_id: 12 }),
      } as Response;
    }
    requested.push(new URL(String(input), "http://localhost").searchParams);
    const status = statuses.shift() ?? 200;
    return {
      ok: status < 400,
      status,
      json: async () => (status < 400 ? QUESTION : { detail: "x" }),
    } as Response;
  }) as typeof fetch;
});

/* ---- 도구 ---- */

/** 한 번 그린다. 훅 칸은 이어 쓰고 effect 는 새로 모은다. */
function render(props: Props): El {
  cursor = 0;
  effects = [];
  return QuizBoard(props) as unknown as El;
}

/** 응답을 기다린다. fetch -> json 두 번이다. */
async function settle() {
  for (let i = 0; i < 5; i++) await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
}

/** 첫 문제를 받은 판. */
async function start(props: Props): Promise<void> {
  render(props);
  const load = effects.filter((e) => e.deps?.length === 1 && typeof e.deps[0] === "function");
  assert.equal(load.length, 1, "첫 문제를 부르는 effect 를 못 찾았다");
  load[0].run();
  await settle();
}

/** 트리에서 조건에 맞는 요소를 모두. 함수 컴포넌트 안으로는 안 들어간다. */
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

/** 유형 고르개. 한 판에 하나다. */
function picker(tree: El): El {
  const found = findAll(tree, named("KindPicker"));
  assert.equal(found.length, 1, "유형 고르개가 하나여야 한다");
  return found[0];
}

/** 유형을 바꾼다. 사용자가 메뉴에서 고른 것과 같다. */
async function choose(props: Props, next: string) {
  const onChange = picker(render(props)).props.onChange as (v: string) => void;
  onChange(next);
  await settle();
}

/** 첫 보기를 고르고 채점을 기다린다. */
async function answer(props: Props) {
  const choices = findAll(render(props), named("ChoiceButton"));
  assert.ok(choices.length > 0, "보기가 없다 - 문제를 못 받았다");
  (choices[0].props.onClick as () => void)();
  await settle();
}

/** "다음 문제" 를 누른다. */
async function next(props: Props) {
  const button = findAll(
    render(props),
    (el) => el.type === "button" && el.props.children === "다음 문제",
  );
  assert.equal(button.length, 1, "다음 문제 버튼이 없다");
  (button[0].props.onClick as () => void)();
  await settle();
}

/** 판 전체를 HTML 로. */
function html(props: Props): string {
  const tree = render(props);
  // 고르개의 훅 칸이 판의 칸을 덮지 않게 뒤에 붙인다.
  cursor = slots.length;
  return renderToStaticMarkup(tree as never);
}

/** 유형 고르개만 따로 그린다. 훅 칸은 판 뒤에 붙인다. */
function mountPicker(props: Props): () => El {
  const el = picker(render(props));
  const base = slots.length;
  return () => {
    cursor = base;
    return (el.type as (p: unknown) => El)(el.props);
  };
}

const trigger = (tree: El) => findAll(tree, (el) => el.type === "button")[0];

function menuItems(tree: El): El[] {
  const [menu] = findAll(tree, (el) => el.props.role === "group");
  return menu ? findAll(menu, (el) => el.type === "button") : [];
}

function openMenu(draw: () => El): El {
  (trigger(draw()).props.onClick as () => void)();
  return draw();
}

const itemText = (el: El) => (el.props.children as unknown[])[0] as string;

/** 메뉴의 항목 이름과 고른 항목. */
function menu(props: Props): { labels: string[]; selected: string | undefined } {
  const all = menuItems(openMenu(mountPicker(props)));
  return {
    labels: all.map(itemText),
    selected: all.filter((el) => el.props["aria-current"]).map(itemText)[0],
  };
}

const kinds = () => requested.map((q) => q.get("kind"));

/* ---- 테스트 ---- */

const WORDS: Props = { content: "words" };
const SENTENCES: Props = { content: "sentences" };

describe("유형 고르개 - 요청", () => {
  it("기본은 섞어서다 - 첫 요청에 kind 가 없다", async () => {
    await start(WORDS);
    assert.deepEqual(kinds(), [null]);
    const page = html(WORDS);
    assert.deepEqual(menu(WORDS), {
      labels: ["섞어서", "뜻 고르기", "단어 고르기", "설명 보고 맞히기"],
      selected: "섞어서",
    });
    assert.match(page, />섞어서<\/span>/, "알약에 섞어서가 보여야 한다");
  });

  it("답하기 전에 바꾸면 곧바로 그 유형으로 새로 받는다", async () => {
    await start(WORDS);
    await choose(WORDS, "term");
    assert.deepEqual(kinds(), [null, "term"]);
    assert.match(html(WORDS), />단어 고르기<\/span>/, "알약이 고른 유형을 보여야 한다");
    assert.equal(menu(WORDS).selected, "단어 고르기");
  });

  it("섞어서로 되돌리면 kind 가 빠진다(빈 값도 싣지 않는다)", async () => {
    await start(WORDS);
    await choose(WORDS, "description");
    await choose(WORDS, "");
    assert.deepEqual(kinds(), [null, "description", null]);
    assert.equal(requested[2].has("kind"), false, "kind= 빈 값이 실리면 안 된다");
  });

  it("답한 뒤에 바꾸면 곧바로 받지 않고 다음 문제부터 싣는다", async () => {
    await start(WORDS);
    await answer(WORDS);
    await choose(WORDS, "description");
    assert.equal(requested.length, 1, "해설을 읽는 도중에 새 문제를 받으면 안 된다");
    // 해설과 다음 문제 버튼이 그대로 남아 있다.
    assert.match(html(WORDS), /다음 문제/);

    await next(WORDS);
    assert.deepEqual(kinds(), [null, "description"]);
  });

  it("고른 유형은 그 뒤 모든 요청에 계속 실린다", async () => {
    await start(WORDS);
    await choose(WORDS, "meaning");
    for (let i = 0; i < 3; i++) {
      await answer(WORDS);
      await next(WORDS);
    }
    assert.deepEqual(kinds(), [null, "meaning", "meaning", "meaning", "meaning"]);
  });

  it("문제를 받는 도중에 바꾸면 그 요청이 끝난 뒤 새 유형으로 한 번 더 받는다", async () => {
    // 첫 요청을 붙잡아 둔다. 그 사이 load 가 겹치는 요청을 막는다.
    let release!: () => void;
    const held = new Promise<void>((r) => (release = r));
    const realStub = globalThis.fetch;
    globalThis.fetch = (async (input: string | URL, init?: RequestInit) => {
      if (!init?.method && requested.length === 0) {
        requested.push(new URL(String(input), "http://localhost").searchParams);
        await held;
        return { ok: true, status: 200, json: async () => QUESTION } as Response;
      }
      return realStub(input, init);
    }) as typeof fetch;

    render(WORDS);
    effects.find((e) => e.deps?.length === 1 && typeof e.deps[0] === "function")!.run();
    await choose(WORDS, "term");
    assert.equal(requested.length, 1, "겹치는 요청이 나가면 안 된다");
    release();
    await settle();

    // 요청이 끝나면 load 가 유형이 바뀐 것을 보고 그 자리에서 한 번 더 받는다.
    // 답하지 않아도 고른 유형의 문제가 떠야 한다. 안 그러면 고르개는 "단어
    // 고르기" 인데 화면은 섞어서로 받은 문제다.
    assert.deepEqual(kinds(), [null, "term"]);
  });

  it("?item= 문제를 받는 도중에 유형을 바꾸면 같은 항목을 새 유형으로 다시 받는다", async () => {
    // 상세의 "이 단어로 문제 풀기" 로 왔다. 첫 문제를 받는 도중에 유형만
    // 바꿨는데 다른 단어가 나오면 온 이유가 사라진다.
    let release!: () => void;
    const held = new Promise<void>((r) => (release = r));
    const realStub = globalThis.fetch;
    globalThis.fetch = (async (input: string | URL, init?: RequestInit) => {
      if (!init?.method && requested.length === 0) {
        requested.push(new URL(String(input), "http://localhost").searchParams);
        await held;
        return { ok: true, status: 200, json: async () => QUESTION } as Response;
      }
      return realStub(input, init);
    }) as typeof fetch;

    const ITEM: Props = { content: "words", item: "7" };
    render(ITEM);
    effects.find((e) => e.deps?.length === 1 && typeof e.deps[0] === "function")!.run();
    await choose(ITEM, "term");
    release();
    await settle();

    assert.deepEqual(
      requested.map((q) => [q.get("item"), q.get("kind")]),
      [
        ["7", null],
        ["7", "term"],
      ],
    );
  });

  it("문장 화면은 빈칸·상황만 고를 수 있고 content 와 함께 싣는다", async () => {
    await start(SENTENCES);
    assert.deepEqual(menu(SENTENCES).labels, ["섞어서", "빈칸 채우기", "상황 고르기"]);
    await choose(SENTENCES, "situation");
    assert.equal(requested[1].get("kind"), "situation");
    assert.equal(requested[1].get("content"), "sentences");
  });

  it("분류와 유형을 함께 싣는다", async () => {
    const props: Props = { content: "words", category: "git" };
    await start(props);
    await choose(props, "term");
    assert.deepEqual(
      [requested[1].get("category"), requested[1].get("kind")],
      ["git", "term"],
    );
  });
});

describe("유형 고르개 - 메뉴", () => {
  it("브라우저 기본 select 를 쓰지 않는다", async () => {
    await start(WORDS);
    assert.doesNotMatch(html(WORDS), /<select/);
  });

  it("분류 고르개와 같은 버튼·메뉴·항목 모양을 쓴다", async () => {
    const shared = await import("./PickerMenu");
    await start(WORDS);
    const tree = openMenu(mountPicker(WORDS));
    assert.equal(trigger(tree).props.className, shared.PICKER_BUTTON_CLASS);
    assert.equal(trigger(tree).props.style, shared.PICKER_BUTTON_STYLE);
    const [panel] = findAll(tree, (el) => el.props.role === "group");
    assert.equal(panel.props.className, shared.PICKER_MENU_CLASS);
    assert.ok(String(menuItems(tree)[0].props.className).startsWith(shared.PICKER_ITEM_CLASS));
  });

  it("처음에는 닫혀 있고, 누르면 열린다", async () => {
    await start(WORDS);
    const draw = mountPicker(WORDS);
    assert.equal(menuItems(draw()).length, 0);
    assert.equal(menuItems(openMenu(draw)).length, 4);
  });

  it("항목을 누르면 그 유형으로 받고, 메뉴를 닫고, 초점을 여는 버튼으로 돌린다", async () => {
    await start(WORDS);
    const draw = mountPicker(WORDS);
    const tree = openMenu(draw);
    const focus = mock.fn();
    (trigger(tree).props.ref as { current: unknown }).current = { focus };

    (menuItems(tree)[2].props.onClick as () => void)();
    await settle();

    assert.deepEqual(kinds(), [null, "term"]);
    assert.equal(menuItems(draw()).length, 0, "메뉴가 닫혀야 한다");
    assert.equal(focus.mock.callCount(), 1);
  });

  it("이미 고른 항목을 누르면 닫기만 하고 새로 받지 않는다", async () => {
    await start(WORDS);
    const draw = mountPicker(WORDS);
    const tree = openMenu(draw);

    (menuItems(tree)[0].props.onClick as () => void)();
    await settle();

    assert.deepEqual(kinds(), [null]);
    assert.equal(menuItems(draw()).length, 0);
  });

  // 화면 폭 390, 메뉴 폭 256(16rem), 여백 16.
  for (const [where, left, width, expected] of [
    ["넘치면 넘치는 만큼만 왼쪽으로 민다", 150, 390, -32],
    ["넘치지 않으면 그대로 둔다", 20, 390, 0],
    ["좁은 화면에서도 왼쪽 여백 밖으로는 밀지 않는다", 30, 200, -14],
    ["메뉴가 화면보다 넓으면 줄어든 폭으로 계산한다", 60, 260, -44],
  ] as const) {
    it(`유형 메뉴: ${where}`, async (t) => {
      await start(WORDS);
      const g = globalThis as { document?: unknown; getComputedStyle?: unknown };
      const real = { document: g.document, getComputedStyle: g.getComputedStyle };
      g.document = { documentElement: { clientWidth: width } };
      g.getComputedStyle = () => ({ fontSize: "16px" });
      t.after(() => Object.assign(g, real));
      const draw = mountPicker(WORDS);
      (trigger(draw()).props.ref as { current: unknown }).current = {
        getBoundingClientRect: () => ({ left, right: left + 124 }),
      };

      const [panel] = findAll(openMenu(draw), (el) => el.props.role === "group");

      assert.equal((panel.props.style as { left: number }).left, expected);
    });
  }

  it("메뉴를 연 채 화면 폭이 바뀌면 다시 민다", async (t) => {
    await start(WORDS);
    const g = globalThis as unknown as {
      document?: unknown;
      getComputedStyle?: unknown;
      window: Record<string, unknown>;
    };
    const real = { document: g.document, getComputedStyle: g.getComputedStyle };
    t.after(() => Object.assign(g, real));
    const doc = { documentElement: { clientWidth: 1224 } };
    g.document = doc;
    g.getComputedStyle = () => ({ fontSize: "16px" });
    let onResize = () => {};
    g.window.addEventListener = (type: string, fn: () => void) => {
      if (type === "resize") onResize = fn;
    };
    g.window.removeEventListener = () => {};

    const draw = mountPicker(WORDS);
    (trigger(draw()).props.ref as { current: unknown }).current = {
      getBoundingClientRect: () => ({ left: 150, right: 274 }),
    };
    openMenu(draw);
    for (const e of effects.filter((one) => one.deps?.length === 1 && one.deps[0] === true)) {
      e.run();
    }
    // 펼친 폴드에서 열었으니 아직 밀지 않았다. 접어서 390 이 되면 넘친다.
    doc.documentElement.clientWidth = 390;
    onResize();

    const [panel] = findAll(draw(), (el) => el.props.role === "group");
    assert.equal((panel.props.style as { left: number }).left, -32);
  });
});

describe("유형 고르개 - 가지가 바뀌어도 남는다", () => {
  it("가져오는 중에도 고르개가 있다", () => {
    const page = html(WORDS);
    assert.match(page, /문제를 가져오는 중/);
    assert.match(page, />유형<\/span>/);
  });

  it("문제를 못 낸 안내 화면에도 고르개가 있고, 안내보다 앞에 선다", async () => {
    statuses = [404];
    await start(WORDS);
    const page = html(WORDS);
    const at = page.indexOf(">유형</span>");
    assert.ok(at >= 0, "안내 화면에 고르개가 없다");
    assert.ok(at < page.indexOf("다 풀었습니다"), "고르개가 안내보다 위에 있어야 한다");
  });

  it("안내 화면에서 유형을 바꾸면 그 자리에서 다시 받는다", async () => {
    statuses = [200, 404];
    await start(WORDS);
    await choose(WORDS, "description");
    assert.match(html(WORDS), /이 유형으로/);

    await choose(WORDS, "");
    assert.deepEqual(kinds(), [null, "description", null]);
    const page = html(WORDS);
    assert.doesNotMatch(page, /다 풀었습니다/);
    assert.equal(findAll(render(WORDS), named("ChoiceButton")).length, 4);
  });
});

describe("유형 고르개 - 안내 문구", () => {
  it("유형을 골랐는데 404 면 유형을 바꾸라고 안내한다", async () => {
    statuses = [200, 404];
    await start(WORDS);
    await choose(WORDS, "description");
    const page = html(WORDS);
    assert.match(page, /이 유형으로 낼 수 있는 문제가 없거나 다 풀었습니다/);
    assert.match(page, /섞어서/);
  });

  it("섞어서인데 404 면 원래 안내(분류를 넓히라)다", async () => {
    statuses = [404];
    await start(WORDS);
    const page = html(WORDS);
    assert.match(page, /낼 수 있는 문제를 다 풀었습니다\. 분류를 넓히거나/);
    assert.doesNotMatch(page, /이 유형으로/);
  });

  it("유형을 골랐어도 서버 오류(5xx)면 유형 탓으로 말하지 않는다", async () => {
    statuses = [200, 503];
    await start(WORDS);
    await choose(WORDS, "term");
    const page = html(WORDS);
    assert.match(page, /문제를 불러오지 못했습니다/);
    assert.doesNotMatch(page, /이 유형으로/);
    // 버튼도 유형을 풀지 않는다. 섞어서로 풀기를 두면 고른 유형이 안내 없이
    // 사라지고, 같은 값을 다시 골라도 아무 일이 안 일어나 되돌릴
    // 길이 없다.
    assert.doesNotMatch(page, /섞어서로 풀기/);
    // 잠깐의 서버 오류라 점수를 지우는 "처음부터 다시" 가 아니라 같은 요청을
    // 다시 보내는 버튼이다.
    // 안내 문구에도 "다시 시도" 가 들어 있어 버튼 글자로 찾는다.
    assert.match(page, />다시 시도<\/button>/);
    assert.doesNotMatch(page, /처음부터 다시/);
  });

  it("유형 때문에 못 냈으면 갈색 버튼이 섞어서로 되돌린다(처음부터 다시가 아니다)", async () => {
    // "처음부터 다시" 는 점수를 지우는데, 유형이 그대로라 같은 404 가 또 난다.
    statuses = [200, 404];
    await start(WORDS);
    await choose(WORDS, "description");
    const tree = render(WORDS);
    assert.equal(
      findAll(tree, (el) => el.type === "button" && el.props.children === "처음부터 다시").length,
      0,
    );
    const mix = findAll(tree, (el) => el.type === "button" && el.props.children === "섞어서로 풀기");
    assert.equal(mix.length, 1);
    (mix[0].props.onClick as () => void)();
    await settle();
    assert.deepEqual(kinds(), [null, "description", null]);
    assert.equal(menu(WORDS).selected, "섞어서");
  });
});

describe("유형 고르개 - 점수는 이어진다", () => {
  /** 머리 줄의 점수 글자. 없으면 빈 문자열. */
  function scoreLine(props: Props): string {
    const page = html(props);
    return /(\d+)문제 중 (\d+)개/.exec(page)?.[0] ?? "";
  }

  it("답한 뒤 유형을 바꿔도 점수·연속이 그대로다", async () => {
    await start(WORDS);
    await answer(WORDS);
    await next(WORDS);
    await answer(WORDS);
    assert.equal(scoreLine(WORDS), "2문제 중 2개");

    await choose(WORDS, "term");
    await next(WORDS);
    const page = html(WORDS);
    assert.match(page, /2문제 중 2개/);
    assert.match(page, /연속<\/span>2/);
  });

  it("답하기 전에 바꿔서 새로 받아도 점수·연속이 그대로다", async () => {
    await start(WORDS);
    await answer(WORDS);
    await next(WORDS);
    await answer(WORDS);
    await next(WORDS);
    // 세 번째 문제가 떠 있고 아직 안 골랐다.
    await choose(WORDS, "meaning");
    assert.equal(requested.length, 4);
    const page = html(WORDS);
    assert.match(page, /2문제 중 2개/);
    assert.match(page, /연속<\/span>2/);
  });

  it("오답으로 끊긴 연속은 유형을 바꿔도 되살아나지 않는다", async () => {
    grades = [true, true, false];
    await start(WORDS);
    for (let i = 0; i < 3; i++) {
      await answer(WORDS);
      await next(WORDS);
    }
    await choose(WORDS, "term");
    const page = html(WORDS);
    assert.match(page, /3문제 중 2개/);
    assert.doesNotMatch(page, /연속<\/span>/);
  });
});
