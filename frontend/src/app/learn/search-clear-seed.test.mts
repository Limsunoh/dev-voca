/**
 * 익히기 목록의 검색창이 검색어를 비울 때 섞기 시드를 싣는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 시드 없이 비우면 목록 화면이 시드를 붙여 한 번 더 보내고, 그 사이 화면이
 * 새로 그려져 펼쳐 둔 필터 상자가 닫힌다. 그래서 목록 화면이 새 시드를
 * 만들어 검색창에 넘기고(정렬 중이면 안 섞으므로 없다), 검색창은 검색어를
 * 비울 때만 그것을 싣는다.
 *
 * 보는 것:
 * - 검색창 제출: 검색 중/아님 x 정렬 중/아님 x 입력값. page 는 늘 떨어지고,
 *   다른 조건은 남고, 옛 시드는 안 남는다.
 * - 목록 화면이 검색창에 넘기는 seed: 정렬 중이 아니면 있고(검색 중에도),
 *   정렬 중이면 없고, 그릴 때마다 새 값이다.
 * - 이어 보기: 검색창이 보낸 주소로 목록 화면을 열면 redirect 가 없다.
 * - 공백·쉼표만 있는 ?search= 는 검색이 아니다.
 *
 * 검색창은 react 의 useState 를 작은 대역으로 바꿔 함수로 부르고, 트리에서
 * input 의 onChange 와 form 의 onSubmit 을 꺼내 부른다. 목록 화면은 그리지
 * 않고 돌려준 트리에서 SearchInput 요소의 props 를 읽는다. 백엔드는 전역
 * fetch 대역이다(sort-page.test.mts 와 같은 방식).
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

import type { ReactElement } from "react";

// ---- next/navigation 대역 --------------------------------------------------

class NotFound extends Error {}
class Redirect extends Error {
  constructor(readonly to: string) {
    super("NEXT_REDIRECT");
  }
}

/** 검색창이 router.push 로 보낸 주소. */
let pushed: string[] = [];
/** 검색창이 읽는 지금 주소의 쿼리. */
let current = new URLSearchParams();

mock.module("next/navigation", {
  namedExports: {
    notFound: () => {
      throw new NotFound();
    },
    redirect: (to: string) => {
      throw new Redirect(to);
    },
    useRouter: () => ({
      push: (to: string) => pushed.push(to),
      replace() {},
      prefetch() {},
    }),
    useSearchParams: () => current,
    usePathname: () => "/",
  },
});

// ---- react 훅 대역 ---------------------------------------------------------

const realReact = await import("react");

type Slot = { value: unknown };
let slots: Slot[] = [];
let cursor = 0;

mock.module("react", {
  defaultExport: realReact.default,
  namedExports: {
    ...realReact,
    useState<T>(init: T | (() => T)) {
      if (cursor >= slots.length) {
        slots.push({
          value: typeof init === "function" ? (init as () => T)() : init,
        });
      }
      const s = slots[cursor++];
      const set = (next: T | ((prev: T) => T)) => {
        s.value =
          typeof next === "function" ? (next as (prev: T) => T)(s.value as T) : next;
      };
      return [s.value, set];
    },
  },
});

// ---- 백엔드 대역 -----------------------------------------------------------

let listQueries: URLSearchParams[] = [];

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
  const url = new URL(String(input));
  const path = url.pathname;
  if (path.endsWith("/categories/")) return json(choices(["git", "api"]));
  if (path.endsWith("/difficulties/")) return json(choices(["1", "2"]));
  if (path.endsWith("/exam_subjects/")) return json(choices(["design"]));
  if (path.endsWith("/kinds/")) return json(choices(["phrase", "error"]));
  if (/\/(words|sentences)\/$/.test(path)) {
    listQueries.push(url.searchParams);
    return json({ count: 0, next: null, previous: null, results: [] });
  }
  throw new Error(`대역에 없는 요청: ${url}`);
}) as typeof fetch;

after(() => {
  globalThis.fetch = realFetch;
});

const { SearchInput } = await import("@/components/SearchInput");
const WordsPage = (await import("./words/page")).default;
const SentencesPage = (await import("./sentences/page")).default;

