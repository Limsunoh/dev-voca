/**
 * 홈의 오늘의 개발영어에서 연 단어 상세(`?today=1`).
 *
 * 실행: cd frontend && npm test
 *
 * 상세는 today=1 이면 홈과 같은 getDailyWords(HOME_WORDS) 로 묶음을 받아
 * 몇 번째인지 찾고, 이전 / n/7 / 다음 줄을 그린다. 되돌아가기는 홈이다.
 * 묶음에 없는 단어(자정이 지났거나 단어 수가 바뀐 경우)는 줄을 그리지 않고,
 * 묶음을 못 받아도 상세 자체는 그대로 열린다.
 *
 * getWord·getDailyWords 는 대역으로 바꾼다. 실제 함수는 fetch 를 치고,
 * 여기서 보려는 것은 페이지가 그 결과로 무엇을 그리는가다.
 */
import assert from "node:assert/strict";
import { beforeEach, describe, it, mock } from "node:test";

class NotFound extends Error {}

mock.module("next/navigation", {
  namedExports: {
    notFound: () => {
      throw new NotFound();
    },
    redirect: (to: string) => {
      throw new Error(`redirect ${to}`);
    },
    useRouter: () => ({ back() {}, push() {}, replace() {}, prefetch() {} }),
  },
});

const { createElement } = await import("react");

// 넘길 때 방문 기록을 쌓지 않는 것(replace)은 정적 HTML 에 안 남는다.
// Link 를 replace 값을 속성으로 남기는 a 로 바꿔 그것까지 본다.
mock.module("next/link", {
  // 주소·replace·글자만 옮긴다. 이 테스트가 보는 것은 그 셋뿐이다.
  defaultExport: ({
    href,
    replace,
    children,
  }: {
    href: string;
    replace?: boolean;
    children?: never;
  }) =>
    createElement(
      "a",
      { href, "data-replace": replace ? "true" : undefined },
      children,
    ),
});

const BUNDLE = [57, 939, 576, 720, 372, 291, 940];

let dailyCalls = 0;
let dailyResult: () => Promise<{ id: number }[]> = async () =>
  BUNDLE.map((id) => ({ id }));
let wordGate: Promise<void> = Promise.resolve();

const fakeWord = (id: number) => ({
  id,
  term: `term-${id}`,
  pronunciation: "",
  reading: "",
  reading_note: "",
  meaning: `뜻-${id}`,
  category: "devops",
  category_label: "배포",
  difficulty: "easy",
  difficulty_label: "쉬움",
  is_exam: false,
  exam_subject: "",
  exam_subject_label: "",
  description: "",
  example: "",
  example_translation: "",
  aliases: "",
});

