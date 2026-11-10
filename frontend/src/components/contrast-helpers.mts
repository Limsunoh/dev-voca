/**
 * 테스트 전용: globals.css 의 색 토큰을 읽어 WCAG 대비를 잰다.
 *
 * contrast-pairs, menu-track, focus-ring 테스트가 같이 쓴다. 셋이 같은 식을
 * 따로 들고 있으면 한 곳만 고쳐져 테스트끼리 다른 값으로 재게 된다.
 *
 * node:fs 로 파일을 읽으므로 화면 코드에서 가져다 쓰지 않는다. 이름이
 * .test.mts 로 끝나지도, test- 로 시작하지도 않아 npm test 와 Node 의 기본
 * 테스트 찾기 어느 쪽도 이 파일을 테스트로 돌리지 않는다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

/** 주석을 걷어 낸 globals.css. 주석 안의 옛 값에 정규식이 걸리지 않게 한다. */
export const css = readFileSync(join(HERE, "..", "app", "globals.css"), "utf8").replace(
  /\/\*[\s\S]*?\*\//g,
  "",
);

/** 토큰 이름(--x)의 값을 var() 까지 끝까지 풀어 돌려준다. #rrggbb 인지는 luminance 가 본다. */
export function token(name: string): string {
  const found = new RegExp(`${name}\\s*:\\s*([^;]+);`).exec(css);
  assert.ok(found, `${name} 가 globals.css 에 없다`);
  const value = found[1].trim();
  const ref = /^var\((--[\w-]+)\)$/.exec(value);
  return ref ? token(ref[1]) : value;
}

/** "var(--x)" 를 #rrggbb 로. 토큰이 아니면 계산할 수 없어 실패시킨다. */
export function resolve(value: unknown): string {
  const ref = /^var\((--[\w-]+)\)$/.exec(String(value).trim());
  assert.ok(ref, `${String(value)} 는 토큰이 아니다`);
  return token(ref[1]);
}

/** WCAG 2 상대 휘도. */
export function luminance(hex: string): number {
  assert.match(hex, /^#[0-9a-f]{6}$/i, `${hex} 는 계산할 수 없는 값이다`);
  const [r, g, b] = [1, 3, 5].map((at) => {
    const channel = parseInt(hex.slice(at, at + 2), 16) / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** 두 색의 대비. 순서와 관계없이 1 이상이다. */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
