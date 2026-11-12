/**
 * 아래 탭바 높이와 그 높이에 묶인 값들이 서로 맞는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - 탭 칸은 최소 64px(min-h-16)이다. 56px 이던 것을 사용자가 "너무 짧다" 고 해서
 *     올렸다(11-12).
 *   - --tabbar-height 는 칸 높이 + 위 테두리 1px 이다. globals.css 의 .vx 처럼
 *     탭바 바로 위에 붙는 요소가 이 값으로 자리를 비킨다. 칸만 키우고 이 값을
 *     두면 그 요소가 탭바에 8px 묻힌다.
 *   - --tabbar-space 와 자리막이 높이는 같은 값이고 탭바보다 크다. 작으면 목록의
 *     마지막 줄이 탭바 뒤로 들어가 눌리지 않는다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const source = readFileSync(new URL("./TabBar.tsx", import.meta.url), "utf-8");
const REM = 16;

/** Tailwind min-h-N 은 N x 0.25rem 이다. */
function cellMinHeightPx(): number {
  const m = source.match(/"flex min-h-(\d+) flex-col/);
  assert.ok(m, "탭 칸의 min-h 를 못 찾았다");
  return Number(m[1]) * 0.25 * REM;
}

describe("탭바 높이", () => {
  it("탭 칸이 64px 이다", () => {
    assert.equal(cellMinHeightPx(), 64);
  });

  it("--tabbar-height 는 칸 높이 + 테두리 1px 이다", () => {
    const m = source.match(/--tabbar-height:calc\((\d+)px \+ env\(safe-area-inset-bottom\)\)/);
    assert.ok(m, "--tabbar-height 를 못 찾았다");
    assert.equal(Number(m[1]), cellMinHeightPx() + 1);
  });

  it("--tabbar-space 와 자리막이 높이가 같고 탭바보다 크다", () => {
    const space = source.match(/--tabbar-space:calc\(([\d.]+)rem \+ env\(safe-area-inset-bottom\)\)/);
    const spacer = source.match(/h-\[calc\(([\d.]+)rem\+env\(safe-area-inset-bottom\)\)\]/);
    assert.ok(space && spacer, "여백 값을 못 찾았다");
    assert.equal(Number(space[1]), Number(spacer[1]));
    assert.ok(Number(space[1]) * REM > cellMinHeightPx() + 1);
  });
});
