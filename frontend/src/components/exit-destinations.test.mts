/**
 * 문제 화면의 나가기 버튼이 **어디로** 보내는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 단어·문장 문제풀기와 한 판은 탭바가 없어 나가기 버튼이 유일한 출구다.
 * 이 화면에 들어오는 길은 문제풀기 허브(/test)라서 나가면 거기로 돌아가야
 * 한다 - 홈으로 보내면 허브까지 한 번 더 누른다. 한 판을 끝낸 뒤의 출구는
 * 로그인한 사람만 "내 기록" 이다. 게스트는 기록이 없어 내정보가 로그인
 * 화면으로 보내므로 이름과 다른 곳에 닿는다.
 *
 * 형제 leave-exits.test.mts 는 ExitGuard 가 **어떻게** 묻는지를 본다. 여기는
 * ExitGuard 를 props 만 모으는 대역으로 바꾸고, 화면이 넘긴 to·label·confirm
 * 을 본다.
 *
 * RoundBoard 는 단계(idle·playing·done)마다 다른 출구를 그린다. 단계를 상태
 * 칸에 직접 넣지 않고 fetch 대역으로 시작·채점·끝내기 응답을 흉내 내 실제
 * 전이로 몬다 - 게스트 여부가 결과 화면까지 제대로 이어지는지도 같이 본다.
 * 훅 대역은 quiz-board-item.test.mts 와 같은 방식이다(렌더마다 호출 순서로
 * 칸을 찾는다). 페이지 둘은 async 서버 컴포넌트라 함수로 불러 돌려받은
 * 트리를 훑는다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

const realReact = await import("react");

// ---------------------------------------------------------------------------
// 훅 대역. RoundBoard 를 브라우저 없이 함수로 부르려면 필요하다.
// ---------------------------------------------------------------------------

type Slot = { value: unknown };

let slots: Slot[] = [];
let cursor = 0;

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
    // 타이머 effect 는 돌리지 않는다. 판을 끝내는 것은 마지막 채점 응답의
    // finished 로 한다 - 시계에 기대면 테스트가 느리고 흔들린다.
    useEffect() {},
  },
});

/** ExitGuard 대역. 트리에서 이 함수를 type 으로 가진 요소를 찾는다. */
function ExitGuardStub() {
  return null;
}

mock.module("@/components/ExitGuard", {
  namedExports: { ExitGuard: ExitGuardStub },
});

// 페이지가 부르는 분류 목록. 백엔드 없이 빈 배열로 둔다.
mock.module("@/lib/api/vocab", {
  namedExports: { getCategories: async () => [] },
});
mock.module("@/lib/api/sentences", {
  namedExports: { getSentenceCategories: async () => [] },
});

/** 한 판 페이지가 게스트를 가리는 토큰. 테스트마다 바꾼다. */
let token: string | null = null;
mock.module("@/lib/session", {
  namedExports: { getToken: async () => token },
});

const { RoundBoard } = await import("./RoundBoard");
const { routes } = await import("@/lib/routes");
const wordsPage = (await import("@/app/test/words/page")).default;
const sentencesPage = (await import("@/app/test/sentences/page")).default;
const roundPage = (await import("@/app/test/round/page")).default;

// ---------------------------------------------------------------------------
// 트리 훑기
// ---------------------------------------------------------------------------

type Element = { type: unknown; props: Record<string, unknown> };

const isElement = (node: unknown): node is Element =>
  typeof node === "object" && node !== null && "type" in node && "props" in node;

/** 트리의 요소를 전부 편다. 아직 그리지 않은 자식 컴포넌트 안은 안 본다. */
function flatten(node: unknown, out: Element[] = []): Element[] {
  if (Array.isArray(node)) {
    for (const child of node) flatten(child, out);
  } else if (isElement(node)) {
    out.push(node);
    flatten(node.props.children, out);
  }
  return out;
}

/** 트리의 출구들. key·children 은 빼고 넘긴 props 만. */
const exits = (tree: unknown) =>
  flatten(tree)
    .filter((e) => e.type === ExitGuardStub)
    .map((e) => ({ ...e.props }));

/** 출구가 딱 하나이고 그 props 가 이것이다. */
function onlyExit(tree: unknown, expected: Record<string, unknown>) {
  const found = exits(tree);
  assert.equal(found.length, 1, `출구가 ${found.length}개다: ${JSON.stringify(found)}`);
  assert.deepEqual(found[0], expected);
}

