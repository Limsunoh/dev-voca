/**
 * 익히기 목록 카드(LearningCard)와 상세 머리(DetailHero)가 긴 덩어리에
 * 줄바꿈 자리(<wbr>)를 받아 그려지는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 에러 문장 속 긴 URL·이름이 폰에서 낱말 가운데서 잘렸다. 제목과 그 아래
 * 뜻(문장의 해석)이 같은 URL 을 옮겨 적으므로 둘 다 본다.
 *
 * 보는 것:
 * - 긴 덩어리(21자 이상)에는 <wbr> 이 들어가고, 짧은 글(단어 제목)은
 *   전과 같은 글자 그대로다.
 * - <wbr> 을 빼면 화면 글자가 원문과 같다(빠지거나 바뀐 글자가 없다).
 * - 꺾쇠 같은 글자가 태그로 새지 않는다.
 * - 그리는 동안 react 경고(key 등)가 없다.
 * 자리 규칙 자체는 lib/wrap-points.edge.test.mts 가 본다.
 */
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DetailHero } from "./DetailLayout";
import { LearningCard } from "./LearningCard";

const URL_ERROR =
  "fatal: unable to access 'https://github.com/acme/demo.git/': Could not resolve host";
const URL_TRANSLATION =
  "치명적 오류: 'https://github.com/acme/demo.git/' 에 접근할 수 없다";
const CLASS_ERROR =
  "java.lang.UnsupportedClassVersionError: com/acme/App has been compiled";

/** 경고를 잡는다. react 는 key 빠짐 같은 것을 console.error 로 알린다. */
let errors: unknown[][] = [];
const realError = console.error;
beforeEach(() => {
  errors = [];
  console.error = (...args: unknown[]) => {
    errors.push(args);
  };
});
afterEach(() => {
  console.error = realError;
  assert.deepEqual(errors, [], "그리는 동안 react 경고가 났다");
});

function unescape(html: string): string {
  return html
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&quot;", '"')
    .replaceAll("&#x27;", "'")
    .replaceAll("&amp;", "&");
}

/** 태그 안의 내용. 같은 태그가 여럿이면 처음 것. */
function inner(html: string, open: RegExp, tag: string): string {
  const start = html.search(open);
  assert.ok(start >= 0, `${open} 가 없다`);
  const from = html.indexOf(">", start) + 1;
  const to = html.indexOf(`</${tag}>`, from);
  return html.slice(from, to);
}

/** 화면에 보이는 글자. <wbr> 과 태그를 빼고 엔티티를 푼다. */
const visible = (fragment: string) => unescape(fragment.replace(/<[^>]*>/g, ""));
const wbrCount = (fragment: string) => (fragment.match(/<wbr\/?>/g) ?? []).length;

function card(title: string, subtitle: string, extra: Record<string, unknown> = {}) {
  const html = renderToStaticMarkup(
    createElement(LearningCard, { href: "/learn/sentences/1", title, subtitle, ...extra }),
  );
  return {
    html,
    title: inner(html, /<h2\b/, "h2"),
    // 뜻은 제목 다음의 첫 문단이다.
    subtitle: inner(html.slice(html.indexOf("</h2>")), /<p\b/, "p"),
  };
}

function hero(title: string, meaning?: string, mono = false) {
  const html = renderToStaticMarkup(createElement(DetailHero, { title, meaning, mono }));
  return {
    html,
    title: inner(html, /<h1\b/, "h1"),
    meaning: html.includes("<p") ? inner(html, /<p\b/, "p") : null,
  };
}

