/**
 * 문제풀기(QuizBoard)가 문제를 못 받았을 때 어떤 버튼을 주는지, 그 버튼이
 * 점수를 지키는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 결함 넷이다.
 *
 *   끊김에 점수가 날아감   지하철에서 한 번 끊겼는데 버튼이 "처음부터 다시" 뿐이라
 *                          누르면 그때까지 푼 점수·연속·푼 목록이 지워진다
 *   다시 시도가 점수를 지움 버튼 이름만 바뀌고 하는 일은 처음부터 다시와 같다
 *   404 에 다시 시도       다 풀어서 못 내는 것인데 같은 요청을 다시 보내 같은
 *                          안내가 끝없이 뜬다
 *   영어가 샘              끊김이 브라우저의 "Failed to fetch" 로 보인다
 *
 * quiz-kind-picker.test.mts 와 같은 방식으로 react 훅 넷만 대역으로 바꾸고
 * QuizBoard 를 함수로 부른다. 돌려받은 트리에서 버튼의 onClick 을 꺼내 부른다.
 */
import assert from "node:assert/strict";
import { after, afterEach, beforeEach, describe, it, mock } from "node:test";

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

const OFFLINE = "인터넷에 연결되어 있지 않습니다. 연결되면 다시 눌러주세요.";
const SERVER = "서버에 연결하지 못했습니다. 잠시 뒤 다시 눌러주세요.";

const realFetch = globalThis.fetch;
const realWindow = (globalThis as { window?: unknown }).window;
const realNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
after(() => {
  globalThis.fetch = realFetch;
  (globalThis as { window?: unknown }).window = realWindow;
});

const setOnline = (onLine: boolean) =>
  Object.defineProperty(globalThis, "navigator", {
    value: { onLine },
    configurable: true,
    writable: true,
  });

/** 문제 요청의 쿼리. 채점(POST)은 세지 않는다. */
let requested: URLSearchParams[] = [];
/** 문제 요청에 차례로 줄 것. 숫자는 상태 코드, "drop" 은 연결 끊김. 비면 200. */
let replies: (number | "drop")[] = [];

let nextId = 100;

beforeEach(() => {
  slots = [];
  requested = [];
  replies = [];
  nextId = 100;
  setOnline(true);
  (globalThis as { window?: unknown }).window = { scrollTo() {}, innerWidth: 390 };
  globalThis.fetch = (async (input: string | URL, init?: RequestInit) => {
    if (init?.method === "POST") {
      // 매번 다른 문제로 친다. 푼 목록(exclude)이 쌓이는지 보려고.
      const answerId = nextId++;
      return {
        ok: true,
        status: 200,
        json: async () => ({ correct: true, answer_id: answerId }),
      } as Response;
    }
    requested.push(new URL(String(input), "http://localhost").searchParams);
    const reply = replies.shift() ?? 200;
    if (reply === "drop") throw new TypeError("Failed to fetch");
    return {
      ok: reply < 400,
      status: reply,
      json: async () =>
        reply < 400
          ? {
              kind: "meaning",
              kind_label: "뜻 고르기",
              question: "이 단어의 뜻은?",
              prompt: "commit",
              category: "git",
              category_label: "Git",
              choices: [
                { id: 12, text: "a" },
                { id: 13, text: "b" },
              ],
              token: "t",
            }
          : { detail: "x" },
    } as Response;
  }) as typeof fetch;
});

afterEach(() => {
  if (realNavigator) Object.defineProperty(globalThis, "navigator", realNavigator);
});

/* ---- 도구 ---- */

function render(props: Props): El {
  cursor = 0;
  effects = [];
  return QuizBoard(props) as unknown as El;
}

async function settle() {
  for (let i = 0; i < 5; i++) await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
}

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

async function start(props: Props) {
  render(props);
  const load = effects.filter((e) => e.deps?.length === 1 && typeof e.deps[0] === "function");
  assert.equal(load.length, 1, "첫 문제를 부르는 effect 를 못 찾았다");
  load[0].run();
  await settle();
}

/** 글자가 이것인 버튼. 없으면 undefined. */
const buttonText = (props: Props, text: string) =>
  findAll(render(props), (el) => el.type === "button" && el.props.children === text)[0];

async function pressText(props: Props, text: string) {
  const button = buttonText(props, text);
  assert.ok(button, `"${text}" 버튼이 없다`);
  (button.props.onClick as () => void)();
  await settle();
}

async function answer(props: Props) {
  const choices = findAll(render(props), named("ChoiceButton"));
  assert.ok(choices.length > 0, "보기가 없다 - 문제를 못 받았다");
  (choices[0].props.onClick as () => void)();
  await settle();
}

function html(props: Props): string {
  const tree = render(props);
  cursor = slots.length;
  return renderToStaticMarkup(tree as never);
}

