/**
 * 상세에서 목록으로 돌아가는 링크(DetailBackLink).
 *
 * 실행: cd frontend && npm test
 *
 * 바로 앞 기록이 그 목록이면 뒤로가기로 돌아가 스크롤을 지킨다. 아니면 평범한
 * 링크다. 앞 기록을 판단하는 isPreviousEntry 와 클릭 처리를 따로 본다.
 */
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it, mock } from "node:test";

import type { MouseEvent, ReactElement } from "react";

let backCalls = 0;

mock.module("next/navigation", {
  namedExports: {
    useRouter: () => ({
      back() {
        backCalls += 1;
      },
      push() {},
      replace() {},
      prefetch() {},
    }),
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { DetailBackLink, isPreviousEntry } = await import("./DetailBackLink");
const { DetailBack } = await import("./DetailLayout");

const ORIGIN = "https://devvoca.example";

/** Navigation API 대역. index 는 currentEntry 의 위치다. */
const nav = (urls: (string | null)[], index: number) => ({
  currentEntry: { index },
  entries: () => urls.map((url) => ({ url })),
});

const previousIs = (previous: string | null) =>
  nav([previous === null ? null : `${ORIGIN}${previous}`, `${ORIGIN}/learn/words/7`], 1);

describe("isPreviousEntry - 앞 기록이 그 주소인가", () => {
  const same: [string, string, string][] = [
    ["같은 주소", "/learn/words?shuffle=s&page=2", "/learn/words?shuffle=s&page=2"],
    ["쿼리 순서만 다름", "/learn/words?page=2&shuffle=s", "/learn/words?shuffle=s&page=2"],
    ["쿼리 순서만 다름(반대)", "/learn/words?shuffle=s&page=2", "/learn/words?page=2&shuffle=s"],
    ["쿼리 없는 목록", "/learn/words", "/learn/words"],
    ["공백이 %20 과 +", "/learn/words?search=a%20b", "/learn/words?search=a+b"],
    ["공백이 + 와 %20", "/learn/words?search=a+b", "/learn/words?search=a%20b"],
    ["한글을 인코딩한 것과 안 한 것", "/learn/words?search=커밋", "/learn/words?search=%EC%BB%A4%EB%B0%8B"],
    ["쉼표 인코딩 차이", "/learn/words?search=a,b", "/learn/words?search=a%2Cb"],
    ["해시는 안 본다", "/learn/words?page=2#card", "/learn/words?page=2"],
  ];
  for (const [name, previous, href] of same) {
    it(`${name}: 같은 주소다`, () => {
      assert.equal(isPreviousEntry(href, previousIs(previous)), true);
    });
  }

  const different: [string, string, string][] = [
    ["쪽이 다름", "/learn/words?page=2", "/learn/words?page=3"],
    ["쿼리가 하나 더 있음", "/learn/words?page=2&sort=easy", "/learn/words?page=2"],
    ["앞 기록이 다른 화면", "/learn/sentences?page=2", "/learn/words?page=2"],
    ["앞 기록이 상세", "/learn/words/5", "/learn/words"],
    ["경로 앞부분만 같음", "/learn/words/extra?page=2", "/learn/words?page=2"],
    ["검색어의 + 글자와 공백은 다르다", "/learn/words?search=a%2Bb", "/learn/words?search=a+b"],
    ["같은 키 값의 순서가 다름", "/learn/words?a=1&a=2", "/learn/words?a=2&a=1"],
    ["대소문자가 다른 값", "/learn/words?search=A", "/learn/words?search=a"],
  ];
  for (const [name, previous, href] of different) {
    it(`${name}: 다른 주소다`, () => {
      assert.equal(isPreviousEntry(href, previousIs(previous)), false);
    });
  }

  it("Navigation API 가 없으면 false", () => {
    assert.equal(isPreviousEntry("/learn/words", undefined), false);
  });

  it("currentEntry 가 없으면 false", () => {
    assert.equal(
      isPreviousEntry("/learn/words", { currentEntry: null, entries: () => [] }),
      false,
    );
  });

  it("첫 기록이면 false", () => {
    assert.equal(
      isPreviousEntry("/learn/words", nav([`${ORIGIN}/learn/words/7`], 0)),
      false,
    );
  });

  it("앞 기록이 없으면 false", () => {
    assert.equal(isPreviousEntry("/learn/words", nav([], 1)), false);
  });

  it("앞 기록의 주소가 null 이면 false", () => {
    assert.equal(isPreviousEntry("/learn/words", previousIs(null)), false);
  });
});

// ---- 클릭 ------------------------------------------------------------------

const HREF = "/learn/words?page=2&shuffle=s";

type ClickEvent = Pick<
  MouseEvent,
  "metaKey" | "ctrlKey" | "shiftKey" | "altKey" | "preventDefault"
>;

function click(modifiers: Partial<ClickEvent> = {}) {
  let prevented = 0;
  const event = {
    metaKey: false,
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
    preventDefault() {
      prevented += 1;
    },
    ...modifiers,
  } as ClickEvent;
  const element = DetailBackLink({
    href: HREF,
    className: "c",
    style: {},
    children: "돌아가기",
  }) as ReactElement<{ onClick(e: ClickEvent): void }>;
  element.props.onClick(event);
  return { prevented, back: backCalls };
}

function setWindow(navigation?: unknown) {
  (globalThis as { window?: unknown }).window = { navigation };
}

describe("isPreviousEntry - 목록일 수 없는 앞 기록", () => {
  it("about:blank 이면 예외 없이 false 다", () => {
    const blank = nav(["about:blank", `${ORIGIN}/learn/words/7`], 1);
    assert.equal(isPreviousEntry("/learn/words", blank), false);
  });
});

describe("DetailBackLink - 클릭", () => {
  beforeEach(() => {
    backCalls = 0;
  });

  afterEach(() => {
    delete (globalThis as { window?: unknown }).window;
  });

  it("앞 기록이 그 목록이면 링크를 막고 뒤로 간다", () => {
    setWindow(previousIs(HREF));
    assert.deepEqual(click(), { prevented: 1, back: 1 });
  });

  it("앞 기록의 쿼리 순서만 달라도 뒤로 간다", () => {
    setWindow(previousIs("/learn/words?shuffle=s&page=2"));
    assert.deepEqual(click(), { prevented: 1, back: 1 });
  });

  it("앞 기록이 다르면 링크로 간다", () => {
    setWindow(previousIs("/learn/words?page=9&shuffle=s"));
    assert.deepEqual(click(), { prevented: 0, back: 0 });
  });

  it("앞 기록이 없으면(공유받은 주소) 링크로 간다", () => {
    setWindow(nav([`${ORIGIN}/learn/words/7`], 0));
    assert.deepEqual(click(), { prevented: 0, back: 0 });
  });

  it("Navigation API 가 없으면 링크로 간다", () => {
    setWindow(undefined);
    assert.deepEqual(click(), { prevented: 0, back: 0 });
  });

  for (const key of ["metaKey", "ctrlKey", "shiftKey", "altKey"] as const) {
    it(`${key} 를 누르면 앞 기록이 맞아도 브라우저에 맡긴다`, () => {
      setWindow(previousIs(HREF));
      assert.deepEqual(click({ [key]: true }), { prevented: 0, back: 0 });
    });
  }
});

describe("DetailBack", () => {
  it("링크로 그려지고 href 와 이름이 있다", () => {
    const html = renderToStaticMarkup(
      DetailBack({ href: HREF, label: "단어장" }) as ReactElement,
    );
    assert.match(html, /<a\b[^>]*href="\/learn\/words\?page=2&amp;shuffle=s"/);
    assert.ok(html.includes("단어장"));
  });
});
