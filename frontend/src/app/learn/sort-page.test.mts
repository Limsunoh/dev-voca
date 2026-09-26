/**
 * 익히기 목록(/learn/words, /learn/sentences)의 정렬(`?sort=`)을 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 정렬을 고르면 섞지 않는다 - 시드를 붙이는 redirect 도 안 하고 백엔드에
 * shuffle 도 안 보낸다. 모르는 sort 값은 없는 것으로 보고 평소처럼 시드를
 * 붙여 보낸다. 고른 정렬은 필터 칩·페이지 넘기기·카드의 되돌아올 주소가
 * 모두 들고 다녀야 한다 - 한 곳이라도 빠지면 거기서 순서가 섞인 목록으로
 * 돌아간다.
 *
 * 백엔드는 부르지 않는다. 전역 fetch 를 대역으로 바꿔 목록 요청의 쿼리를
 * 잡고, 페이지가 그린 트리를 HTML 로 펴서 링크를 읽는다. redirect·notFound 는
 * 실제 Next 처럼 던지는 대역이다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

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

/** 목록 요청마다 받은 쿼리. */
let listQueries: URLSearchParams[] = [];
/** 목록 요청에 돌려줄 상태 코드. 200 이 아니면 에러 응답이다. */
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
    // 앞뒤 페이지가 다 있다고 답해 페이지 넘기기 링크 둘을 모두 그리게 한다.
    return json({ count: 99, next: "n", previous: "p", results: [item] });
  }
  throw new Error(`대역에 없는 요청: ${url}`);
}) as typeof fetch;

after(() => {
  globalThis.fetch = realFetch;
});

const { renderToStaticMarkup } = await import("react-dom/server");
const WordsPage = (await import("./words/page")).default;
const SentencesPage = (await import("./sentences/page")).default;
const { WORD_SORTS } = await import("@/lib/api/vocab");
const { SENTENCE_SORTS } = await import("@/lib/api/sentences");

type Params = Record<string, string | string[]>;
type Page = typeof WordsPage;

const visit = (page: Page, params: Params) =>
  page({ searchParams: Promise.resolve(params) });

/** 보내진 곳. redirect 가 아니면 실패다. */
async function redirectedTo(page: Page, params: Params): Promise<URL> {
  let to = "";
  await assert.rejects(visit(page, params), (error) => {
    assert.ok(error instanceof Redirect, `redirect 가 아니다: ${error}`);
    to = error.to;
    return true;
  });
  return new URL(to, "http://x");
}

/** 그린 화면의 링크 전부. [보이는 글자, 주소]. */
async function renderedLinks(page: Page, params: Params) {
  const html = renderToStaticMarkup(
    (await visit(page, params)) as React.ReactElement,
  );
  return [...html.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/g)].map((m) => {
    const href = (m[1].match(/href="([^"]*)"/)?.[1] ?? "").replaceAll(
      "&amp;",
      "&",
    );
    return { text: m[2].replace(/<[^>]*>/g, ""), href, html: m[0] };
  });
}

/** 정렬 줄(nav aria-label="정렬 필터") 안의 링크만. */
async function sortRow(page: Page, params: Params) {
  const html = renderToStaticMarkup(
    (await visit(page, params)) as React.ReactElement,
  );
  const nav = html.match(/<nav aria-label="정렬 필터"[\s\S]*?<\/nav>/)?.[0];
  assert.ok(nav, "정렬 줄이 없다");
  return [...nav.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/g)].map((m) => ({
    text: m[2].replace(/<[^>]*>/g, ""),
    href: (m[1].match(/href="([^"]*)"/)?.[1] ?? "").replaceAll("&amp;", "&"),
    active: /aria-current/.test(m[1]),
  }));
}

const query = (href: string) => new URL(href, "http://x").searchParams;

beforeEach(() => {
  listQueries = [];
  listStatus = 200;
});

// ---- 정렬 표 자체 --------------------------------------------------------

