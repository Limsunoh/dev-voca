/**
 * 단어 목록의 ABC순(?sort=abc)을 조합으로 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 검색 중에는 섞지 않아 백엔드 기본 순서(term)가 곧 ABC순이다. 그래서 검색
 * 중에는 정렬 줄 맨 앞 칩을 "ABC순" 이라 부르고 ABC순 칩은 뺀다. 검색과
 * sort=abc 가 같이 오면 맨 앞 칩이 켜지고 필터 배지는 정렬을 세지 않는다.
 * 그래도 주소의 sort=abc 는 필터 칩·페이지 넘기기·되돌아올 주소가 들고
 * 다닌다. 검색어를 지우면 ABC순으로 돌아가야 해서다.
 *
 * 보는 것: sort 값(없음/easy/abc/모르는 값/배열) x 검색 유무 x 다른 조건에서
 * 백엔드로 가는 ordering·shuffle 과 redirect, 정렬 줄 칩, 다른 링크가 싣는
 * sort, 배지 숫자, 검색창에 넘기는 seed. 문장 목록은 그대로인지도 본다.
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
    useRouter: () => ({ push() {}, replace() {}, prefetch() {} }),
    useSearchParams: () => new URLSearchParams(),
    usePathname: () => "/",
  },
});

// ---- 백엔드 대역 ----------------------------------------------------------

let listQueries: URLSearchParams[] = [];
let listStatus = 200;

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
  if (/\/(words|sentences)\/$/.test(path)) {
    listQueries.push(url.searchParams);
    if (listStatus !== 200) return json({ detail: "x" }, listStatus);
    const item = {
      id: 7,
      term: "commit",
      text: "It works on my machine.",
      translation: "내 컴퓨터에서는 된다.",
      pronunciation: "",
      reading: "",
      meaning: "m",
      difficulty: 1,
      difficulty_label: "쉬움",
      category: "git",
      category_label: "Git",
      kind: "phrase",
      kind_label: "실무 표현",
      is_exam: false,
      exam_subject: "",
      exam_subject_label: "",
    };
    return json({ count: 99, next: "n", previous: "p", results: [item] });
  }
  throw new Error(`대역에 없는 요청: ${url}`);
}) as typeof fetch;

after(() => {
  globalThis.fetch = realFetch;
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { SearchInput } = await import("@/components/SearchInput");
const WordsPage = (await import("./words/page")).default;
const SentencesPage = (await import("./sentences/page")).default;

type Params = Record<string, string | string[]>;
type Page = typeof WordsPage;
type Chip = { text: string; href: string; active: boolean; aria: string };

beforeEach(() => {
  listQueries = [];
  listStatus = 200;
});

// ---- 도우미 ----------------------------------------------------------------

const visit = (page: Page, params: Params) =>
  page({ searchParams: Promise.resolve(params) });

const query = (href: string) => new URL(href, "http://x").searchParams;

async function redirectedTo(page: Page, params: Params): Promise<URL> {
  let to = "";
  await assert.rejects(visit(page, params), (error) => {
    assert.ok(error instanceof Redirect, `redirect 가 아니다: ${error}`);
    to = error.to;
    return true;
  });
  return new URL(to, "http://x");
}

function links(html: string): Chip[] {
  return [...html.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/g)].map((m) => ({
    text: m[2].replace(/<[^>]*>/g, ""),
    href: (m[1].match(/href="([^"]*)"/)?.[1] ?? "").replaceAll("&amp;", "&"),
    active: /aria-current/.test(m[1]),
    aria: m[1].match(/aria-label="([^"]*)"/)?.[1] ?? "",
  }));
}

/** 한 번 그린 화면. 트리와 HTML, 줄별 링크를 같이 돌려준다. */
async function screen(page: Page, params: Params) {
  const tree = (await visit(page, params)) as ReactElement;
  const html = renderToStaticMarkup(tree);
  const nav = (label: string) => {
    const found = html.match(
      new RegExp(`<nav aria-label="${label}"[\\s\\S]*?</nav>`),
    )?.[0];
    return found ? links(found) : [];
  };
  const summary = (html.match(/<summary[\s\S]*?<\/summary>/)?.[0] ?? "").replace(
    /<[^>]*>/g,
    "",
  );
  return {
    tree,
    html,
    sortRow: nav("정렬 필터"),
    nav,
    badge: Number(summary.match(/\d+/)?.[0] ?? 0),
    cards: links(html).filter((l) => l.href.startsWith("/learn/words/7")),
  };
}

