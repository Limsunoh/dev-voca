/**
 * safeNext 가 점 조각으로 바깥 주소를 만드는 꼴을 막는지.
 *
 * 실행: cd frontend && npm test
 *
 * "/.//evil.example" 은 "슬래시 하나로 시작" 검사를 지나지만, 브라우저 쪽 Next 가
 * 주소를 풀면 "//evil.example" 이 되어 바깥 사이트로 간다. safeNext 는 한 번 풀어 본
 * 값으로 판단하고 풀린 값을 돌려준다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { safeNext } from "./routes";

describe("점 조각으로 만든 바깥 주소는 홈으로", () => {
  for (const value of [
    "/.//evil.example",
    "/..//evil.example/x?y=1",
    "/a/..//evil.example",
    "/././/evil.example",
    "/%2e//evil.example",
  ]) {
    it(value, () => {
      assert.equal(safeNext(value), "/");
    });
  }
});

describe("평범한 안쪽 주소는 그대로", () => {
  for (const value of ["/", "/profile", "/learn/words?page=2&search=api", "/test/daily#top"]) {
    it(value, () => {
      assert.equal(safeNext(value), value);
    });
  }

  it("점 조각이 안쪽으로만 풀리면 풀린 주소", () => {
    assert.equal(safeNext("/learn/./words"), "/learn/words");
    assert.equal(safeNext("/learn/x/../words"), "/learn/words");
  });
});
