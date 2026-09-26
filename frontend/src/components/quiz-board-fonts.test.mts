/**
 * 문제풀기(QuizBoard)가 유형별로 지문과 보기를 **실제로** 어떤 글꼴로
 * 그리는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 한글을 고정폭으로 그리면 고정폭 글꼴(JetBrains Mono)에 한글이 없어 OS
 * 글꼴로 굵고 뭉툭하게 떨어진다. 그래서 용어만 고정폭 + lang="en" 이고,
 * 한글(뜻·설명·상황)은 본문체다(lib/quiz-text 의 표).
 *
 * **원문을 정규식으로 보지 않는다.** "choicesAreTerms 를 부르는가" 만 보면
 * ChoiceButton 이 mono 를 받고도 안 쓰거나, lang 을 빼먹거나, Prompt 가
 * 다른 가지로 새는 것을 못 잡는다. 여기서는 판을 한 번 그려 HTML 에서
 * 글자를 감싼 태그를 뽑는다.
 *
 * QuizBoard 는 첫 문제를 effect 에서 받아온다. 브라우저가 없어 effect 가
 * 돌지 않으므로 quiz-board-item.test.mts 와 같은 방법을 쓴다 - react 의 훅
 * 넷만 작은 대역으로 바꿔 QuizBoard 를 함수로 부르고, 첫 문제 effect 를
 * 손으로 돌린 뒤 한 번 더 그려 돌려받은 트리를 renderToStaticMarkup 한다.
 *
 * 한 판·일일공부·복습(QuestionCard)과 같은 규칙인지도 여기서 나란히 본다.
 * 두 화면이 따로 정하던 때 서로 달랐다.
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
const { QuestionCard } = await import("./QuestionCard");
const { createElement } = await import("react");
const { renderToStaticMarkup } = await import("react-dom/server");

type Board = ReturnType<typeof QuizBoard>;

function render(): Board {
  cursor = 0;
  effects = [];
  return QuizBoard({ content: "words" });
}

/** 서버가 돌려줄 문제. 테스트마다 바꾼다. */
let served: unknown = null;

const realFetch = globalThis.fetch;
const realWindow = (globalThis as { window?: unknown }).window;
after(() => {
  globalThis.fetch = realFetch;
  (globalThis as { window?: unknown }).window = realWindow;
});

beforeEach(() => {
  slots = [];
  (globalThis as { window?: unknown }).window = { scrollTo() {} };
  globalThis.fetch = (async () =>
    ({ ok: true, status: 200, json: async () => served }) as Response) as typeof fetch;
});

/** 이 문제를 받아온 뒤의 판을 HTML 로. */
async function board(
  kind: string,
  prompt: string,
  choices: string[],
  sentenceKind?: string,
): Promise<string> {
  served = {
    kind,
    kind_label: "유형이름",
    question: "무엇일까?",
    prompt,
    category: "git",
    category_label: "Git",
    choices: choices.map((text, i) => ({ id: i + 1, text })),
    token: "t",
    ...(sentenceKind === undefined ? {} : { sentence_kind: sentenceKind }),
  };
  render();
  const load = effects.filter(
    (e) => e.deps?.length === 1 && typeof e.deps[0] === "function",
  );
  assert.equal(load.length, 1, "첫 문제를 부르는 effect 를 못 찾았다");
  load[0].run();
  for (let i = 0; i < 5; i++) await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));

  const html = renderToStaticMarkup(render() as never);
  // 문제를 못 받았으면 아래 검사가 전부 엉뚱한 이유로 실패한다. 먼저 끊는다.
  assert.doesNotMatch(html, /가져오는 중|불러오지 못했/, "문제를 받지 못했다");
  return html;
}

function card(
  kind: string,
  prompt: string,
  choices: string[],
  sentenceKind?: string,
): string {
  const question = {
    kind,
    kind_label: "유형이름",
    question: "무엇일까?",
    prompt,
    category: "git",
    category_label: "Git",
    choices: choices.map((text, i) => ({ id: i + 1, text })),
    ...(sentenceKind === undefined ? {} : { sentence_kind: sentenceKind }),
  };
  return renderToStaticMarkup(
    createElement(QuestionCard, {
      question: question as never,
      busy: false,
      onPick: () => {},
    }),
  );
}

