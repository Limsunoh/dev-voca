/**
 * 익히기 목록과 상세의 다듬기 묶음을 경계로 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 쪽 넘기기(전체 쪽수·처음·끝), 검색어가 안 보이는 칸에서 걸렸다는 안내,
 * 쪽 번호와 상세 id 를 고친 주소로 보내기, 목록 개수 문구, 400 화면, 문장 카드,
 * 긴 제목의 글자 크기다.
 *
 * 하네스는 sort-page.test.mts 와 같다. 전역 fetch 를 대역으로 바꾸고 페이지가
 * 그린 트리를 HTML 로 펴서 읽는다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

import type { ReactElement } from "react";

class NotFound extends Error {}
class Redirect extends Error {
  constructor(readonly to: string) {
    super("NEXT_REDIRECT");
  }
}

mock.module("next/navigation", {
  namedExports: {
    notFound: () => {
      throw new NotFound();
    },
    redirect: (to: string) => {
      throw new Redirect(to);
    },
    useRouter: () => ({ push() {}, replace() {}, prefetch() {}, back() {} }),
    useSearchParams: () => new URLSearchParams(),
    usePathname: () => "/",
  },
});

// ---- 백엔드 대역 ----------------------------------------------------------

type Item = Record<string, unknown>;

const WORD: Item = {
  id: 7,
  term: "commit",
  pronunciation: "",
  reading: "커밋발음",
  meaning: "변경을 저장하다",
  description: "d",
  difficulty: 1,
  difficulty_label: "쉬움",
  category: "git",
  category_label: "Git",
  is_exam: false,
  exam_subject: "",
  exam_subject_label: "",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const SENTENCE: Item = {
  ...WORD,
  text: "It works on my machine.",
  translation: "내 컴퓨터에서는 된다.",
  reading: "잇웍스발음",
  context: "임포트가 실패할 때",
  kind: "phrase",
  kind_label: "실무 표현",
};

let listQueries: URLSearchParams[] = [];
let listStatus = 200;
let listBody: { count: number; next: string | null; previous: string | null; results: Item[] };
let wordItem: Item = WORD;
let sentenceItem: Item = SENTENCE;
let detailCalls: string[] = [];

const choices = (values: string[]) =>
  values.map((value) => ({ value, label: `${value}-label` }));

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request) => {
  const url = new URL(String(input));
  const path = url.pathname;
  if (path.endsWith("/categories/")) return json(choices(["git", "api"]));
  if (path.endsWith("/difficulties/")) return json(choices(["1", "2"]));
  if (path.endsWith("/exam_subjects/")) return json(choices(["design"]));
  if (path.endsWith("/kinds/")) return json(choices(["phrase", "error"]));

  const detail = path.match(/\/(words|sentences)\/([^/]+)\/$/);
  if (detail) {
    detailCalls.push(detail[2]);
    // 숫자가 아니거나 범위를 벗어난 번호는 DRF 처럼 404 다.
    if (!/^[1-9]\d{0,17}$/.test(detail[2])) return json({ detail: "없음" }, 404);
    return json(detail[1] === "words" ? wordItem : sentenceItem);
  }

  if (/\/(words|sentences)\/$/.test(path)) {
    listQueries.push(url.searchParams);
    // 없는 쪽 번호는 DRF 처럼 404 다. 고친 주소가 도는지 볼 때 쓴다.
    if (Number(url.searchParams.get("page")) > 1000) return json({ detail: "x" }, 404);
    if (listStatus !== 200) return json({ detail: "x" }, listStatus);
    return json(listBody);
  }
  throw new Error(`대역에 없는 요청: ${url}`);
}) as typeof fetch;

after(() => {
  globalThis.fetch = realFetch;
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { Pagination } = await import("@/components/Pagination");
const { LearningCard, matchVisible } = await import("@/components/LearningCard");
const { DetailHero } = await import("@/components/DetailLayout");
const { canonicalId } = await import("./canonical-id");
const WordsPage = (await import("./words/page")).default;
const SentencesPage = (await import("./sentences/page")).default;
const WordDetailPage = (await import("./words/[id]/page")).default;
const SentenceDetailPage = (await import("./sentences/[id]/page")).default;

type Params = Record<string, string | string[]>;

const LISTS = [
  { name: "words", page: WordsPage, noun: "단어", item: WORD },
  { name: "sentences", page: SentencesPage, noun: "문장", item: SENTENCE },
] as const;

const DETAILS = [
  { name: "words", page: WordDetailPage },
  { name: "sentences", page: SentenceDetailPage },
] as const;

beforeEach(() => {
  listQueries = [];
  listStatus = 200;
  wordItem = WORD;
  sentenceItem = SENTENCE;
  detailCalls = [];
  // 문장 칸과 단어 칸이 다 있는 값이라 두 목록 모두 그릴 수 있다.
  listBody = { count: 99, next: null, previous: null, results: [SENTENCE] };
});

// ---- 도우미 ----------------------------------------------------------------

const visit = (page: (p: never) => unknown, params: Params) =>
  (page as (p: unknown) => Promise<ReactElement>)({
    searchParams: Promise.resolve(params),
  });

const htmlOf = async (page: (p: never) => unknown, params: Params) =>
  renderToStaticMarkup(await visit(page, params));

const decoded = (s: string) =>
  s
    .replaceAll("&amp;", "&")
    .replaceAll("&#x27;", "'")
    .replaceAll("&quot;", '"');

const textOf = (html: string) => decoded(html.replace(/<[^>]*>/g, ""));

function links(html: string) {
  return [...html.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/g)].map((m) => ({
    text: m[2].replace(/<[^>]*>/g, ""),
    href: decoded(m[1].match(/href="([^"]*)"/)?.[1] ?? ""),
  }));
}

const query = (href: string) => new URL(href, "http://x").searchParams;

async function redirectedTo(
  page: (p: never) => unknown,
  params: Params,
): Promise<URL> {
  let to = "";
  await assert.rejects(visit(page, params), (error) => {
    assert.ok(error instanceof Redirect, `redirect 가 아니다: ${error}`);
    to = error.to;
    return true;
  });
  return new URL(to, "http://x");
}

// ---- Pagination ------------------------------------------------------------

type PageProps = {
  currentPage: number;
  hasPrevious: boolean;
  hasNext: boolean;
  count?: number;
  pageLength?: number;
  filters?: Record<string, string | undefined>;
};

function pager(props: PageProps) {
  const html = renderToStaticMarkup(
    Pagination({
      basePath: "/learn/words",
      filters: { shuffle: "s1" },
      ...props,
    }) as ReactElement,
  );
  return {
    links: links(html).map((l) => [l.text, query(l.href).get("page")]),
    label: textOf(html.replace(/<a\b[\s\S]*?<\/a>/g, "")).trim(),
  };
}

describe("Pagination - 전체 쪽수와 처음·끝", () => {
  it("566개 20개씩이면 첫 쪽에 1 / 29 와 다음·끝이 있다", () => {
    const p = pager({
      currentPage: 1,
      hasPrevious: false,
      hasNext: true,
      count: 566,
      pageLength: 20,
    });
    assert.equal(p.label, "1 / 29");
    assert.deepEqual(p.links, [
      ["다음", "2"],
      ["끝", "29"],
    ]);
  });

  it("마지막 쪽은 실린 개수와 무관하게 현재 쪽이 전체 쪽수다", () => {
    const p = pager({
      currentPage: 29,
      hasPrevious: true,
      hasNext: false,
      count: 566,
      pageLength: 6,
    });
    assert.equal(p.label, "29 / 29");
    assert.deepEqual(p.links, [
      ["처음", null],
      ["이전", "28"],
    ]);
  });

  it('2쪽에서 "처음" 은 "이전" 과 같은 곳이라 없다', () => {
    const p = pager({
      currentPage: 2,
      hasPrevious: true,
      hasNext: true,
      count: 566,
      pageLength: 20,
    });
    assert.deepEqual(p.links, [
      ["이전", null],
      ["다음", "3"],
      ["끝", "29"],
    ]);
  });

  it('3쪽부터 "처음" 이 있고 1쪽은 page 를 안 적는다', () => {
    const p = pager({
      currentPage: 3,
      hasPrevious: true,
      hasNext: true,
      count: 566,
      pageLength: 20,
    });
    assert.deepEqual(p.links[0], ["처음", null]);
  });

  it('뒤에서 둘째 쪽의 "끝" 은 "다음" 과 같은 곳이라 없다', () => {
    const p = pager({
      currentPage: 28,
      hasPrevious: true,
      hasNext: true,
      count: 566,
      pageLength: 20,
    });
    assert.equal(p.label, "28 / 29");
    assert.deepEqual(p.links, [
      ["처음", null],
      ["이전", "27"],
      ["다음", "29"],
    ]);
  });

  it("개수가 쪽 크기의 배수면 올림 없이 맞는다", () => {
    const p = pager({
      currentPage: 1,
      hasPrevious: false,
      hasNext: true,
      count: 40,
      pageLength: 20,
    });
    assert.equal(p.label, "1 / 2");
    assert.deepEqual(p.links, [["다음", "2"]]);
  });

  for (const currentPage of [1, 2, 3, 29]) {
    it(`count 를 안 넘기면 ${currentPage}쪽 표시는 "${currentPage} 페이지" 그대로다`, () => {
      const p = pager({ currentPage, hasPrevious: currentPage > 1, hasNext: true });
      assert.equal(p.label, `${currentPage} 페이지`);
      assert.ok(!p.links.some(([text]) => text === "끝"), JSON.stringify(p.links));
    });
  }

  it("count 만 있고 pageLength 가 0 이면 전체 쪽수를 안 쓴다", () => {
    const p = pager({
      currentPage: 3,
      hasPrevious: true,
      hasNext: false,
      count: 566,
      pageLength: 0,
    });
    assert.equal(p.label, "3 페이지");
  });

  it("count 가 0 이면 전체 쪽수를 안 쓴다", () => {
    const p = pager({
      currentPage: 3,
      hasPrevious: true,
      hasNext: true,
      count: 0,
      pageLength: 20,
    });
    assert.equal(p.label, "3 페이지");
  });

  it("앞뒤가 모두 없으면 아무것도 그리지 않는다", () => {
    const p = pager({ currentPage: 1, hasPrevious: false, hasNext: false, count: 3, pageLength: 3 });
    assert.equal(p.label, "");
    assert.deepEqual(p.links, []);
  });

  it("모든 링크가 지금 조건을 들고 간다", () => {
    const html = renderToStaticMarkup(
      Pagination({
        basePath: "/learn/words",
        filters: { search: "a b", sort: "easy", category: "git" },
        currentPage: 3,
        hasPrevious: true,
        hasNext: true,
        count: 100,
        pageLength: 20,
      }) as ReactElement,
    );
    for (const link of links(html)) {
      const q = query(link.href);
      assert.equal(q.get("search"), "a b", link.href);
      assert.equal(q.get("sort"), "easy", link.href);
      assert.equal(q.get("category"), "git", link.href);
    }
  });
});

describe("Pagination - 목록 화면이 넘기는 값", () => {
  for (const { name, page, item } of LISTS) {
    it(`/learn/${name}: 응답의 count 와 실린 개수로 쪽수를 낸다`, async () => {
      listBody = {
        count: 566,
        next: "n",
        previous: null,
        results: Array.from({ length: 20 }, (_, id) => ({ ...item, id: id + 1 })),
      };
      const html = await htmlOf(page, { shuffle: "s1" });
      const nav = html.match(/<nav aria-label="페이지 이동"[\s\S]*?<\/nav>/)?.[0];
      assert.ok(nav, "쪽 넘기기가 없다");
      assert.match(textOf(nav), /1 \/ 29/);
      const last = links(nav).at(-1);
      assert.equal(last?.text, "끝");
      assert.equal(query(last.href).get("page"), "29");
      assert.equal(query(last.href).get("shuffle"), "s1");
    });

    it(`/learn/${name}: 마지막 쪽 표시`, async () => {
      listBody = {
        count: 566,
        next: null,
        previous: "p",
        results: Array.from({ length: 6 }, (_, id) => ({ ...item, id: id + 1 })),
      };
      const html = await htmlOf(page, { shuffle: "s1", page: "29" });
      const nav = html.match(/<nav aria-label="페이지 이동"[\s\S]*?<\/nav>/)?.[0];
      assert.ok(nav, "쪽 넘기기가 없다");
      assert.match(textOf(nav), /29 \/ 29/);
      assert.ok(!links(nav).some((l) => l.text === "끝" || l.text === "다음"));
    });
  }
});

// ---- matchVisible ----------------------------------------------------------

describe("matchVisible - 구절은 한 칸 안에 있어야 한다", () => {
  it("따옴표 구절이 제목과 뜻에 나뉘어 있으면 안 보이는 것으로 친다", () => {
    assert.equal(matchVisible('"commit message"', "commit", "message"), false);
  });

  it("낱말은 칸이 달라도 각각 있으면 보이는 것으로 친다", () => {
    assert.equal(matchVisible("commit message", "commit", "message"), true);
  });
});

describe("matchVisible", () => {
  const cases: [string, string[], boolean, string][] = [
    ["commit", ["commit", "뜻"], true, "제목에 있음"],
    ["COMMIT", ["commit", "뜻"], true, "검색어 대문자"],
    ["commit", ["COMMIT", "뜻"], true, "카드 대문자"],
    ["커밋", ["commit", "변경을 저장"], false, "카드에 없음"],
    ['"commit message"', ["commit message 예시"], true, "따옴표 구가 있음"],
    ['"commit message"', ["commit 과 message"], false, "따옴표 구는 붙어 있어야 한다"],
    ["'commit'", ["commit"], true, "작은따옴표"],
    ["commit,merge", ["commit merge"], true, "쉼표로 나눈 두 낱말"],
    ["commit,merge", ["commit"], false, "쉼표 낱말 하나만 있음"],
    ["commit 저장", ["commit", "변경을 저장"], true, "낱말이 서로 다른 칸에 있음"],
    ["commit 저장", ["commit", "변경"], false, "낱말 하나가 없음"],
    ['""', ["무엇이든"], true, "빈 따옴표는 낱말이 없다"],
    [",", ["무엇이든"], true, "쉼표만 있으면 낱말이 없다"],
  ];
  for (const [search, visible, want, name] of cases) {
    it(`${name}: ${JSON.stringify(search)} -> ${want}`, () => {
      assert.equal(matchVisible(search, ...visible), want);
    });
  }
});

describe("검색어 안내 - 카드", () => {
  const NOTE = "설명에 검색어가 있습니다";

  it("단어: 제목이나 뜻에 있으면 안내가 없다", async () => {
    for (const search of ["commit", "COMMIT", '"commit"', "저장"]) {
      assert.ok(!(await htmlOf(WordsPage, { search })).includes(NOTE), search);
    }
  });

  it("단어: 보이는 칸에 없으면 안내가 붙는다", async () => {
    for (const search of ["숨은말", '"숨은 말"', "commit,숨은말"]) {
      assert.ok((await htmlOf(WordsPage, { search })).includes(NOTE), search);
    }
  });

  it("문장: 본문·해석·상황에 있으면 안내가 없다", async () => {
    listBody.results = [SENTENCE];
    for (const search of ["machine", "컴퓨터", "임포트가"]) {
      assert.ok(!(await htmlOf(SentencesPage, { search })).includes(NOTE), search);
    }
  });

  it("문장: 어디에도 안 보이면 안내가 붙는다", async () => {
    listBody.results = [SENTENCE];
    assert.ok((await htmlOf(SentencesPage, { search: "숨은말" })).includes(NOTE));
  });

  it("검색이 아니면 안내가 없다", async () => {
    assert.ok(!(await htmlOf(WordsPage, { shuffle: "s1" })).includes(NOTE));
  });

  it("LearningCard 는 note 를 뜻 아래에 그리고 compact 면 안 그린다", () => {
    const base = { href: "/x", title: "t", subtitle: "s", note: NOTE };
    assert.ok(renderToStaticMarkup(LearningCard(base) as ReactElement).includes(NOTE));
    assert.ok(
      !renderToStaticMarkup(
        LearningCard({ ...base, compact: true } as never) as ReactElement,
      ).includes(NOTE),
    );
  });
});

// ---- canonicalId -----------------------------------------------------------

describe("canonicalId", () => {
  const fixed: [string, string][] = [
    ["007", "7"],
    ["00", "0"],
    ["000", "0"],
    ["0007", "7"],
    ["009007199254740991", "9007199254740991"],
  ];
  for (const [input, want] of fixed) {
    it(`${input} 는 ${want} 로 고친다`, () => {
      assert.equal(canonicalId(input), want);
    });
  }

  const untouched = [
    "7",
    "0",
    "120",
    "9007199254740991",
    // 안전 범위 밖은 Number 가 값을 바꾸므로 고치지 않는다.
    "9007199254740992",
    "0009007199254740993",
    "9".repeat(30),
    "",
    "abc",
    "007a",
    "-7",
    "+7",
    "7.0",
    "1e3",
    " 7",
    "\u0663",
    "\uff17",
  ];
  for (const input of untouched) {
    it(`${JSON.stringify(input)} 는 그대로다`, () => {
      assert.equal(canonicalId(input), null);
    });
  }
});

describe("상세 주소 정리", () => {
  const detail = (page: (p: never) => unknown, id: string, params: Params = {}) =>
    (page as (p: unknown) => Promise<ReactElement>)({
      params: Promise.resolve({ id }),
      searchParams: Promise.resolve(params),
    });

  const redirectOf = async (page: (p: never) => unknown, id: string) => {
    let to = "";
    await assert.rejects(detail(page, id), (error) => {
      assert.ok(error instanceof Redirect, `redirect 가 아니다: ${error}`);
      to = error.to;
      return true;
    });
    return to;
  };

  for (const { name, page } of DETAILS) {
    it(`/learn/${name}/007 은 /learn/${name}/7 로 보내고 백엔드를 안 부른다`, async () => {
      assert.equal(await redirectOf(page, "007"), `/learn/${name}/7`);
      assert.deepEqual(detailCalls, []);
    });

    it(`/learn/${name}/00 은 /learn/${name}/0 으로 보낸다`, async () => {
      assert.equal(await redirectOf(page, "00"), `/learn/${name}/0`);
    });

    it(`/learn/${name}/7 은 그대로 연다`, async () => {
      const html = renderToStaticMarkup(await detail(page, "7"));
      assert.ok(html.includes("<h1"));
      assert.deepEqual(detailCalls, ["7"]);
    });

    for (const id of ["0", "abc", "9".repeat(30), "007a"]) {
      it(`/learn/${name}/${id.slice(0, 8)} 는 redirect 없이 notFound 다`, async () => {
        await assert.rejects(detail(page, id), NotFound);
      });
    }
  }
});

// ---- 쪽 번호 정규화 --------------------------------------------------------

describe("쪽 번호 정규화", () => {
  const fixed: [string, string | null][] = [
    ["0", null],
    ["abc", null],
    ["3.7", null],
    ["1", null],
    ["-2", null],
    ["", null],
    ["01", null],
    ["02", "2"],
    ["2.0", "2"],
    ["+3", "3"],
    ["1e1", "10"],
    [" 2", "2"],
  ];

  for (const { name, page } of LISTS) {
    for (const [raw, want] of fixed) {
      it(`/learn/${name}?page=${JSON.stringify(raw)} 는 page=${want ?? "없음"} 으로 보낸다`, async () => {
        const to = await redirectedTo(page, { shuffle: "s1", page: raw });
        assert.equal(to.pathname, `/learn/${name}`);
        assert.equal(to.searchParams.get("page"), want, to.href);
        assert.equal(to.searchParams.get("shuffle"), "s1", to.href);
        assert.equal(listQueries.length, 0, "보내기 전에 목록을 불렀다");
      });
    }

    it(`/learn/${name}?page=2 는 보내지 않는다`, async () => {
      await visit(page, { shuffle: "s1", page: "2" });
      assert.equal(listQueries[0].get("page"), "2");
    });

    it(`/learn/${name}: 쪽 번호가 없으면 정규화하지 않는다`, async () => {
      await visit(page, { shuffle: "s1" });
      assert.equal(listQueries.length, 1);
    });

    it(`/learn/${name}: 여럿이면 첫 값으로 판단한다`, async () => {
      await visit(page, { shuffle: "s1", page: ["2", "abc"] });
      assert.equal(listQueries[0].get("page"), "2");
      const to = await redirectedTo(page, { shuffle: "s1", page: ["abc", "2"] });
      assert.equal(to.searchParams.get("page"), null);
    });

    it(`/learn/${name}: 고칠 때 조건은 두고 모르는 키는 버린다`, async () => {
      const to = await redirectedTo(page, {
        page: "abc",
        search: "git",
        sort: "easy",
        category: "git",
        utm: "x",
      });
      assert.equal(to.searchParams.get("search"), "git");
      assert.equal(to.searchParams.get("sort"), "easy");
      assert.equal(to.searchParams.get("category"), "git");
      assert.equal(to.searchParams.get("utm"), null);
    });

    for (const raw of ["0", "abc", "99999999999999999999", "1e21", "1e400", "Infinity"]) {
      it(`/learn/${name}?page=${raw}: 몇 번 안에 멈춘다`, async () => {
        let current: Params = { shuffle: "s1", page: raw };
        for (let hop = 0; ; hop++) {
          assert.ok(hop < 4, "redirect 가 멈추지 않는다");
          try {
            await visit(page, current);
            return;
          } catch (error) {
            assert.ok(error instanceof Redirect, String(error));
            current = Object.fromEntries(
              new URL(error.to, "http://x").searchParams,
            ) as Params;
          }
        }
      });
    }
  }
});

// ---- 목록 개수 문구 --------------------------------------------------------

describe("목록 개수 문구", () => {
  for (const { name, page, noun } of LISTS) {
    it(`/learn/${name}: 조건이 없으면 전체`, async () => {
      assert.ok(textOf(await htmlOf(page, { shuffle: "s1" })).includes("전체 99개"));
    });

    it(`/learn/${name}: 정렬만 고른 것은 조건이 아니라 전체다`, async () => {
      assert.ok(textOf(await htmlOf(page, { sort: "easy" })).includes("전체 99개"));
    });

    for (const condition of [
      { category: "git" },
      { difficulty: "2" },
      { category: "git", difficulty: "2" },
    ] as Params[]) {
      it(`/learn/${name} ${JSON.stringify(condition)}: 조건에 맞는 ${noun}`, async () => {
        const text = textOf(await htmlOf(page, { shuffle: "s1", ...condition }));
        assert.ok(text.includes(`조건에 맞는 ${noun} 99개`), text.slice(0, 300));
        assert.ok(!text.includes("전체 99개"));
      });
    }

    it(`/learn/${name}: 검색은 검색 결과로 쓴다(조건이 있어도)`, async () => {
      const plain = textOf(await htmlOf(page, { search: "git" }));
      assert.ok(plain.includes('"git" 검색 결과 99개'), plain.slice(0, 300));
      const filtered = textOf(await htmlOf(page, { search: "git", category: "git" }));
      assert.ok(filtered.includes('"git" 검색 결과 99개'));
      assert.ok(!filtered.includes("조건에 맞는"));
    });

    it(`/learn/${name}: 0개면 조건 지우기가 있다`, async () => {
      listBody = { count: 0, next: null, previous: null, results: [] };
      const html = await htmlOf(page, { shuffle: "s1", category: "git" });
      const clear = links(html).find((l) => l.text === "조건 지우기");
      assert.ok(clear, "조건 지우기가 없다");
      assert.equal(query(clear.href).get("category"), null);
      assert.ok(query(clear.href).get("shuffle"));
    });
  }

  it("/learn/words: 정처기 조건도 조건이다", async () => {
    for (const condition of [
      { is_exam: "true" },
      { exam_subject: "design" },
    ] as Params[]) {
      const text = textOf(await htmlOf(WordsPage, { shuffle: "s1", ...condition }));
      assert.ok(text.includes("조건에 맞는 단어 99개"), JSON.stringify(condition));
    }
  });

  it('/learn/words: is_exam 값이 "true" 가 아니면 조건이 아니다', async () => {
    const text = textOf(await htmlOf(WordsPage, { shuffle: "s1", is_exam: "false" }));
    assert.ok(text.includes("전체 99개"), text.slice(0, 300));
  });

  it("/learn/sentences: 종류도 조건이다", async () => {
    const text = textOf(await htmlOf(SentencesPage, { shuffle: "s1", kind: "error" }));
    assert.ok(text.includes("조건에 맞는 문장 99개"), text.slice(0, 300));
  });
});

// ---- 400 화면 --------------------------------------------------------------

describe("조건값이 틀린 화면", () => {
  for (const { name, page } of LISTS) {
    it(`/learn/${name}: 400 은 조건 지우기를 준다`, async () => {
      listStatus = 400;
      const html = await htmlOf(page, { shuffle: "s1", difficulty: "9" });
      const text = textOf(html);
      assert.ok(text.includes("조건을 지우고 다시 골라보세요"), text.slice(0, 400));
      assert.ok(!text.includes("위에서 분류를"));

      const clear = links(html).find((l) => l.text === "조건 지우기");
      assert.ok(clear, "조건 지우기가 없다");
      const q = query(clear.href);
      assert.equal(new URL(clear.href, "http://x").pathname, `/learn/${name}`);
      assert.equal(q.get("difficulty"), null);
      assert.ok(q.get("shuffle"), "시드가 없으면 서버가 한 번 더 보낸다");
    });

    it(`/learn/${name}: 400 은 검색어도 함께 지운다`, async () => {
      listStatus = 400;
      const html = await htmlOf(page, { search: "git", category: "zzz" });
      const clear = links(html).find((l) => l.text === "조건 지우기");
      assert.ok(clear);
      assert.equal(query(clear.href).get("search"), null);
      assert.equal(query(clear.href).get("category"), null);
    });

    it(`/learn/${name}: 400 이 아닌 에러에는 조건 지우기가 없다`, async () => {
      listStatus = 500;
      const html = await htmlOf(page, { shuffle: "s1" });
      assert.ok(!links(html).some((l) => l.text === "조건 지우기"));
      assert.ok(!textOf(html).includes("조건을 지우고"));
    });
  }
});

// ---- 카드와 제목 -----------------------------------------------------------

describe("문장 카드", () => {
  beforeEach(() => {
    listBody.results = [SENTENCE];
  });

  it("한글 발음을 싣지 않는다", async () => {
    const html = await htmlOf(SentencesPage, { shuffle: "s1" });
    assert.ok(!html.includes("잇웍스발음"));
    assert.ok(html.includes("내 컴퓨터에서는"), "해석은 있어야 한다");
  });

  it("단어 카드의 발음은 그대로다", async () => {
    listBody.results = [WORD];
    assert.ok((await htmlOf(WordsPage, { shuffle: "s1" })).includes("커밋"));
  });

  it("상황은 줄을 따로 쓴다", async () => {
    const html = await htmlOf(SentencesPage, { shuffle: "s1" });
    assert.match(html, /<span class="basis-full"[^>]*>임포트가 실패할 때<\/span>/);
  });

  it("상황이 없으면 그 줄이 없다", async () => {
    listBody.results = [{ ...SENTENCE, context: "" }];
    assert.ok(!(await htmlOf(SentencesPage, { shuffle: "s1" })).includes("basis-full"));
  });
});

describe("DetailHero 제목 크기", () => {
  const styleOf = (title: string, mono?: boolean) => {
    const html = renderToStaticMarkup(
      DetailHero({ title, meaning: "뜻", mono } as never) as ReactElement,
    );
    return html.match(/<h1[^>]*style="([^"]*)"/)?.[1] ?? "";
  };
  const title = (length: number) => "x".repeat(length);

  const mono: [number, string, string][] = [
    [1, "var(--text-hero)", "1.02"],
    [24, "var(--text-hero)", "1.02"],
    [25, "clamp(1.5rem,7vw,2rem)", "1.15"],
    [100, "clamp(1.5rem,7vw,2rem)", "1.15"],
    [101, "clamp(1.0625rem,4.4vw,1.25rem)", "1.3"],
    [215, "clamp(1.0625rem,4.4vw,1.25rem)", "1.3"],
  ];
  for (const [length, size, line] of mono) {
    it(`고정폭 ${length}자: ${size}`, () => {
      const style = styleOf(title(length));
      assert.ok(style.includes(`font-size:${size}`), style);
      assert.ok(style.includes(`line-height:${line}`), style);
    });
  }

  const sans: [number, string, string][] = [
    [40, "clamp(1.75rem,8vw,2.25rem)", "1.08"],
    [41, "clamp(1.375rem,6vw,1.75rem)", "1.25"],
    [215, "clamp(1.375rem,6vw,1.75rem)", "1.25"],
  ];
  for (const [length, size, line] of sans) {
    it(`가변폭 ${length}자: ${size}`, () => {
      const style = styleOf(title(length), false);
      assert.ok(style.includes(`font-size:${size}`), style);
      assert.ok(style.includes(`line-height:${line}`), style);
    });
  }
});
