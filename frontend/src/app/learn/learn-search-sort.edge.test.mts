/**
 * 익히기 목록의 검색어 판정·정렬 줄·에러 문장 서체를 경계로 깨 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 세 가지를 본다.
 * 1. searchText 가 백엔드(DRF search_smart_split)와 같은 판정을 하는지.
 *    기댓값은 같은 입력을 DRF 에 넣어 "빈 문자열이 아닌 조각이 있나" 로 뽑은
 *    표다(아래 BACKEND_*). 표를 다시 뽑으려면 backend 의 venv 로
 *    rest_framework.filters.search_smart_split 를 부르면 된다.
 * 2. 단어 목록 정렬 줄의 맨 앞 칩(allValue)이 검색 유무 x sort x 다른 조건
 *    에서 어디를 가리키고, 그 링크를 따라가면 redirect 없이 열리는지.
 *    문장 목록은 allValue 를 안 넘기므로 이전과 같아야 한다.
 * 3. 문장 목록·상세가 에러 문장만 고정폭으로 그리는지.
 *
 * searchText 는 DRF 의 쪼개기 규칙을 옮긴 것이라, 따옴표 조합도 DRF 와 같아야 한다.
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
    useRouter: () => ({ push() {}, replace() {}, prefetch() {} }),
    useSearchParams: () => new URLSearchParams(),
    usePathname: () => "/",
  },
});

// ---- 백엔드 대역 ----------------------------------------------------------

let listQueries: URLSearchParams[] = [];
let sentenceKind = "phrase";

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
  const item = {
    id: 7,
    term: "commit",
    text: "It works on my machine.",
    translation: "내 컴퓨터에서는 된다.",
    pronunciation: "",
    reading: "",
    meaning: "m",
    description: "d",
    context: "",
    difficulty: 1,
    difficulty_label: "쉬움",
    category: "git",
    category_label: "Git",
    kind: sentenceKind,
    kind_label: "종류",
    is_exam: false,
    exam_subject: "",
    exam_subject_label: "",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
  if (/\/sentences\/\d+\/$/.test(path)) return json(item);
  if (/\/(words|sentences)\/$/.test(path)) {
    listQueries.push(url.searchParams);
    return json({ count: 99, next: "n", previous: "p", results: [item] });
  }
  throw new Error(`대역에 없는 요청: ${url}`);
}) as typeof fetch;

after(() => {
  globalThis.fetch = realFetch;
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { searchText } = await import("@/lib/routes");
const { ChoiceFilter } = await import("@/components/ChoiceFilter");
const WordsPage = (await import("./words/page")).default;
const SentencesPage = (await import("./sentences/page")).default;
const SentenceDetailPage = (await import("./sentences/[id]/page")).default;

type Params = Record<string, string | string[]>;
type Chip = { text: string; href: string; active: boolean; aria: string };

beforeEach(() => {
  listQueries = [];
  sentenceKind = "phrase";
});

// ---- 도우미 ----------------------------------------------------------------

const query = (href: string) => new URL(href, "http://x").searchParams;

function links(html: string): Chip[] {
  return [...html.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/g)].map((m) => ({
    text: m[2].replace(/<[^>]*>/g, ""),
    href: (m[1].match(/href="([^"]*)"/)?.[1] ?? "")
      .replaceAll("&amp;", "&")
      .replaceAll("&#x27;", "'")
      .replaceAll("&quot;", '"'),
    active: /aria-current/.test(m[1]),
    aria: m[1].match(/aria-label="([^"]*)"/)?.[1] ?? "",
  }));
}

function sortRowOf(html: string): Chip[] {
  const nav = html.match(/<nav aria-label="정렬 필터"[\s\S]*?<\/nav>/)?.[0];
  assert.ok(nav, "정렬 줄이 없다");
  return links(nav);
}

async function render(page: (p: never) => unknown, params: Params) {
  const tree = (await (page as (p: unknown) => Promise<ReactElement>)({
    searchParams: Promise.resolve(params),
  })) as ReactElement;
  return renderToStaticMarkup(tree);
}

async function redirectedTo(
  page: (p: never) => unknown,
  params: Params,
): Promise<URL> {
  let to = "";
  await assert.rejects(render(page, params), (error) => {
    assert.ok(error instanceof Redirect, `redirect 가 아니다: ${error}`);
    to = error.to;
    return true;
  });
  return new URL(to, "http://x");
}

/** 링크의 쿼리를 그대로 다음 방문의 searchParams 로 쓴다. */
const follow = (href: string): Params =>
  Object.fromEntries(query(href)) as Params;