/** 이 props 이름을 가진 요소(StartCard 의 onStart, PlayCard 의 onPick). */
function withProp(tree: unknown, name: string): Element {
  const found = flatten(tree).find((e) => typeof e.props[name] === "function");
  assert.ok(found, `${name} 를 가진 요소가 없다`);
  return found;
}

// ---------------------------------------------------------------------------
// fetch·document 대역
// ---------------------------------------------------------------------------

const QUESTION = {
  kind: "meaning",
  kind_label: "뜻 고르기",
  question: "이 단어의 뜻은?",
  prompt: "commit",
  category: "git",
  category_label: "Git",
  choices: [
    { id: 1, text: "a" },
    { id: 2, text: "b" },
  ],
};

const RESULT = {
  correct: true,
  skipped: false,
  in_time: true,
  score: 1,
  elapsed_ms: 500,
  answer_type: "",
  answer_text: "a",
  answer_extra: "",
};

/** 다음 채점 응답이 판을 끝내는가. */
let finishNext = false;
/** 끝내기 요청이 실패하는가. */
let finishFails = false;
/**
 * 판을 닫을 때 서버가 알려주는 guest. 기본은 판을 연 화면의 isGuest 와 같다
 * (startRound 가 맞춘다). 쿠키의 토큰을 서버가 거절해 판이 게스트로 열린
 * 경우처럼 둘이 어긋나는 상황은 테스트가 직접 덮어쓴다.
 */
let serverGuest: boolean | undefined;

const realFetch = globalThis.fetch;
const realDocument = (globalThis as { document?: unknown }).document;
after(() => {
  globalThis.fetch = realFetch;
  (globalThis as { document?: unknown }).document = realDocument;
});

beforeEach(() => {
  slots = [];
  finishNext = false;
  finishFails = false;
  serverGuest = undefined;
  token = null;
  (globalThis as { document?: unknown }).document = {
    documentElement: { style: { setProperty() {}, removeProperty() {} } },
  };
  globalThis.fetch = (async (_input: string, init: RequestInit) => {
    const body = JSON.parse(String(init.body)) as { action: string };
    const reply = (status: number, data: unknown) =>
      ({ ok: status < 400, status, json: async () => data }) as Response;

    if (body.action === "start") {
      return reply(200, {
        token: "t0",
        question: QUESTION,
        round_seconds: 90,
        max_skips: 3,
        reaction_pause_ms: 0,
      });
    }
    if (body.action === "answer") {
      return reply(200, {
        token: "t1",
        result: RESULT,
        question: finishNext ? null : QUESTION,
        finished: finishNext,
      });
    }
    if (finishFails) return reply(500, { detail: "닫지 못했다" });
    return reply(200, {
      score: 2,
      answered: 2,
      correct: 2,
      skipped: 0,
      recorded: !serverGuest,
      guest: serverGuest,
    });
  }) as typeof fetch;
});

/** 한 테스트 안에서 새 판을 다시 몰 때. 화면을 새로 연 것과 같다. */
function fresh() {
  slots = [];
  finishNext = false;
  serverGuest = undefined;
}

/** 한 번 그린다. 상태 칸은 이어 쓴다. */
function render(isGuest: boolean) {
  cursor = 0;
  return RoundBoard({ isGuest });
}

/** 비동기 처리(fetch -> json -> 상태)를 끝까지 흘린다. */
const settle = () => new Promise((r) => setTimeout(r, 0));

/** 시작 전 -> 판 진행 중. */
async function startRound(isGuest: boolean) {
  serverGuest ??= isGuest;
  const idle = render(isGuest);
  (withProp(idle, "onStart").props.onStart as () => Promise<void>)();
  await settle();
  return render(isGuest);
}

/** 한 문제 답한다. finishNext 면 판이 끝난다. */
async function answer(isGuest: boolean, tree: unknown) {
  (withProp(tree, "onPick").props.onPick as (id: number) => void)(1);
  await settle();
  return render(isGuest);
}

/** 두 문제를 풀고 판을 끝낸다. */
async function playToEnd(isGuest: boolean) {
  const playing = await startRound(isGuest);
  const second = await answer(isGuest, playing);
  finishNext = true;
  return answer(isGuest, second);
}

// ---------------------------------------------------------------------------
// RoundBoard
// ---------------------------------------------------------------------------

