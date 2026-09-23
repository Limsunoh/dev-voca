/**
 * quiz-progress 의 경계값. 기본 동작은 형제 quiz-progress.test.mts 가 본다.
 *
 * 실행: cd frontend && npm test
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

describe("푼 수 경계", () => {
  it("더하지 않고 덮어쓴다", () => {
    // 판은 누적한 값을 통째로 넘긴다. 여기서 더하면 두 배로 부푼다.
    markSolved(5);
    markSolved(2);
    assert.equal(solvedNow(), 2);
  });

  it("아주 큰 수도 그대로 돌려준다", () => {
    markSolved(Number.MAX_SAFE_INTEGER);
    assert.equal(solvedToConfirm(click()), Number.MAX_SAFE_INTEGER);
  });

  it("0 을 적으면 안 묻는다", () => {
    // 판이 새로 시작하며 0 을 적는 경로.
    markSolved(3);
    markSolved(0);
    assert.equal(solvedToConfirm(click()), 0);
  });

  it("두 번 지워도 0 이다", () => {
    clearSolved();
    clearSolved();
    assert.equal(solvedNow(), 0);
  });
});

describe("어떤 클릭에 묻나 - 경계", () => {
  it("오른쪽 버튼(2)에는 안 묻는다", () => {
    markSolved(2);
    assert.equal(solvedToConfirm(click({ button: 2 })), 0);
  });

  it("뒤로·앞으로 버튼(3, 4)에도 안 묻는다", () => {
    markSolved(2);
    for (const button of [3, 4]) {
      assert.equal(solvedToConfirm(click({ button })), 0, `button ${button}`);
    }
  });

  it("보조키를 여러 개 같이 눌러도 안 묻는다", () => {
    markSolved(2);
    assert.equal(
      solvedToConfirm(click({ ctrlKey: true, shiftKey: true, metaKey: true, altKey: true })),
      0,
    );
    assert.equal(solvedToConfirm(click({ ctrlKey: true, button: 1 })), 0);
  });

  it("보조키를 다 뗀 왼쪽 클릭에만 묻는다", () => {
    markSolved(2);
    assert.equal(
      solvedToConfirm(click({ ctrlKey: false, shiftKey: false, metaKey: false, altKey: false })),
      2,
    );
  });
});

describe("확인 문구 - 경계", () => {
  it("큰 수도 쉼표 없이 그대로 말한다", () => {
    assert.equal(leaveDetail(1000), "지금까지 푼 1000문제가 사라집니다.");
  });

  it("한 문제도 숫자로 말한다", () => {
    assert.equal(leaveDetail(1), "지금까지 푼 1문제가 사라집니다.");
  });
});