// ---- 1. searchText 와 백엔드 판정 -----------------------------------------

/**
 * DRF search_smart_split 가 "검색어 있음" 으로 본 입력.
 * 값은 같은 입력을 DRF 에 넣어 빈 문자열이 아닌 조각이 있는지 본 결과다.
 */
const BACKEND_SEARCH = [
  "git",
  "  git ",
  ",git,",
  "a b",
  "it's",
  "a'b",
  'a"b',
  '"a b" c',
  '"a b"',
  "'git'",
  '","',
  '" "',
  "','",
  "' '",
  '" , "',
  "\"it's\"",
  '"a\\"b"',
  '"x',
  "'x",
  'a"',
  "\\",
  '"\\"',
  "　a　",
  '"　"',
  '"a" "',
  '""a',
  '"" a',
];

/** DRF 가 "검색어 없음"(빈 조각뿐)으로 본 입력. */
const BACKEND_EMPTY = [
  "",
  " ",
  "  ",
  "　",
  "　 \t",
  ",",
  " , ",
  ",,,",
  '"',
  "'",
  '""',
  "''",
  '"""',
];

describe("searchText - 백엔드가 검색으로 보는 입력", () => {
  for (const value of BACKEND_SEARCH) {
    it(`${JSON.stringify(value)} 는 검색이다`, () => {
      assert.equal(searchText(value), value.trim());
    });
  }
});

describe("searchText - 백엔드가 빈 검색어로 보는 입력", () => {
  for (const value of BACKEND_EMPTY) {
    it(`${JSON.stringify(value)} 는 검색이 아니다`, () => {
      assert.equal(searchText(value), undefined);
    });
  }

  it("undefined 도 검색이 아니다", () => {
    assert.equal(searchText(undefined), undefined);
  });
});

/**
 * 백엔드와 어긋나는 입력. DRF 판정은 위와 같은 방법으로 뽑았다.
 *
 * 앞 묶음은 서로 다른 따옴표가 섞이거나(`"'`) 따옴표가 짝지어 읽히는 것(`""""`)이다. DRF 는 따옴표로 감싼 조각이
 * 아니라서 따옴표 글자 자체를 찾는데(`"'` -> 조각 `"'`), 화면은 이것을 검색이
 * 아닌 것으로 보고 검색어를 버려 전체를 섞어 보여준다. 이 변경 전에는 검색으로
 * 봤다.
 *
 * 뒷 묶음은 빈 따옴표 쌍 뒤에 따옴표가 하나 더 와서 `" "` 같은 조각이 쌍
 * 경계를 넘어 잡히는 것이다. DRF 는 빈 조각 둘로 읽는다.
 */
describe("searchText - 백엔드와 어긋나는 입력", () => {
  const backendSearches = ["\"'", "'\"", "\"'\"", '""""'];
  for (const value of backendSearches) {
    it(
      `${JSON.stringify(value)}: 백엔드는 검색, 화면은 검색 아님`,
      {},
      () => {
        assert.equal(searchText(value), value);
      },
    );
  }

  const backendEmpty = ['"" "', '"","', "'',' ", '"" ""'];
  for (const value of backendEmpty) {
    it(
      `${JSON.stringify(value)}: 백엔드는 빈 검색어, 화면은 검색`,
      {},
      () => {
        assert.equal(searchText(value), undefined);
      },
    );
  }
});

describe("searchText - 이 변경이 새로 만든 어긋남이 아닌 것", () => {
  it("이전 규칙이 검색으로 본 것 중 따옴표 없는 입력은 그대로 검색이다", () => {
    for (const v of ["a", "한글", "1", "a,b", ",a", "a,", "\\", "​"]) {
      assert.equal(searchText(v), v);
    }
  });
});

