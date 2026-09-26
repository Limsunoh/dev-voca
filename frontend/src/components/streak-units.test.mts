/**
 * 순위표 숫자 옆 단위를 **실제로 그려서** 본다.
 *
 * 꾸준함은 큰 숫자가 날 수("4일"), 작은 줄이 점수 합("18점")이다.
 * 이번 주/전체는 그대로 큰 숫자가 점수("60점"), 작은 줄이 판 수("1판").
 * 단위가 뒤집히면 "4점 / 18일" 이 되어 화면이 거짓말을 한다.
 *
 * 기대 단위는 BOARD_LABELS 에서 다시 읽지 않고 글자로 적는다. 같은 표로
 * 기대값을 만들면 표가 틀려도 테스트가 같이 틀려 초록불이다.
 *
 * 실행: cd frontend && npm test
 */
import assert from "node:assert/strict";
import { describe, it, mock } from "node:test";
import { createElement } from "react";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

mock.module("next/link", {
  defaultExport: (props: { href: string; className?: string; style?: object; children?: ReactNode }) =>
    createElement("a", { href: props.href, className: props.className, style: props.style }, props.children),
});

const { BoardRowItem } = await import("./BoardRow");
const { MyStandings } = await import("./MyStandings");

type Kind = "weekly" | "all_time" | "streak";

const row = (score: number, entries: number) => ({
  rank: 7,
  display_name: "tester",
  avatar: { type: "preset", key: "a1" },
  score,
  entries,
  is_me: false,
});

/** 태그를 걷어 보이는 글자만. */
const text = (html: string) => html.replace(/<[^>]*>/g, "");

const drawRow = (kind: Kind, score: number, entries: number) =>
  text(renderToStaticMarkup(createElement(BoardRowItem, { row: row(score, entries), kind } as never)));

describe("BoardRowItem 단위", () => {
  it("꾸준함은 큰 숫자가 날 수(일), 작은 줄이 점수 합(점)", () => {
    const t = drawRow("streak", 4, 18);
    assert.match(t, /4일/);
    assert.match(t, /18점/);
    assert.doesNotMatch(t, /4점/, "날 수를 점수로 읽게 하면 안 된다");
    assert.doesNotMatch(t, /18일/);
  });

  it("이번 주는 큰 숫자가 점수(점), 작은 줄이 판 수(판)", () => {
    const t = drawRow("weekly", 60, 1);
    assert.match(t, /60점/);
    assert.match(t, /1판/);
    assert.doesNotMatch(t, /일/);
  });

  it("전체도 점/판", () => {
    const t = drawRow("all_time", 1040, 12);
    assert.match(t, /1,040점/);
    assert.match(t, /12판/);
  });
});

describe("MyStandings", () => {
  const html = renderToStaticMarkup(
    createElement(MyStandings, {
      standings: { weekly: row(60, 1), streak: row(4, 18) },
    } as never),
  );

  it("꾸준함 칸은 '일', 이번 주 칸은 '점'. 빈 칸은 단위 없이 하이픈", () => {
    const t = text(html);
    assert.match(t, /꾸준함4일7위/);
    assert.match(t, /이번 주60점7위/);
    assert.match(t, /전체-아직/);
  });

  it("'순위표 전체' 링크는 누르는 높이가 44px(--hit-floor)", () => {
    const link = html.match(/<a[^>]*>순위표 전체<\/a>/)?.[0] ?? "";
    assert.ok(link, "링크가 그려져야 한다");
    assert.match(link, /min-height:var\(--hit-floor\)/);
    assert.doesNotMatch(link, /py-1/, "글자 높이만 누를 수 있던 때로 돌아가면 안 된다");
  });

  it("세 칸 이름은 12px(text-xs), 11px 이 아니다", () => {
    const dts = [...html.matchAll(/<dt class="([^"]*)"/g)].map((m) => m[1]);
    assert.equal(dts.length, 3);
    for (const cls of dts) {
      assert.match(cls, /\btext-xs\b/);
      assert.doesNotMatch(cls, /text-11/);
    }
  });
});
