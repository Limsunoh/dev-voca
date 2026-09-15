/**
 * 일상영어 주소 만들기.
 *
 * 실행: cd frontend && npm test
 *
 * 갈래 탭과 난이도 탭이 둘 다 이 함수로 href 를 만든다. 한쪽 축을 빠뜨리면
 * 탭을 누를 때 다른 축이 조용히 풀린다 - 화면은 멀쩡해 보여서 눈으로 잘
 * 안 걸린다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { routes } from "./routes";

describe("routes.talk", () => {
  it("기본값(일상 표현·전부)은 쿼리를 싣지 않는다", () => {
    assert.equal(routes.talk(), "/talk");
    assert.equal(routes.talk("daily"), "/talk");
    assert.equal(routes.talk("daily", 0), "/talk");
  });

  it("두 축을 함께 싣는다", () => {
    assert.equal(routes.talk("dev"), "/talk?kind=dev");
    assert.equal(routes.talk("daily", 3), "/talk?level=3");
    assert.equal(routes.talk("dev", 2), "/talk?kind=dev&level=2");
  });
});