type Params = Record<string, string | string[]>;
type Page = typeof WordsPage;
type Props = { basePath: string; seed?: string };

beforeEach(() => {
  pushed = [];
  listQueries = [];
  current = new URLSearchParams();
  slots = [];
  cursor = 0;
});

// ---- 도우미 ----------------------------------------------------------------

/** 트리에서 조건에 맞는 요소를 모두 찾는다. 컴포넌트는 펼치지 않는다. */
function findAll(
  node: unknown,
  match: (el: ReactElement) => boolean,
  out: ReactElement[] = [],
): ReactElement[] {
  if (Array.isArray(node)) {
    for (const child of node) findAll(child, match, out);
    return out;
  }
  if (!node || typeof node !== "object" || !("props" in node)) return out;
  const el = node as ReactElement<Record<string, unknown>>;
  if (match(el)) out.push(el);
  for (const value of Object.values(el.props)) findAll(value, match, out);
  return out;
}

function findOne<P>(node: unknown, type: string): ReactElement<P> {
  const found = findAll(node, (el) => el.type === type);
  assert.equal(found.length, 1, `${type} 가 하나가 아니다: ${found.length}`);
  return found[0] as ReactElement<P>;
}

function renderInput(props: Props) {
  cursor = 0;
  return SearchInput(props);
}

/**
 * 지금 주소가 `from` 인 검색창에 `typed` 를 넣고(없으면 그대로) 제출한다.
 * 보낸 주소를 돌려준다.
 */
function submit(from: string, props: Props, typed?: string): URL {
  current = new URLSearchParams(from);
  slots = [];
  pushed = [];
  let tree = renderInput(props);
  if (typed !== undefined) {
    const input = findOne<{
      onChange: (e: { target: { value: string } }) => void;
    }>(tree, "input");
    input.props.onChange({ target: { value: typed } });
    tree = renderInput(props);
  }
  let prevented = false;
  const form = findOne<{
    onSubmit: (e: { preventDefault: () => void }) => void;
  }>(tree, "form");
  form.props.onSubmit({
    preventDefault: () => {
      prevented = true;
    },
  });
  assert.ok(prevented, "제출 기본 동작(새로고침)을 막지 않았다");
  assert.equal(pushed.length, 1, "router.push 를 한 번 부르지 않았다");
  return new URL(pushed[0], "http://x");
}

const visit = (page: Page, params: Params) =>
  page({ searchParams: Promise.resolve(params) });

/** 목록 화면이 검색창에 넘긴 props. */
async function searchInputProps(page: Page, params: Params): Promise<Props> {
  const tree = await visit(page, params);
  const found = findAll(tree, (el) => el.type === SearchInput);
  assert.equal(found.length, 1, `검색창이 하나가 아니다: ${found.length}`);
  return found[0].props as Props;
}

async function redirectedTo(page: Page, params: Params): Promise<URL> {
  let to = "";
  await assert.rejects(visit(page, params), (error) => {
    assert.ok(error instanceof Redirect, `redirect 가 아니다: ${error}`);
    to = error.to;
    return true;
  });
  return new URL(to, "http://x");
}

// ---- 검색창 제출 -----------------------------------------------------------

const BLANKS = ["", " ", "   ", "\t", ",", " , ", ",,", "　,", " ,\t, "];

/** 지금 보고 있을 수 있는 목록 주소. 목록 화면이 redirect 없이 그리는 것만. */
const states = [
  { name: "섞인 목록", from: "shuffle=old&category=git&difficulty=1&page=3", sorted: false, searching: false },
  { name: "검색 중", from: "search=git&category=git&page=2", sorted: false, searching: true },
  { name: "정렬 중", from: "sort=easy&category=git&page=2", sorted: true, searching: false },
  { name: "검색 + 정렬 중", from: "search=git&sort=easy&difficulty=1&page=2", sorted: true, searching: true },
] as const;