mock.module("@/lib/api/vocab", {
  namedExports: {
    HOME_WORDS: 7,
    getDailyWords: (size: number) => {
      dailyCalls += 1;
      assert.equal(size, 7, "홈과 같은 개수로 받아야 순서가 같다");
      return dailyResult();
    },
    getWord: async (id: string) => {
      await wordGate;
      return /^\d+$/.test(id) ? fakeWord(Number(id)) : null;
    },
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { default: WordDetailPage } = await import("./[id]/page");
const { routes } = await import("@/lib/routes");

const realError = console.error;

beforeEach(() => {
  dailyCalls = 0;
  dailyResult = async () => BUNDLE.map((id) => ({ id }));
  wordGate = Promise.resolve();
  console.error = realError;
});

async function render(id: number | string, query: Record<string, string | string[]> = {}) {
  const element = await WordDetailPage({
    params: Promise.resolve({ id: String(id) }),
    searchParams: Promise.resolve(query),
  });
  return renderToStaticMarkup(element);
}

/** 넘기는 줄만 잘라 낸다. 없으면 null. */
function todayNav(html: string): string | null {
  const start = html.indexOf('aria-label="오늘의 개발영어"');
  if (start < 0) return null;
  return html.slice(start, html.indexOf("</nav>", start));
}

const hrefs = (fragment: string) =>
  [...fragment.matchAll(/<a[^>]*href="([^"]*)"/g)].map((m) => m[1].replaceAll("&amp;", "&"));

const position = (fragment: string) =>
  fragment.match(/tabular-nums[^>]*>([\s\S]*?)<\/p>/)?.[1].replace(/<!-- -->/g, "");

/** 되돌아가기 링크(본문 첫 링크)의 주소와 글자. */
function back(html: string) {
  const main = html.slice(html.indexOf("<main"));
  const a = main.match(/<a[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/)!;
  return { href: a[1].replaceAll("&amp;", "&"), label: a[2].replace(/<[^>]+>/g, "").replace("←", "").trim() };
}

describe("routes.todayWord", () => {
  it("상세 주소에 today=1 을 붙인다", () => {
    assert.equal(routes.todayWord(57), "/learn/words/57?today=1");
    assert.equal(routes.todayWord("57"), "/learn/words/57?today=1");
  });
});

describe("today=1 이고 묶음 안의 단어", () => {
  BUNDLE.forEach((id, index) => {
    it(`${index + 1}번째(${id}) 는 ${index + 1} / 7 이고 앞뒤 단어로 넘긴다`, async () => {
      const nav = todayNav(await render(id, { today: "1" }));
      assert.ok(nav, "넘기는 줄이 있어야 한다");
      assert.equal(position(nav), `${index + 1} / 7`);

      const expected = [
        ...(index > 0 ? [routes.todayWord(BUNDLE[index - 1])] : []),
        ...(index < BUNDLE.length - 1 ? [routes.todayWord(BUNDLE[index + 1])] : []),
      ];
      assert.deepEqual(hrefs(nav), expected);
      // 끝에서 자리만 지키는 쪽은 링크가 아니라 누를 수 없다.
      assert.equal((nav.match(/<a /g) ?? []).length, expected.length);
    });
  });

  it("되돌아가기는 홈이다", async () => {
    assert.deepEqual(back(await render(576, { today: "1" })), { href: "/", label: "홈" });
  });

  it("from 이 같이 붙어 있어도 되돌아가기는 홈이다", async () => {
    const html = await render(576, { today: "1", from: "/learn/words?search=abc" });
    assert.deepEqual(back(html), { href: "/", label: "홈" });
    assert.ok(todayNav(html));
  });

  it("묶음은 단어와 동시에 받는다 - 단어를 기다린 뒤에 부르지 않는다", async () => {
    let release!: () => void;
    wordGate = new Promise((resolve) => {
      release = resolve;
    });
    const pending = render(576, { today: "1" });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(dailyCalls, 1, "getWord 가 끝나기 전에 getDailyWords 가 불려야 한다");
    release();
    assert.ok(todayNav(await pending));
  });
});

describe("넘기기는 방문 기록을 쌓지 않는다", () => {
  it("이전·다음 링크는 모두 replace 다 - 뒤로 가기 한 번이면 홈이다", async () => {
    const nav = todayNav(await render(576, { today: "1" }))!;
    const links = nav.match(/<a [^>]*>/g) ?? [];
    assert.equal(links.length, 2);
    for (const link of links) assert.match(link, /data-replace="true"/);
  });

  it("되돌아가기(홈) 링크는 replace 가 아니다", async () => {
    const html = await render(576, { today: "1" });
    const main = html.slice(html.indexOf("<main"));
    assert.doesNotMatch(main.match(/<a [^>]*>/)![0], /data-replace/);
  });
});

describe("today=1 이지만 넘길 수 없는 경우", () => {
  it("묶음에 없는 단어는 줄을 그리지 않고, 되돌아가기는 홈이다", async () => {
    const html = await render(1, { today: "1" });
    assert.equal(todayNav(html), null);
    assert.deepEqual(back(html), { href: "/", label: "홈" });
  });

  it("묶음을 못 받아도 상세는 열리고 줄만 없다", async () => {
    console.error = () => {};
    dailyResult = async () => {
      throw new Error("backend down");
    };
    const html = await render(576, { today: "1" });
    assert.match(html, /term-576/);
    assert.equal(todayNav(html), null);
    assert.deepEqual(back(html), { href: "/", label: "홈" });
  });

  it("없는 단어는 today=1 이어도 404 다", async () => {
    await assert.rejects(render("abc", { today: "1" }), NotFound);
  });
});

describe("today=1 이 아니면 예전 상세 그대로", () => {
  const queries: Record<string, string>[] = [{}, { today: "0" }, { today: "true" }];
  for (const query of queries) {
    it(`${JSON.stringify(query)}: 묶음을 받지 않고 줄도 없고 단어장으로 돌아간다`, async () => {
      const html = await render(576, query);
      assert.equal(dailyCalls, 0);
      assert.equal(todayNav(html), null);
      assert.deepEqual(back(html), { href: "/learn/words", label: "단어장" });
    });
  }

  it("from 이 있으면 그 목록으로 돌아간다", async () => {
    const html = await render(576, { from: "/learn/words?search=abc" });
    assert.deepEqual(back(html), { href: "/learn/words?search=abc", label: "단어장" });
  });
});
