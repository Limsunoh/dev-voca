/**
 * 축포(Burst)가 판정 순간에 연출 층 위에서 터지는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 어둡게 까는 연출(Reaction 의 dim)이 도는 화면에서 축포가 바로 터지면 두
 * 가지가 깨진다. 연출 층(z-40) 아래면 가운데 무대에 전부 가려 안 보이고, 위에
 * 올려도 바로 터지면 "66% 전에는 결과를 모른다" 를 축포가 먼저 알린다. 그래서
 * 그 화면들만 atReveal 을 켜서 연출의 66% 까지 기다렸다 그 위에서 터진다.
 *
 * 기다리는 동안은 키프레임 0% 에 서 있다(fill-mode: both). 그 프레임이
 * 보이는 상태면 조각 열여섯 개가 화면 가운데에 미리 모여 있다.
 *
 * 화면을 띄울 판이 없어 마크업과 원문을 글자로 본다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { Burst } from "./Burst";

const HERE = dirname(fileURLToPath(import.meta.url));

function read(...parts: string[]): string {
  return readFileSync(join(HERE, ...parts), "utf8").replace(/\r\n/g, "\n");
}

function stripComments(source: string): string {
  return source
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

const html = (props: { fire: number; atReveal?: boolean }) =>
  renderToStaticMarkup(createElement(Burst, props));

/** 바깥 div 의 여는 태그. */
const outer = (page: string) => /^<div[^>]*>/.exec(page)?.[0] ?? "";

/** 조각들의 animation-delay. */
const delays = (page: string) =>
  [...page.matchAll(/animation-delay:([^;"]+)/g)].map((m) => m[1]);

/** CSS 의 `여는 이름 {` 부터 짝이 맞는 `}` 까지의 알맹이. */
function body(source: string, opener: string): string {
  const at = source.indexOf(opener);
  assert.notEqual(at, -1, `${opener} 를 못 찾았다`);
  const from = source.indexOf("{", at);
  let depth = 0;
  for (let i = from; i < source.length; i++) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(from + 1, i);
    }
  }
  throw new Error(`${opener} 의 끝을 못 찾았다`);
}

/** 키프레임을 정지점과 선언으로. 주석은 걷어 낸다. */
function stops(keyframes: string): { at: string; decls: string }[] {
  const clean = keyframes.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...clean.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    at: m[1].replace(/\s+/g, " ").trim(),
    decls: m[2],
  }));
}

const css = read("..", "app", "globals.css");

describe("Burst 마크업", () => {
  it("한 번도 안 맞혔으면 켜든 끄든 아무것도 안 그린다", () => {
    assert.equal(html({ fire: 0 }), "");
    assert.equal(html({ fire: 0, atReveal: true }), "");
  });

  it("기본은 본문 위·탭바 아래(z-10)에서 기다리지 않고 터진다", () => {
    const page = html({ fire: 1 });
    const tag = outer(page);
    assert.match(tag, /\bz-10\b/);
    assert.doesNotMatch(tag, /z-\[45\]/);
    assert.doesNotMatch(tag, /style=/, "기본 축포에 기다리는 시간이 실렸다");
    assert.doesNotMatch(page, /--burst-wait:|--burst-duration:/);
  });

  it("atReveal 은 연출 층 위(z-[45])에서 연출 길이로 구한 시간을 싣는다", () => {
    const tag = outer(html({ fire: 1, atReveal: true }));
    assert.match(tag, /z-\[45\]/);
    assert.doesNotMatch(tag, /\bz-10\b/);
    assert.match(tag, /--burst-wait:calc\(var\(--duration-verdict\) \* 0\.66\)/);
    assert.match(tag, /--burst-duration:calc\(var\(--duration-verdict\) \* [\d.]+\)/);
  });

  it("atReveal 축포는 연출이 끝나기 전에 다 사라진다", () => {
    // 한 판은 연출이 끝나는 순간 다음 문제를 띄운다. 그때까지 조각이 남아
    // 있으면 z-[45] 라 새 문제 글자 위에 불투명하게 겹친다. 기다림 + 길이 +
    // 조각별 최대 시차(36ms, 연출 1000ms 기준 0.036)가 1 을 넘으면 안 된다.
    const tag = outer(html({ fire: 1, atReveal: true }));
    const wait = Number(/--burst-wait:calc\(var\(--duration-verdict\) \* ([\d.]+)\)/.exec(tag)?.[1]);
    const dur = Number(/--burst-duration:calc\(var\(--duration-verdict\) \* ([\d.]+)\)/.exec(tag)?.[1]);
    assert.ok(wait > 0 && dur > 0, tag);
    assert.ok(wait + dur + 0.036 <= 1, `기다림 ${wait} + 길이 ${dur} + 시차 0.036 이 1 을 넘는다`);
  });

  it("atReveal={false} 는 기본과 같다", () => {
    assert.equal(html({ fire: 3, atReveal: false }), html({ fire: 3 }));
  });

  for (const atReveal of [false, true]) {
    it(`조각 열여섯 개가 기다리는 시간 위에 제 시차를 더한다(atReveal ${atReveal})`, () => {
      const got = delays(html({ fire: 1, atReveal }));
      assert.equal(got.length, 16);
      assert.deepEqual(
        got,
        Array.from({ length: 16 }, (_, i) => `calc(var(--burst-wait, 0ms) + ${(i % 4) * 12}ms)`),
      );
    });
  }

  it("기다리는 비율이 무대가 판정색으로 넘어가는 순간과 같다", () => {
    // vx-spot 은 마지막으로 바탕색인 정지점 다음에 판정색이 된다. 그 정지점을
    // 옮기고 여기를 그대로 두면 축포가 판정보다 먼저 또는 늦게 터진다.
    const spot = stops(body(css, "@keyframes vx-spot {"));
    const lastPlain = spot.filter((s) => /background:\s*var\(--background\)/.test(s.decls)).at(-1);
    assert.ok(lastPlain, "vx-spot 에 바탕색 정지점이 없다");
    const reveal = Math.max(...lastPlain.at.split(",").map((p) => parseFloat(p)));
    const wait = /--burst-wait:calc\(var\(--duration-verdict\) \* ([\d.]+)\)/.exec(
      outer(html({ fire: 1, atReveal: true })),
    );
    assert.ok(wait);
    assert.equal(Number(wait[1]) * 100, reveal);
  });
});

