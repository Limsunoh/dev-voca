/**
 * 오늘의 단어 넘기는 줄(TodayWordNav)을 today-word-nav-zoom.test.mts 보다 넓게 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 폰 글자 크기를 키우면(안드로이드 크롬은 페이지를 확대한다) 360폭 폰이 115% 에
 * 313px, 150% 에 240px, 200% 에 180px 폭처럼 그려진다. 그 폭에서 이 줄이 넘치지
 * 않고 장마다 같은 자리를 지키는지는 브라우저로 재야 알 수 있다. 여기서는 그 결과를
 * 만드는 조건을 묶음 크기(2~7, 그리고 두 자리 쪽수)와 모든 장에 걸쳐 본다.
 *
 * - 화면 낭독기와 키보드는 DOM 순서를 따른다. 줄 안은 언제나 이전, 쪽수, 다음
 *   순서이고, 누를 수 있는 것은 링크뿐이다. 좁은 화면에서 쪽수를 위로 올리는 것은
 *   CSS order 로만 해야 한다(DOM 을 옮기면 낭독 순서가 바뀐다).
 * - 첫·끝 장의 회색 칸은 링크와 같은 모양 클래스를 가진다. 하나라도 다르면 그 장만
 *   버튼 폭이 달라져 넘길 때마다 버튼이 움직인다.
 * - 쪽수를 첫 줄로 올리는 클래스는 좁은 화면 변형(max-[20rem]:)에만 있다. 맨
 *   클래스로 두면 보통 폰에서도 세 줄이 된다.
 * - 넘침을 숨겨서 막는 방법(overflow-hidden, truncate)은 쓰지 않는다. 버튼 글자가
 *   잘려 보인다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";


import { TodayWordNav } from "./TodayWordNav";

const bundle = (size: number) => Array.from({ length: size }, (_, i) => ({ id: 100 + i * 7 }));

const render = (words: { id: number }[], index: number) =>
  renderToStaticMarkup(createElement(TodayWordNav, { words, index }));

/** nav 바로 아래 칸 셋. 태그, 클래스, aria-hidden, href, 글자. */
function slots(html: string) {
  const inner = html.match(/^<nav[^>]*>([\s\S]*)<\/nav>$/)?.[1];
  assert.ok(inner, html);
  const found = [
    ...inner.matchAll(/<(a|span|p)(\s[^>]*)?>([\s\S]*?)<\/\1>(?=<(?:a|span|p)[\s>]|$)/g),
  ];
  return found.map((m) => {
    const attrs = m[2] ?? "";
    return {
      tag: m[1],
      cls: (attrs.match(/class="([^"]*)"/)?.[1] ?? "").split(/\s+/).filter(Boolean),
      hidden: /aria-hidden="true"/.test(attrs),
      href: attrs.match(/href="([^"]*)"/)?.[1]?.replace(/&amp;/g, "&") ?? null,
      tabindex: attrs.match(/tabindex="([^"]*)"/)?.[1] ?? null,
      text: m[3].replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim(),
    };
  });
}

const navClasses = (html: string) =>
  (html.match(/^<nav[^>]*class="([^"]*)"/)?.[1] ?? "").split(/\s+/);

// 링크와 회색 칸이 같아야 하는 모양. 폭을 정하는 것들이다.
const SHAPE = ["flex", "flex-1", "items-center", "justify-center", "gap-1.5", "px-4", "whitespace-nowrap"];

const CASES: [number, number][] = [];
for (let size = 2; size <= 7; size++) for (let i = 0; i < size; i++) CASES.push([size, i]);
CASES.push([30, 0], [30, 11], [30, 29]);

describe("모든 묶음 크기와 장에서 줄의 구조", () => {
  for (const [size, index] of CASES) {
    it(`${size}장 중 ${index + 1}번째: 이전, 쪽수, 다음 순서이고 끝에서만 회색 칸이 된다`, () => {
      const words = bundle(size);
      const html = render(words, index);
      const [prev, count, next, ...rest] = slots(html);
      assert.equal(rest.length, 0, html);

      // DOM 순서 = 낭독 순서
      assert.equal(prev.text, "← 이전");
      assert.equal(count.tag, "p");
      assert.equal(count.text, `${index + 1} / ${size}`);
      assert.equal(next.text, "다음 →");

      // 끝에서만 회색 칸이고, 회색 칸은 낭독기와 Tab 에서 빠진다.
      assert.equal(prev.tag, index === 0 ? "span" : "a");
      assert.equal(next.tag, index === size - 1 ? "span" : "a");
      for (const one of [prev, next]) {
        if (one.tag === "span") {
          assert.ok(one.hidden, "회색 칸은 aria-hidden");
          assert.equal(one.href, null);
          assert.equal(one.tabindex, null);
        } else {
          assert.ok(!one.hidden, "링크는 낭독기에서 숨지 않는다");
        }
      }

      // 링크는 묶음 순서를 그대로 싣고 바로 앞뒤 단어로 간다.
      const order = words.map((w) => w.id).join("-");
      if (prev.tag === "a") assert.equal(prev.href, `/learn/words/${words[index - 1].id}?today=${order}`);
      if (next.tag === "a") assert.equal(next.href, `/learn/words/${words[index + 1].id}?today=${order}`);

      // 장마다 버튼 폭이 같으려면 회색 칸과 링크의 모양이 같아야 한다.
      for (const one of [prev, next]) {
        for (const need of SHAPE) assert.ok(one.cls.includes(need), `${one.tag} 에 ${need} 없음: ${one.cls.join(" ")}`);
        assert.ok(!one.cls.some((c) => /(^|:)(hidden|sr-only|invisible)$/.test(c)), one.cls.join(" "));
      }
    });
  }
});

describe("좁은 화면 처리가 보통 폰을 건드리지 않는다", () => {
  const html = render(bundle(7), 3);
  const [prev, count, next] = slots(html);

  it("쪽수를 첫 줄로 올리는 클래스는 max-[20rem]: 변형에만 있다", () => {
    for (const bare of ["order-first", "basis-full", "w-full", "order-last"]) {
      assert.ok(!count.cls.includes(bare), `맨 ${bare}: ${count.cls.join(" ")}`);
    }
    for (const one of [prev, next]) {
      assert.ok(!one.cls.some((c) => c.includes("order-") || c.includes("basis-")), one.cls.join(" "));
    }
  });

  it("쪽수는 꺾이지도 줄어들지도 않는다(두 자리 쪽수 포함)", () => {
    const wide = slots(render(bundle(30), 11))[1];
    for (const one of [count, wide]) {
      assert.ok(one.cls.includes("whitespace-nowrap"), one.cls.join(" "));
      assert.ok(one.cls.includes("shrink-0"), one.cls.join(" "));
    }
    assert.equal(wide.text, "12 / 30");
  });

  it("넘침을 숨겨서 막지 않는다", () => {
    const all = [navClasses(html), prev.cls, count.cls, next.cls].flat();
    for (const bad of ["flex-nowrap", "overflow-hidden", "overflow-x-hidden", "overflow-x-auto", "overflow-x-scroll", "truncate", "text-ellipsis"]) {
      assert.ok(!all.includes(bad), `${bad} 가 있다`);
    }
    assert.ok(navClasses(html).includes("flex-wrap"));
  });
});
