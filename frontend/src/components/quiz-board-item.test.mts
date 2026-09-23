/**
 * QuizBoard 가 item(상세의 "이 단어로 문제 풀기")을 **첫 요청에만** 싣는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 매 요청에 실으면 같은 단어만 계속 나오고, 실패한 뒤 "다시 시도" 에도
 * 실으면 같은 이유로 또 실패한다. 둘 다 화면으로는 "문제가 잘 나온다" 로
 * 보여서 눈으로 잡기 어렵다.
 *
 * 브라우저가 없어 effect 가 돌지 않으므로, react 의 훅 넷(useState·useRef·
 * useCallback·useEffect)만 작은 대역으로 바꿔 QuizBoard 를 함수로 부른다.
 * 나머지 react 는 진짜를 그대로 넘긴다 - JSX 가 그쪽을 쓴다. 대역은 렌더마다
 * 훅 호출 순서로 칸을 찾는 React 의 규칙을 그대로 따른다.
 *
 * "다음 문제" 와 "다시 시도" 는 둘 다 load() 를 부른다. 그래서 load 를
 * 의존으로 받는 첫 문제 effect 를 다시 불러 같은 경로를 흉내 낸다.
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

/** 한 번 그린다. 훅 칸은 이어 쓰고 effect 는 새로 모은다. */
function render(props: Parameters<typeof QuizBoard>[0]) {
  cursor = 0;
  effects = [];
  QuizBoard(props);
}

/** 첫 문제를 부르는 effect. load 하나만 의존으로 받는 것이 그것이다. */
function loadEffect(): Effect {
  const found = effects.filter(
    (e) => e.deps?.length === 1 && typeof e.deps[0] === "function",
  );
  assert.equal(found.length, 1, "load 를 부르는 effect 를 못 찾았다");
  return found[0];
}

const realFetch = globalThis.fetch;
const realWindow = (globalThis as { window?: unknown }).window;
after(() => {
  globalThis.fetch = realFetch;
  (globalThis as { window?: unknown }).window = realWindow;
});

/** 요청한 주소의 쿼리. */
let requested: URLSearchParams[] = [];
/** 차례로 돌려줄 상태 코드. 비면 200. */
let statuses: number[] = [];

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
  (globalThis as { window?: unknown }).window = { scrollTo() {} };
  globalThis.fetch = (async (input: string | URL) => {
    const url = new URL(String(input), "http://localhost");
    requested.push(url.searchParams);
    const status = statuses.shift() ?? 200;
    return {
      ok: status < 400,
      status,
      json: async () => (status < 400 ? QUESTION : { detail: "x" }),
    } as Response;
  }) as typeof fetch;
});

/** load 한 번을 끝까지 기다린다. */
async function loadOnce(props: Parameters<typeof QuizBoard>[0]) {
  render(props);
  loadEffect().run();
  // load 는 fetch -> json 두 번을 기다린다. 넉넉히 돌린다.
  for (let i = 0; i < 5; i++) await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
}

describe("QuizBoard item", () => {
  it("첫 요청에만 item 을 싣는다", async () => {
    const props = { item: "12", content: "words" as const };
    await loadOnce(props);
    await loadOnce(props);
    await loadOnce(props);

    assert.equal(requested.length, 3);
    assert.equal(requested[0].get("item"), "12");
    assert.equal(requested[1].get("item"), null);
    assert.equal(requested[2].get("item"), null);
  });

  it("첫 요청이 실패해도 다시 시도에는 싣지 않는다", async () => {
    statuses = [404];
    const props = { item: "12", content: "sentences" as const };
    await loadOnce(props);
    await loadOnce(props);

    assert.equal(requested[0].get("item"), "12");
    assert.equal(requested[0].get("content"), "sentences");
    assert.equal(requested[1].get("item"), null);
    // 두 번째는 평소 요청이다 - 분류·콘텐츠는 그대로 싣는다.
    assert.equal(requested[1].get("content"), "sentences");
  });

  it("잘못된 번호(400)여도 다시 시도에는 싣지 않는다", async () => {
    statuses = [400];
    const props = { item: "abc", content: "words" as const };
    await loadOnce(props);
    await loadOnce(props);

    assert.equal(requested[1].get("item"), null);
  });

  it("서버가 잠깐 안 될 때(5xx)는 다시 시도에도 그 항목을 싣는다", async () => {
    // 항목 탓이 아니라서 버리면, 다시 눌렀을 때 청하지 않은 문제가 나온다.
    statuses = [503];
    const props = { item: "12", content: "words" as const };
    await loadOnce(props);
    await loadOnce(props);
    await loadOnce(props);

    assert.equal(requested[0].get("item"), "12");
    assert.equal(requested[1].get("item"), "12");
    assert.equal(requested[2].get("item"), null, "받은 뒤에는 비운다");
  });

  it("item 이 없거나 빈 값이면 싣지 않는다", async () => {
    await loadOnce({ content: "words" });
    slots = [];
    await loadOnce({ item: "", content: "words" });

    assert.equal(requested.length, 2);
    for (const query of requested) assert.equal(query.has("item"), false);
  });

  it("분류는 매 요청에 그대로 싣는다", async () => {
    const props = { item: "12", category: "git", content: "words" as const };
    await loadOnce(props);
    await loadOnce(props);

    assert.deepEqual(
      requested.map((q) => [q.get("category"), q.get("item")]),
      [
        ["git", "12"],
        ["git", null],
      ],
    );
  });
});
