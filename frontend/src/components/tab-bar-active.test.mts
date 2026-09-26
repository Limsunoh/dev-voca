/**
 * 탭바가 **실제로 그렸을 때** 어느 탭을 켜는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * routes.test.mts 는 activeTabSegment 함수만 본다. 그래서 TabBar 가 그
 * 함수를 안 부르고 옛 판정(pathname.split("/")[1])으로 돌아가도 거기는
 * 초록불이다. 여기는 usePathname 을 대역으로 바꿔 TabBar 를 그리고,
 * aria-current="page" 가 붙은 링크의 글자를 읽는다.
 *
 * 기대 탭은 routes 로 다시 계산하지 않고 글자로 적는다. 구현과 같은
 * 함수로 기대값을 만들면 그 함수가 틀려도 테스트가 같이 틀려 초록불이다.
 */
import assert from "node:assert/strict";
import { describe, it, mock } from "node:test";
import { createElement } from "react";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

/** 지금 그릴 경로. 대역 usePathname 이 이걸 돌려준다. */
let pathname = "/";

mock.module("next/navigation", {
  namedExports: { usePathname: () => pathname },
});

type LinkProps = {
  href: string;
  "aria-current"?: string;
  children?: ReactNode;
};

mock.module("next/link", {
  defaultExport: (props: LinkProps) =>
    createElement(
      "a",
      { href: props.href, "aria-current": props["aria-current"] },
      props.children,
    ),
});

const { TabBar } = await import("./TabBar");

/** 켜진 탭의 글자들. 둘 이상 켜지면 그것도 결함이라 배열로 돌려준다. */
function activeLabels(path: string): string[] {
  pathname = path;
  const html = renderToStaticMarkup(createElement(TabBar));
  return [...html.matchAll(/<a [^>]*aria-current="page"[^>]*>(.*?)<\/a>/g)].map(
    // 앞의 코랄 막대(span)를 걷고 글자만 남긴다.
    (m) => m[1].replace(/<[^>]+>/g, ""),
  );
}

describe("TabBar 켜진 탭", () => {
  const cases: [string, string][] = [
    ["/", "홈"],
    ["/learn/words", "익히기"],
    ["/learn/sentences/3", "익히기"],
    ["/test", "문제풀기"],
    ["/test/daily", "문제풀기"],
    ["/test/review", "문제풀기"],
    ["/talk", "일상영어"],
    ["/profile", "내정보"],
    // 이번 변경의 요점. 옛 판정으로 돌아가면 여기서 아무것도 안 켜진다.
    ["/board", "문제풀기"],
    ["/board/streak", "문제풀기"],
    ["/board/all_time", "문제풀기"],
    ["/mistakes", "문제풀기"],
  ];

  for (const [path, label] of cases) {
    it(`${path} 에서는 ${label} 하나만 켜진다`, () => {
      assert.deepEqual(activeLabels(path), [label]);
    });
  }

  it("board·mistakes 를 닮았지만 다른 주소는 아무 탭도 켜지 않는다", () => {
    // 접두어로 거르면 /boards 같은 없는 주소(404)에서 문제풀기가 켜진다.
    for (const path of ["/boards", "/mistakesx", "/BOARD", "/Mistakes", "/xboard"]) {
      assert.deepEqual(activeLabels(path), [], path);
    }
  });

  it("다른 탭 아래의 board 는 그 탭을 켠다", () => {
    // 둘째 segment 가 board 라고 문제풀기로 끌려가면 안 된다.
    assert.deepEqual(activeLabels("/learn/board"), ["익히기"]);
    assert.deepEqual(activeLabels("/profile/mistakes"), ["내정보"]);
  });

  it("Object 속성 이름인 주소에서 예외 없이 아무 탭도 켜지 않는다", () => {
    for (const name of ["__proto__", "constructor", "toString", "valueOf"]) {
      assert.deepEqual(activeLabels(`/${name}`), [], name);
    }
  });
});
