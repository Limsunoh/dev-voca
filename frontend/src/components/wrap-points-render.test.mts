/**
 * 지문·해설 문장·보기가 줄바꿈 자리(<wbr>)와 줄 고르기 클래스를 받아
 * 그려지는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 문제풀기(QuizBoard)와 한 판·일일공부·복습(QuestionCard) 두 곳이다. 두
 * 화면에서 긴 URL·경로 지문이 "de|mo.git" 처럼 낱말 가운데서 끊겼다.
 *
 * 보는 것:
 * - 지문(설명 문제 포함)과 해설 카드 문장의 긴 덩어리(21자 이상)에 <wbr>
 *   가 들어가고, 짧은 덩어리("node.js")에는 안 들어간다. 자리 규칙 자체는
 *   lib/wrap-points.edge.test.mts 가 본다.
 * - wbr 를 빼면 화면 글자가 원문과 같다.
 * - 보기에는 wbr 를 넣지 않고 text-pretty 만, QuizBoard 지문에는 text-balance.
 *
 * QuizBoard 를 그리는 법은 quiz-board-fonts.test.mts 와 같다 - react 훅
 * 넷을 작은 대역으로 바꿔 함수로 부르고, 첫 문제 effect 를 손으로 돌린다.
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

function render() {
  cursor = 0;
  effects = [];
  return QuizBoard({ content: "words" });
}

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

async function settle() {
  for (let i = 0; i < 5; i++) await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
}

function question(kind: string, prompt: string, choices: string[], sentenceKind?: string) {
  return {
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
}

async function board(kind: string, prompt: string, choices: string[], sentenceKind?: string) {
  served = question(kind, prompt, choices, sentenceKind);
  render();
  const load = effects.filter((e) => e.deps?.length === 1 && typeof e.deps[0] === "function");
  assert.equal(load.length, 1, "첫 문제를 부르는 effect 를 못 찾았다");
  load[0].run();
  await settle();
  const html = renderToStaticMarkup(render() as never);
  assert.doesNotMatch(html, /가져오는 중|불러오지 못했/, "문제를 받지 못했다");
  return html;
}

function card(kind: string, prompt: string, choices: string[], sentenceKind?: string) {
  return renderToStaticMarkup(
    createElement(QuestionCard, {
      question: question(kind, prompt, choices, sentenceKind) as never,
      busy: false,
      onPick: () => {},
    }),
  );
}

/**
 * wbr 를 걷어낸 HTML 에서 text 를 찾아 그 글을 감싼 여는 태그와, 원래
 * HTML 에서 그 자리의 글(wbr 포함)을 돌려준다. 한 번만 나와야 한다.
 */
function find(html: string, text: string): { tag: string; inner: string } {
  const re = new RegExp(
    ">(" +
      [...text]
        .map((ch) => ch.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
        .join("(?:<wbr/>)?") +
      ")<",
    "g",
  );
  const hits = [...html.matchAll(re)];
  assert.equal(hits.length, 1, `${text} 가 ${hits.length}번 나온다`);
  const at = hits[0].index!;
  return { tag: html.slice(html.lastIndexOf("<", at), at + 1), inner: hits[0][1] };
}

const classes = (tag: string) => (/class="([^"]*)"/.exec(tag)?.[1] ?? "").split(/\s+/);

const URL = "https://github.com/acme/demo.git";
const URL_WBR = "https://<wbr/>github<wbr/>.com/<wbr/>acme/<wbr/>demo<wbr/>.git";