describe("검색창 제출", () => {
  for (const state of states) {
    // 목록 화면이 넘기는 규칙 그대로: 정렬 중이면 없다.
    const seed = state.sorted ? undefined : "SEED";
    const props = { basePath: "/learn/words", seed };
    const before = new URLSearchParams(state.from);

    for (const blank of BLANKS) {
      it(`${state.name}에서 ${JSON.stringify(blank)} 로 비우면 search 를 떼고 ${seed ? "새 시드를 싣는다" : "시드를 안 싣는다"}`, () => {
        const to = submit(state.from, props, blank);
        assert.equal(to.pathname, "/learn/words");
        assert.equal(to.searchParams.get("search"), null, to.href);
        assert.equal(to.searchParams.get("page"), null, to.href);
        assert.equal(to.searchParams.get("shuffle"), seed ?? null, to.href);
        // 다른 조건은 그대로 남는다.
        for (const key of ["category", "difficulty", "sort"]) {
          assert.equal(to.searchParams.get(key), before.get(key), `${key} ${to.href}`);
        }
      });
    }

    for (const [typed, expected] of [
      ["git", "git"],
      [" git ", "git"],
      ["　git\t", "git"],
      [",git", ",git"],
      ["a, b", "a, b"],
      ["c++ & c#?", "c++ & c#?"],
    ]) {
      it(`${state.name}에서 ${JSON.stringify(typed)} 로 검색하면 search=${JSON.stringify(expected)} 이고 시드는 없다`, () => {
        const to = submit(state.from, props, typed);
        assert.equal(to.searchParams.get("search"), expected, to.href);
        assert.equal(to.searchParams.getAll("search").length, 1, to.href);
        assert.equal(to.searchParams.get("shuffle"), null, to.href);
        assert.equal(to.searchParams.get("page"), null, to.href);
        for (const key of ["category", "difficulty", "sort"]) {
          assert.equal(to.searchParams.get(key), before.get(key), `${key} ${to.href}`);
        }
      });
    }
  }

  it("검색 중에 손대지 않고 다시 제출하면 같은 검색어로 1페이지를 연다", () => {
    const to = submit("search=git&page=4", { basePath: "/learn/words", seed: "S" });
    assert.equal(to.searchParams.get("search"), "git");
    assert.equal(to.searchParams.get("page"), null);
    assert.equal(to.searchParams.get("shuffle"), null);
  });

  it("시드도 다른 조건도 없이 비우면 쿼리 없는 주소로 간다(끝에 ? 가 안 붙는다)", () => {
    submit("search=git", { basePath: "/learn/sentences" }, "");
    assert.equal(pushed[0], "/learn/sentences");
  });

  it("주소에 시드가 둘 이상 남아 있어도 비울 때 실리는 것은 새 시드 하나다", () => {
    const to = submit("shuffle=a&shuffle=b&search=x", { basePath: "/learn/words", seed: "NEW" }, "");
    assert.deepEqual(to.searchParams.getAll("shuffle"), ["NEW"]);
  });

  it("빈 문자열 시드는 싣지 않는다(shuffle= 로 가면 서버가 다시 보낸다)", () => {
    const to = submit("search=x", { basePath: "/learn/words", seed: "" }, "");
    assert.equal(to.searchParams.has("shuffle"), false, to.href);
  });
});

// ---- 목록 화면이 넘기는 seed ----------------------------------------------

const pages = [
  { name: "words", page: WordsPage },
  { name: "sentences", page: SentencesPage },
] as const;