// ---- 2. 단어 목록 정렬 줄 --------------------------------------------------

const SEARCHES = [
  "git",
  "a&sort=easy",
  "100%",
  "a+b",
  "한글 검색",
  '"a b"',
  "it's",
  '" "',
  "a#b",
  "x=1&y=2",
];

const SORT_VALUES: (string | string[] | undefined)[] = [
  undefined,
  "abc",
  "easy",
  "ABC",
  "term",
  "",
  ["abc", "easy"],
  ["easy", "abc"],
  ["zzz", "abc"],
];

const OTHERS: Params[] = [
  {},
  { category: "git", difficulty: "2" },
  { is_exam: "true", exam_subject: "design", page: "3" },
  { shuffle: "s1", page: "2" },
];

describe("/learn/words 정렬 줄 - 검색 중 맨 앞 칩", () => {
  for (const search of SEARCHES) {
    for (const sort of SORT_VALUES) {
      for (const others of OTHERS) {
        const p: Params = {
          ...others,
          search,
          ...(sort === undefined ? {} : { sort }),
        };
        it(`${JSON.stringify(p)}`, async () => {
          const html = await render(WordsPage, p);
          const row = sortRowOf(html);
          assert.deepEqual(
            row.map((c) => c.text),
            ["ABC순", "쉬운 것부터"],
          );

          // 켜진 칩은 하나. sort=easy 만 두 번째 칩이고 나머지는 맨 앞이다.
          const first = Array.isArray(sort) ? sort[0] : sort;
          const on = row.filter((c) => c.active).map((c) => c.text);
          assert.deepEqual(on, [first === "easy" ? "쉬운 것부터" : "ABC순"]);

          const head = query(row[0].href);
          assert.equal(head.get("sort"), "abc", row[0].href);
          assert.equal(head.get("search"), search, row[0].href);
          assert.equal(head.get("shuffle"), null, row[0].href);
          assert.equal(head.get("page"), null, row[0].href);
          assert.equal(new URL(row[0].href, "http://x").pathname, "/learn/words");
          for (const key of ["category", "difficulty", "is_exam", "exam_subject"]) {
            const want = (others as Record<string, string>)[key];
            assert.equal(head.get(key), want ?? null, `${key} ${row[0].href}`);
          }

          // 두 칩 모두 따라가면 redirect 없이 열리고 순서는 term(ABC) 이거나
          // 쉬운 것부터다.
          for (const chip of row) {
            listQueries = [];
            await render(WordsPage, follow(chip.href));
            assert.equal(listQueries.length, 1, chip.href);
            const ordering = listQueries[0].get("ordering");
            const to = query(chip.href).get("sort");
            assert.equal(
              ordering,
              to === "easy" ? "difficulty,term" : to === "abc" ? "term" : null,
              chip.href,
            );
            assert.equal(listQueries[0].get("search"), search, chip.href);
            assert.equal(listQueries[0].get("shuffle"), null, chip.href);
          }

          // 맨 앞 칩을 누른 뒤 검색어를 지워도 ABC 순서가 이어진다.
          const cleared = follow(row[0].href);
          delete cleared.search;
          listQueries = [];
          const afterClear = await render(WordsPage, cleared);
          assert.equal(listQueries.length, 1, "검색을 지우니 redirect 했다");
          assert.equal(listQueries[0].get("ordering"), "term");
          assert.equal(listQueries[0].get("search"), null);
          assert.equal(
            sortRowOf(afterClear).find((c) => c.active)?.text,
            "ABC순",
          );
        });
      }
    }
  }
});

