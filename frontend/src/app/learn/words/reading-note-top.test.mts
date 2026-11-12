/**
 * 단어 상세 화면에서 "발음 자세히" 가 맨 위 되돌아가기 옆에 그려지는가.
 *
 * 실행: cd frontend && npm test
 *
 * detail-head.test.mts 는 컴포넌트만 따로 그린다. 여기서는 페이지 전체를 그려,
 * 페이지가 그 컴포넌트를 실제로 쓰고 발음 설명(reading_note)을 넘기는지 본다.
 * 되돌아가기가 "단어장" 일 때(목록에서 옴)와 "홈" 일 때(홈의 오늘의 단어에서 옴)
 * 둘 다 본다.
 *
 * getWord 는 대역이다. 보려는 것은 페이지가 받은 단어로 무엇을 그리는가다.
 */
import assert from "node:assert/strict";
import { describe, it, mock } from "node:test";

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

const { createElement } = await import("react");

mock.module("next/link", {
  defaultExport: ({ href, children }: { href: string; children?: never }) =>
    createElement("a", { href }, children),
});

const NOTE = "sl 은 s 뒤에 혀끝을 붙인 l 이 바로 이어진다.";

const word = (id: number, note: string) => ({
  id,
  term: `term-${id}`,
  pronunciation: "/ˈsloʊ ˌkwɪri/",
  reading: "",
  reading_note: note,
  meaning: `뜻-${id}`,
  category: "database",
  category_label: "데이터베이스",
  difficulty: 1,
  difficulty_label: "쉬움",
  is_exam: false,
  exam_subject: "",
  exam_subject_label: "",
  description: "설명",
  example: "",
  example_translation: "",
  aliases: "",
});

mock.module("@/lib/api/vocab", {
  namedExports: {
    HOME_WORDS: 7,
    getDailyWords: async () => [],
    getWord: async (id: string) => word(Number(id), id === "829" ? NOTE : ""),
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { default: WordDetailPage } = await import("./[id]/page");

async function render(id: string, query: Record<string, string> = {}) {
  const element = await WordDetailPage({
    params: Promise.resolve({ id }),
    searchParams: Promise.resolve(query),
  });
  return renderToStaticMarkup(element);
}

/** 본문 첫 줄(맨 위 줄)의 HTML. */
function topRow(html: string): string {
  const main = html.slice(html.indexOf("<main"));
  const row = main.match(/<div\b[^>]*class="[^"]*flex-wrap[^"]*"[^>]*>([\s\S]*?<\/button>)/);
  assert.ok(row, main.slice(0, 600));
  return row[1];
}

describe("발음 설명이 있는 단어", () => {
  for (const [name, query, label] of [
    ["목록에서 연 상세", {}, "단어장"],
    ["홈의 오늘의 단어에서 연 상세", { today: "829-830" }, "홈"],
  ] as const) {
    it(`${name}: 맨 위 줄에 되돌아가기("${label}") 다음으로 "발음 자세히" 가 선다`, async () => {
      const row = topRow(await render("829", query));
      const back = row.indexOf("<a ");
      const button = row.indexOf("<button");
      assert.ok(back >= 0 && back < button, row);
      assert.match(row.slice(back, button), new RegExp(label));
      assert.match(row.slice(button), /발음 자세히/);
    });
  }

  it("설명은 단어 제목(h1) 아래에 있고 처음엔 닫혀 있다", async () => {
    const html = await render("829");
    const h1 = html.indexOf("<h1");
    const note = html.indexOf(NOTE);
    assert.ok(h1 >= 0 && h1 < note, "설명이 제목보다 먼저 나온다");
    assert.match(html, /<p[^>]*hidden=""[^>]*>[^<]*sl 은/);
  });

  it("뜻 카드와 설명 카드 사이에 따로 선 줄(옛 details)은 없다", async () => {
    assert.doesNotMatch(await render("829"), /<details/);
  });
});

describe("발음 설명이 없는 단어", () => {
  it("버튼 없이 되돌아가기만 있다", async () => {
    const html = await render("830");
    assert.doesNotMatch(html, /발음 자세히/);
    assert.match(html.slice(html.indexOf("<main")), /<a [^>]*href="\/learn\/words"/);
  });
});