describe("한 판의 출구", () => {
  for (const isGuest of [true, false]) {
    const who = isGuest ? "게스트" : "로그인";

    it(`${who}: 시작 전에는 묻지 않고 문제풀기 허브로 간다`, () => {
      onlyExit(render(isGuest), { to: routes.test, label: "문제풀기", ariaLabel: "문제풀기로 나가기" });
    });

    it(`${who}: 진행 중 "그만두기" 는 허브로 가고, 묻고, 딴 점수와 시계를 알린다`, async () => {
      const playing = await startRound(isGuest);
      onlyExit(playing, {
        to: routes.test,
        label: "그만두기",
        confirm: true,
        score: 0,
        countdown: true,
      });

      // 점수는 그릴 때의 값이 아니라 지금까지 딴 값이다.
      const after = await answer(isGuest, playing);
      assert.equal(exits(after)[0].score, 1);
    });
  }

  it("게스트는 판을 끝낸 뒤 허브로 나간다 - \"내 기록\" 을 주지 않는다", async () => {
    const done = await playToEnd(true);
    onlyExit(done, { to: routes.test, label: "문제풀기", ariaLabel: "문제풀기로 나가기" });
  });

  it("로그인한 사람은 판을 끝낸 뒤 \"내 기록\" 으로 나간다", async () => {
    const done = await playToEnd(false);
    onlyExit(done, { to: routes.profile, label: "내 기록" });
  });

  it("쿠키는 있었지만 서버가 게스트 판으로 열었으면 결과 화면은 게스트다", async () => {
    // 페이지는 쿠키만 보고 isGuest=false 로 열었는데, 중계가 죽은 토큰을
    // 거절당해 게스트 판을 열었다. 기록 안 된 판에 "내 기록" 을 주면 안 된다.
    serverGuest = true;
    const done = await playToEnd(false);
    onlyExit(done, { to: routes.test, label: "문제풀기", ariaLabel: "문제풀기로 나가기" });
    const card = flatten(done).find((e) => "summary" in e.props);
    assert.equal(card?.props.isGuest, true, "결과 카드도 게스트로 그려야 한다");
  });

  it("서버가 기록된 판이라고 하면 페이지의 isGuest 보다 그것을 따른다", async () => {
    serverGuest = false;
    const done = await playToEnd(true);
    onlyExit(done, { to: routes.profile, label: "내 기록" });
    const card = flatten(done).find((e) => "summary" in e.props);
    assert.equal(card?.props.isGuest, false);
  });

  it("끝내기가 실패해 결과 화면으로 가도 출구는 게스트 여부를 따른다", async () => {
    finishFails = true;
    onlyExit(await playToEnd(true), { to: routes.test, label: "문제풀기", ariaLabel: "문제풀기로 나가기" });
    fresh();
    onlyExit(await playToEnd(false), { to: routes.profile, label: "내 기록" });
  });

  it("어느 단계에서도 홈으로 보내지 않는다", async () => {
    for (const isGuest of [true, false]) {
      fresh();
      const trees = [render(isGuest)];
      trees.push(await startRound(isGuest));
      fresh();
      trees.push(await playToEnd(isGuest));
      for (const tree of trees) {
        for (const exit of exits(tree)) {
          assert.notEqual(exit.to, routes.home, JSON.stringify(exit));
        }
      }
    }
  });
});

describe("한 판 페이지", () => {
  const board = async () => (await roundPage()) as unknown as Element;

  it("토큰이 없으면 게스트로 그린다", async () => {
    token = null;
    const found = flatten(await board()).find((e) => e.type === RoundBoard);
    assert.equal(found?.props.isGuest, true);
  });

  it("토큰이 있으면 게스트가 아니다", async () => {
    token = "abc";
    const found = flatten(await board()).find((e) => e.type === RoundBoard);
    assert.equal(found?.props.isGuest, false);
  });
});

// ---------------------------------------------------------------------------
// 단어·문장 문제풀기 페이지
// ---------------------------------------------------------------------------

describe("낱개 문제풀기 페이지의 출구", () => {
  const pages = [
    ["단어", wordsPage],
    ["문장", sentencesPage],
  ] as const;

  for (const [name, page] of pages) {
    for (const params of [{}, { category: "git" }, { item: "12" }]) {
      it(`${name} ${JSON.stringify(params)}: 푼 것이 있을 때만 묻고 허브로 간다`, async () => {
        const tree = await page({ searchParams: Promise.resolve(params) });
        onlyExit(tree, {
          to: routes.test,
          label: "문제풀기",
          ariaLabel: "문제풀기로 나가기",
          confirmWhenSolved: true,
        });
      });
    }
  }

  it("허브 주소는 /test 다", () => {
    // routes.test 가 다른 곳을 가리키면 위 검사가 전부 그쪽을 기대값으로 삼는다.
    assert.equal(routes.test, "/test");
    assert.notEqual(routes.test, routes.home);
  });
});