describe("/learn/words 정렬 줄 - 검색이 아닐 때는 맨 앞 칩이 끄기다", () => {
  const notSearch = ["", " ", ",", '"', "'", '""', "''", " ' ", '",']; // 모두 DRF 도 빈 검색어
  for (const search of notSearch) {
    it(`search=${JSON.stringify(search)} + sort=abc: 섞어서 칩이 정렬을 끈다`, async () => {
      const html = await render(WordsPage, { search, sort: "abc" });
      const row = sortRowOf(html);
      assert.deepEqual(
        row.map((c) => c.text),
        ["섞어서", "쉬운 것부터", "ABC순"],
      );
      assert.deepEqual(
        row.filter((c) => c.active).map((c) => c.text),
        ["ABC순"],
      );
      const head = query(row[0].href);
      assert.equal(head.get("sort"), null, row[0].href);
      assert.ok(head.get("shuffle"), "끄면 섞은 시드를 싣는다");
      assert.equal(head.get("search"), null, row[0].href);
      // 요청에도 검색어가 안 간다.
      assert.equal(listQueries.at(-1)?.get("search"), null);
      assert.equal(listQueries.at(-1)?.get("ordering"), "term");
    });

    it(`search=${JSON.stringify(search)} 만 오면 시드를 붙여 검색 없는 주소로 보낸다`, async () => {
      const to = await redirectedTo(WordsPage, { search });
      assert.equal(to.searchParams.get("search"), null);
      assert.ok(to.searchParams.get("shuffle"));
      assert.equal(listQueries.length, 0);
    });
  }
});

describe("/learn/words 정렬 줄 - 검색 없음", () => {
  for (const sort of ["abc", "easy", undefined] as const) {
    it(`sort=${sort ?? "없음"}: 칩 셋, 맨 앞은 끄기, ABC순 칩은 sort=abc`, async () => {
      const html = await render(WordsPage, {
        shuffle: "s1",
        category: "git",
        ...(sort ? { sort } : {}),
      });
      const row = sortRowOf(html);
      assert.deepEqual(
        row.map((c) => c.text),
        ["섞어서", "쉬운 것부터", "ABC순"],
      );
      const head = query(row[0].href);
      assert.equal(head.get("sort"), null);
      assert.equal(head.get("category"), "git");
      const abc = query(row[2].href);
      assert.equal(abc.get("sort"), sort === "abc" ? null : "abc");
    });
  }
});

describe("ChoiceFilter allValue - 컴포넌트 단독", () => {
  const options = [{ value: "easy", label: "쉬운 것부터" }];
  const firstChip = (props: Record<string, unknown>) =>
    links(
      renderToStaticMarkup(
        ChoiceFilter({
          label: "정렬",
          paramName: "sort",
          options,
          basePath: "/p",
          ...props,
        } as never) as ReactElement,
      ),
    )[0];

  it("allValue 가 없으면 맨 앞 칩은 줄 값을 빼고 keepWhenOff 를 싣는다", () => {
    const chip = firstChip({
      selected: "easy",
      keep: { search: "a", sort: "easy" },
      keepWhenOff: { shuffle: "s9" },
    });
    assert.equal(chip.href, "/p?search=a&shuffle=s9");
  });

  it("allValue 가 있으면 그 값을 가리키고 keepWhenOff 는 싣지 않는다", () => {
    const chip = firstChip({
      selected: "easy",
      allValue: "abc",
      keep: { search: "a" },
      keepWhenOff: { shuffle: "s9" },
    });
    assert.equal(chip.href, "/p?search=a&sort=abc");
  });

  it("keep 에 같은 키가 섞여 와도 allValue 가 이긴다", () => {
    const chip = firstChip({
      allValue: "abc",
      keep: { sort: "easy" },
    });
    assert.equal(chip.href, "/p?sort=abc");
  });

  it("allValue 가 빈 문자열이면 끄는 링크로 돌아간다", () => {
    const chip = firstChip({ allValue: "", selected: "easy" });
    assert.equal(chip.href, "/p");
  });

  it("allValue 가 선택된 값과 같으면 맨 앞 칩이 끄는 링크가 된다(함정)", () => {
    // 화면은 검색 중 sort=abc 를 selected 에서 빼서 이 경우를 피한다.
    // 컴포넌트만 보면 같은 값을 넘기는 순간 "이미 고른 것을 다시 누름" 이다.
    const chip = firstChip({ allValue: "abc", selected: "abc" });
    assert.equal(chip.href, "/p");
  });

  it("맨 앞 칩은 selected 가 없을 때만 켜진다", () => {
    assert.equal(firstChip({ allValue: "abc" }).active, true);
    assert.equal(firstChip({ allValue: "abc", selected: "easy" }).active, false);
  });
});

