/**
 * 탭바 높이를 읽어 가는 쪽들이 탭바와 같은 약속을 쓰는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * tab-bar-height.test.mts 는 TabBar 안의 숫자끼리 맞는지를 본다. 여기는 그
 * 바깥이다. 탭바 높이를 바꿔도 아래가 하나라도 어긋나면 숫자는 맞는데 화면이
 * 깨진다.
 *
 *   - html 의 scroll-padding-bottom 이 --tabbar-space 를 읽고, 탭바가 없는
 *     화면에서는 0 으로 떨어진다. 브라우저로 재 보니 이 값이 탭바(65px)보다
 *     작으면 390x844 의 단어 목록에서 Tab 으로 간 링크 여섯 개가 탭바 뒤로
 *     숨었다(옛 높이 57px 로 두면 8px 씩 가린다).
 *   - QuizBoard 가 높이를 잴 때 찾는 [data-tabbar] 가 탭바에 붙어 있다.
 *   - 탭바·두 변수·자리막이가 모두 safe-area 만큼 두꺼워진다. 하나라도 빠지면
 *     아이폰에서만 마지막 줄이 가려진다.
 *   - 변수와 자리막이는 탭바를 숨기는 화면에서 그려지지 않는다. 숨긴 화면에
 *     남으면 빈 띠와 여분 스크롤이 생긴다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const tabBar = readFileSync(new URL("./TabBar.tsx", import.meta.url), "utf-8");
const quizBoard = readFileSync(new URL("./QuizBoard.tsx", import.meta.url), "utf-8");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf-8");

/** 주석을 지운 CSS. 주석 안의 예시 문구에 걸리지 않게 한다. */
const cssCode = css.replace(/\/\*[\s\S]*?\*\//g, "");

describe("탭바 높이를 읽는 쪽", () => {
  it("html 의 scroll-padding-bottom 이 --tabbar-space 를 읽고 기본값은 0 이다", () => {
    assert.match(cssCode, /html\s*\{[^}]*scroll-padding-bottom:\s*var\(--tabbar-space,\s*0(px)?\)/);
  });

  it("QuizBoard 가 찾는 [data-tabbar] 가 탭바 nav 에 있다", () => {
    assert.match(quizBoard, /querySelector\("\[data-tabbar\]"\)/);
    const nav = tabBar.slice(tabBar.indexOf("<nav"), tabBar.indexOf(">", tabBar.indexOf("className=\"fixed")));
    assert.match(nav, /\bdata-tabbar\b/);
  });

  it("탭바 nav 가 safe-area 만큼 아래를 띄운다", () => {
    assert.match(tabBar, /className="fixed inset-x-0 bottom-0[^"]*pb-\[env\(safe-area-inset-bottom\)\]/);
  });

  it("변수와 자리막이는 탭바를 숨기는 return null 뒤에서만 그려진다", () => {
    const lastHide = tabBar.lastIndexOf("return null;");
    assert.ok(lastHide > 0, "탭바를 숨기는 분기를 못 찾았다");
    for (const marker of ["--tabbar-space:", "--tabbar-height:", "h-[calc("]) {
      const at = tabBar.indexOf(marker);
      assert.ok(at > lastHide, `${marker} 가 숨김 분기보다 앞에 있다`);
    }
  });

  it("CSS 에 탭바 높이를 숫자로 박아 둔 곳이 없다", () => {
    // 높이를 바꿀 때 TabBar 한 곳만 고치면 되도록, CSS 는 변수만 읽는다.
    assert.doesNotMatch(cssCode, /bottom:\s*(57|65)px/);
    assert.doesNotMatch(cssCode, /scroll-padding-bottom:\s*(5|5\.5)rem/);
  });
});
