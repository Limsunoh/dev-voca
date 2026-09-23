/**
 * 문제 판과 출구가 주고받는 "푼 문제 수" 규칙을 **실제로 실행해서** 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 분류·탭·"한 판 풀기"·홈 중 어디로 나가도 판이 새로 시작돼 푼 점수가
 * 사라진다. 점수는 서버에 안 남아 되돌릴 수 없어서, 푼 것이 있을 때만
 * 확인을 묻는다. 판과 네 출구는 서로를 모르고 이 파일의 함수로 값 하나만
 * 주고받는다 - 여기가 어긋나면 네 출구가 한꺼번에 조용히 안 묻게 된다.
 */
import assert from "node:assert/strict";
import { beforeEach, describe, it } from "node:test";

import {
  clearSolved,
  leaveDetail,
  markSolved,
  solvedNow,
  solvedToConfirm,
} from "./quiz-progress";

const click = (over: Partial<Parameters<typeof solvedToConfirm>[0]> = {}) => ({
  metaKey: false,
  ctrlKey: false,
  shiftKey: false,
  altKey: false,
  button: 0,
  ...over,
});

beforeEach(() => clearSolved());

describe("푼 문제 수를 주고받는다", () => {
  it("적은 값을 그대로 읽는다", () => {
    markSolved(3);
    assert.equal(solvedNow(), 3);
  });

  it("판이 없는 화면에서는 0 이다", () => {
    assert.equal(solvedNow(), 0);
  });

  it("판이 사라지면 0 으로 돌아간다", () => {
    markSolved(2);
    clearSolved();
    assert.equal(solvedNow(), 0);
  });
});

describe("어떤 클릭에 묻나", () => {
  it("푼 것이 있으면 그냥 클릭에 묻는다", () => {
    markSolved(2);
    assert.equal(solvedToConfirm(click()), 2);
  });

  it("한 문제도 안 풀었으면 안 묻는다", () => {
    assert.equal(solvedToConfirm(click()), 0);
  });

  it("새 탭·새 창으로 여는 클릭에는 안 묻는다", () => {
    // 지금 판은 그대로 남으니 잃는 것이 없다. 막으면 새 탭도 못 연다.
    markSolved(2);
    for (const key of ["metaKey", "ctrlKey", "shiftKey", "altKey"] as const) {
      assert.equal(solvedToConfirm(click({ [key]: true })), 0, key);
    }
  });

  it("0 이하나 숫자가 아닌 값에는 안 묻는다", () => {
    // 홈 버튼은 "0 보다 클 때" 묻는다. 링크 출구도 같은 선을 써야 한다 -
    // 안 그러면 "푼 -1문제가 사라집니다" 가 뜬다.
    for (const bad of [-1, Number.NaN]) {
      markSolved(bad);
      assert.equal(solvedToConfirm(click()), 0, String(bad));
    }
  });

  it("왼쪽 버튼이 아닌 클릭에는 안 묻는다", () => {
    markSolved(2);
    assert.equal(solvedToConfirm(click({ button: 1 })), 0);
  });
});

describe("확인 문구", () => {
  it("잃는 문제 수를 숫자로 말한다", () => {
    assert.match(leaveDetail(2), /2문제가 사라/);
  });
});
