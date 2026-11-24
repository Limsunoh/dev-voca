/**
 * leaveIfSignedOut: 판 화면의 중계가 401 이면 지금 주소(쿼리 포함)를 들고 로그인으로 간다.
 *
 * 실행: cd frontend && npm test
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it } from "node:test";

import { leaveIfSignedOut } from "./connection";

const g = globalThis as unknown as { window?: unknown };
const hadWindow = "window" in g;
const realWindow = g.window;
after(() => {
  if (hadWindow) g.window = realWindow;
  else delete g.window;
});

let moved: string[] = [];
function at(pathname: string, search: string) {
  g.window = { location: { pathname, search, replace: (to: string) => moved.push(to) } };
}

beforeEach(() => {
  moved = [];
});

describe("leaveIfSignedOut", () => {
  it("401 이면 쿼리까지 들고 로그인으로 바꿔치기하고 흐름을 끊는다", () => {
    at("/test/daily", "?choose=1");
    assert.throws(() => leaveIfSignedOut(new Response(null, { status: 401 })));
    assert.deepEqual(moved, ["/login?next=%2Ftest%2Fdaily%3Fchoose%3D1"]);
  });

  for (const status of [200, 400, 403, 429, 500, 503]) {
    it(`${status} 면 아무것도 안 한다`, () => {
      at("/test/review", "");
      leaveIfSignedOut(new Response(null, { status }));
      assert.deepEqual(moved, []);
    });
  }
});
