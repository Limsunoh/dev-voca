/**
 * 빈 순위표의 문구와 버튼을 탭 셋 x 게스트/로그인으로 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 문구는 백엔드 규칙을 말로 옮긴 것이다(backend learning/leaderboards.py,
 * 시나리오는 learning/tests_leaderboards_empty_promise.py).
 *   - 이번 주·전체는 판을 끝내기만 하면 오른다. 다 틀린 판도 0점으로 오른다.
 *   - 꾸준함은 하루 점수가 1점 이상인 날이 있어야 오른다. 다 틀린 판 하나로는
 *     빈 표다. 일일공부로 점수를 얻어도 그날 판이 음수면 하루 점수가 0점일 수
 *     있다. 그래서 꾸준함에 "한 판" 이나 "점수를 얻으면" 이라고 하면 거짓말이 된다.
 *   - 게스트가 푼 판은 어느 표에도 안 오른다. 게스트에게는 로그인을 권하고
 *     로그인 뒤 지금 보던 탭으로 돌아온다.
 * 표가 있으면 빈 칸 문구와 그 버튼은 나오지 않는다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { Board, BoardKind, BoardRow } from "@/lib/api/leaderboards";
import { BOARD_KINDS } from "@/lib/api/leaderboards";

import { Leaderboard } from "./Leaderboard";

const HEADLINE: Record<BoardKind, string> = {
  weekly: "이번 주 1등 자리가 비어 있습니다.",
  all_time: "전체 1등 자리가 비어 있습니다.",
  streak: "꾸준함 1등 자리가 비어 있습니다.",
};

const MEMBER: Record<BoardKind, string> = {
  weekly: "지금 한 판을 끝내면 이번 주 1등으로 올라갑니다.",
  all_time: "지금 한 판을 끝내면 1등으로 올라갑니다.",
  streak: "오늘 하루 점수를 1점 이상 모으면 1등으로 올라갑니다.",
};

const GUEST: Record<BoardKind, string> = {
  weekly: "로그인하고 한 판을 끝내면 이번 주 1등으로 올라갑니다.",
  all_time: "로그인하고 한 판을 끝내면 1등으로 올라갑니다.",
  streak: "로그인하고 하루 점수를 1점 이상 모으면 1등으로 올라갑니다.",
};

/** 탭이 가리키는 주소. routes.board 를 쓰지 않고 손으로 적는다 - 둘이 같이 틀리면 못 잡는다. */
const BOARD_PATH: Record<BoardKind, string> = {
  weekly: "/board",
  all_time: "/board/all_time",
  streak: "/board/streak",
};

const TAB_PATHS = BOARD_KINDS.map((kind) => BOARD_PATH[kind]);

const ROW: BoardRow = {
  rank: 1,
  display_name: "누군가",
  avatar: { type: "preset", key: "a1" },
  score: 3,
  entries: 1,
  is_me: false,
};

function render(kind: BoardKind, isGuest: boolean, rows: BoardRow[] = [], me: BoardRow | null = null) {
  const board: Board = {
    kind,
    rows,
    me,
    ...(kind === "weekly" ? { period: { start: "2026-11-09", end: "2026-11-15" } } : {}),
  };
  const html = renderToStaticMarkup(createElement(Leaderboard, { board, isGuest }));
  const hrefs = [...html.matchAll(/href="([^"]*)"/g)].map((m) => m[1].replaceAll("&amp;", "&"));
  // 탭을 뺀 링크. 빈 칸 버튼과 게스트 안내 줄의 "로그인" 이 여기 든다.
  const actions = hrefs.filter((href) => !TAB_PATHS.includes(href));
  return { html, hrefs, actions };
}

/** 링크 글자로 그 링크의 주소를 찾는다. */
function hrefOf(html: string, label: string): string | undefined {
  const found = html.match(new RegExp(`<a[^>]*href="([^"]*)"[^>]*>${label}</a>`));
  return found?.[1];
}