/** 트리에서 SearchInput 요소를 찾는다. 컴포넌트는 펼치지 않는다. */
function findSearchInput(node: unknown): ReactElement<{ seed?: string }>[] {
  if (Array.isArray(node)) return node.flatMap(findSearchInput);
  if (!node || typeof node !== "object" || !("props" in node)) return [];
  const el = node as ReactElement<Record<string, unknown>>;
  const here = el.type === SearchInput ? [el as ReactElement<{ seed?: string }>] : [];
  return [...here, ...Object.values(el.props).flatMap(findSearchInput)];
}

function seedOf(tree: unknown): string | undefined {
  const found = findSearchInput(tree);
  assert.equal(found.length, 1, "SearchInput 이 하나가 아니다");
  return found[0].props.seed;
}

// ---- 조합 표 ---------------------------------------------------------------

/** 주소의 sort 값과 그것이 뜻하는 정렬. 모르는 값은 undefined. */
const SORTS: [string | string[] | undefined, "easy" | "abc" | undefined][] = [
  [undefined, undefined],
  ["easy", "easy"],
  ["abc", "abc"],
  ["ABC", undefined],
  ["abc ", undefined],
  ["term", undefined],
  [["abc", "easy"], "abc"],
  [["easy", "abc"], "easy"],
  [["zzz", "abc"], undefined],
];

const ORDERING = { easy: "difficulty,term", abc: "term" } as const;

const OTHERS: Params[] = [
  {},
  { category: "git" },
  { difficulty: "2" },
  { is_exam: "true", exam_subject: "design" },
  { category: "api", difficulty: "1", is_exam: "true" },
];

function params(
  sort: string | string[] | undefined,
  search: string | undefined,
  others: Params,
): Params {
  return {
    ...others,
    ...(sort === undefined ? {} : { sort }),
    ...(search === undefined ? {} : { search }),
  };
}

/** 배지가 세야 하는 조건 수(정렬 제외). */
const filterCount = (others: Params) =>
  ["category", "difficulty", "is_exam", "exam_subject"].filter((k) => others[k])
    .length;

// ---- 백엔드 요청과 redirect -----------------------------------------------

describe("/learn/words ABC순 - 백엔드 요청", () => {
  for (const [sort, meant] of SORTS) {
    for (const search of [undefined, "git", "  "]) {
      for (const others of OTHERS) {
        const p = params(sort, search, others);
        const searching = Boolean(search?.trim());
        it(`${JSON.stringify(p)}`, async () => {
          if (!searching && !meant) {
            // 정렬도 검색도 아니면 시드를 붙여 보낸다. 모르는 sort 는 버린다.
            const to = await redirectedTo(WordsPage, p);
            assert.equal(listQueries.length, 0, "redirect 전에 목록을 불렀다");
            assert.equal(to.pathname, "/learn/words");
            assert.ok(to.searchParams.get("shuffle"));
            assert.equal(to.searchParams.get("sort"), null);
            assert.equal(to.searchParams.get("search"), null);
            for (const [k, v] of Object.entries(others)) {
              assert.equal(to.searchParams.get(k), v, k);
            }
            return;
          }
          await visit(WordsPage, p);
          assert.equal(listQueries.length, 1);
          const q = listQueries[0];
          assert.equal(q.get("ordering"), meant ? ORDERING[meant] : null);
          assert.equal(q.get("shuffle"), null, "정렬·검색 중인데 섞었다");
          assert.equal(q.get("sort"), null, "sort 를 백엔드로 보냈다");
          assert.equal(q.get("search"), searching ? "git" : null);
          for (const [k, v] of Object.entries(others)) {
            assert.equal(q.get(k), v, k);
          }
        });
      }
    }
  }

  it("ABC순이면 주소에 남은 shuffle 을 백엔드로 보내지 않는다", async () => {
    await visit(WordsPage, { sort: "abc", shuffle: "s1" });
    assert.equal(listQueries[0].get("shuffle"), null);
    assert.equal(listQueries[0].get("ordering"), "term");
  });

  it("검색 + ABC순에서 없는 페이지면 정렬을 둔 채 첫 페이지로 보낸다", async () => {
    listStatus = 404;
    const to = await redirectedTo(WordsPage, {
      search: "git",
      sort: "abc",
      page: "9",
    });
    assert.equal(to.searchParams.get("page"), null);
    assert.equal(to.searchParams.get("sort"), "abc");
    assert.equal(to.searchParams.get("search"), "git");
    assert.equal(to.searchParams.get("shuffle"), null);
  });

  it("ABC순에서 번호 없는 404 는 redirect 를 돌지 않고 notFound 다", async () => {
    listStatus = 404;
    await assert.rejects(visit(WordsPage, { sort: "abc" }), NotFound);
  });
});

// ---- 정렬 줄 ---------------------------------------------------------------