for (const { name, page } of pages) {
  describe(`/learn/${name} 가 검색창에 넘기는 seed`, () => {
    for (const params of [
      { shuffle: "now" },
      { shuffle: "now", category: "git", difficulty: "1", page: "2" },
      { search: "git" },
      { search: "git", category: "git" },
      { search: "  git ", shuffle: "now" },
    ] as Params[]) {
      it(`${JSON.stringify(params)} 이면 새 시드가 있다`, async () => {
        const props = await searchInputProps(page, params);
        assert.equal(props.basePath, `/learn/${name}`);
        assert.ok(props.seed, `seed 가 없다: ${JSON.stringify(props)}`);
        assert.notEqual(props.seed, "now", "지금 시드를 물려주면 비워도 같은 순서다");
      });
    }

    for (const params of [
      { sort: "easy" },
      { sort: "easy", shuffle: "now" },
      { sort: "easy", search: "git" },
      { sort: "easy", search: "," },
    ] as Params[]) {
      it(`${JSON.stringify(params)} 이면 seed 가 없다(정렬 중엔 안 섞는다)`, async () => {
        const props = await searchInputProps(page, params);
        assert.equal(props.seed, undefined);
      });
    }

    it("그릴 때마다 새 시드다", async () => {
      const a = await searchInputProps(page, { search: "git" });
      const b = await searchInputProps(page, { search: "git" });
      assert.notEqual(a.seed, b.seed);
    });

    for (const blank of [",", " , ", ",,,", "　,\t", "\n"]) {
      it(`?search=${JSON.stringify(blank)} 는 검색이 아니다 - 목록을 부르지 않고 시드를 붙여 보낸다`, async () => {
        const to = await redirectedTo(page, { search: blank, category: "git" });
        assert.equal(to.pathname, `/learn/${name}`);
        assert.equal(to.searchParams.get("search"), null, to.href);
        assert.ok(to.searchParams.get("shuffle"), to.href);
        assert.equal(to.searchParams.get("category"), "git", to.href);
        assert.equal(listQueries.length, 0);
      });
    }

    it("?search=, 가 여러 개면 첫 값으로 본다", async () => {
      const to = await redirectedTo(page, { search: [",", "git"] });
      assert.equal(to.searchParams.get("search"), null, to.href);
    });

    it("정렬 중 ?search=, 는 redirect 없이 그리고 백엔드에 search 를 안 보낸다", async () => {
      await visit(page, { search: " , ", sort: "easy" });
      assert.equal(listQueries.length, 1);
      assert.equal(listQueries[0].get("search"), null);
    });

    it("검색어 사이 쉼표는 그대로 검색어다(쉼표만 있을 때만 버린다)", async () => {
      await visit(page, { search: " ,git, " });
      assert.equal(listQueries.length, 1);
      assert.equal(listQueries[0].get("search"), ",git,");
      assert.equal(listQueries[0].get("shuffle"), null);
    });
  });

  // ---- 이어 보기: 검색창이 보낸 주소를 목록 화면이 다시 보내지 않는가 ----

  describe(`/learn/${name} 검색창에서 보낸 주소를 열면 redirect 가 없다`, () => {
    for (const state of states) {
      for (const typed of ["", " , ", "git"]) {
        it(`${state.name}에서 ${JSON.stringify(typed)} 제출`, async () => {
          const params = Object.fromEntries(new URLSearchParams(state.from));
          const props = await searchInputProps(page, params);
          const to = submit(state.from, props, typed);
          listQueries = [];
          // redirect 가 던지면 여기서 실패한다. 그 사이 필터 상자가 닫힌다.
          await visit(page, Object.fromEntries(to.searchParams));
          assert.equal(listQueries.length, 1);
          const sent = listQueries[0];
          if (typed.trim() === "git") {
            assert.equal(sent.get("search"), "git");
            assert.equal(sent.get("shuffle"), null);
          } else {
            assert.equal(sent.get("search"), null);
            assert.equal(sent.get("shuffle"), props.seed ?? null);
          }
        });
      }
    }
  });
}

describe("검색창 - 비우면 입력창도 비운다", () => {
  // 검색 중이 아니었으면 key 가 그대로라 입력창이 새로 만들어지지 않는다.
  // 비우지 않으면 쉼표를 친 채로 남아 목록(전체)과 입력창이 다른 말을 한다.
  for (const typed of [",", " , ", "  "]) {
    it(`${JSON.stringify(typed)} 를 넣고 제출하면 입력창이 빈다`, () => {
      const props = { basePath: "/learn/words", seed: "fresh" };
      submit("shuffle=now", props, typed);
      const input = findOne<{ value: string }>(renderInput(props), "input");
      assert.equal(input.props.value, "");
    });
  }

  it("검색어가 있으면 입력창을 그대로 둔다", () => {
    // 같은 검색어를 다시 내면 key 가 그대로라, 여기서 비우면 주소는
    // search=git 인데 입력창만 빈다.
    const props = { basePath: "/learn/words", seed: "fresh" };
    submit("search=git", props, "git");
    const input = findOne<{ value: string }>(renderInput(props), "input");
    assert.equal(input.props.value, "git");
  });
});