for (const kind of BOARD_KINDS) {
  describe(`빈 순위표 - ${kind}`, () => {
    it("로그인했으면 이 탭의 문구와 문제풀이 버튼 하나다", () => {
      const { html, actions } = render(kind, false);

      assert.ok(html.includes(HEADLINE[kind]), `제목 문구가 다르다: ${kind}`);
      assert.ok(html.includes(MEMBER[kind]), `안내 문구가 다르다: ${kind}`);
      assert.deepEqual(actions, ["/test/round"]);
      assert.equal(hrefOf(html, "문제 풀러 가기"), "/test/round");
      assert.ok(!html.includes("로그인"), "로그인한 사람에게 로그인을 권한다");
      assert.ok(!html.includes(GUEST[kind]));
    });

    it("다른 탭의 문구가 섞여 나오지 않는다", () => {
      const { html } = render(kind, false);

      for (const other of BOARD_KINDS) {
        if (other === kind) continue;
        assert.ok(!html.includes(HEADLINE[other]), `${kind} 에 ${other} 제목`);
        assert.ok(!html.includes(MEMBER[other]), `${kind} 에 ${other} 안내`);
      }
    });

    it("게스트에게는 로그인 버튼 하나이고, 돌아올 곳은 지금 탭이다", () => {
      const { html, actions } = render(kind, true);

      assert.ok(html.includes(HEADLINE[kind]));
      assert.ok(html.includes(GUEST[kind]));
      assert.deepEqual(actions, [`/login?next=${BOARD_PATH[kind]}`]);
      assert.equal(hrefOf(html, "로그인하기"), `/login?next=${BOARD_PATH[kind]}`);
    });

    it("게스트에게 회원용 약속과 문제풀이 버튼을 보이지 않는다", () => {
      const { html, hrefs } = render(kind, true);

      for (const text of Object.values(MEMBER)) {
        assert.ok(!html.includes(text), `게스트에게 회원 문구: ${text}`);
      }
      assert.ok(!hrefs.includes("/test/round"));
      assert.ok(!html.includes("문제 풀러 가기"));
      // 표가 빌 때는 아래 게스트 안내 줄을 그리지 않는다. 버튼과 겹친다.
      assert.ok(!html.includes("로그인하면 내 순위도 함께 보입니다."));
    });

    it("탭 셋의 주소가 맞고 지금 탭에만 aria-current 가 붙는다", () => {
      const { html, hrefs } = render(kind, true);

      for (const path of TAB_PATHS) assert.ok(hrefs.includes(path), `탭 없음: ${path}`);
      const current = [...html.matchAll(/<a[^>]*aria-current="page"[^>]*>/g)];
      assert.equal(current.length, 1);
      assert.ok(current[0][0].includes(`href="${BOARD_PATH[kind]}"`));
    });

    for (const isGuest of [false, true]) {
      it(`표가 있으면 빈 칸 문구와 버튼이 없다 (${isGuest ? "게스트" : "로그인"})`, () => {
        const { html, hrefs } = render(kind, isGuest, [ROW]);

        assert.ok(html.includes("누군가"), "줄이 안 그려졌다");
        assert.ok(!html.includes("자리가 비어 있습니다"));
        assert.ok(!html.includes("1등으로 올라갑니다"));
        assert.ok(!html.includes("문제 풀러 가기"));
        assert.ok(!html.includes("로그인하기"));
        assert.ok(!hrefs.includes("/test/round"));
        if (isGuest) {
          // 표가 있을 때 게스트에게는 안내 줄의 "로그인" 하나. 돌아올 곳은 지금 탭이다.
          assert.equal(hrefOf(html, "로그인"), `/login?next=${BOARD_PATH[kind]}`);
        } else {
          assert.ok(!html.includes("로그인"));
        }
      });
    }
  });
}

describe("꾸준함 문구", () => {
  it('꾸준함은 "한 판" 이나 "점수를 얻으면" 으로 약속하지 않고 하루 점수로 말한다', () => {
    for (const isGuest of [false, true]) {
      const { html } = render("streak", isGuest);
      assert.ok(!/한 판/.test(html), `꾸준함 빈 칸에 "한 판": guest=${isGuest}`);
      assert.ok(!/점수를 얻으면/.test(html), `꾸준함 빈 칸에 "점수를 얻으면": guest=${isGuest}`);
      assert.ok(html.includes("하루 점수를 1점 이상"), `꾸준함 조건이 없다: guest=${isGuest}`);
    }
  });

  it("목록은 비었는데 내 줄(0일)만 온 경우 빈 칸과 내 순위가 함께 나온다", () => {
    // 다 틀린 판 하나만 한 사람. 서버가 목록은 비우고 me 에 0일 줄을 준다.
    const me: BoardRow = { ...ROW, display_name: "영일차회원", score: 0, entries: 0, is_me: true };
    const { html, actions } = render("streak", false, [], me);

    assert.ok(html.includes(HEADLINE.streak));
    assert.ok(html.includes(MEMBER.streak));
    assert.ok(html.includes("내 순위"));
    assert.ok(html.includes("영일차회원"));
    assert.deepEqual(actions, ["/test/round"]);
  });
});
