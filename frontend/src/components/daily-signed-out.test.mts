/**
 * 일일공부(/test/daily) 도중 로그인이 풀리면(중계가 401) 로그인 화면으로 가는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - 시작·답 어느 쪽이든 401 이면 window.location.replace 로
 *     /login?next=<지금 경로> 에 간다. 쌓지 않고 바꿔치기다(앱의 뒤로 가기).
 *   - 그 next 를 로그인 액션이 safeNext 로 거르면 지금 경로가 그대로 남는다.
 *   - 401 이 아닌 실패(400·403·429·500·503·끊김)는 이 화면에 오류를 띄우고
 *     어디로도 보내지 않는다.
 *
 * 복습의 같은 동작은 review-resume.test.mts 가 본다(판을 지우지 않는 것까지).
 *
 * 방식은 verdict-wait.test.mts 와 같다. react 의 훅만 작은 대역으로 바꾸고 보드가
 * 넘긴 onStart·onPick 을 진짜로 부른다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

import type { DailyStatus, StudyProgress } from "@/lib/api/daily";
import type { RoundQuestion } from "@/lib/api/rounds";
import { connectionLostMessage } from "@/lib/connection";
import { safeNext } from "@/lib/routes";

const realReact = await import("react");

type Slot = { value: unknown };
type Effect = () => void | (() => void);

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
    useEffect(run: Effect) {
      effects.push(run);
    },
    useSyncExternalStore<T>(_subscribe: unknown, getSnapshot: () => T) {
      return getSnapshot();
    },
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { createElement } = realReact;
const { DailyStudyBoard } = await import("./DailyStudyBoard");

/* ---- 브라우저·중계 대역 ---- */

const g = globalThis as unknown as { window?: unknown };
const hadWindow = "window" in g;
const realWindow = g.window;
const realFetch = globalThis.fetch;

after(() => {
  globalThis.fetch = realFetch;
  if (hadWindow) g.window = realWindow;
  else delete g.window;
});

/** location.replace 로 간 곳. */
let moved: string[] = [];
let reply: { status: number; detail?: string } | Error;

beforeEach(() => {
  slots = [];
  moved = [];
  g.window = {
    location: { pathname: "/test/daily", search: "", replace: (to: string) => moved.push(to) },
    matchMedia: () => ({ matches: true }),
  };
  globalThis.fetch = (async () => {
    if (reply instanceof Error) throw reply;
    const { status, detail } = reply;
    return { ok: status < 400, status, json: async () => ({ detail }) } as Response;
  }) as typeof fetch;
});

/* ---- 보드 다루기 ---- */

type Node = { type?: unknown; props: Record<string, unknown> };

function branch(board: () => unknown): Node {
  cursor = 0;
  effects = [];
  const tree = board() as { props: { children: unknown[] } };
  for (const run of effects) run();
  return tree.props.children[1] as Node;
}

function draw(status: DailyStatus): string {
  cursor = 0;
  return renderToStaticMarkup(createElement(DailyStudyBoard, { status }) as never);
}

async function settle() {
  for (let i = 0; i < 5; i++) await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
}

/* ---- 자료 ---- */

const FIRST: RoundQuestion = {
  kind: "meaning",
  kind_label: "뜻 고르기",
  question: "질문-commit",
  prompt: "commit",
  category: "git",
  category_label: "Git",
  choices: [0, 1, 2, 3].map((i) => ({ id: 10 + i, text: `보기-${i}` })),
};

const progress: StudyProgress = {
  length: "5m",
  total: 2,
  answered: 0,
  correct: 0,
  score: 0,
  bonus: 0,
  done: false,
  chunk_size: 3,
  chunk_count: 1,
  chunk_index: 0,
};

const CHOOSING = { lengths: [], today: null, token: null, question: null, learning: [] } as unknown as DailyStatus;
const PLAYING: DailyStatus = { lengths: [], today: progress, token: "tok-1", question: FIRST, learning: [] };

async function start(): Promise<void> {
  const board = () => DailyStudyBoard({ status: CHOOSING });
  const choose = branch(board);
  assert.equal(typeof choose.props.onStart, "function", "고르기 화면이 아니다");
  await (choose.props.onStart as (l: string) => Promise<void>)("5m");
  await settle();
}

async function answer(): Promise<void> {
  const board = () => DailyStudyBoard({ status: PLAYING });
  const play = branch(board);
  assert.equal(typeof play.props.onPick, "function", "문제 화면이 아니다");
  await (play.props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
  await settle();
}

/* ================================================================ */

describe("일일공부 - 로그인이 풀리면(401)", () => {
  for (const [label, act] of [
    ["시작", start],
    ["답", answer],
  ] as const) {
    it(`${label}이 401 이면 지금 경로를 들고 로그인 화면으로 바꿔치기한다`, async () => {
      reply = { status: 401, detail: "토큰이 유효하지 않습니다." };
      await act();
      assert.deepEqual(moved, ["/login?next=%2Ftest%2Fdaily"]);
    });
  }

  it("로그인 화면이 받은 next 는 safeNext 를 지나 지금 경로로 돌아온다", async () => {
    reply = { status: 401 };
    await answer();
    const next = new URL(moved[0], "https://dev-voca.vercel.app").searchParams.get("next");
    assert.equal(safeNext(next), "/test/daily");
  });

  it("서버 문구를 그대로 띄우지 않는다", async () => {
    reply = { status: 401, detail: "토큰이 유효하지 않습니다." };
    await answer();
    assert.doesNotMatch(draw(PLAYING), /토큰이 유효하지 않습니다/);
  });
});

describe("일일공부 - 401 이 아닌 실패는 이 화면에 남는다", () => {
  for (const [label, r] of [
    ["400", { status: 400, detail: "판이 끝났습니다." }],
    ["403", { status: 403, detail: "권한이 없습니다." }],
    ["429", { status: 429, detail: "잠시 후 다시 시도해주세요." }],
    ["500", { status: 500, detail: "알 수 없는 오류가 발생했습니다." }],
    ["503", { status: 503, detail: "서버에 연결할 수 없습니다." }],
    ["끊김", new TypeError("Failed to fetch")],
  ] as const) {
    it(label, async () => {
      reply = r;
      await answer();
      assert.deepEqual(moved, [], "로그인 화면으로 보냈다");
      const shown = r instanceof Error ? connectionLostMessage() : r.detail;
      assert.ok(draw(PLAYING).includes(shown), "오류 문구가 안 보인다");
    });
  }
});