describe("어느 화면이 판정 순간에 터뜨리나", () => {
  /**
   * 어둡게 까는 화면과 판정 순간에 터뜨리는 화면은 같아야 한다. 어둡게 깔면서
   * 끄면 무대에 가려 안 보이고, 안 깔면서 켜면 탭바(z-20) 위로 조각이 지나고
   * 이미 결과가 보이는데 0.66초를 기다린다.
   */
  const BOARDS = {
    "QuizBoard.tsx": true,
    "RoundBoard.tsx": true,
    "DailyStudyBoard.tsx": false,
    "ReviewBoard.tsx": false,
  } as const;

  for (const [name, on] of Object.entries(BOARDS)) {
    const code = stripComments(read(name));
    const tag = /<Burst\b[^>]*\/>/.exec(code)?.[0] ?? "";

    it(`${name} 은 atReveal 을 ${on ? "켠다" : "안 켠다"}`, () => {
      assert.ok(tag, "<Burst /> 를 못 찾았다");
      if (on) assert.match(tag, /\satReveal(\s|\/|=\{true\})/);
      else assert.doesNotMatch(tag, /atReveal/);
    });

    it(`${name} 은 어둡게 까는 것과 축포 자리가 짝이 맞는다`, () => {
      const dims = /<Reaction[^/]*\sdim\s*\/>/.test(code);
      assert.equal(/atReveal/.test(tag), dims);
    });
  }
});

describe("burst 키프레임", () => {
  const frames = stops(body(css, "@keyframes burst {"));
  const piece = body(css, "@utility burst-piece {").replace(/\/\*[\s\S]*?\*\//g, "");

  it("0% 는 투명하다 - 기다리는 동안 가운데 모여 보이지 않는다", () => {
    assert.equal(frames[0].at, "0%");
    assert.match(frames[0].decls, /opacity:\s*0\s*;/);
    assert.match(frames[0].decls, /scale\(0\.4\)/);
  });

  it("1% 에 곧바로 보인다 - 바로 터지는 쪽은 달라지지 않는다", () => {
    assert.equal(frames[1].at, "1%");
    assert.match(frames[1].decls, /opacity:\s*1\s*;/);
  });

  it("끝은 투명하다", () => {
    const last = frames.at(-1);
    assert.ok(last);
    assert.equal(last.at, "100%");
    assert.match(last.decls, /opacity:\s*0\s*;/);
  });

  it("조각은 길이를 변수로 받고 기본은 900ms 다", () => {
    assert.match(piece, /animation-duration:\s*var\(--burst-duration,\s*900ms\)\s*;/);
  });

  it("조각은 기다리는 동안 0% 에 서 있다(fill-mode both)", () => {
    // backwards 가 빠지면 기다리는 동안 키프레임 밖의 기본 모양(불투명, 제자리)
    // 으로 그려져 0% 를 투명하게 둔 것이 소용없다.
    assert.match(piece, /animation-fill-mode:\s*(both|backwards)\s*;/);
  });

  it("단축 animation 으로 길이·지연을 덮지 않는다", () => {
    // 단축은 안 적은 값을 초기화한다. 조각마다 싣는 animation-delay 가 사라진다.
    assert.doesNotMatch(piece, /\banimation\s*:/);
  });
});
