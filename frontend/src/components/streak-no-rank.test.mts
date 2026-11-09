/**
 * 꾸준함 0일인 사람에게 등수를 쓰지 않는지 본다.
 *
 * 실행: cd frontend && npm test
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { type BoardRow, shownRank } from "@/lib/api/leaderboards";

import { BoardRowItem } from "./BoardRow";
import { MyStandings } from "./MyStandings";

function row(over: Partial<BoardRow>): BoardRow {
  return {
    rank: 10,
    display_name: "초롱",
    avatar: { type: "preset", key: "a1" },
    score: 0,
    entries: 0,
    is_me: true,
    ...over,
  } as BoardRow;
}

describe("shownRank", () => {
  it("꾸준함 0일이면 등수가 없다", () => {
    assert.equal(shownRank("streak", row({ score: 0 })), null);
  });

  it("꾸준함 1일부터는 등수를 쓴다", () => {
    assert.equal(shownRank("streak", row({ score: 1 })), 10);
  });

  it("최고점의 0점은 실제 등수가 있다", () => {
    assert.equal(shownRank("weekly", row({ score: 0 })), 10);
    assert.equal(shownRank("all_time", row({ score: 0 })), 10);
  });
});

describe("순위표 줄", () => {
  const html = (kind: "streak" | "weekly", r: BoardRow) =>
    renderToStaticMarkup(createElement(BoardRowItem, { row: r, kind, pinned: true }));

  it("꾸준함 0일이면 1등으로 계산돼도 메달과 번호를 안 그린다", () => {
    const out = html("streak", row({ score: 0, rank: 1 }));

    assert.doesNotMatch(out, /medal-1/);
    assert.match(out, />-</);
  });

  it("꾸준함 1일의 1등은 메달과 번호를 그린다", () => {
    const out = html("streak", row({ score: 1, rank: 1 }));

    assert.match(out, /medal-1/);
    assert.doesNotMatch(out, />-</);
  });

  it("꾸준함 0일이 2·3등으로 계산돼도 메달이 없다", () => {
    for (const rank of [2, 3]) {
      assert.doesNotMatch(html("streak", row({ score: 0, rank })), /medal-/);
    }
  });

  it("최고점 0점의 등수는 대시로 바뀌지 않는다", () => {
    const out = html("weekly", row({ score: 0, rank: 12 }));

    assert.match(out, />12</);
    assert.doesNotMatch(out, />-</);
  });

  it("최고점 0점의 1등은 메달을 그린다", () => {
    assert.match(html("weekly", row({ score: 0, rank: 1 })), /medal-1/);
  });
});

describe("내정보의 순위 칸", () => {
  const html = (standings: Parameters<typeof MyStandings>[0]["standings"]) =>
    renderToStaticMarkup(createElement(MyStandings, { standings }));

  it("꾸준함 0일에는 10위를 쓰지 않는다", () => {
    assert.doesNotMatch(html({ streak: row({ score: 0 }) }), /10위/);
  });

  it("꾸준함만 대시이고 다른 칸의 0점 등수는 그대로다", () => {
    const out = html({
      weekly: row({ score: 0, rank: 3 }),
      all_time: row({ score: 0, rank: 7 }),
      streak: row({ score: 0, rank: 10 }),
    });

    assert.match(out, /3위/);
    assert.match(out, /7위/);
    assert.doesNotMatch(out, /10위/);
  });

  it("꾸준함 3일이면 등수를 쓴다", () => {
    assert.match(html({ streak: row({ score: 3, rank: 2 }) }), /2위/);
  });
});
