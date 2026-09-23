/**
 * 주소 만들기.
 *
 * 실행: cd frontend && npm test
 *
 * routes.talk: 갈래 탭과 난이도 탭이 둘 다 이 함수로 href 를 만든다. 한쪽
 * 축을 빠뜨리면 탭을 누를 때 다른 축이 조용히 풀린다 - 화면은 멀쩡해
 * 보여서 눈으로 잘 안 걸린다.
 *
 * tabHref: 익히기는 보던 콘텐츠를 따라가고 문제풀기는 허브로 간다. 둘이
 * 한 분기에 있었던 적이 있어서, 되돌리면 문제풀기 탭이 다시 단어 문제로
 * 곧장 가고 일일공부·한 판으로 가는 길이 탭에서 사라진다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { immersiveRoutes, routes, tabHref, tabs } from "./routes";

function tab(key: string) {
  const found = tabs.find((t) => t.key === key);
  assert.ok(found, `탭 ${key} 가 없다`);
  return found;
}

describe("tabHref", () => {
  it("문제풀기는 어디서 눌러도 허브로 간다", () => {
    assert.equal(tabHref(tab("test"), "/learn/sentences"), routes.test);
    assert.equal(tabHref(tab("test"), "/test/sentences"), routes.test);
    assert.equal(tabHref(tab("test"), "/"), routes.test);
  });

  it("익히기는 보던 콘텐츠를 따라간다", () => {
    assert.equal(tabHref(tab("learn"), "/test/sentences"), "/learn/sentences");
    assert.equal(tabHref(tab("learn"), "/learn/sentences/3"), "/learn/sentences");
  });

  it("콘텐츠를 알 수 없으면 익히기는 단어로 간다", () => {
    assert.equal(tabHref(tab("learn"), "/test"), "/learn/words");
    assert.equal(tabHref(tab("learn"), "/"), "/learn/words");
  });

  it("문제풀기는 판 화면(일일공부·복습·한 판)·허브 자신·상세에서도 허브로 간다", () => {
    for (const path of ["/test", "/test/daily", "/test/review", "/test/round", "/learn/words/3"]) {
      assert.equal(tabHref(tab("test"), path), routes.test, path);
    }
  });

  it("판의 종류(daily·review)를 콘텐츠로 읽지 않는다 - 익히기는 단어로 간다", () => {
    assert.equal(tabHref(tab("learn"), "/test/daily"), "/learn/words");
    assert.equal(tabHref(tab("learn"), "/test/review"), "/learn/words");
    assert.equal(tabHref(tab("learn"), "/learn/zzz"), "/learn/words");
    assert.equal(tabHref(tab("learn"), "/learn/sentences"), "/learn/sentences");
  });

  it("홈·일상영어·내정보는 보던 경로와 무관하다", () => {
    for (const path of ["/", "/learn/sentences", "/test/sentences", "/test"]) {
      assert.equal(tabHref(tab("home"), path), routes.home, path);
      assert.equal(tabHref(tab("talk"), path), "/talk", path);
      assert.equal(tabHref(tab("profile"), path), routes.profile, path);
    }
  });

  it("탭이 보내는 곳에서 그 탭이 켜진다", () => {
    // TabBar 는 첫 segment 가 tab.segment 와 같으면 켠다. 보낸 곳에서
    // 다른 탭이 켜지면 누른 탭과 켜진 탭이 어긋난다.
    for (const t of tabs.filter((x) => x.ready)) {
      for (const path of ["/", "/learn/sentences", "/test/daily", "/talk"]) {
        assert.equal(tabHref(t, path).split("/")[1], t.segment, `${t.key} @ ${path}`);
      }
    }
  });
});

describe("immersiveRoutes", () => {
  it("허브·일일공부·복습은 탭바를 숨기지 않는다", () => {
    // 허브에는 ExitGuard 가 없다. 여기 들어가면 나갈 길이 없는 화면이 된다.
    for (const path of [routes.test, routes.testDaily, routes.testReview]) {
      assert.ok(!immersiveRoutes.includes(path), path);
    }
  });
});

describe("routes.talk", () => {
  it("기본값(일상 표현·전체)은 쿼리를 싣지 않는다", () => {
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