/** 이 글자를 바로 감싼 여는 태그. 글자가 한 번만 나와야 한다. */
function tagOf(html: string, text: string): string {
  const at = html.indexOf(`>${text}<`);
  assert.ok(at >= 0, `${text} 를 감싼 태그를 못 찾았다`);
  assert.equal(html.indexOf(`>${text}<`, at + 1), -1, `${text} 가 두 번 나온다`);
  return html.slice(html.lastIndexOf("<", at), at + 1);
}

type Look = { mono: boolean; en: boolean };

/** 태그 하나의 글꼴과 lang. class 의 낱말 단위로 본다. */
function look(tag: string): Look {
  const cls = /class="([^"]*)"/.exec(tag)?.[1] ?? "";
  return {
    mono: cls.split(/\s+/).includes("font-mono"),
    en: /\slang="en"/.test(tag),
  };
}

const TERM: Look = { mono: true, en: true };
const BODY: Look = { mono: false, en: false };

/** 보기 태그에는 고정폭·lang 이 늘 짝으로 간다. 하나만 붙으면 안 된다. */
function choiceLooks(html: string, texts: string[]): Look[] {
  return texts.map((t) => look(tagOf(html, t)));
}

describe("QuizBoard 지문", () => {
  it("뜻 고르기: 용어 지문은 고정폭 + lang=en", async () => {
    const html = await board("meaning", "rebase", ["커밋을 옮기기", "합치기"]);
    assert.deepEqual(look(tagOf(html, "rebase")), TERM);
  });

  it("단어 고르기: 한글 뜻 지문은 본문체, lang 없음", async () => {
    const html = await board("term", "원격 저장소의 변경을 가져오기", ["fetch", "push"]);
    assert.deepEqual(look(tagOf(html, "원격 저장소의 변경을 가져오기")), BODY);
  });

  it("설명 문제: 본문체이고 줄바꿈을 살린다", async () => {
    const html = await board("description", "여러 커밋을\n하나로 합친다", ["squash", "merge"]);
    const tag = tagOf(html, "여러 커밋을\n하나로 합친다");
    assert.deepEqual(look(tag), BODY);
    assert.match(tag, /whitespace-pre-line/);
  });

  // 문장 지문은 문장 종류로 가른다(lib/quiz-text 의 promptIsMono). 에러
  // 메시지만 고정폭이고, 실무 표현과 종류를 모르는 문장은 본문체다. 어느
  // 쪽이든 영어라 lang=en 은 붙는다.
  const SENTENCE_BODY: Look = { mono: false, en: true };

  it("빈칸·상황: 에러 메시지 문장 지문은 고정폭 + lang=en", async () => {
    let html = await board("blank", "fatal: ____ unrelated histories", ["refusing to merge", "x"], "error");
    assert.deepEqual(look(tagOf(html, "fatal: ____ unrelated histories")), TERM);
    html = await board("situation", "error: failed to push some refs", ["push 가 거부될 때", "배포할 때"], "error");
    assert.deepEqual(look(tagOf(html, "error: failed to push some refs")), TERM);
  });

  it("빈칸·상황: 실무 표현 문장 지문은 본문체 + lang=en", async () => {
    let html = await board("blank", "I ran ____ before push.", ["git fetch", "git stash"], "phrase");
    assert.deepEqual(look(tagOf(html, "I ran ____ before push.")), SENTENCE_BODY);
    html = await board("situation", "Can you rebase onto main?", ["리뷰 전에", "배포할 때"], "phrase");
    assert.deepEqual(look(tagOf(html, "Can you rebase onto main?")), SENTENCE_BODY);
  });

  it("빈칸·상황: 문장 종류가 없으면 본문체다(옛 응답)", async () => {
    const html = await board("situation", "Can you rebase onto main?", ["리뷰 전에", "배포할 때"]);
    assert.deepEqual(look(tagOf(html, "Can you rebase onto main?")), SENTENCE_BODY);
  });

  it("모르는 유형: 지문을 고정폭으로 그리지 않는다", async () => {
    // 에러 메시지 사전 같은 새 유형이 먼저 서버에 붙을 수 있다. 한글이 올지
    // 모르니 본문체가 안전하다.
    const html = await board("error", "커밋 전에 보이는 경고", ["a", "b"]);
    assert.deepEqual(look(tagOf(html, "커밋 전에 보이는 경고")), BODY);
  });

  it("유형 이름은 대소문자까지 맞아야 용어로 본다", async () => {
    const html = await board("Meaning", "rebase", ["x", "y"]);
    assert.deepEqual(look(tagOf(html, "rebase")), BODY);
  });
});