describe("LearningCard 줄바꿈 자리", () => {
  for (const compact of [false, true]) {
    const label = compact ? "작은 카드" : "목록 카드";

    it(`${label}: 긴 URL 제목과 뜻에 <wbr> 이 들어가고 글자는 그대로다`, () => {
      const c = card(URL_ERROR, URL_TRANSLATION, { compact });
      assert.ok(wbrCount(c.title) > 0, c.title);
      assert.ok(wbrCount(c.subtitle) > 0, c.subtitle);
      assert.equal(visible(c.title), URL_ERROR);
      assert.equal(visible(c.subtitle), URL_TRANSLATION);
    });

    it(`${label}: 단어 제목·짧은 뜻은 <wbr> 없이 전과 같다`, () => {
      const c = card("commit", "변경 사항을 저장소에 기록하다", { compact });
      assert.equal(c.title, "commit");
      assert.equal(c.subtitle, "변경 사항을 저장소에 기록하다");
    });
  }

  it("점 없는 긴 클래스 이름도 대문자 앞에서 끊을 자리를 받는다", () => {
    const c = card(CLASS_ERROR, "번역");
    assert.ok(/Unsupported<wbr\/?>Class<wbr\/?>Version<wbr\/?>Error/.test(c.title), c.title);
    assert.equal(visible(c.title), CLASS_ERROR);
  });

  it("20자 덩어리는 그대로, 21자부터 끊는다", () => {
    const twenty = "abcdefghi.klmnopqrst"; // 20자
    const twentyOne = "abcdefghij.klmnopqrst"; // 21자
    assert.equal(twenty.length, 20);
    assert.equal(twentyOne.length, 21);
    assert.equal(wbrCount(card(twenty, twenty).title), 0);
    assert.equal(wbrCount(card(twentyOne, twentyOne).title), 1);
    assert.equal(wbrCount(card(twentyOne, twentyOne).subtitle), 1);
  });

  it("꺾쇠·앰퍼샌드가 섞인 긴 덩어리도 글자로만 나온다(태그로 새지 않는다)", () => {
    const tricky = "Error:<b>https://example.com/a?x=1&y=<img/src=x>";
    const c = card(tricky, tricky);
    assert.ok(!c.html.includes("<b>"), c.html);
    assert.ok(!c.html.includes("<img"), c.html);
    assert.equal(visible(c.title), tricky);
    assert.equal(visible(c.subtitle), tricky);
  });

  it("한글과 이모지 사이 긴 경로도 글자가 깨지지 않는다", () => {
    const mixed = "경로 /home/사용자/projects/devvoca/src/app.py 를 찾을 수 없음 \u{1F600}";
    const c = card(mixed, mixed);
    assert.equal(visible(c.title), mixed);
    assert.equal(visible(c.subtitle), mixed);
  });

  it("빈 뜻도 그린다(빈 문단)", () => {
    const c = card("commit", "");
    assert.equal(c.subtitle, "");
  });
});

describe("DetailHero 줄바꿈 자리", () => {
  for (const mono of [true, false]) {
    it(`${mono ? "고정폭" : "가변폭"} 제목: 긴 URL 제목·뜻에 <wbr> 이 들어가고 글자는 그대로다`, () => {
      const h = hero(URL_ERROR, URL_TRANSLATION, mono);
      assert.ok(wbrCount(h.title) > 0, h.title);
      assert.ok(h.meaning !== null && wbrCount(h.meaning) > 0, String(h.meaning));
      assert.equal(visible(h.title), URL_ERROR);
      assert.equal(visible(h.meaning ?? ""), URL_TRANSLATION);
    });
  }

  it("뜻의 <wbr> 은 형광펜 안에 있다(형광펜이 줄마다 따라간다)", () => {
    const h = hero(URL_ERROR, URL_TRANSLATION);
    const pen = inner(h.meaning ?? "", /<span\b/, "span");
    assert.ok(wbrCount(pen) > 0, pen);
    assert.equal(visible(pen), URL_TRANSLATION);
  });

  it("단어 제목·짧은 뜻은 <wbr> 없이 전과 같다", () => {
    const h = hero("idempotent", "멱등의", true);
    assert.equal(h.title, "idempotent");
    assert.equal(visible(h.meaning ?? ""), "멱등의");
    assert.equal(wbrCount(h.html), 0);
  });

  it("뜻이 없거나 비면 뜻 문단을 그리지 않는다", () => {
    assert.equal(hero(URL_ERROR).meaning, null);
    assert.equal(hero(URL_ERROR, "").meaning, null);
  });

  it("제목 글자 크기는 <wbr> 이 아니라 원문 길이로 정한다", () => {
    // 24자 고정폭 제목은 큰 글자. 끊을 자리가 들어가도 그대로여야 한다.
    const title = "a.b.c.d.e.f.g.h.i.j.k.lm"; // 24자, 21자 넘는 한 덩어리
    assert.equal(title.length, 24);
    const h = hero(title, undefined, true);
    assert.ok(wbrCount(h.title) > 0, h.title);
    assert.ok(h.html.includes("font-size:var(--text-hero)"), h.html);
  });
});
