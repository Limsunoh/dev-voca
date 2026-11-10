/**
 * 키보드 포커스 테두리가 앱 어디서나 같은 토큰(--focus)을 쓰는지, 안쪽으로
 * 그리는 테두리가 자기 바탕 위에서 보이는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * contrast-pairs.test.mts 는 --focus 를 칸 바깥 바탕 넷과 잰다. 여기는 그
 * 계산이 실제 화면에 걸리는 두 조건을 지킨다.
 *
 * 1. 색 클래스가 outline-focus 하나뿐이다. Tailwind 는 모르는 색 이름
 *    (예: 지운 outline-focus-pill)에 규칙을 만들지 않고 빌드도 안 깨진다.
 *    그러면 테두리가 글자색(currentColor)으로 조용히 바뀌어 위 계산이
 *    그 칸에서는 아무것도 지키지 못한다.
 * 2. 안쪽 테두리(-outline-offset)는 칸 밖이 아니라 칸 자기 바탕 위에
 *    그려진다. 고르개의 고른 칸은 --coral-soft 라 바깥 바탕 넷에 없다.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import {
  PICKER_ITEM_CLASS,
  pickerItemStyle,
  pickerMenuStyle,
} from "./PickerMenu";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..");
const css = readFileSync(join(SRC, "app", "globals.css"), "utf8").replace(
  /\/\*[\s\S]*?\*\//g,
  "",
);

/* ---- 계산 (contrast-pairs.test.mts 와 같은 식) ---- */

function token(name: string): string {
  const found = new RegExp(`${name}\\s*:\\s*([^;]+);`).exec(css);
  assert.ok(found, `${name} 가 globals.css 에 없다`);
  const value = found[1].trim();
  const ref = /^var\((--[\w-]+)\)$/.exec(value);
  return ref ? token(ref[1]) : value;
}

function resolve(value: unknown): string {
  const ref = /^var\((--[\w-]+)\)$/.exec(String(value).trim());
  assert.ok(ref, `${String(value)} 는 토큰이 아니다`);
  return token(ref[1]);
}

function luminance(hex: string): number {
  assert.match(hex, /^#[0-9a-f]{6}$/i, `${hex} 는 계산할 수 없는 값이다`);
  const [r, g, b] = [1, 3, 5].map((at) => {
    const channel = parseInt(hex.slice(at, at + 2), 16) / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/* ---- 소스 훑기 ---- */

function sources(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) sources(path, out);
    else if (/\.tsx?$/.test(entry.name) && !/\.test\./.test(entry.name)) out.push(path);
  }
  return out;
}

/** focus 계열 상태의 outline 색 클래스. 굵기(-2)·간격(-offset)·모양은 뺀다.
 *  `has-[:focus-visible]:outline-…` 처럼 대괄호로 감싼 형태도 잡는다. 인라인
 *  style 의 outlineColor 는 보지 않는다(지금 쓰는 곳이 없다). */
const OUTLINE_COLOR =
  /(?:focus|focus-visible|focus-within)\]?:outline-(?!offset-|none\b|hidden\b|solid\b|dashed\b|dotted\b|double\b|\d)([^\s"'`]+)/g;

/* ---- 테스트 ---- */

describe("포커스 테두리 색 클래스", () => {
  const found = new Map<string, string[]>();
  for (const file of sources(SRC)) {
    for (const m of readFileSync(file, "utf8").matchAll(OUTLINE_COLOR)) {
      const where = found.get(m[1]) ?? [];
      where.push(relative(SRC, file));
      found.set(m[1], where);
    }
  }

  it("앱이 쓰는 포커스 테두리 색은 outline-focus 하나다", () => {
    const others = [...found].filter(([name]) => name !== "focus");
    assert.deepEqual(
      others.map(([name, files]) => `outline-${name}: ${[...new Set(files)].join(", ")}`),
      [],
    );
  });

  it("outline-focus 를 실제로 쓰고 있다 - 위 검사가 빈 목록으로 통과하지 않는다", () => {
    assert.ok((found.get("focus")?.length ?? 0) >= 50, `outline-focus ${found.get("focus")?.length ?? 0}곳`);
  });

  it("outline-focus 의 색이 @theme 에 --focus 로 이어져 있다", () => {
    // 이 줄이 빠지면 Tailwind 가 outline-focus 규칙을 안 만든다.
    assert.match(css, /--color-focus\s*:\s*var\(--focus\)\s*;/);
  });
});

describe("고르개 칸의 안쪽 포커스 테두리 3:1", () => {
  it("고르개 칸은 안쪽으로 그린다 - 그래서 칸 자기 바탕과 잰다", () => {
    assert.match(PICKER_ITEM_CLASS, /focus-visible:-outline-offset-\d/);
    assert.match(PICKER_ITEM_CLASS, /focus-visible:outline-focus(?=\s|$)/);
  });

  for (const active of [true, false]) {
    it(active ? "고른 칸(--coral-soft) 위" : "안 고른 칸(투명, 메뉴 종이) 위", () => {
      const own = pickerItemStyle(active).background;
      const back = own === "transparent" ? pickerMenuStyle().background : own;
      const ratio = contrast(token("--focus"), resolve(back));
      assert.ok(ratio >= 3, `--focus / ${String(back)} 는 ${ratio.toFixed(2)}:1 이다`);
    });
  }

  it("밝은 코랄이면 고른 칸 위에서 3:1 에 못 미친다 - 기준이 실제로 거른다", () => {
    assert.ok(contrast(token("--coral"), resolve(pickerItemStyle(true).background)) < 3);
  });
});