describe("/learn/words ABC순 - 정렬 줄", () => {
  for (const [sort, meant] of SORTS) {
    for (const search of [undefined, "git"]) {
      if (!search && !meant) continue;
      for (const others of [OTHERS[0], OTHERS[4]]) {
        const p = params(sort, search, others);
        it(`${JSON.stringify(p)}`, async () => {
          const { sortRow } = await screen(WordsPage, p);
          const texts = sortRow.map((c) => c.text);

          // 칩 목록. 검색 중에는 맨 앞이 ABC순이고 ABC순 칩은 없다.
          assert.deepEqual(
            texts,
            search ? ["ABC순", "쉬운 것부터"] : ["섞어서", "쉬운 것부터", "ABC순"],
          );
          assert.equal(new Set(texts).size, texts.length, "같은 이름 칩");
          const arias = sortRow.map((c) => c.aria);
          assert.equal(new Set(arias).size, arias.length, "같은 aria-label");

          // 켜진 칩은 정확히 하나다.
          const on = sortRow.filter((c) => c.active);
          assert.equal(on.length, 1, JSON.stringify(sortRow));
          const expected =
            meant === "easy" ? "쉬운 것부터" : meant === "abc" ? "ABC순" : search ? "ABC순" : "섞어서";
          assert.equal(on[0].text, expected);
          if (search && meant !== "easy") assert.equal(on[0], sortRow[0]);

          for (const [i, chip] of sortRow.entries()) {
            const q = query(chip.href);
            assert.equal(new URL(chip.href, "http://x").pathname, "/learn/words");
            assert.equal(q.get("page"), null, chip.href);
            assert.equal(q.get("search"), search ?? null, chip.href);
            for (const [k, v] of Object.entries(others)) {
              assert.equal(q.get(k), v, `${k} ${chip.href}`);
            }
            const turnsOff = i === 0 || chip.active;
            if (turnsOff) {
              assert.equal(q.get("sort"), null, `끄는 링크 ${chip.href}`);
              // 정렬을 끄면 검색 중이 아닐 때만 섞인 목록으로 가서 시드를 싣는다.
              assert.equal(Boolean(q.get("shuffle")), !search, chip.href);
            } else {
              const value = chip.text === "ABC순" ? "abc" : "easy";
              assert.equal(q.get("sort"), value, chip.href);
              assert.equal(q.get("shuffle"), null, chip.href);
            }
          }
        });
      }
    }
  }

  it("검색 + ABC순의 칩 링크를 따라가면 redirect 없이 열린다", async () => {
    const { sortRow } = await screen(WordsPage, { search: "git", sort: "abc" });
    for (const chip of sortRow) {
      listQueries = [];
      await visit(WordsPage, Object.fromEntries(query(chip.href)));
      assert.equal(listQueries.length, 1, chip.href);
    }
  });

  it("ABC순 칩을 누른 주소는 ABC순 칩이 켜진 화면이다", async () => {
    const first = await screen(WordsPage, { category: "git", shuffle: "s1" });
    const abc = first.sortRow.find((c) => c.text === "ABC순");
    assert.ok(abc);
    const next = await screen(WordsPage, Object.fromEntries(query(abc.href)));
    assert.equal(next.sortRow.find((c) => c.active)?.text, "ABC순");
    assert.equal(listQueries.at(-1)?.get("ordering"), "term");
    assert.equal(listQueries.at(-1)?.get("category"), "git");
  });
});

// ---- 다른 링크가 싣는 sort -------------------------------------------------

describe("/learn/words ABC순 - 필터 칩·페이지 넘기기·카드", () => {
  for (const search of [undefined, "git"]) {
    it(`검색 ${search ?? "없음"} + ABC순: 다른 조건 링크가 sort=abc 를 들고 간다`, async () => {
      const s = await screen(WordsPage, {
        ...(search ? { search } : {}),
        sort: "abc",
        is_exam: "true",
      });
      const rows = ["분류 필터", "난이도 필터", "정처기 범위 필터", "과목 필터"];
      for (const label of rows) {
        const row = s.nav(label);
        assert.ok(row.length > 0, `${label} 이 없다`);
        for (const chip of row) {
          const q = query(chip.href);
          assert.equal(q.get("sort"), "abc", `${label} ${chip.href}`);
          assert.equal(q.get("shuffle"), null, `${label} ${chip.href}`);
          assert.equal(q.get("search"), search ?? null, `${label} ${chip.href}`);
        }
      }

      const pages = s.nav("페이지 이동");
      assert.equal(pages.length, 2);
      for (const link of pages) {
        assert.equal(query(link.href).get("sort"), "abc", link.href);
        assert.equal(query(link.href).get("shuffle"), null, link.href);
        assert.equal(query(link.href).get("search"), search ?? null, link.href);
      }

      assert.equal(s.cards.length, 1);
      const back = query(query(s.cards[0].href).get("from") ?? "");
      assert.equal(back.get("sort"), "abc");
      assert.equal(back.get("search"), search ?? null);
      assert.equal(back.get("shuffle"), null);
    });
  }

  it("검색 + 모르는 sort 는 정렬 줄 밖 링크에 sort 를 싣지 않는다", async () => {
    const s = await screen(WordsPage, { search: "git", sort: "ABC" });
    const outside = links(s.html).filter((l) => !l.aria.startsWith("정렬 "));
    assert.ok(outside.length > 5);
    for (const link of outside) {
      const q = query(link.href);
      assert.equal(q.get("sort"), null, link.href);
      const back = q.get("from");
      if (back) assert.equal(query(back).get("sort"), null, back);
    }
  });

  it("2 페이지에서 ABC순이면 페이지 넘기기 번호가 맞고 sort 를 들고 간다", async () => {
    const s = await screen(WordsPage, { sort: "abc", page: "2" });
    const pages = s.nav("페이지 이동").map((l) => query(l.href));
    assert.deepEqual(
      pages.map((q) => [q.get("page"), q.get("sort")]),
      [
        [null, "abc"],
        ["3", "abc"],
      ],
    );
  });
});

