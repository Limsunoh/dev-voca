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

import {
  activeTabSegment,
  immersiveRoutes,
  routes,
  tabHref,
  tabs,
} from "./routes";

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
    // TabBar 는 activeTabSegment 가 tab.segment 와 같으면 켠다. 보낸
    // 곳에서 다른 탭이 켜지면 누른 탭과 켜진 탭이 어긋난다.
    for (const t of tabs.filter((x) => x.ready)) {
      for (const path of ["/", "/learn/sentences", "/test/daily", "/talk", "/board"]) {
        assert.equal(activeTabSegment(tabHref(t, path)), t.segment, `${t.key} @ ${path}`);
      }
    }
  });
});

describe("activeTabSegment", () => {
  it("탭이 있는 화면은 첫 segment 그대로다", () => {
    assert.equal(activeTabSegment("/"), "");
    assert.equal(activeTabSegment("/learn/words/3"), "learn");
    assert.equal(activeTabSegment("/test/daily"), "test");
    assert.equal(activeTabSegment("/profile"), "profile");
  });

  it("순위표와 오답 노트에서는 문제풀기가 켜진다", () => {
    // 되돌리면 두 화면에서 탭바에 아무것도 안 켜진다. 깨지는 것이 없어
    // 눈으로 보기 전에는 모른다.
    for (const path of [
      routes.board(),
      routes.board("streak"),
      routes.board("all_time"),
      routes.mistakes,
    ]) {
      assert.equal(activeTabSegment(path), tab("test").segment, path);
    }
  });

  it("Object 의 속성 이름인 주소가 탭을 켜지 않는다", () => {
    for (const name of ["constructor", "toString", "__proto__", "hasOwnProperty"]) {
      assert.equal(activeTabSegment(`/${name}`), name);
      assert.ok(!tabs.some((t) => t.segment === activeTabSegment(`/${name}`)), name);
    }
  });

  it("열린 탭 주소는 자기 탭을 그대로 켠다", () => {
    // 옮김표에 탭 segment 를 잘못 넣으면(예: ["test", "learn"]) 그 탭을
    // 눌러도 다른 탭이 켜진다.
    for (const t of tabs.filter((x) => x.ready)) {
      assert.equal(activeTabSegment(`/${t.segment}`), t.segment, t.key);
      assert.equal(activeTabSegment(`/${t.segment}/x/y`), t.segment, t.key);
    }
  });

  it("끝에 / 가 붙어도 순위표·오답 노트는 문제풀기다", () => {
    // Next 가 /board/ 를 /board 로 308 보내지만, 옮겨지기 전 한 번의
    // 렌더에서 다른 탭이 깜빡이면 안 된다.
    assert.equal(activeTabSegment("/board/"), "test");
    assert.equal(activeTabSegment("/mistakes/"), "test");
  });

  it("비슷하지만 다른 이름은 옮기지 않는다", () => {
    for (const path of ["/boards", "/mistakesx", "/BOARD", "/Mistakes", "/xboard"]) {
      assert.ok(!tabs.some((t) => t.segment === activeTabSegment(path)), path);
    }
  });

  it("둘째 segment 의 board 는 옮기지 않는다", () => {
    assert.equal(activeTabSegment("/learn/board"), "learn");
    assert.equal(activeTabSegment("/profile/mistakes"), "profile");
  });

  it("빈 문자열과 // 에서 예외를 내지 않는다", () => {
    // usePathname 은 늘 / 로 시작하고 Next 가 //board 를 /board 로 308
    // 보내므로 실제로는 안 들어온다. 들어와도 터지지만 않으면 된다.
    for (const path of ["", "/", "//", "//board"]) {
      assert.equal(typeof activeTabSegment(path), "string", JSON.stringify(path));
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
