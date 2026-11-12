/**
 * 단어 상세 머리(DetailHead) 를 detail-head.test.mts 보다 넓은 상태에서 본다.
 *
 * 실행: cd frontend && npm test
 *
 * detail-head.test.mts 는 "한 번 열고 한 번 닫기" 를 컴포넌트만 따로 그려 본다.
 * 여기서는 그 바깥을 본다.
 *
 * - 같은 렌더에서 onClick 이 두 번 불려도 두 번 뒤집힌다. 빠르게 두 번 누르면
 *   React 가 두 클릭 사이에 다시 그리지 못할 수 있는데, setOpen(!open) 처럼 렌더
 *   당시 값을 쓰면 두 번째 클릭이 먹혀 열린 채로 남는다.
 * - 열고 닫기를 여러 번 반복해도 aria-expanded, hidden, 삼각형 셋이 늘 같은 쪽을
 *   가리키고, aria-controls 가 가리키는 설명이 언제나 그려져 있다.
 * - 되돌아가기와 히어로는 열든 닫든 꼭 한 번씩만 그려진다.
 * - 페이지 전체를 진짜 useId 로 그려도 aria-controls 가 페이지 안의 설명 하나를
 *   가리킨다(컴포넌트 테스트는 useId 를 고정값으로 바꿔서 이걸 못 본다).
 * - 페이지에서 설명은 제목(h1) 뒤, "설명" 카드 앞이다. 버튼은 맨 위 줄 안에 있고
 *   그 줄에는 되돌아가기 링크가 하나뿐이다.
 * - 설명에 들어온 꺾쇠는 글자로 나간다.
 *
 * useState 는 컴포넌트 함수를 직접 부를 때만 대역으로 바꾼다(direct). 페이지를
 * 그릴 때는 진짜 훅을 쓴다 - DetailBackLink 같은 다른 컴포넌트가 같은 대역 칸을
 * 나눠 쓰면 안 된다.
 */
import assert from "node:assert/strict";
import { beforeEach, describe, it, mock } from "node:test";
import type { ReactElement, ReactNode } from "react";

const realReact = await import("react");

let direct = false;
let slot: { value: unknown } | null = null;

mock.module("react", {
  defaultExport: realReact.default,
  namedExports: {
    ...realReact,
    useState<T>(init: T) {
      if (!direct) return realReact.useState(init);
      if (!slot) slot = { value: init };
      const s = slot;
      const set = (next: T | ((prev: T) => T)) => {
        s.value =
          typeof next === "function" ? (next as (prev: T) => T)(s.value as T) : next;
      };
      return [s.value as T, set];
    },
    useId: () => (direct ? "note-id" : realReact.useId()),
  },
});

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

const { createElement } = realReact;

mock.module("next/link", {
  defaultExport: ({ href, children }: { href: string; children?: never }) =>
    createElement("a", { href }, children),
});

const LONG_NOTE = "길다 ".repeat(300) + "<b>꺾쇠</b> & 끝";

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
  description: "설명 본문",
  example: "",
  example_translation: "",
  aliases: "",
});

