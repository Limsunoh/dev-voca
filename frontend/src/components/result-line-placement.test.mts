/**
 * 일일공부·복습에서 "앞 문제" 결과 줄이 문제 **위**에 서는지, 다음 묶음을
 * 익히기 전에는 다음 문제가 **안 보이는지** 실제로 그려서 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 결함 둘이다.
 *
 *   결과 줄이 문제 아래   답하면 곧바로 다음 문제가 뜨는 화면이라, 아래에
 *                        두면 방금 답의 결과가 새 문제의 답처럼 읽혔다
 *   익히기 전 문제 노출   보기만 잠가 두면 아직 안 배운 단어의 문제와 보기가
 *                        다 보여서, 익히기 전에 답을 훑어볼 수 있었다
 *
 * 둘 다 결과가 **답한 뒤에만** 생기는 상태라, 첫 화면만 그려서는 안 보인다.
 * 그래서 quiz-board-item.test.mts 와 같은 방식으로 react 의 훅 셋(useState·
 * useRef·useEffect)만 작은 대역으로 바꾸고, 보드가 넘긴 onPick·onStart 를
 * 진짜로 불러 답한 뒤의 상태를 만든다. 그 상태로 react-dom/server 가 그린
 * 글자를 본다. 보드 아래의 조각들(PlayCard·QuestionCard·WrongAnswer·
 * Reaction·Burst)은 훅을 안 써서 대역과 부딪히지 않는다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

import type { DailyAnswered, DailyStatus, StudyCard, StudyProgress } from "@/lib/api/daily";
import type { RoundQuestion } from "@/lib/api/rounds";
import type { ReviewAnswered, ReviewQuestion, ReviewStarted } from "@/lib/api/review";

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
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { createElement } = realReact;
const { DailyStudyBoard } = await import("./DailyStudyBoard");
const { ReviewBoard } = await import("./ReviewBoard");

/* ---- 대역 ---- */

const realFetch = globalThis.fetch;
after(() => {
  globalThis.fetch = realFetch;
});

/** 차례로 돌려줄 응답 본문. */
let replies: unknown[] = [];

beforeEach(() => {
  slots = [];
  replies = [];
  globalThis.fetch = (async () => {
    const body = replies.shift();
    assert.ok(body, "준비한 것보다 요청이 많다");
    return { ok: true, status: 200, json: async () => body } as Response;
  }) as typeof fetch;
});

/** 보드를 한 번 부르고, 돌려준 트리에서 본문 가지(overlays 다음)를 꺼낸다. */
function branch(board: () => unknown): { props: Record<string, unknown> } {
  cursor = 0;
  effects = [];
  const tree = board() as { props: { children: unknown[] } };
  for (const run of effects) run();
  return tree.props.children[1] as { props: Record<string, unknown> };
}

/** 같은 훅 칸으로 실제로 그린다. */
function draw(element: unknown): string {
  cursor = 0;
  return renderToStaticMarkup(element as never);
}

/** 응답을 기다린다. fetch -> json 두 번이다. */
async function settle() {
  for (let i = 0; i < 5; i++) await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
}

/** 결과 줄. aria-live 인 <p> 하나다. */
function resultLine(html: string): { at: number; inner: string; open: string } {
  const all = [...html.matchAll(/<p([^>]*aria-live="polite"[^>]*)>([\s\S]*?)<\/p>/g)];
  assert.equal(all.length, 1, "결과 줄은 하나여야 한다");
  const [whole, attrs, inner] = all[0];
  // 두 번째 답부터 바뀐 부분만 읽히면 "앞 문제" 가 빠진다.
  assert.match(attrs, /aria-atomic="true"/, "결과 줄 전체를 읽혀야 한다");
  return { at: html.indexOf(whole), inner, open: attrs };
}

/** 보기 버튼 개수. QuestionCard 만 <li><button 으로 그린다. */
const choiceButtons = (html: string) => (html.match(/<li><button/g) ?? []).length;

/* ---- 자료 ---- */

function question(prompt: string, base: number): RoundQuestion {
  return {
    kind: "meaning",
    kind_label: "뜻 고르기",
    question: `질문-${prompt}`,
    prompt,
    category: "git",
    category_label: "Git",
    choices: [0, 1, 2, 3].map((i) => ({ id: base + i, text: `보기-${prompt}-${i}` })),
  };
}

const FIRST = question("commit", 10);
const NEXT = question("rebase", 20);

function progress(answered: number): StudyProgress {
  return {
    length: "5m",
    total: 10,
    answered,
    correct: 0,
    score: 0,
    bonus: 0,
    done: false,
    chunk_size: 3,
    chunk_count: 2,
    chunk_index: 0,
  };
}

