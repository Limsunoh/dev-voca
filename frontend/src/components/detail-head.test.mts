/**
 * 단어 상세의 머리(DetailHead): 되돌아가기 옆의 "발음 자세히" 와 펼친 설명.
 *
 * 실행: cd frontend && npm test
 *
 * 2026-11-12 사용자 요청으로 "발음 자세히" 를 뜻 카드 아래 줄에서 맨 위
 * 되돌아가기 옆으로 올렸다. 펼친 설명은 히어로 카드 아래(원래 자리)에 온다.
 *
 * 전에는 details 라 여닫기를 브라우저가 맡았는데, 이제는 컴포넌트 상태가
 * 맡는다. 서버 렌더로는 누를 수 없어서 react 의 useState 를 대역으로 바꿔
 * 버튼의 onClick 을 진짜로 부른다(category-picker-focus.test.mts 와 같은 방식).
 */
import assert from "node:assert/strict";
import { beforeEach, describe, it, mock } from "node:test";
import type { ReactElement, ReactNode } from "react";

const realReact = await import("react");

/** 상태 칸 하나. 테스트마다 비운다 - 새로 마운트한 것과 같다. */
let slot: { value: unknown } | null = null;

mock.module("react", {
  defaultExport: realReact.default,
  namedExports: {
    ...realReact,
    useState<T>(init: T) {
      if (!slot) slot = { value: init };
      const s = slot;
      const set = (next: T | ((prev: T) => T)) => {
        s.value = typeof next === "function" ? (next as (prev: T) => T)(s.value as T) : next;
      };
      return [s.value as T, set];
    },
    // 진짜 useId 는 렌더 중에만 부를 수 있다. 여기서는 컴포넌트 함수를 직접
    // 부르므로 고정값을 준다.
    useId: () => "note-id",
  },
});

const { createElement } = realReact;
const { renderToStaticMarkup } = await import("react-dom/server");
const { DetailHead } = await import("./DetailHead");

const BACK = createElement("a", { href: "/learn/words", "data-back": "1" }, "단어장");
const HERO = createElement("h1", { "data-hero": "1" }, "slow query");
const NOTE = "sl 은 s 뒤에 혀끝을 붙인 l 이 바로 이어진다.";

beforeEach(() => {
  slot = null;
});

/** 컴포넌트를 한 번 그린다. 돌려준 트리는 훅 없이 HTML 로 바꿀 수 있다. */
function draw(note = NOTE): ReactElement {
  return DetailHead({ back: BACK, note, children: HERO }) as ReactElement;
}

/** 트리에서 button 요소를 찾는다. */
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

const html = (tree: ReactElement) => renderToStaticMarkup(tree);

describe("발음 설명이 있으면", () => {
  it("되돌아가기와 같은 줄(flex-wrap)에 되돌아가기 다음으로 버튼이 온다", () => {
    const out = html(draw());
    const row = out.match(/^<div\b[^>]*class="([^"]*)"[^>]*>([\s\S]*?)<\/div>/);
    assert.ok(row, out);
    assert.ok(row[1].split(/\s+/).includes("flex-wrap"), row[1]);
    assert.ok(row[2].indexOf('data-back="1"') < row[2].indexOf("<button"), row[2]);
    assert.match(row[2], /발음 자세히/);
  });

  it("펼칠 설명은 히어로 아래에 있다 - 제목과 발음보다 먼저 읽히지 않는다", () => {
    const out = html(draw());
    const row = out.indexOf("</div>");
    const hero = out.indexOf('data-hero="1"');
    const note = out.indexOf("<p ");
    assert.ok(row < hero && hero < note, out);
  });

  it("처음에는 닫혀 있다 - aria-expanded=false, 설명은 hidden, 삼각형은 그대로", () => {
    const out = html(draw());
    assert.match(out, /<button[^>]*aria-expanded="false"/);
    assert.match(out, /<p[^>]*hidden=""[^>]*>[^<]*sl 은/);
    assert.doesNotMatch(out, /rotate-180/);
  });

  it("누르면 열리고 한 번 더 누르면 닫힌다", () => {
    findButton(draw())!.props.onClick();
    const opened = html(draw());
    assert.match(opened, /<button[^>]*aria-expanded="true"/);
    assert.doesNotMatch(opened, /<p[^>]*hidden/);
    assert.match(opened, /rotate-180/);

    findButton(draw())!.props.onClick();
    const closed = html(draw());
    assert.match(closed, /<button[^>]*aria-expanded="false"/);
    assert.match(closed, /<p[^>]*hidden=""/);
    assert.doesNotMatch(closed, /rotate-180/);
  });

  it("버튼이 설명을 가리킨다(aria-controls = 설명 id)", () => {
    const out = html(draw());
    const controls = out.match(/aria-controls="([^"]+)"/)?.[1];
    assert.ok(controls);
    assert.ok(out.includes(`<p id="${controls}"`), out);
  });

  it("버튼 높이가 되돌아가기와 같은 44px 바닥(min-h-11)이다", () => {
    const cls = html(draw()).match(/<button[^>]*class="([^"]*)"/)?.[1].split(/\s+/) ?? [];
    assert.ok(cls.includes("min-h-11"), cls.join(" "));
  });
});

describe("발음 설명이 없으면", () => {
  it("버튼도 설명도 없고 되돌아가기와 히어로만 있다", () => {
    const out = html(draw(""));
    assert.doesNotMatch(out, /<button/);
    assert.doesNotMatch(out, /<p /);
    assert.match(out, /data-back="1"/);
    assert.match(out, /data-hero="1"/);
  });
});