describe("QuizBoard 보기", () => {
  it("뜻 고르기: 한글 뜻 보기는 본문체", async () => {
    const texts = ["커밋을 옮기기", "HEAD 를 옮기기"];
    const html = await board("meaning", "rebase", texts);
    assert.deepEqual(choiceLooks(html, texts), [BODY, BODY]);
  });

  it("단어·설명·빈칸: 용어 보기는 전부 고정폭 + lang=en", async () => {
    for (const kind of ["term", "description", "blank"]) {
      const texts = ["fetch", "cherry-pick", "git stash"];
      const html = await board(kind, `지문-${kind}`, texts);
      assert.deepEqual(choiceLooks(html, texts), [TERM, TERM, TERM], kind);
    }
  });

  it("상황 고르기: 한글·영어가 섞인 보기도 본문체", async () => {
    // 실제 상황 보기 380개 중 172개가 "git push 할 때" 처럼 영어가 섞였다.
    // 글자가 아니라 유형으로 가른다 - 영어가 끼었다고 고정폭으로 가면
    // 한글이 뭉개진다.
    const texts = ["git push 할 때", "PR 리뷰에서", "CI 로그"];
    const html = await board("situation", "It's up to date.", texts);
    assert.deepEqual(choiceLooks(html, texts), [BODY, BODY, BODY]);
  });

  it("모르는 유형: 보기를 고정폭으로 그리지 않는다", async () => {
    const texts = ["경고를 끈다", "npm audit"];
    const html = await board("error", "지문", texts);
    assert.deepEqual(choiceLooks(html, texts), [BODY, BODY]);
  });

  it("보기가 비어도 지문은 그리고 보기 버튼은 없다", async () => {
    const html = await board("term", "빈 보기 지문", []);
    assert.deepEqual(look(tagOf(html, "빈 보기 지문")), BODY);
    // 판 안의 버튼은 보기와 "다음 문제" 뿐이고, 고르기 전이라 다음 문제도 없다.
    assert.doesNotMatch(html, /<button/);
  });

  it("글자가 빈 보기도 그 유형의 글꼴을 받는다", async () => {
    const html = await board("blank", "빈 글자 지문", [""]);
    const span = /<span[^>]*class="min-w-0[^"]*"[^>]*><\/span>/.exec(html);
    assert.ok(span, "빈 보기 칸을 못 찾았다");
    assert.deepEqual(look(span[0]), TERM);
  });
});

describe("QuestionCard 와 QuizBoard 가 같은 규칙을 쓴다", () => {
  const KINDS = ["meaning", "term", "description", "blank", "situation", "error", ""];

  it("보기: 유형마다 두 화면의 글꼴·lang 이 같다", async () => {
    for (const kind of KINDS) {
      const texts = ["보기가 무엇이든", "anything"];
      const fromBoard = choiceLooks(await board(kind, "지문", texts), texts);
      const fromCard = choiceLooks(card(kind, "지문", texts), texts);
      assert.deepEqual(fromCard, fromBoard, `유형 "${kind}"`);
    }
  });

  it("지문: 용어·한글 지문은 두 화면이 같다", async () => {
    // 문장 지문(blank·situation)은 아래 "문장 지문: ... 같은 규칙" 에서 본다.
    for (const kind of ["meaning", "term", "description", "error"]) {
      const fromBoard = look(tagOf(await board(kind, "지문글자", ["a"]), "지문글자"));
      const fromCard = look(tagOf(card(kind, "지문글자", ["a"]), "지문글자"));
      assert.deepEqual(fromCard, fromBoard, `유형 "${kind}"`);
    }
  });
});