const CARD: StudyCard = {
  id: 1,
  term: "cherry-pick",
  pronunciation: "",
  reading: "",
  meaning: "골라 가져오기",
  description: "",
  example: "",
  example_translation: "",
  category_label: "Git",
};

const PLAYING: DailyStatus = {
  lengths: [],
  today: progress(0),
  token: "tok-1",
  question: FIRST,
  learning: [],
};

function dailyAnswer(correct: boolean, learning: StudyCard[] = []): DailyAnswered {
  return {
    result: {
      correct,
      skipped: false,
      in_time: true,
      score: correct ? 1 : 0,
      elapsed_ms: 1000,
      answer_type: "word",
      answer_text: "commit",
      answer_extra: "변경을 기록하기",
    },
    token: "tok-2",
    question: NEXT,
    finished: false,
    study: progress(1),
    learning,
  };
}

/* ---- 일일공부 ---- */

describe("일일공부 결과 줄", () => {
  const board = () => DailyStudyBoard({ status: PLAYING });

  /** 첫 문제에 답한 뒤의 화면. */
  async function afterAnswer(reply: DailyAnswered): Promise<string> {
    const play = branch(board);
    replies = [reply];
    await (play.props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    return draw(createElement(DailyStudyBoard, { status: PLAYING }));
  }

  it("첫 문제에서는 결과 줄이 비어 있고 높이는 잡혀 있다", () => {
    branch(board);
    const html = draw(createElement(DailyStudyBoard, { status: PLAYING }));
    const line = resultLine(html);
    assert.equal(line.inner, "", "답하기 전인데 무언가 적혀 있다");
    // 비어 있을 때도 두 줄 높이를 잡아야 첫 답에 보기가 밀리지 않는다.
    assert.match(line.open, /min-h-10/);
    assert.equal(choiceButtons(html), 4);
  });

  it("맞히면 '앞 문제 · 정답' 이 다음 문제보다 먼저 온다", async () => {
    const html = await afterAnswer(dailyAnswer(true));
    const line = resultLine(html);
    assert.match(line.inner, /앞 문제 ·[\s\S]*정답/);
    assert.ok(
      line.inner.indexOf("앞 문제") < line.inner.indexOf("정답"),
      "'앞 문제' 가 판정 앞에 붙어야 한다",
    );
    assert.match(line.open, /min-h-10/);
    // 문서 순서상 결과 줄이 다음 문제의 질문·지문·보기보다 앞이다.
    for (const text of [NEXT.question, NEXT.prompt, NEXT.choices[0].text]) {
      const at = html.indexOf(text);
      assert.ok(at > 0, `다음 문제의 "${text}" 가 안 그려졌다`);
      assert.ok(line.at < at, `결과 줄이 "${text}" 보다 뒤에 있다`);
    }
    // 진행 막대와 문제 사이다.
    assert.ok(html.indexOf('role="progressbar"') < line.at);
    assert.equal(choiceButtons(html), 4);
    // 지난 문제는 이미 사라졌다 - 결과가 가리키는 것은 앞 문제다.
    assert.equal(html.includes(FIRST.prompt + "<"), false);
  });

  it("틀리면 결과 줄에 정답과 그 뜻이 나온다", async () => {
    const html = await afterAnswer(dailyAnswer(false));
    const line = resultLine(html);
    assert.match(line.inner, /앞 문제 ·/);
    assert.match(line.inner, /오답 · commit/);
    assert.match(line.inner, /변경을 기록하기/);
    assert.doesNotMatch(line.inner, />정답</);
    assert.ok(line.at < html.indexOf(NEXT.prompt));
  });
});

describe("일일공부 - 다음 묶음을 익히기 전", () => {
  const board = () => DailyStudyBoard({ status: PLAYING });

  async function waiting(correct: boolean): Promise<string> {
    const play = branch(board);
    replies = [dailyAnswer(correct, [CARD])];
    await (play.props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    // 보드가 onLearn 을 넘기는지부터. 없으면 아래 검사가 전부 헛돈다.
    const next = branch(board);
    assert.equal(typeof next.props.onLearn, "function", "학습 대기인데 onLearn 이 없다");
    return draw(createElement(DailyStudyBoard, { status: PLAYING }));
  }

  it("다음 문제의 질문·지문·보기가 하나도 안 그려진다", async () => {
    const html = await waiting(true);
    assert.equal(choiceButtons(html), 0, "보기 버튼이 그려졌다");
    assert.doesNotMatch(html, /<li>/);
    for (const text of [NEXT.question, NEXT.prompt, NEXT.kind_label, ...NEXT.choices.map((c) => c.text)]) {
      assert.equal(html.includes(text), false, `익히기 전인데 "${text}" 가 보인다`);
    }
  });

  it("안내 문장과 '이어서 익히기' 만 있고, 결과 줄은 그대로 남는다", async () => {
    const html = await waiting(false);
    assert.match(html, /다음 문제는 새 단어를 익힌 뒤에 나옵니다\./);
    assert.match(html, /<button[^>]*>이어서 익히기<\/button>/);
    // 누를 수 있는 것은 "이어서 익히기" 하나뿐이다(오류가 없을 때).
    assert.equal((html.match(/<button/g) ?? []).length, 1);
    const line = resultLine(html);
    assert.match(line.inner, /앞 문제 ·[\s\S]*오답 · commit/);
    assert.ok(line.at < html.indexOf("다음 문제는 새 단어를"));
  });

  it("'이어서 익히기' 를 누르면 학습 카드로 가고, 다 넘기면 가려 둔 문제가 뜬다", async () => {
    await waiting(true);
    const play = branch(board);
    (play.props.onLearn as () => void)();
    const study = branch(board);
    assert.equal(typeof study.props.onDone, "function", "학습 카드 가지로 안 갔다");
    (study.props.onDone as () => void)();
    const html = draw(createElement(DailyStudyBoard, { status: PLAYING }));
    assert.equal(choiceButtons(html), 4);
    assert.ok(html.includes(NEXT.prompt));
    // 익히고 돌아오면 앞 문제의 결과는 지운다 - 사이에 학습이 끼었다.
    assert.equal(resultLine(html).inner, "");
    assert.doesNotMatch(html, /다음 문제는 새 단어를/);
  });
});

/* ---- 복습 ---- */

const DUE = { due: 5, round_size: 20, graduate_streak: 2 };

function reviewQuestion(q: RoundQuestion, answered: number): ReviewQuestion {
  return { ...q, answered, total: 5 };
}

const STARTED: ReviewStarted = { token: "r-1", question: reviewQuestion(FIRST, 0) };

function reviewAnswer(correct: boolean): ReviewAnswered {
  return {
    result: {
      correct,
      streak: correct ? 1 : 0,
      graduated: false,
      answer_type: "word",
      answer_text: "commit",
      answer_extra: "변경을 기록하기",
    },
    token: "r-2",
    question: reviewQuestion(NEXT, 1),
    finished: false,
  };
}

describe("복습 결과 줄", () => {
  const board = () => ReviewBoard({ due: DUE });

  async function playing(): Promise<{ props: Record<string, unknown> }> {
    const idle = branch(board);
    replies = [STARTED];
    await (idle.props.onStart as () => Promise<void>)();
    await settle();
    const play = branch(board);
    assert.equal(typeof play.props.onPick, "function", "시작했는데 문제 가지가 아니다");
    return play;
  }

  async function afterAnswer(reply: ReviewAnswered): Promise<string> {
    const play = await playing();
    replies = [reply];
    await (play.props.onPick as (id: number) => Promise<void>)(FIRST.choices[0].id);
    await settle();
    return draw(createElement(ReviewBoard, { due: DUE }));
  }

  it("첫 문제에서는 결과 줄이 비어 있고 높이는 잡혀 있다", async () => {
    await playing();
    const html = draw(createElement(ReviewBoard, { due: DUE }));
    const line = resultLine(html);
    assert.equal(line.inner, "");
    assert.match(line.open, /min-h-10/);
    assert.ok(line.at < html.indexOf(FIRST.prompt));
    assert.equal(choiceButtons(html), 4);
  });

  it("맞히면 '앞 문제 · 정답' 과 남은 횟수가 다음 문제보다 먼저 온다", async () => {
    const html = await afterAnswer(reviewAnswer(true));
    const line = resultLine(html);
    assert.match(line.inner, /앞 문제 ·[\s\S]*정답[\s\S]*한 번 더 맞히면 끝/);
    assert.match(line.open, /min-h-10/);
    for (const text of [NEXT.question, NEXT.prompt, NEXT.choices[0].text]) {
      const at = html.indexOf(text);
      assert.ok(at > 0, `다음 문제의 "${text}" 가 안 그려졌다`);
      assert.ok(line.at < at, `결과 줄이 "${text}" 보다 뒤에 있다`);
    }
    assert.ok(html.indexOf('role="progressbar"') < line.at);
    assert.equal(choiceButtons(html), 4);
  });

  it("틀리면 결과 줄에 정답과 그 뜻이 나온다", async () => {
    const html = await afterAnswer(reviewAnswer(false));
    const line = resultLine(html);
    assert.match(line.inner, /앞 문제 ·[\s\S]*오답 · commit[\s\S]*변경을 기록하기/);
    assert.ok(line.at < html.indexOf(NEXT.prompt));
    // 복습은 학습 대기가 없다 - 보기는 늘 그대로다.
    assert.equal(choiceButtons(html), 4);
  });
});
