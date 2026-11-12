/**
 * 문장 상세의 듣기 버튼을 문장 종류(kind)별로 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 지키는 것:
 * - 에러 메시지 문장(kind "error")에는 "문장 듣기" 버튼이 없고, 버튼을 감싸는
 *   줄(empty:hidden div)도 그리지 않는다. 한글 발음(reading)이 있어도 같다.
 * - 에러 메시지라도 제목 고정폭, 해석, 종류 배지, 문제 풀기 버튼은 그대로다.
 * - 그 밖의 종류(expression, phrase, 빈 문자열, null, undefined, 대문자
 *   "ERROR" 처럼 예상 밖 값)는 버튼이 하나 있고 제목은 가변폭이다.
 *   판정은 isErrorSentence 와 같다 - 버튼과 고정폭이 한 판정을 따라 갈리지 않는다.
 * - 문장이 없으면(검수 전 포함) notFound, 0 이 붙은 id 는 정규 주소로 redirect.
 *
 * 하네스: @/lib/api/sentences 를 대역으로 바꿔 페이지 함수를 직접 부르고
 * renderToStaticMarkup 으로 그린다. 대역이 돌려줄 문장은 테스트마다 정한다.
 */
import assert from "node:assert/strict";
import { beforeEach, describe, it, mock } from "node:test";

const { createElement } = await import("react");

mock.module("next/navigation", {
  namedExports: {
    notFound: () => {
      throw new Error("notFound");
    },
    redirect: (to: string) => {
      throw new Error(`redirect ${to}`);
    },
    useRouter: () => ({ back() {}, push() {}, replace() {}, prefetch() {} }),
  },
});

mock.module("next/link", {
  defaultExport: ({ href, children }: { href: string; children?: never }) =>
    createElement("a", { href }, children),
});

type Sentence = Record<string, unknown> | null;
let fixture: Sentence = null;
const calls: string[] = [];

mock.module("@/lib/api/sentences", {
  namedExports: {
    getSentence: async (id: string) => {
      calls.push(id);
      return fixture;
    },
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { isErrorSentence } = await import("@/lib/quiz-text");
const { default: SentenceDetailPage, generateMetadata } = await import(
  "../app/learn/sentences/[id]/page"
);

const ERROR_TEXT = "IntegrityError: UNIQUE constraint failed: vocab_word.term";

function sentence(kind: unknown, extra: Record<string, unknown> = {}): Sentence {
  return {
    id: 42,
    text: ERROR_TEXT,
    reading: "",
    translation: "유일 제약 조건 위반",
    kind,
    kind_label: "종류 표시",
    category: "database",
    category_label: "데이터베이스",
    difficulty: 2,
    difficulty_label: "보통",
    context: "",
    description: "",
    ...extra,
  };
}

async function render(id = "42"): Promise<string> {
  const el = await SentenceDetailPage({
    params: Promise.resolve({ id }),
    searchParams: Promise.resolve({}),
  });
  return renderToStaticMarkup(el);
}

const count = (html: string, needle: string) => html.split(needle).length - 1;
const h1Style = (html: string) => /<h1[^>]*style="([^"]*)"/.exec(html)?.[1] ?? "";

beforeEach(() => {
  fixture = null;
  calls.length = 0;
});

describe("에러 메시지 문장", () => {
  it("듣기 버튼이 없다", async () => {
    fixture = sentence("error");
    const html = await render();
    assert.equal(count(html, 'aria-label="문장 듣기"'), 0);
    assert.doesNotMatch(html, /<button/, "히어로 안에 다른 버튼도 남지 않는다");
  });

  it("버튼 줄(empty:hidden div)을 그리지 않는다", async () => {
    fixture = sentence("error");
    assert.doesNotMatch(await render(), /empty:hidden/);
  });

  it("한글 발음이 있어도 버튼과 버튼 줄이 없고 발음은 보인다", async () => {
    fixture = sentence("error", { reading: "인테그리티 에러" });
    const html = await render();
    assert.doesNotMatch(html, /aria-label="문장 듣기"/);
    assert.doesNotMatch(html, /empty:hidden/);
    assert.match(html, /인테그리티 에러/);
  });

  it("제목 고정폭과 나머지 표시는 그대로다", async () => {
    fixture = sentence("error", { kind_label: "에러 메시지" });
    const html = await render();
    assert.match(h1Style(html), /font-family:var\(--font-mono\)/);
    assert.match(html, /UNIQUE/);
    assert.match(html, /유일 제약 조건 위반/);
    assert.match(html, /에러 메시지/);
    assert.match(html, /데이터베이스/);
    assert.match(html, /이 문장으로 문제 풀기/);
    assert.match(html, /item=42/);
  });
});

describe("에러가 아닌 문장", () => {
  const cases: Array<[string, unknown]> = [
    ["expression", "expression"],
    ["phrase", "phrase"],
    ["빈 문자열", ""],
    ["null", null],
    ["undefined", undefined],
    ["대문자 ERROR", "ERROR"],
    ["앞뒤 공백 error", " error "],
  ];

  for (const [name, kind] of cases) {
    it(`${name}: 듣기 버튼이 하나 있고 제목은 가변폭이다`, async () => {
      fixture = sentence(kind);
      const html = await render();
      assert.equal(count(html, 'aria-label="문장 듣기"'), 1);
      assert.equal(count(html, "empty:hidden"), 1);
      assert.match(h1Style(html), /font-family:var\(--font-sans\)/);
    });
  }

  it("버튼과 고정폭은 isErrorSentence 하나를 따라 갈린다", async () => {
    for (const kind of ["error", "expression", "", null, undefined, "ERROR", "Error"]) {
      fixture = sentence(kind);
      const html = await render();
      const hasButton = html.includes('aria-label="문장 듣기"');
      const mono = h1Style(html).includes("var(--font-mono)");
      const err = isErrorSentence(kind as string | null | undefined);
      assert.equal(hasButton, !err, `kind=${String(kind)} 버튼`);
      assert.equal(mono, err, `kind=${String(kind)} 고정폭`);
    }
  });
});

describe("문장이 없는 경로", () => {
  it("문장이 없으면 notFound", async () => {
    fixture = null;
    await assert.rejects(render("42"), /notFound/);
  });

  it("0 이 붙은 id 는 문장을 부르기 전에 정규 주소로 redirect", async () => {
    fixture = sentence("error");
    await assert.rejects(render("0042"), /redirect .*\/42/);
    assert.equal(calls.length, 0);
  });

  it("문장이 없으면 메타 제목이 찾을 수 없음이다", async () => {
    fixture = null;
    const meta = await generateMetadata({
      params: Promise.resolve({ id: "42" }),
      searchParams: Promise.resolve({}),
    });
    assert.match(String(meta.title), /찾을 수 없습니다/);
  });
});
