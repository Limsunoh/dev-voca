/**
 * 크림 바탕 색이 세 곳에서 같은지 검증.
 *
 * 실행: cd frontend && npm test
 *
 * 크림 바탕은 globals.css 의 --background 말고도 layout.tsx 와
 * profile/layout.tsx 의 themeColor(폰 브라우저 주소창 색)에 적혀 있다. 하나만
 * 바꾸면 주소창 색과 화면 바탕이 어긋난다. 시작 화면 로고 그림(start/logo.webp)의
 * 바탕도 같은 색이지만 노드에 webp 해석기가 없어 여기서는 못 본다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

describe("크림 바탕 색", () => {
  // 주석에 옛 값을 예로 적어 둔 곳이 있어도 그것을 읽지 않게 주석부터 지운다.
  const read = (path: string) =>
    readFileSync(join(HERE, path), "utf8").replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
  const background = read("globals.css").match(/--background:\s*(#[0-9a-f]{6})\s*;/i)?.[1];

  it("globals.css 에 --background 가 있다", () => {
    assert.ok(background);
  });

  for (const layout of ["layout.tsx", "profile/layout.tsx"]) {
    it(`${layout} 의 themeColor 가 --background 와 같다`, () => {
      const themeColor = read(layout).match(/themeColor:\s*"(#[0-9a-f]{6})"/i)?.[1];
      assert.equal(themeColor?.toLowerCase(), background?.toLowerCase());
    });
  }
});