mock.module("@/lib/api/vocab", {
  namedExports: {
    HOME_WORDS: 7,
    getDailyWords: async () => [],
    getWord: async (id: string) =>
      word(Number(id), id === "1" ? LONG_NOTE : id === "2" ? "짧은 설명" : ""),
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { DetailHead } = await import("./DetailHead");
const { default: WordDetailPage } = await import("../app/learn/words/[id]/page");

const NOTE = "sl 은 s 뒤에 혀끝을 붙인 l 이 바로 이어진다.";
const BACK = createElement("a", { href: "/learn/words", "data-back": "1" }, "단어장");
const HERO = createElement("h1", { "data-hero": "1" }, "slow query");

beforeEach(() => {
  slot = null;
  direct = false;
});

/** 컴포넌트를 훅 대역으로 한 번 그린다. */
function draw(note = NOTE): ReactElement {
  direct = true;
  try {
    return DetailHead({ back: BACK, note, children: HERO }) as ReactElement;
  } finally {
    direct = false;
  }
}

function findButton(node: ReactNode): ReactElement<{ onClick: () => void }> | null {
  if (!node || typeof node !== "object") return null;
  if (Array.isArray(node)) {
    for (const child of node) {
      const hit = findButton(child);
      if (hit) return hit;
    }
    return null;
  }
  const el = node as ReactElement<{ children?: ReactNode; onClick: () => void }>;
  if (el.type === "button") return el;
  return findButton(el.props?.children);
}

/** 그린 HTML 에서 열림 상태 셋(aria-expanded, 설명 hidden, 삼각형 회전)을 읽는다. */
function stateOf(html: string) {
  return {
    expanded: html.match(/<button[^>]*aria-expanded="(true|false)"/)?.[1],
    hidden: /<p[^>]*\bhidden=""/.test(html),
    rotated: /rotate-180/.test(html),
  };
}

const count = (html: string, needle: string) => html.split(needle).length - 1;

describe("DetailHead 여닫기", () => {
  it("같은 렌더에서 두 번 눌러도 두 번 뒤집혀 닫힌 채로 돌아온다", () => {
    const tree = draw();
    findButton(tree)!.props.onClick();
    findButton(tree)!.props.onClick();
    assert.equal(stateOf(renderToStaticMarkup(draw())).expanded, "false");
  });

  it("열고 닫기를 9번 반복해도 aria-expanded, hidden, 삼각형이 늘 같은 쪽이다", () => {
    for (let i = 1; i <= 9; i++) {
      findButton(draw())!.props.onClick();
      const html = renderToStaticMarkup(draw());
      const open = i % 2 === 1;
      assert.deepEqual(
        stateOf(html),
        { expanded: String(open), hidden: !open, rotated: open },
        `${i}번째 누름`,
      );
      // 설명은 닫혀도 그려 둔다 - aria-controls 가 가리킬 자리.
      assert.equal(count(html, '<p id="note-id"'), 1, `${i}번째 누름`);
      assert.match(html, /aria-controls="note-id"/);
    }
  });

  it("되돌아가기와 히어로는 열든 닫든 한 번씩만 그려진다", () => {
    for (let i = 0; i < 2; i++) {
      const html = renderToStaticMarkup(draw());
      assert.equal(count(html, 'data-back="1"'), 1);
      assert.equal(count(html, 'data-hero="1"'), 1);
      findButton(draw())!.props.onClick();
    }
  });

  it("버튼은 form 안에서도 제출하지 않는다(type=button)", () => {
    assert.match(renderToStaticMarkup(draw()), /<button type="button"/);
  });

  it("설명이 없으면 누를 것도 가리킬 것도 없다 - aria-controls 가 남지 않는다", () => {
    const html = renderToStaticMarkup(draw(""));
    assert.doesNotMatch(html, /aria-controls|aria-expanded|<p /);
  });
});

async function renderPage(id: string, query: Record<string, string> = {}) {
  const element = await WordDetailPage({
    params: Promise.resolve({ id }),
    searchParams: Promise.resolve(query),
  });
  return renderToStaticMarkup(element);
}

describe("단어 상세 페이지 (진짜 useId)", () => {
  for (const [name, query] of [
    ["목록에서", { from: "/learn/words?page=2" }],
    ["홈에서", { today: "2-3" }],
  ] as const) {
    it(`${name} 연 상세: aria-controls 가 페이지 안의 설명 하나를 가리킨다`, async () => {
      const html = await renderPage("2", query);
      const id = html.match(/aria-controls="([^"]+)"/)?.[1];
      assert.ok(id, "aria-controls 가 없다");
      assert.equal(count(html, `id="${id}"`), 1, html);
      assert.match(html, new RegExp(`<p id="${id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"[^>]*hidden=""[^>]*>짧은 설명</p>`));
    });
  }

  it("설명은 제목(h1) 뒤, 설명 카드 앞에 온다", async () => {
    const html = await renderPage("2");
    const h1 = html.indexOf("<h1");
    const note = html.indexOf("짧은 설명");
    const desc = html.indexOf("설명 본문");
    assert.ok(h1 >= 0 && h1 < note && note < desc, `${h1} ${note} ${desc}`);
  });

  it("맨 위 줄에는 되돌아가기 링크 하나와 발음 버튼 하나만 있다", async () => {
    const html = await renderPage("2", { today: "2-3" });
    const main = html.slice(html.indexOf("<main"));
    const row = main.match(/<div\b[^>]*class="[^"]*flex-wrap[^"]*"[^>]*>([\s\S]*?)<\/button><\/div>/);
    assert.ok(row, main.slice(0, 600));
    assert.equal(count(row[1], "<a "), 1, row[1]);
    assert.equal(count(row[1], "<button"), 1, row[1]);
    assert.match(row[1], /href="\/"/);
    // 맨 위 줄이 히어로보다 앞이다.
    assert.ok(main.indexOf(row[0]) < main.indexOf("<h1"));
  });

  it("아주 긴 설명과 꺾쇠: 글자로 나가고 태그가 되지 않는다", async () => {
    const html = await renderPage("1");
    assert.doesNotMatch(html, /<b>꺾쇠<\/b>/);
    assert.match(html, /&lt;b&gt;꺾쇠&lt;\/b&gt; &amp; 끝/);
    assert.equal(count(html, "발음 자세히"), 1);
  });

  it("설명 없는 단어를 홈에서 열어도 버튼 없이 홈 되돌아가기만 있다", async () => {
    const html = await renderPage("3", { today: "2-3" });
    assert.doesNotMatch(html, /발음 자세히|aria-controls/);
    assert.match(html.slice(html.indexOf("<main")), /<a [^>]*href="\/"/);
  });
});
