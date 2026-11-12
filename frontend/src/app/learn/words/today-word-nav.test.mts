/**
 * 홈의 오늘의 단어에서 연 단어 상세(`?today=57-939-...`).
 *
 * 실행: cd frontend && npm test
 *
 * 홈은 보여준 묶음의 순서를 상세 주소에 싣는다(`?today=57-939-...`,
 * routes.todayWord). 상세는 그 순서로 몇 번째인지 찾아 이전 / n / 다음 줄을
 * 그리고, 되돌아가기는 홈이다. 서버에 묶음을 다시 묻지 않는다 - 로그인한
 * 사람의 묶음은 일일공부 상태에서 오는데, 넘길 때마다 부르면 일일공부와 같은
 * 요청 한도를 나눠 쓴다. 묶음에 없는 단어나 예전 주소(today=1)는 줄을 그리지
 * 않는다.
 *
 * getWord 는 대역으로 바꾼다. getDailyWords 도 대역으로 두고 불리지 않는 것을
 * 센다.
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

// 상세가 날짜 묶음을 다시 부르게 되돌아가면 잡으려고 센다. 지금은 주소의
// 순서만 쓰므로 0 이어야 한다.
let dailyCalls = 0;

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
    getDailyWords: async () => {
      dailyCalls += 1;
      return BUNDLE.map((id) => ({ id }));
    },
    getWord: async (id: string) => (/^\d+$/.test(id) ? fakeWord(Number(id)) : null),
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { default: WordDetailPage } = await import("./[id]/page");
const { routes } = await import("@/lib/routes");

beforeEach(() => {
  dailyCalls = 0;
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

const TODAY = BUNDLE.join("-");

describe("routes.todayWord", () => {
  it("상세 주소에 홈이 보여준 묶음 순서를 싣는다", () => {
    assert.equal(routes.todayWord(57, BUNDLE), `/learn/words/57?today=${TODAY}`);
    assert.equal(routes.todayWord("57", [57, 939]), "/learn/words/57?today=57-939");
  });
});

describe("묶음 순서가 실린 상세", () => {
  BUNDLE.forEach((id, index) => {
    it(`${index + 1}번째(${id}) 는 ${index + 1} / 7 이고 앞뒤 단어로 넘긴다`, async () => {
      const nav = todayNav(await render(id, { today: TODAY }));
      assert.ok(nav, "넘기는 줄이 있어야 한다");
      assert.equal(position(nav), `${index + 1} / 7`);

      const expected = [
        ...(index > 0 ? [routes.todayWord(BUNDLE[index - 1], BUNDLE)] : []),
        ...(index < BUNDLE.length - 1 ? [routes.todayWord(BUNDLE[index + 1], BUNDLE)] : []),
      ];
      assert.deepEqual(hrefs(nav), expected);
      // 끝에서 자리만 지키는 쪽은 링크가 아니라 누를 수 없다.
      assert.equal((nav.match(/<a /g) ?? []).length, expected.length);
    });
  });

  it("두 개짜리 묶음(5분 첫 묶음)도 그 안에서 넘긴다", async () => {
    const nav = todayNav(await render(939, { today: "57-939" }));
    assert.equal(position(nav!), "2 / 2");
    assert.deepEqual(hrefs(nav!), [routes.todayWord(57, [57, 939])]);
  });

  it("같은 번호가 두 번 오면 한 번만 센다(손으로 고친 주소)", async () => {
    assert.equal(position(todayNav(await render(939, { today: "57-939-57" }))!), "2 / 2");
  });

  it("묶음은 홈 개수(7)에서 자른다 - 주소로 아무 길이나 넣을 수 있다", async () => {
    const long = [...BUNDLE, 11, 12].join("-");
    assert.equal(position(todayNav(await render(57, { today: long }))!), "1 / 7");
  });

  it("되돌아가기는 홈이다", async () => {
    assert.deepEqual(back(await render(576, { today: TODAY })), { href: "/", label: "홈" });
  });

  it("from 이 같이 붙어 있어도 되돌아가기는 홈이다", async () => {
    const html = await render(576, { today: TODAY, from: "/learn/words?search=abc" });
    assert.deepEqual(back(html), { href: "/", label: "홈" });
    assert.ok(todayNav(html));
  });

  it("묶음을 서버에 다시 묻지 않는다", async () => {
    await render(576, { today: TODAY });
    assert.equal(dailyCalls, 0);
  });
});

describe("넘기기는 방문 기록을 쌓지 않는다", () => {
  it("이전·다음 링크는 모두 replace 다 - 뒤로 가기 한 번이면 홈이다", async () => {
    const nav = todayNav(await render(576, { today: TODAY }))!;
    const links = nav.match(/<a [^>]*>/g) ?? [];
    assert.equal(links.length, 2);
    for (const link of links) assert.match(link, /data-replace="true"/);
  });

  it("되돌아가기(홈) 링크도 쌓지 않는다", async () => {
    // 앞 기록이 홈이면 뒤로 가기로 돌아가고(DetailBackLink), 아니면(공유받은
    // 주소로 앱을 열었다) 홈으로 바꿔치기한다. 쌓으면 [상세, 홈] 이 되어 홈에서
    // 뒤로 가기가 상세로 가고 앱(TWA)이 안 닫힌다(lib/history-nav.ts).
    const html = await render(576, { today: TODAY });
    const main = html.slice(html.indexOf("<main"));
    assert.match(main.match(/<a [^>]*>/)![0], /data-replace="true"/);
  });
});

describe("홈에서 왔지만 넘길 수 없는 경우", () => {
  it("묶음에 없는 단어는 줄을 그리지 않고, 되돌아가기는 홈이다", async () => {
    const html = await render(1, { today: TODAY });
    assert.equal(todayNav(html), null);
    assert.deepEqual(back(html), { href: "/", label: "홈" });
  });

  it("예전 주소(today=1)는 되돌아가기만 홈이고 줄은 없다", async () => {
    const html = await render(576, { today: "1" });
    assert.match(html, /term-576/);
    assert.equal(todayNav(html), null);
    assert.deepEqual(back(html), { href: "/", label: "홈" });
  });

  it("없는 단어는 홈에서 왔어도 404 다", async () => {
    await assert.rejects(render("abc", { today: TODAY }), NotFound);
  });
});

describe("묶음 순서가 없거나 망가지면 예전 상세 그대로", () => {
  const queries: Record<string, string>[] = [
    {},
    { today: "0" },
    { today: "true" },
    { today: "57--939" },
    { today: "-57" },
    { today: "57-0" },
  ];
  for (const query of queries) {
    it(`${JSON.stringify(query)}: 줄도 없고 단어장으로 돌아간다`, async () => {
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
