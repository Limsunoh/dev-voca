/**
 * 오늘의 단어 이전/다음 줄(TodayWordNav)이 폰 글자 크기 200% 에서 넘치지 않는가.
 *
 * 실행: cd frontend && npm test
 *
 * 글자 크기 200% 면 360폭 폰이 180px 폭처럼 그려진다(본문 140px). 이 줄은
 * 이전·쪽수·다음을 줄바꿈 없이 한 줄에 놓아 약 240px 이 필요했고, 화면이
 * 넓어지며 아래 탭바까지 밀렸다. 실제 폭은 브라우저로만 잴 수 있어서, 여기서는
 * 그 폭에서 버티게 해 주는 클래스가 빠지지 않았는지를 본다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { TodayWordNav } from "./TodayWordNav";

const WORDS = [{ id: 57 }, { id: 939 }, { id: 576 }];

const render = (index: number) =>
  renderToStaticMarkup(createElement(TodayWordNav, { words: WORDS, index }));

const classOf = (html: string, pattern: RegExp) =>
  html.match(pattern)?.[1].split(/\s+/) ?? [];

const linkClasses = (html: string) =>
  [...html.matchAll(/<a[^>]*class="([^"]*)"/g)].map((m) => m[1].split(/\s+/));

describe("좁은 화면에서 줄을 바꾼다", () => {
  const html = render(1);

  it("줄이 flex-wrap 이다", () => {
    const nav = classOf(html, /<nav[^>]*class="([^"]*)"/);
    assert.ok(nav.includes("flex-wrap"), nav.join(" "));
  });

  it("320px 보다 좁으면 쪽수를 첫 줄에 혼자 올린다", () => {
    const count = classOf(html, /<p[^>]*class="([^"]*)"/);
    for (const need of ["max-[20rem]:order-first", "max-[20rem]:basis-full", "text-center"]) {
      assert.ok(count.includes(need), `${need} 없음: ${count.join(" ")}`);
    }
  });

  it("버튼은 글자를 꺾지 않고(whitespace-nowrap) 어떤 폭에서도 숨지 않는다", () => {
    const links = linkClasses(html);
    assert.equal(links.length, 2);
    for (const cls of links) {
      assert.ok(cls.includes("whitespace-nowrap"), cls.join(" "));
      assert.ok(!cls.some((c) => c.endsWith(":hidden") || c === "hidden"), cls.join(" "));
    }
  });
});

describe("첫 장과 끝 장의 자리 지킴 칸", () => {
  for (const [name, index] of [["첫 장", 0], ["끝 장", WORDS.length - 1]] as const) {
    it(`${name}: 좁은 화면에서도 자리를 지킨다 - 숨기면 장마다 버튼 자리가 바뀐다`, () => {
      const html = render(index);
      const placeholder = classOf(html, /<span aria-hidden="true" class="([^"]*)"/);
      assert.ok(placeholder.includes("flex-1"), placeholder.join(" "));
      assert.ok(!placeholder.some((c) => c.endsWith(":hidden") || c === "hidden"), placeholder.join(" "));
      // 누를 수 있는 버튼은 하나만 남는다.
      assert.equal(linkClasses(html).length, 1);
    });
  }
});