describe("정렬 표", () => {
  it("단어 정렬은 전부 unique 인 term 으로 끝난다(동점이면 페이지 사이에 겹친다)", () => {
    for (const sort of WORD_SORTS) {
      assert.equal(sort.ordering.split(",").at(-1), "term", sort.value);
    }
  });

  it("문장 정렬은 전부 id 로 끝난다(문장엔 unique 한 글자 필드가 없다)", () => {
    for (const sort of SENTENCE_SORTS) {
      assert.equal(sort.ordering.split(",").at(-1), "id", sort.value);
    }
  });

  it("쉬운 것부터는 난이도가 첫 키다", () => {
    const words = WORD_SORTS.find((s) => s.value === "easy");
    const sentences = SENTENCE_SORTS.find((s) => s.value === "easy");
    assert.equal(words?.ordering, "difficulty,term");
    assert.equal(sentences?.ordering, "difficulty,id");
  });
});

// ---- 단어 목록 ------------------------------------------------------------

describe("/learn/words 정렬", () => {
  for (const [sort, ordering] of [["easy", "difficulty,term"]]) {
    it(`?sort=${sort} 는 보내지 않고 ordering=${ordering} 로 부르며 섞지 않는다`, async () => {
      await visit(WordsPage, { sort });
      assert.equal(listQueries.length, 1);
      assert.equal(listQueries[0].get("ordering"), ordering);
      assert.equal(listQueries[0].get("shuffle"), null);
    });
  }

  it("정렬과 시드가 같이 오면 시드를 버린다(백엔드에도, 링크에도)", async () => {
    const links = await renderedLinks(WordsPage, {
      sort: "easy",
      shuffle: "abc",
    });
    assert.equal(listQueries[0].get("shuffle"), null);
    assert.equal(listQueries[0].get("ordering"), "difficulty,term");
    for (const link of links) {
      const seed = query(link.href).get("shuffle");
      // 옛 시드("abc")는 어느 링크에도 새지 않는다. 시드가 붙는 것은 정렬을
      // 끄는 링크뿐이고, 그것은 새로 만든 시드다(섞인 목록으로 가니까).
      assert.notEqual(seed, "abc", link.href);
      if (query(link.href).get("sort") === "easy") {
        assert.equal(seed, null, link.href);
      }
    }
  });

  // abc 는 한때 있던 ABC순이다. 대소문자 정렬 문제로 뺐다(vocab.ts WORD_SORTS).
  for (const bad of ["", "EASY", " easy", "easy ", "__proto__", "toString", "constructor", "latest", "abc"]) {
    it(`모르는 sort ${JSON.stringify(bad)} 는 없는 것으로 보고 시드를 붙여 보낸다`, async () => {
      const to = await redirectedTo(WordsPage, { sort: bad });
      assert.equal(to.pathname, "/learn/words");
      assert.ok(to.searchParams.get("shuffle"), to.href);
      assert.equal(to.searchParams.get("sort"), null, to.href);
      assert.equal(listQueries.length, 0, "보내기 전에 목록을 부르지 않는다");
    });
  }

  it("sort 가 여러 개면 첫 값을 쓴다", async () => {
    await visit(WordsPage, { sort: ["easy", "latest"] });
    assert.equal(listQueries[0].get("ordering"), "difficulty,term");
  });

  it("정렬이 없으면 여전히 시드를 붙여 보낸다", async () => {
    const to = await redirectedTo(WordsPage, { category: "git" });
    assert.ok(to.searchParams.get("shuffle"));
    assert.equal(to.searchParams.get("category"), "git");
  });

  it("없는 페이지(404)는 정렬을 둔 채 첫 페이지로 보낸다", async () => {
    listStatus = 404;
    const to = await redirectedTo(WordsPage, { sort: "easy", page: "999" });
    assert.equal(to.searchParams.get("sort"), "easy");
    assert.equal(to.searchParams.get("page"), null);
    assert.equal(to.searchParams.get("shuffle"), null);
  });

  it("page=2.5 는 1페이지로 보고 정렬은 그대로 부른다", async () => {
    await visit(WordsPage, { sort: "easy", page: "2.5" });
    assert.equal(listQueries[0].get("page"), null);
    assert.equal(listQueries[0].get("ordering"), "difficulty,term");
  });

  it("페이지 넘기기·카드 되돌아올 주소·거르는 칩이 모두 sort 를 들고 간다", async () => {
    const links = await renderedLinks(WordsPage, {
      sort: "easy",
      category: "git",
      difficulty: "1",
      is_exam: "true",
      exam_subject: "design",
      page: "3",
    });

    const pages = links.filter((l) => l.text === "이전" || l.text === "다음");
    assert.equal(pages.length, 2);
    for (const l of pages) assert.equal(query(l.href).get("sort"), "easy", l.href);

    const cards = links.filter((l) => /^\/learn\/words\/\d+\?/.test(l.href));
    assert.ok(cards.length > 0);
    for (const l of cards) {
      const back = new URL(query(l.href).get("from") ?? "", "http://x");
      assert.equal(back.searchParams.get("sort"), "easy", l.href);
      assert.equal(back.searchParams.get("page"), "3", l.href);
    }

    // 필터 패널 안의 칩: 정처기·과목·난이도·분류. 정렬 줄과 탭바는 뺀다.
    const filterChips = links.filter(
      (l) =>
        l.href.startsWith("/learn/words") &&
        !/aria-label="정렬 /.test(l.html) &&
        (/aria-label="(정처기|과목|난이도|분류) /.test(l.html)),
    );
    assert.ok(filterChips.length >= 8, `칩이 너무 적다: ${filterChips.length}`);
    for (const l of filterChips) {
      assert.equal(query(l.href).get("sort"), "easy", `${l.text} ${l.href}`);
      assert.equal(query(l.href).get("shuffle"), null, `${l.text} ${l.href}`);
    }
  });

  it("정렬 줄: 켜진 칩을 누르면 정렬이 풀리고, 섞어서는 sort 를 떼며, 다른 조건은 남긴다", async () => {
    const row = await sortRow(WordsPage, { sort: "easy", category: "git" });
    assert.deepEqual(
      row.map((c) => [c.text, c.active]),
      [
        ["섞어서", false],
        ["쉬운 것부터", true],
      ],
    );
    for (const chip of row) {
      assert.equal(query(chip.href).get("category"), "git", chip.href);
    }
    assert.equal(query(row[0].href).get("sort"), null);
    assert.equal(query(row[1].href).get("sort"), null, "켜진 칩은 끄는 링크다");
    // 정렬을 끄는 두 링크는 섞인 목록으로 가므로 새 시드를 미리 싣는다.
    // 없으면 서버가 시드를 붙여 한 번 더 보내고 그 사이 필터 상자가 닫힌다.
    assert.ok(query(row[0].href).get("shuffle"), row[0].href);
    assert.ok(query(row[1].href).get("shuffle"), row[1].href);
  });

  it("필터 칩 링크는 새 시드를 미리 싣는다 - 서버가 한 번 더 보내며 필터 상자를 닫지 않게", async () => {
    // 되돌리면 칩을 누를 때마다 서버가 시드를 붙여 다시 보내고, 그 사이 화면이
    // 새로 그려져 펼쳐 둔 필터 상자가 닫힌다(실측: 정렬 없는 목록에서 칩을
    // 누르면 닫히고, 정렬 중에는 안 닫혔다).
    const links = await renderedLinks(WordsPage, { shuffle: "now", category: "git" });
    const chips = links.filter((l) =>
      /aria-label="(정처기|난이도|분류) /.test(l.html),
    );
    assert.ok(chips.length >= 5, `칩이 너무 적다: ${chips.length}`);
    for (const chip of chips) {
      const seed = query(chip.href).get("shuffle");
      assert.ok(seed, chip.href);
      // 지금 보는 시드를 물려주지 않는다 - 조건을 바꾸면 새 순서여야 한다.
      assert.notEqual(seed, "now", chip.href);
    }
  });

  it("검색 중에는 칩 링크에 시드를 싣지 않는다(검색 중엔 섞지 않는다)", async () => {
    const links = await renderedLinks(WordsPage, { search: "git" });
    for (const link of links) {
      assert.equal(query(link.href).get("shuffle"), null, link.href);
    }
  });

  it("공백만 있는 검색어는 검색이 아니다 - 섞은 목록으로 보낸다", async () => {
    // 되돌리면 "  " 을 검색 중으로 보고 섞지 않은 채 '"  " 검색 결과' 를 띄운다.
    const to = await redirectedTo(WordsPage, { search: "   " });
    assert.ok(to.searchParams.get("shuffle"), to.href);
    assert.equal(to.searchParams.get("search"), null, to.href);
  });

  it("정렬을 안 골랐으면 섞어서가 켜진다", async () => {
    const row = await sortRow(WordsPage, { shuffle: "seed" });
    assert.equal(row.find((c) => c.active)?.text, "섞어서");
  });

  it("검색 중에는 섞지 않으므로 맨 앞 칩이 섞어서가 아니라 기본순이다", async () => {
    // 되돌리면 켜진 "섞어서" 칩이 섞이지 않은 검색 결과 위에 뜬다.
    for (const page of [WordsPage, SentencesPage]) {
      const row = await sortRow(page, { search: "git" });
      assert.equal(row[0].text, "기본순");
      assert.equal(row.find((c) => c.active)?.text, "기본순");
      assert.ok(!row.some((c) => c.text === "섞어서"));
    }
  });
});

// ---- 문장 목록 ------------------------------------------------------------

describe("/learn/sentences 정렬", () => {
  it("?sort=easy 는 ordering=difficulty,id 로 부르며 섞지 않는다", async () => {
    await visit(SentencesPage, { sort: "easy", shuffle: "abc" });
    assert.equal(listQueries[0].get("ordering"), "difficulty,id");
    assert.equal(listQueries[0].get("shuffle"), null);
  });

  it("문장에 없는 ?sort=abc 는 없는 것으로 보고 시드를 붙여 보낸다", async () => {
    const to = await redirectedTo(SentencesPage, { sort: "abc" });
    assert.ok(to.searchParams.get("shuffle"));
    assert.equal(to.searchParams.get("sort"), null);
  });

  it("페이지 넘기기·카드·종류/난이도/분류 칩이 모두 sort 를 들고 간다", async () => {
    const links = await renderedLinks(SentencesPage, {
      sort: "easy",
      kind: "error",
      difficulty: "1",
      category: "git",
      page: "2",
    });

    const pages = links.filter((l) => l.text === "이전" || l.text === "다음");
    assert.equal(pages.length, 2);
    for (const l of pages) assert.equal(query(l.href).get("sort"), "easy", l.href);

    const cards = links.filter((l) => /^\/learn\/sentences\/\d+\?/.test(l.href));
    assert.ok(cards.length > 0);
    for (const l of cards) {
      const back = new URL(query(l.href).get("from") ?? "", "http://x");
      assert.equal(back.searchParams.get("sort"), "easy", l.href);
    }

    const filterChips = links.filter(
      (l) =>
        l.href.startsWith("/learn/sentences") &&
        /aria-label="(종류|난이도|분류) /.test(l.html),
    );
    assert.ok(filterChips.length >= 8, `칩이 너무 적다: ${filterChips.length}`);
    for (const l of filterChips) {
      assert.equal(query(l.href).get("sort"), "easy", `${l.text} ${l.href}`);
    }
  });

  it("정렬 줄은 섞어서·쉬운 것부터 둘이다", async () => {
    const row = await sortRow(SentencesPage, { sort: "easy" });
    assert.deepEqual(
      row.map((c) => [c.text, c.active]),
      [
        ["섞어서", false],
        ["쉬운 것부터", true],
      ],
    );
  });
});

// ---- 필터 칩의 섞기 시드 (두 목록 공통) ----------------------------------
//
// 칩 링크에 시드가 없으면 서버가 시드를 붙여 한 번 더 보내고, 그 사이 화면이
// 다시 그려져 펼쳐 둔 필터 상자가 닫힌다. 그래서 칩은 새 시드를 미리 싣고,
// 페이지 넘기기·카드의 되돌아올 주소는 지금 시드를 그대로 싣는다.

const lists = [
  { name: "words", page: WordsPage, rows: /aria-label="(정처기|과목|난이도|분류) / },
  { name: "sentences", page: SentencesPage, rows: /aria-label="(종류|난이도|분류) / },
] as const;

for (const { name, page, rows } of lists) {
  describe(`/learn/${name} 칩의 시드`, () => {
    const shuffled = { shuffle: "now", category: "git", difficulty: "1" };

    it("거르는 칩은 전부 새 시드를, 페이지 넘기기·카드는 지금 시드를 싣는다", async () => {
      const links = await renderedLinks(page, { ...shuffled, page: "2" });

      const chips = links.filter((l) => rows.test(l.html));
      assert.ok(chips.length >= 6, `칩이 너무 적다: ${chips.length}`);
      for (const chip of chips) {
        const seed = query(chip.href).get("shuffle");
        assert.ok(seed, chip.href);
        assert.notEqual(seed, "now", chip.href);
        // 칩은 page 를 떼고 간다(조건이 바뀌면 1페이지부터).
        assert.equal(query(chip.href).get("page"), null, chip.href);
      }

      const pages = links.filter((l) => l.text === "이전" || l.text === "다음");
      assert.equal(pages.length, 2);
      for (const l of pages) assert.equal(query(l.href).get("shuffle"), "now", l.href);

      const cards = links.filter((l) => new RegExp(`^/learn/${name}/\\d+\\?`).test(l.href));
      assert.ok(cards.length > 0);
      for (const l of cards) {
        const back = new URL(query(l.href).get("from") ?? "", "http://x");
        assert.equal(back.searchParams.get("shuffle"), "now", l.href);
      }
    });

    it("칩 시드는 그릴 때마다 새로 만든다(고정값이면 칩을 눌러도 늘 같은 순서)", async () => {
      const seedOf = async () => {
        const links = await renderedLinks(page, shuffled);
        return query(links.find((l) => rows.test(l.html))!.href).get("shuffle");
      };
      assert.notEqual(await seedOf(), await seedOf());
    });

    it("정렬 줄: 끄는 칩(섞어서)만 시드를 싣고, 켜는 칩은 안 싣는다", async () => {
      const row = await sortRow(page, shuffled);
      const off = row.find((c) => c.text === "섞어서")!;
      const on = row.find((c) => c.text === "쉬운 것부터")!;
      assert.ok(query(off.href).get("shuffle"), off.href);
      assert.notEqual(query(off.href).get("shuffle"), "now", off.href);
      assert.equal(query(on.href).get("shuffle"), null, on.href);
      assert.equal(query(on.href).get("sort"), "easy", on.href);
    });

    it("정렬 중: 거르는 칩은 시드 없이 정렬을, 정렬을 끄는 칩은 새 시드를 싣는다", async () => {
      const links = await renderedLinks(page, { sort: "easy", category: "git" });
      for (const chip of links.filter((l) => rows.test(l.html))) {
        assert.equal(query(chip.href).get("shuffle"), null, chip.href);
        assert.equal(query(chip.href).get("sort"), "easy", chip.href);
      }
      for (const chip of await sortRow(page, { sort: "easy", category: "git" })) {
        assert.equal(query(chip.href).get("sort"), null, chip.href);
        assert.ok(query(chip.href).get("shuffle"), chip.href);
      }
    });

    it("검색 + 정렬 중에는 어느 링크에도 시드가 없다(정렬을 꺼도 검색 중이라 안 섞는다)", async () => {
      const links = await renderedLinks(page, { search: "git", sort: "easy" });
      for (const link of links) {
        assert.equal(query(link.href).get("shuffle"), null, link.href);
      }
      assert.equal(listQueries[0].get("shuffle"), null);
    });

    for (const blank of [" ", "\t", "\n", "　", " 　\t "]) {
      it(`검색어 ${JSON.stringify(blank)} 는 검색이 아니다 - 다른 조건은 둔 채 섞은 목록으로 보낸다`, async () => {
        const to = await redirectedTo(page, { search: blank, difficulty: "1" });
        assert.equal(to.pathname, `/learn/${name}`);
        assert.ok(to.searchParams.get("shuffle"), to.href);
        assert.equal(to.searchParams.get("search"), null, to.href);
        assert.equal(to.searchParams.get("difficulty"), "1", to.href);
        assert.equal(listQueries.length, 0, "보내기 전에 목록을 부르지 않는다");
      });
    }

    it("공백 검색어 + 정렬이면 보내지 않고, 백엔드에도 search 를 안 보낸다", async () => {
      await visit(page, { search: "  ", sort: "easy" });
      assert.equal(listQueries.length, 1);
      assert.equal(listQueries[0].get("search"), null);
      assert.equal(listQueries[0].get("shuffle"), null);
    });

    it("앞뒤 공백이 있는 검색어는 털어서 검색하고, 링크에도 털린 값이 간다", async () => {
      const links = await renderedLinks(page, { search: "　 git\t" });
      assert.equal(listQueries[0].get("search"), "git");
      assert.equal(listQueries[0].get("shuffle"), null);
      const chips = links.filter((l) => rows.test(l.html));
      assert.ok(chips.length > 0);
      for (const chip of chips) {
        assert.equal(query(chip.href).get("search"), "git", chip.href);
        assert.equal(query(chip.href).get("shuffle"), null, chip.href);
      }
    });
  });
}