describe("QuizBoard 지문", () => {
  it("용어·한글·설명·문장 지문 모두 긴 덩어리에 wbr, 빼면 원문, text-balance", async () => {
    const cases: [string, string, string?][] = [
      ["meaning", URL],
      ["term", `저장소 주소 ${URL}`],
      ["description", `여러 줄 설명\n주소는 ${URL} 이다`],
      ["blank", `git clone ____ ${URL}`, "phrase"],
      ["situation", `fatal: repository '${URL}' not found`, "error"],
    ];
    for (const [kind, prompt, sk] of cases) {
      const html = await board(kind, prompt, ["a", "b"], sk);
      const { tag, inner } = find(html, prompt.replace(/'/g, "&#x27;"));
      assert.ok(inner.includes(URL_WBR), `${kind}: ${inner}`);
      assert.equal(inner.replace(/<wbr\/>/g, ""), prompt.replace(/'/g, "&#x27;"), kind);
      assert.ok(classes(tag).includes("text-balance"), `${kind}: ${tag}`);
    }
  });

  it("빈칸 문제 지문의 '____' 와 문장 끝 마침표는 건드리지 않는다", async () => {
    const prompt = "I ran ____ before push.";
    const html = await board("blank", prompt, ["git fetch", "git stash"], "phrase");
    const { inner } = find(html, prompt);
    assert.equal(inner, prompt);
  });

  it("짧은 용어 지문(node.js)은 wbr 없이, 글꼴 규칙과 text-balance 는 그대로", async () => {
    const html = await board("meaning", "node.js", ["자바스크립트 런타임", "b"]);
    const { tag, inner } = find(html, "node.js");
    assert.equal(inner, "node.js");
    assert.ok(classes(tag).includes("font-mono"), tag);
    assert.ok(classes(tag).includes("text-balance"), tag);
    assert.match(tag, /lang="en"/);
  });

  it("긴 에러 이름 지문은 대문자 앞에서도 끊는다", async () => {
    const prompt = "java.lang.UnsupportedClassVersionError: bad class";
    const html = await board("situation", prompt, ["a", "b"], "error");
    const { tag, inner } = find(html, prompt);
    assert.equal(
      inner,
      "java<wbr/>.lang<wbr/>.Unsupported<wbr/>Class<wbr/>Version<wbr/>Error: bad class",
    );
    assert.ok(classes(tag).includes("font-mono"), tag);
  });
});

describe("QuizBoard 보기", () => {
  it("보기는 text-pretty 를 받고 wbr 는 안 들어간다(긴 경로라도)", async () => {
    const texts = ["src/components/QuizBoard.tsx", "package.json"];
    const html = await board("term", "설정 파일", texts);
    for (const t of texts) {
      const { tag, inner } = find(html, t);
      assert.equal(inner, t, "보기에 wbr 가 들어갔다");
      assert.ok(classes(tag).includes("text-pretty"), tag);
      assert.ok(classes(tag).includes("min-w-0"), tag);
    }
  });
});

describe("QuizBoard 해설 카드 문장", () => {
  type Node = { props?: Record<string, unknown> };
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

  it("정답 문장에 wbr 가 들어가고 빼면 원문, 해석·상황은 그대로", async () => {
    await board("situation", "Prompt sentence here", ["배포할 때", "리뷰할 때"], "error");
    const button = choiceNamed(render(), "배포할 때");
    assert.ok(button, "보기 버튼을 못 찾았다");
    const text = `fatal: unable to access ${URL}/`;
    served = {
      correct: true,
      answer_id: 1,
      answer_type: "sentence",
      sentence: {
        id: 1,
        text,
        reading: "",
        translation: "see/docs/for/details/about/this.Thing",
        context: "deploy/staging/production/rollback.Now",
        description: "",
        kind: "error",
        kind_label: "종류",
        category: "git",
      },
    };
    (button.props!.onClick as () => void)();
    await settle();
    const html = renderToStaticMarkup(render() as never);
    assert.match(html, /맞았습니다/, "채점 결과가 안 그려졌다");
    const { tag, inner } = find(html, text);
    assert.ok(inner.includes(URL_WBR), inner);
    assert.equal(inner.replace(/<wbr\/>/g, ""), text);
    assert.ok(classes(tag).includes("font-mono"), tag);
    // 해석·상황에는 적용하지 않았다(긴 덩어리라도).
    for (const t of ["see/docs/for/details/about/this.Thing", "deploy/staging/production/rollback.Now"]) {
      assert.equal(find(html, t).inner, t);
    }
  });
});

describe("QuestionCard (한 판·일일공부·복습)", () => {
  it("모든 유형의 지문에서 긴 덩어리에 wbr 가 들어가고 빼면 원문", () => {
    const kinds: [string, string?][] = [
      ["meaning"], ["term"], ["description"], ["blank", "error"], ["situation", "phrase"], ["error"],
    ];
    for (const [kind, sk] of kinds) {
      const prompt = `see ${URL} now`;
      const { inner } = find(card(kind, prompt, ["a"], sk), prompt);
      assert.equal(inner, `see ${URL_WBR} now`, kind);
    }
  });

  it("짧은 덩어리 지문은 그대로", () => {
    for (const kind of ["meaning", "term", "situation"]) {
      const prompt = "Bind for 0.0.0.0:8080 failed: src/app.py v2.0.0";
      const { inner } = find(card(kind, prompt, ["a"]), prompt);
      assert.equal(inner, prompt, kind);
    }
  });

  it("설명 문제 지문: 줄바꿈 유지하며 긴 덩어리에 wbr", () => {
    const prompt = `여러 커밋을\n하나로 합친다. 예: ${URL}`;
    const { tag, inner } = find(card("description", prompt, ["squash"]), prompt);
    assert.equal(inner, `여러 커밋을\n하나로 합친다. 예: ${URL_WBR}`);
    assert.ok(classes(tag).includes("whitespace-pre-line"));
  });

  it("보기 버튼은 text-pretty 를 받고 wbr 는 안 들어간다(긴 경로라도)", () => {
    for (const kind of ["meaning", "term", "situation"]) {
      const texts = ["src/components/QuizBoard.tsx", "첫 번째 보기."];
      const html = card(kind, "지문", texts);
      for (const t of texts) {
        const { tag, inner } = find(html, t);
        assert.equal(inner, t, `${kind}: 보기에 wbr 가 들어갔다`);
        assert.match(tag, /^<button/, tag);
        assert.ok(classes(tag).includes("text-pretty"), `${kind}: ${tag}`);
      }
    }
  });

  it("QuestionCard 지문에는 text-balance 를 붙이지 않았다(왼쪽 정렬)", () => {
    const { tag } = find(card("term", "한글 지문", ["a"]), "한글 지문");
    assert.ok(!classes(tag).includes("text-balance"), tag);
  });
});