/** 두 문제를 맞힌 뒤 "다음 문제" 를 눌렀다. 세 번째 요청이 replies 의 맨 앞을 받는다. */
async function solveTwoThenNext(props: Props) {
  await start(props);
  await answer(props);
  await pressText(props, "다음 문제");
  await answer(props);
  await pressText(props, "다음 문제");
}

const WORDS: Props = { content: "words" };

/* ---- 테스트 ---- */

describe("문제 받기 실패 - 끊김", () => {
  it("끊기면 한국어로 알리고 버튼은 다시 시도 하나다", async () => {
    replies = [200, 200, "drop"];
    await solveTwoThenNext(WORDS);
    const page = html(WORDS);
    assert.ok(page.includes(SERVER), "끊김 문구가 없다");
    assert.doesNotMatch(page, /Failed to fetch/);
    assert.match(page, />다시 시도</);
    assert.doesNotMatch(page, /처음부터 다시/);
  });

  it("오프라인이면 인터넷 연결 문구다", async () => {
    replies = ["drop"];
    setOnline(false);
    await start(WORDS);
    assert.ok(html(WORDS).includes(OFFLINE));
  });

  it("다시 시도는 점수·연속·푼 목록을 그대로 두고 같은 요청을 다시 보낸다", async () => {
    replies = [200, 200, "drop"];
    await solveTwoThenNext(WORDS);
    const failedExclude = requested[2].get("exclude");
    assert.ok(failedExclude, "두 문제를 풀었는데 푼 목록이 비었다");

    await pressText(WORDS, "다시 시도");
    assert.equal(requested.length, 4);
    assert.equal(requested[3].get("exclude"), failedExclude, "다시 시도가 푼 목록을 비웠다");

    const page = html(WORDS);
    assert.match(page, /2문제 중 2개/);
    assert.match(page, /연속<\/span>2/);
    assert.equal(findAll(render(WORDS), named("ChoiceButton")).length, 2, "새 문제가 안 떴다");
    assert.ok(!page.includes(SERVER), "받은 뒤에도 끊김 문구가 남았다");
  });

  it("다시 시도도 끊기면 또 다시 시도를 주고 점수는 여전히 남는다", async () => {
    replies = [200, 200, "drop", "drop", 200];
    await solveTwoThenNext(WORDS);
    await pressText(WORDS, "다시 시도");
    assert.ok(buttonText(WORDS, "다시 시도"), "두 번째 끊김에서 다시 시도가 사라졌다");
    await pressText(WORDS, "다시 시도");
    assert.match(html(WORDS), /2문제 중 2개/);
  });

  it("상세에서 청한 항목은 끊김 뒤 다시 시도에도 싣는다", async () => {
    replies = ["drop"];
    const props: Props = { item: "12", content: "words" };
    await start(props);
    assert.ok(buttonText(props, "다시 시도"));
    await pressText(props, "다시 시도");
    assert.deepEqual(
      requested.map((q) => q.get("item")),
      ["12", "12"],
    );
  });

  it("서버 오류(5xx)도 다시 시도다", async () => {
    replies = [200, 503];
    await start(WORDS);
    await answer(WORDS);
    await pressText(WORDS, "다음 문제");
    assert.ok(buttonText(WORDS, "다시 시도"));
    assert.equal(buttonText(WORDS, "처음부터 다시"), undefined);
  });
});

describe("문제 받기 실패 - 다시 눌러도 같은 것", () => {
  it("다 풀어서 404 면 여전히 처음부터 다시이고, 누르면 점수가 비워진다", async () => {
    replies = [200, 200, 404];
    await solveTwoThenNext(WORDS);
    const page = html(WORDS);
    assert.match(page, /낼 수 있는 문제를 다 풀었습니다/);
    assert.doesNotMatch(page, />다시 시도</);
    await pressText(WORDS, "처음부터 다시");
    assert.equal(requested[3].get("exclude"), null, "처음부터 다시가 푼 목록을 안 비웠다");
    assert.doesNotMatch(html(WORDS), /2문제 중/);
  });

  it("청한 항목이 거절되면(404·400) 처음부터 다시다", async () => {
    for (const status of [404, 400]) {
      slots = [];
      replies = [status];
      const props: Props = { item: "12", content: "words" };
      await start(props);
      assert.ok(buttonText(props, "처음부터 다시"), `${status} 인데 처음부터 다시가 없다`);
      assert.equal(buttonText(props, "다시 시도"), undefined, `${status} 인데 다시 시도가 있다`);
    }
  });

  it("끊긴 뒤 다시 시도에서 404 가 나면 처음부터 다시로 바뀐다", async () => {
    replies = [200, 200, "drop", 404];
    await solveTwoThenNext(WORDS);
    await pressText(WORDS, "다시 시도");
    assert.ok(buttonText(WORDS, "처음부터 다시"));
    assert.equal(buttonText(WORDS, "다시 시도"), undefined);
  });
});
