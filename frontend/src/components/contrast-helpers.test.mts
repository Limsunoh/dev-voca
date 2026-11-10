/**
 * contrast-helpers 의 경계를 본다.
 *
 * 대비 테스트 셋(contrast-pairs, menu-track, focus-ring)은 globals.css 의 실제
 * 토큰만 넣으므로, 도우미가 엉뚱한 값을 막는 자리는 거기서 한 번도 지나가지
 * 않는다. 주석 걷기, resolve 의 "토큰이 아니면 실패", luminance 의 #rrggbb 검사를
 * 지워도 셋은 초록불이다. 그 자리를 여기서 잡는다.
 *
 * 기대 대비값은 WCAG 에 널리 실린 값이다(#777777/흰색 4.48, 빨강/흰색 4.00,
 * 파랑/흰색 8.59). 감마나 채널 가중치가 틀리면 여기서 어긋난다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { contrast, css, luminance, resolve, token } from "./contrast-helpers.mjs";

const HEX = /^#[0-9a-f]{6}$/i;

describe("contrast-helpers - css", () => {
  it("주석을 걷어 낸다(주석 속 옛 값이 토큰으로 읽히지 않게)", () => {
    assert.ok(css.length > 0);
    assert.ok(!css.includes("/*"), "주석이 남아 있다");
  });
});

describe("contrast-helpers - token", () => {
  it("var() 를 따라가 가리키는 토큰과 같은 #rrggbb 를 돌려준다", () => {
    // 특정 이름에 묶지 않고, globals.css 에서 다른 토큰을 가리키는 첫 줄을 찾아 쓴다.
    // 이름을 박아 두면 그 토큰에 직접 색을 주는 디자인 변경만으로 빨개진다.
    const alias = /(--[\w-]+)\s*:\s*var\((--[\w-]+)\)\s*;/.exec(css);
    assert.ok(alias, "다른 토큰을 가리키는 줄이 globals.css 에 없다");
    const [, name, target] = alias;
    assert.equal(token(name), token(target));
    assert.match(token(name), HEX);
  });

  it("없는 토큰은 이름을 담아 실패한다", () => {
    assert.throws(() => token("--no-such-token"), /--no-such-token 가 globals\.css 에 없다/);
  });
});

describe("contrast-helpers - resolve", () => {
  it("var(--x) 와 앞뒤 공백을 받는다", () => {
    assert.equal(resolve(" var(--paper) "), token("--paper"));
  });

  for (const value of ["#ffffff", "transparent", undefined, "var(--paper, #fff)"]) {
    it(`토큰이 아닌 ${String(value)} 은 계산하지 않고 실패한다`, () => {
      assert.throws(() => resolve(value), /토큰이 아니다/);
    });
  }
});

describe("contrast-helpers - luminance", () => {
  it("검정 0, 흰색 1. 대문자 hex 도 받는다", () => {
    assert.equal(luminance("#000000"), 0);
    // 정확히 1.0 은 가중치를 더하는 순서에 기댄다. 대문자를 받는지가 요점이라 근삿값으로 본다.
    assert.ok(Math.abs(luminance("#FFFFFF") - 1) < 1e-9);
  });

  // #ffffff80 은 알파가 붙은 8자리다. 뒤를 막지 않으면 알파를 버리고 불투명으로 잰다.
  for (const value of ["#fff", "#ffffff80", "rgb(0 0 0)", " #ffffff", "#gggggg"]) {
    it(`#rrggbb 가 아닌 "${value}" 는 NaN 대신 실패한다`, () => {
      assert.throws(() => luminance(value), /계산할 수 없는 값이다/);
    });
  }
});

describe("contrast-helpers - contrast", () => {
  const near = (actual: number, expected: number) =>
    assert.ok(Math.abs(actual - expected) < 0.01, `${actual} 가 ${expected} 가 아니다`);

  it("알려진 값과 맞는다", () => {
    near(contrast("#000000", "#ffffff"), 21);
    near(contrast("#777777", "#ffffff"), 4.48);
    near(contrast("#ff0000", "#ffffff"), 4.0);
    near(contrast("#0000ff", "#ffffff"), 8.59);
  });

  it("순서와 관계없고 같은 색끼리는 1 이다", () => {
    assert.equal(contrast("#ffffff", "#777777"), contrast("#777777", "#ffffff"));
    assert.equal(contrast("#c13e22", "#c13e22"), 1);
  });
});
