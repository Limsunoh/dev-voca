/**
 * 사진 오려 내기 창의 위치 계산(clampView, panView, zoomView).
 *
 * 실행: cd frontend && npm test
 *
 * 틀어지면 사진 밖(빈 곳)이 함께 오려 올라가거나, 확대할 때 사진이 엉뚱한 곳으로 튄다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { clampView, MAX_ZOOM, panView, type View, zoomView } from "./PhotoCropper";

// 가로 4000 x 세로 3000 사진, 화면의 틀은 한 변 300px.
const SIZE = { w: 4000, h: 3000 };
const FRAME = 300;
const CENTER: View = { zoom: 1, cx: 2000, cy: 1500 };

/** 틀 한 변이 원본으로 몇 px 인가. 오려 낼 정사각형의 한 변이다. */
function side(view: View): number {
  return Math.min(SIZE.w, SIZE.h) / view.zoom;
}

/** 오려 낼 정사각형이 사진 안에 다 들어가나. */
function inside(view: View): boolean {
  const half = side(view) / 2;
  return (
    view.cx - half >= 0 &&
    view.cy - half >= 0 &&
    view.cx + half <= SIZE.w + 1e-9 &&
    view.cy + half <= SIZE.h + 1e-9
  );
}

describe("clampView", () => {
  it("크기는 1배에서 MAX_ZOOM 배 사이다", () => {
    assert.equal(clampView({ ...CENTER, zoom: 0.2 }, SIZE).zoom, 1);
    assert.equal(clampView({ ...CENTER, zoom: 99 }, SIZE).zoom, MAX_ZOOM);
  });

  it("가운데 점을 사진 밖으로 보내도 오려 낼 정사각형은 사진 안에 남는다", () => {
    for (const [cx, cy] of [
      [-500, -500],
      [99999, 99999],
      [0, 1500],
      [4000, 0],
    ]) {
      const view = clampView({ zoom: 1, cx, cy }, SIZE);
      assert.ok(inside(view), JSON.stringify(view));
    }
  });

  it("1배에서는 짧은 변이 틀에 꼭 맞아 세로로는 움직이지 않는다", () => {
    assert.equal(clampView({ zoom: 1, cx: 2000, cy: 0 }, SIZE).cy, 1500);
  });
});

describe("panView", () => {
  it("손가락을 오른쪽으로 끌면 사진이 따라가 가운데 점은 왼쪽(원본 x 감소)으로 간다", () => {
    const moved = panView(CENTER, SIZE, 30, 0, FRAME);
    // 1배에서 화면 1px 은 원본 3000/300 = 10px 이다.
    assert.equal(moved.cx, 2000 - 300);
    assert.equal(moved.cy, 1500);
  });

  it("아무리 끌어도 사진 밖으로 나가지 않는다", () => {
    let view = { ...CENTER, zoom: 2 };
    for (let i = 0; i < 50; i += 1) view = panView(view, SIZE, 400, -400, FRAME);
    assert.ok(inside(view), JSON.stringify(view));
  });
});

describe("zoomView", () => {
  it("가운데를 붙잡고 키우면 가운데 점이 그대로다", () => {
    const zoomed = zoomView(CENTER, SIZE, 2, 0, 0, FRAME);
    assert.equal(zoomed.zoom, 2);
    assert.equal(zoomed.cx, 2000);
    assert.equal(zoomed.cy, 1500);
  });

  it("붙잡은 점 아래의 원본 점이 키운 뒤에도 같은 화면 자리에 있다", () => {
    const start = { zoom: 2, cx: 2000, cy: 1500 };
    const [ax, ay] = [60, -40]; // 틀 가운데에서 오른쪽 60px, 위로 40px
    const pointAt = (view: View) => ({
      x: view.cx + (ax * Math.min(SIZE.w, SIZE.h)) / view.zoom / FRAME,
      y: view.cy + (ay * Math.min(SIZE.w, SIZE.h)) / view.zoom / FRAME,
    });

    const zoomed = zoomView(start, SIZE, 3, ax, ay, FRAME);

    const before = pointAt(start);
    const after = pointAt(zoomed);
    assert.ok(Math.abs(before.x - after.x) < 1e-6, `${before.x} ${after.x}`);
    assert.ok(Math.abs(before.y - after.y) < 1e-6, `${before.y} ${after.y}`);
  });

  it("가장자리를 붙잡고 줄여도 사진 밖이 틀에 들어오지 않는다", () => {
    const edge = clampView({ zoom: 4, cx: 0, cy: 0 }, SIZE);
    const zoomed = zoomView(edge, SIZE, 1, -150, -150, FRAME);
    assert.equal(zoomed.zoom, 1);
    assert.ok(inside(zoomed), JSON.stringify(zoomed));
  });
});
