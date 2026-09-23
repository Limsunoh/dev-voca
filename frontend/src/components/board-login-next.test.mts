/**
 * 순위표에서 로그인하러 간 사람이 **보던 탭으로 돌아오는지**, 그리고 빈
 * 순위표가 게스트에게 헛된 약속을 하지 않는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약은 셋이다.
 *   1. 빈 순위표: 게스트에게는 "로그인하기"(돌아올 곳 = 지금 탭), 로그인한
 *      사람에게는 "문제 풀러 가기"(/test/round). 게스트가 푼 판은 순위표에
 *      안 오르므로 게스트에게 "한 판만 풀어도 올라간다" 를 보이면 안 된다.
 *   2. 표가 있을 때 게스트 안내 줄의 "로그인" 도 지금 탭으로 돌아온다.
 *   3. 로그인 <-> 가입 전환 링크가 next 를 들고 간다. 안 들고 가면 가입을
 *      마친 사람이 홈에 떨어진다.
 *
 * 기대 주소는 routes 로 다시 계산하지 않고 문자열로 적는다. 구현과 같은
 * 함수로 기대값을 만들면 그 함수가 틀려도 테스트가 같이 틀려 초록불이다.
 *
 * 링크는 leave-exits.test.mts 처럼 next/link 를 대역으로 바꿔 넘긴 props 를
 * 모아서 본다.
 */
import assert from "node:assert/strict";
import { describe, it, mock } from "node:test";
import { createElement } from "react";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

type LinkProps = { href: string; children?: ReactNode };

/** 이번 렌더에서 그려진 링크들. */
let links: LinkProps[] = [];

mock.module("next/link", {
  defaultExport: (props: LinkProps) => {
    links.push(props);
    return createElement("a", { href: props.href }, props.children);
  },
});

const { Leaderboard } = await import("./Leaderboard");
const { AuthForm } = await import("./AuthForm");

// ---------------------------------------------------------------------------
// 도구
// ---------------------------------------------------------------------------

type Kind = "weekly" | "all_time" | "streak";

/** 각 탭에서 로그인하러 갈 때 기대하는 주소. */
const LOGIN_FROM: Record<Kind, string> = {
  weekly: "/login?next=/board",
  all_time: "/login?next=/board/all_time",
  streak: "/login?next=/board/streak",
};

const KINDS: Kind[] = ["weekly", "all_time", "streak"];

const row = {
  rank: 1,
  display_name: "someone",
  avatar: { kind: "initial", value: "S" },
  score: 42,
  entries: 3,
  is_me: false,
};

const draw = (element: ReturnType<typeof createElement>) => {
  links = [];
  const html = renderToStaticMarkup(element);
  return { html, hrefs: links.map((l) => l.href) };
};

const board = (kind: Kind, empty: boolean, isGuest: boolean) =>
  draw(
    createElement(Leaderboard, {
      board: { kind, rows: empty ? [] : [row], me: null } as never,
      isGuest,
    }),
  );

/** 탭 링크(/board, /board/all_time, /board/streak)를 뺀 링크. */
const actionHrefs = (hrefs: string[]) =>
  hrefs.filter((h) => !["/board", "/board/all_time", "/board/streak"].includes(h));

// ---------------------------------------------------------------------------
// 빈 순위표
// ---------------------------------------------------------------------------

describe("빈 순위표", () => {
  for (const kind of KINDS) {
    it(`게스트(${kind})에게는 로그인을 권하고, 돌아올 곳은 지금 탭이다`, () => {
      const { html, hrefs } = board(kind, true, true);
      assert.deepEqual(actionHrefs(hrefs), [LOGIN_FROM[kind]]);
      assert.match(html, /로그인하고 한 판을 풀면 이 자리에 이름이 올라갑니다\./);
      assert.match(html, />로그인하기<\/a>/);
    });

    it(`게스트(${kind})에게 "한 판만 풀어도" 와 문제 풀기 링크를 보이지 않는다`, () => {
      // 게스트가 푼 판은 순위표에 안 오른다. 믿고 풀면 다 풀고도 빈 표다.
      const { html, hrefs } = board(kind, true, true);
      assert.doesNotMatch(html, /한 판만 풀어도/);
      assert.doesNotMatch(html, /문제 풀러 가기/);
      assert.ok(!hrefs.includes("/test/round"), hrefs.join(" "));
    });

    it(`로그인했으면(${kind}) 전과 같이 문제 풀기로 보낸다`, () => {
      const { html, hrefs } = board(kind, true, false);
      assert.deepEqual(actionHrefs(hrefs), ["/test/round"]);
      assert.match(html, /한 판만 풀어도 이 자리에 이름이 올라갑니다\./);
      assert.match(html, />문제 풀러 가기<\/a>/);
      assert.doesNotMatch(html, /로그인/);
    });
  }

  it("게스트의 빈 표에 하단 안내 줄이 겹쳐 나오지 않는다", () => {
    // 버튼과 안내 줄이 둘 다 뜨면 로그인 링크가 두 개가 된다.
    const { html } = board("weekly", true, true);
    assert.doesNotMatch(html, /로그인하면 내 순위도/);
  });
});

