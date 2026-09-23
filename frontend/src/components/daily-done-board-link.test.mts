/**
 * 일일공부를 마친 화면의 "순위표에서 확인" 이 꾸준함 탭을 여는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 일일공부 점수는 하루 점수(DailyScore)에만 쌓이고, 그것을 읽는 것은 꾸준함
 * 순위표뿐이다. 이번 주·전체 순위표는 자유 문제풀이 판만 센다(backend
 * learning/leaderboards.py). 전에는 이 버튼이 /board 로 보내 이번 주 탭이
 * 열렸고, 방금 딴 점수가 어디에도 안 보였다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { DailyStatus } from "@/lib/api/daily";
import { routes } from "@/lib/routes";

import { DailyStudyBoard } from "./DailyStudyBoard";

const DONE: DailyStatus = {
  lengths: [],
  today: {
    length: "short",
    total: 10,
    answered: 10,
    correct: 8,
    score: 80,
    bonus: 0,
    done: true,
    chunk_size: 0,
    chunk_count: 0,
    chunk_index: 0,
  },
  token: null,
  question: null,
  learning: [],
};

describe("일일공부를 마친 화면", () => {
  const html = renderToStaticMarkup(createElement(DailyStudyBoard, { status: DONE }));

  it("순위표 버튼이 꾸준함 탭으로 간다", () => {
    const link = html.match(/<a[^>]*href="([^"]+)"[^>]*>순위표에서 확인</);
    assert.ok(link, "순위표 버튼을 못 찾았다");
    assert.equal(link[1], routes.board("streak"));
  });
});