// ---- 문장 목록 정렬 줄은 그대로 -------------------------------------------

describe("/learn/sentences 정렬 줄 - allValue 를 안 넘긴다", () => {
  const cases: [Params, string][] = [
    [{ search: "git" }, "검색"],
    [{ search: "git", sort: "easy" }, "검색 + easy"],
    [{ search: "git", sort: "abc" }, "검색 + 모르는 abc"],
    [{ shuffle: "s1" }, "검색 없음"],
    [{ sort: "easy", kind: "error", category: "git" }, "easy + 다른 조건"],
    [{ search: '"', shuffle: "s1" }, "따옴표 하나는 검색 아님"],
  ];
  for (const [p, name] of cases) {
    it(`${name}: 맨 앞 칩은 sort 가 없다`, async () => {
      const html = await render(SentencesPage, p);
      const row = sortRowOf(html);
      const searching = searchText(p.search as string | undefined) !== undefined;
      assert.deepEqual(
        row.map((c) => c.text),
        [searching ? "기본순" : "섞어서", "쉬운 것부터"],
      );
      const head = query(row[0].href);
      assert.equal(head.get("sort"), null, row[0].href);
      // 검색 중이 아니면 시드를 싣고, 검색 중이면 싣지 않는다.
      assert.equal(Boolean(head.get("shuffle")), !searching, row[0].href);
      assert.equal(head.get("search"), searching ? p.search : null);
      const easy = query(row[1].href);
      assert.equal(easy.get("sort"), p.sort === "easy" ? null : "easy");
      assert.ok(!html.includes("ABC순"));
    });
  }

  it("검색 + 문장 기본순 칩을 따라가면 sort 없이 검색 목록이 열린다", async () => {
    const row = sortRowOf(await render(SentencesPage, { search: "git", sort: "easy" }));
    listQueries = [];
    await render(SentencesPage, follow(row[0].href));
    assert.equal(listQueries.length, 1);
    assert.equal(listQueries[0].get("ordering"), null);
    assert.equal(listQueries[0].get("search"), "git");
  });
});

// ---- 3. 에러 문장 서체 -----------------------------------------------------

/** 목록 카드 제목의 서체 선언 개수. 에러 문장만 고정폭이어야 한다. */
const monoCount = (html: string) =>
  (html.match(/font-family:var\(--font-mono\)/g) ?? []).length;

describe("에러 문장 서체 - 목록", () => {
  it("kind=error 만 고정폭 제목이다", async () => {
    sentenceKind = "phrase";
    const base = monoCount(await render(SentencesPage, { search: "x" }));
    sentenceKind = "error";
    const err = monoCount(await render(SentencesPage, { search: "x" }));
    assert.ok(err > base, `error ${err} <= phrase ${base}`);
    for (const kind of ["Error", "ERROR", "error ", "", "errors"]) {
      sentenceKind = kind;
      assert.equal(
        monoCount(await render(SentencesPage, { search: "x" })),
        base,
        JSON.stringify(kind),
      );
    }
  });
});

describe("에러 문장 서체 - 상세", () => {
  const detail = async (kind: string | null) => {
    sentenceKind = kind as string;
    const tree = (await SentenceDetailPage({
      params: Promise.resolve({ id: "7" }),
      searchParams: Promise.resolve({}),
    })) as ReactElement;
    const html = renderToStaticMarkup(tree);
    return html.match(/<h1[^>]*style="([^"]*)"/)?.[1] ?? "";
  };

  it("kind=error 는 고정폭 제목이다", async () => {
    assert.match(await detail("error"), /font-family:var\(--font-mono\)/);
  });

  for (const kind of ["phrase", "Error", "", null]) {
    it(`kind=${JSON.stringify(kind)} 는 가변폭 제목이다`, async () => {
      const style = await detail(kind);
      assert.match(style, /font-family:var\(--font-sans\)/);
      assert.doesNotMatch(style, /font-mono/);
    });
  }
});