// ---------------------------------------------------------------------------
// 표가 있을 때
// ---------------------------------------------------------------------------

describe("표가 있을 때", () => {
  for (const kind of KINDS) {
    it(`게스트(${kind}) 안내 줄의 로그인은 지금 탭으로 돌아온다`, () => {
      const { html, hrefs } = board(kind, false, true);
      assert.deepEqual(actionHrefs(hrefs), [LOGIN_FROM[kind]]);
      assert.match(html, /로그인하면 내 순위도 함께 보입니다\./);
      // 빈 표의 버튼은 안 나온다.
      assert.doesNotMatch(html, /로그인하기/);
    });

    it(`로그인했으면(${kind}) 로그인 링크가 하나도 없다`, () => {
      const { html, hrefs } = board(kind, false, false);
      assert.deepEqual(actionHrefs(hrefs), []);
      assert.doesNotMatch(html, /로그인/);
    });
  }
});

// ---------------------------------------------------------------------------
// 로그인 <-> 가입 전환
// ---------------------------------------------------------------------------

describe("로그인·가입 전환 링크", () => {
  const noop = async () => ({}) as never;
  const form = (mode: "login" | "signup", next?: string) =>
    draw(createElement(AuthForm, { mode, action: noop, next }));

  /** "가입하기"/"로그인" 전환 링크. 홈("/")·구글 링크와 구분한다. */
  const switchHref = (mode: "login" | "signup", next?: string) => {
    const target = mode === "login" ? "/signup" : "/login";
    const found = form(mode, next).hrefs.filter(
      (h) => h === target || h.startsWith(`${target}?`),
    );
    assert.equal(found.length, 1, `전환 링크가 하나가 아니다: ${found.join(" ")}`);
    return found[0];
  };

  it("로그인 -> 가입이 next 를 들고 간다", () => {
    assert.equal(switchHref("login", "/board/streak"), "/signup?next=%2Fboard%2Fstreak");
  });

  it("가입 -> 로그인이 next 를 들고 간다", () => {
    assert.equal(switchHref("signup", "/board/all_time"), "/login?next=%2Fboard%2Fall_time");
  });

  it("next 가 없으면 전처럼 맨 주소다", () => {
    assert.equal(switchHref("login"), "/signup");
    assert.equal(switchHref("signup"), "/login");
  });

  it("빈 문자열 next 는 없는 것과 같다", () => {
    // /signup?next= 로 가면 받는 쪽이 "" 를 돌아갈 곳으로 싣고 다닌다.
    assert.equal(switchHref("login", ""), "/signup");
  });

  it("쿼리·한글·# 이 섞인 next 도 한 값으로 온전히 넘어간다", () => {
    // 인코딩을 빼먹으면 & 뒤가 다른 쿼리로, # 뒤가 조각으로 떨어져 나간다.
    const next = "/learn/words?search=캐시&page=2#top";
    const href = switchHref("login", next);
    assert.equal(
      href,
      "/signup?next=%2Flearn%2Fwords%3Fsearch%3D%EC%BA%90%EC%8B%9C%26page%3D2%23top",
    );
    assert.equal(new URLSearchParams(href.split("?")[1]).get("next"), next);
  });

  it("밖을 가리키는 next 를 실어도 링크가 가는 곳은 가입 화면이다", () => {
    // 거르는 곳은 제출 때의 safeNext 다. 여기서는 값이 쿼리에만 들어가야 한다.
    for (const next of ["//evil.example", "https://evil.example", "/\\evil.example"]) {
      const href = switchHref("login", next);
      assert.ok(href.startsWith("/signup?next="), href);
      assert.doesNotMatch(href.slice("/signup?next=".length), /[/:\\]/, href);
    }
  });
});
