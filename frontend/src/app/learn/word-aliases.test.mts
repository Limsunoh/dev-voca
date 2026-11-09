/**
 * 단어의 검색 전용 표기(aliases)와 "설명에 검색어가 있습니다" 안내.
 *
 * 실행: cd frontend && npm test
 *
 * 표기로 찾은 카드에는 안내가 붙지 않고, 표기 자체는 화면에 그려지지 않는다.
 * 하네스는 learn-polish.test.mts 와 같다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

import type { ReactElement } from "react";

mock.module("next/navigation", {
  namedExports: {
    notFound: () => {
      throw new Error("notFound");
    },
    redirect: (to: string) => {
      throw new Error(`redirect ${to}`);
    },
    useRouter: () => ({ push() {}, replace() {}, prefetch() {}, back() {} }),
    useSearchParams: () => new URLSearchParams(),
    usePathname: () => "/",
  },
});

type Item = Record<string, unknown>;

const NOTE = "설명에 검색어가 있습니다";
const ALIASES = "표기하나, 표기둘";

const WORD: Item = {
  id: 7,
  term: "commit",
  pronunciation: "",
  reading: "",
  meaning: "변경을 저장하다",
  aliases: ALIASES,
  difficulty: 1,
  difficulty_label: "쉬움",
  category: "git",
  category_label: "Git",
  is_exam: false,
  exam_subject: "",
  exam_subject_label: "",
};

const SENTENCE: Item = {
  ...WORD,
  text: "It works on my machine.",
  translation: "내 컴퓨터에서는 된다.",
  context: "임포트가 실패할 때",
  kind: "phrase",
  kind_label: "실무 표현",
};

let item: Item = WORD;

const choices = (values: string[]) =>
  values.map((value) => ({ value, label: `${value}-label` }));

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request) => {
  const path = new URL(String(input)).pathname;
  if (path.endsWith("/categories/")) return json(choices(["git", "api"]));
  if (path.endsWith("/difficulties/")) return json(choices(["1", "2"]));
  if (path.endsWith("/exam_subjects/")) return json(choices(["design"]));
  if (path.endsWith("/kinds/")) return json(choices(["phrase", "error"]));
  if (/\/(words|sentences)\/$/.test(path)) {
    return json({ count: 1, next: null, previous: null, results: [item] });
  }
  throw new Error(`대역에 없는 요청: ${path}`);
}) as typeof fetch;

after(() => {
  globalThis.fetch = realFetch;
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { matchVisible } = await import("@/components/LearningCard");
const WordsPage = (await import("./words/page")).default;
const SentencesPage = (await import("./sentences/page")).default;

const htmlOf = async (
  page: (p: never) => unknown,
  params: Record<string, string>,
) =>
  renderToStaticMarkup(
    await (page as (p: unknown) => Promise<ReactElement>)({
      searchParams: Promise.resolve(params),
    }),
  );

beforeEach(() => {
  item = WORD;
});

describe("matchVisible - 표기 칸", () => {
  const cases: [string, (string | undefined)[], boolean, string][] = [
    ["커밋", ["commit", "뜻", "커밋, 커미트"], true, "첫 항목"],
    ["커미트", ["commit", "뜻", "커밋, 커미트"], true, "뒤 항목"],
    ["커밋", ["commit", "뜻", undefined], false, "표기를 안 내려 준 응답"],
    ["커밋", ["commit", "뜻", ""], false, "빈 표기"],
    ["GITHUB", ["x", "뜻", "GitHub"], true, "대소문자"],
    ["commit 커밋", ["commit", "뜻", "커밋"], true, "낱말이 제목과 표기에 나뉨"],
    ["commit 없는말", ["commit", "뜻", "커밋"], false, "낱말 하나가 어디에도 없음"],
    ['"커밋, 커미트"', ["c", "뜻", "커밋, 커미트"], true, "따옴표 구절이 표기 안에 있음"],
    ['"commit 커밋"', ["commit", "뜻", "커밋"], false, "따옴표 구절은 칸을 못 넘는다"],
    ['""', ["c", "뜻", undefined], true, "빈 따옴표는 낱말이 없다"],
  ];
  for (const [search, visible, want, name] of cases) {
    it(`${name}: ${JSON.stringify(search)} -> ${want}`, () => {
      assert.equal(matchVisible(search, ...visible), want);
    });
  }
});

describe("단어 목록 - 표기로 찾은 카드", () => {
  it("표기 항목으로 찾으면 안내가 없다", async () => {
    for (const search of ["표기하나", "표기둘"]) {
      assert.ok(!(await htmlOf(WordsPage, { search })).includes(NOTE), search);
    }
  });

  it("표기에 없는 말로 찾으면 안내가 붙는다", async () => {
    assert.ok((await htmlOf(WordsPage, { search: "설명에만있는말" })).includes(NOTE));
  });

  it("표기 칸이 없는 응답에서도 안내가 붙고 죽지 않는다", async () => {
    item = { ...WORD };
    delete item.aliases;

    assert.ok((await htmlOf(WordsPage, { search: "표기하나" })).includes(NOTE));
  });

  it("표기는 화면에 그리지 않는다", async () => {
    // 검색어 자체는 검색창에 다시 그려지므로 검색하지 않은 항목으로 본다.
    const pages: Record<string, string>[] = [{ shuffle: "s" }, { search: "표기하나" }];
    for (const params of pages) {
      const html = await htmlOf(WordsPage, params);
      assert.ok(!html.includes(ALIASES), JSON.stringify(params));
      assert.ok(!html.includes("표기둘"), JSON.stringify(params));
    }
  });

  it("검색이 없으면 안내가 없다", async () => {
    // shuffle 이 없으면 시드를 붙여 redirect 한다.
    assert.ok(!(await htmlOf(WordsPage, { shuffle: "s" })).includes(NOTE));
  });
});

describe("문장 목록 - 표기를 보지 않는다", () => {
  it("응답에 aliases 가 끼어 있어도 안내는 문장 칸으로만 정한다", async () => {
    item = SENTENCE;

    assert.ok((await htmlOf(SentencesPage, { search: "표기하나" })).includes(NOTE));
  });
});