describe("QuizBoard 문장 지문 - 문장 종류의 경계값", () => {
  const SENTENCE_BODY: Look = { mono: false, en: true };

  it("빈 문자열·모르는 값(ERROR·code·Error)은 본문체", async () => {
    for (const kind of ["blank", "situation"]) {
      for (const sk of ["", "ERROR", "code", "Error", " error"]) {
        const text = `It broke ${kind} [${sk}]`;
        const html = await board(kind, text, ["a", "b"], sk);
        assert.deepEqual(look(tagOf(html, text)), SENTENCE_BODY, `${kind} "${sk}"`);
      }
    }
  });

  it("뜻 고르기 용어 지문은 문장 종류가 붙어 와도 고정폭", async () => {
    for (const sk of ["phrase", "", "code"]) {
      const html = await board("meaning", "rebase", ["옮기기", "합치기"], sk);
      assert.deepEqual(look(tagOf(html, "rebase")), TERM, sk);
    }
  });

  it("단어 고르기·설명 지문은 error 가 붙어 와도 본문체", async () => {
    for (const kind of ["term", "description"]) {
      const html = await board(kind, "한글 지문", ["fetch", "push"], "error");
      assert.deepEqual(look(tagOf(html, "한글 지문")), BODY, kind);
    }
  });

  it("고정폭이면 자간을 한 단계 더 좁히고, 본문체면 되돌린다", async () => {
    const styleOf = (tag: string) => /style="([^"]*)"/.exec(tag)?.[1] ?? "";
    let html = await board("blank", "fatal: ____ here", ["a", "b"], "error");
    assert.match(styleOf(tagOf(html, "fatal: ____ here")), /letter-spacing:var\(--tracking-tighter\)/);
    html = await board("blank", "Please ____ here", ["a", "b"], "phrase");
    assert.match(styleOf(tagOf(html, "Please ____ here")), /letter-spacing:var\(--tracking-tight\)/);
  });
});

describe("문장 지문: QuestionCard 와 QuizBoard 가 같은 규칙", () => {
  it("문장 종류마다 두 화면의 글꼴·lang 이 같다", async () => {
    for (const kind of ["blank", "situation"]) {
      for (const sk of ["error", "phrase", "", "ERROR", undefined]) {
        const text = `same rule ${kind} ${String(sk)}`;
        const fromBoard = look(tagOf(await board(kind, text, ["a"], sk), text));
        const fromCard = look(tagOf(card(kind, text, ["a"], sk), text));
        assert.deepEqual(fromCard, fromBoard, `${kind} ${String(sk)}`);
      }
    }
  });
});

/*
 * 해설 카드(SentenceAnswer). 상황 고르기를 채점하면 정답 문장을 다시
 * 보여 주는데, 그 문장의 글꼴도 채점 응답의 sentence.kind 로 가른다.
 * 보기 버튼의 onClick 을 트리에서 찾아 눌러 채점 응답을 받게 한다.
 */
describe("QuizBoard 해설 카드의 문장", () => {
  type Node = { type?: unknown; props?: Record<string, unknown> };

  /** 트리에서 text 가 이 글자인 보기 버튼 요소. */
  function choiceNamed(node: unknown, text: string): Node | null {
    if (!node || typeof node !== "object") return null;
    if (Array.isArray(node)) {
      for (const child of node) {
        const hit = choiceNamed(child, text);
        if (hit) return hit;
      }
      return null;
    }
    const el = node as Node;
    if (el.props?.text === text && typeof el.props.onClick === "function") return el;
    return choiceNamed(el.props?.children, text);
  }

  async function graded(sentenceKind: string | undefined, text: string): Promise<string> {
    await board("situation", "Prompt sentence here.", ["배포할 때", "리뷰할 때"], sentenceKind);
    const button = choiceNamed(render(), "배포할 때");
    assert.ok(button, "보기 버튼을 못 찾았다");
    served = {
      correct: true,
      answer_id: 1,
      answer_type: "sentence",
      sentence: {
        id: 1,
        text,
        reading: "",
        translation: "해석",
        context: "배포할 때",
        description: "",
        ...(sentenceKind === undefined ? {} : { kind: sentenceKind }),
        kind_label: "종류",
        category: "git",
      },
    };
    (button.props!.onClick as () => void)();
    for (let i = 0; i < 5; i++) await Promise.resolve();
    await new Promise((r) => setTimeout(r, 0));
    const html = renderToStaticMarkup(render() as never);
    assert.match(html, /맞았습니다/, "채점 결과가 안 그려졌다");
    return html;
  }

  it("에러 메시지 문장은 고정폭 + lang=en", async () => {
    const html = await graded("error", "fatal: refusing unrelated histories");
    assert.deepEqual(look(tagOf(html, "fatal: refusing unrelated histories")), TERM);
  });

  it("실무 표현·빈 값·없음·모르는 값은 본문체 + lang=en", async () => {
    for (const sk of ["phrase", "", undefined, "ERROR", "code"]) {
      const text = `Could you take a look ${String(sk)}?`;
      const html = await graded(sk, text);
      assert.deepEqual(look(tagOf(html, text)), { mono: false, en: true }, String(sk));
    }
  });
});