// ---- 배지와 검색창 seed ----------------------------------------------------

describe("/learn/words ABC순 - 필터 배지와 검색창 seed", () => {
  for (const [sort, meant] of SORTS) {
    for (const search of [undefined, "git"]) {
      if (!search && !meant) continue;
      for (const others of OTHERS) {
        const p = params(sort, search, others);
        it(`${JSON.stringify(p)}`, async () => {
          const { badge, tree } = await screen(WordsPage, p);
          // 검색 중의 ABC순은 기본 순서와 같아 세지 않는다.
          const sortCounts = meant === "easy" || (meant === "abc" && !search);
          assert.equal(badge, filterCount(others) + (sortCounts ? 1 : 0));

          // 정렬 중이면 검색어를 지워도 섞지 않으므로 seed 가 없다.
          // 검색 + ABC순도 정렬 중이다. 지우면 ?sort=abc 로 가 ABC 순서다.
          const seed = seedOf(tree);
          if (meant) assert.equal(seed, undefined);
          else assert.ok(seed, "정렬이 아닌데 seed 가 없다");
        });
      }
    }
  }

  it("검색 + ABC순에서 검색어를 지운 주소(?sort=abc)는 ABC순 칩이 켜진다", async () => {
    // SearchInput 은 seed 가 없으면 search 만 지우고 나머지를 둔다.
    const s = await screen(WordsPage, { sort: "abc" });
    assert.equal(s.sortRow.find((c) => c.active)?.text, "ABC순");
    assert.equal(s.badge, 1);
    assert.equal(listQueries.at(-1)?.get("ordering"), "term");
  });
});

// ---- 문장 목록 --------------------------------------------------------------

describe("/learn/sentences 는 ABC순과 무관하다", () => {
  it("sort=abc 는 모르는 값이라 버리고 시드를 붙여 보낸다", async () => {
    const to = await redirectedTo(SentencesPage, { sort: "abc", kind: "phrase" });
    assert.equal(to.searchParams.get("sort"), null);
    assert.ok(to.searchParams.get("shuffle"));
    assert.equal(to.searchParams.get("kind"), "phrase");
  });

  for (const sort of [undefined, "abc", "easy"]) {
    it(`검색 + sort=${sort ?? "없음"}: 칩은 기본순·쉬운 것부터이고 ordering 은 ${sort === "easy" ? "difficulty,id" : "없음"}`, async () => {
      const s = await screen(SentencesPage, {
        search: "git",
        ...(sort ? { sort } : {}),
      });
      assert.deepEqual(
        s.sortRow.map((c) => c.text),
        ["기본순", "쉬운 것부터"],
      );
      assert.equal(s.sortRow.filter((c) => c.active).length, 1);
      assert.equal(
        s.sortRow.find((c) => c.active)?.text,
        sort === "easy" ? "쉬운 것부터" : "기본순",
      );
      assert.equal(s.badge, sort === "easy" ? 1 : 0);
      assert.equal(
        listQueries.at(-1)?.get("ordering"),
        sort === "easy" ? "difficulty,id" : null,
      );
      assert.ok(!s.html.includes("ABC순"), "문장 화면에 ABC순이 보인다");
      for (const link of links(s.html)) {
        assert.notEqual(query(link.href).get("sort"), "abc", link.href);
      }
    });
  }

  it("검색 없이 섞어서·쉬운 것부터 두 칩이다", async () => {
    const s = await screen(SentencesPage, { shuffle: "s1" });
    assert.deepEqual(
      s.sortRow.map((c) => c.text),
      ["섞어서", "쉬운 것부터"],
    );
  });
});
