/**
 * lib/spring.ts 의 물리 함수 경계 테스트.
 *
 * spring() 은 rAF 루프라 Node 에서 못 돌린다. 손을 뗀 순간의 판정에
 * 직접 들어가는 project/rubber 둘만 값으로 검증한다 - 이 둘이 틀리면
 * 카드가 안 넘어가거나 화면 밖으로 사라진다.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { project, rubber } from "../src/lib/spring.ts";

/* ---- project: 관성으로 더 갈 거리 ---- */

test("project: 속도 0 이면 더 안 간다", () => {
  assert.equal(project(0), 0);
});

test("project: 부호가 속도를 따라간다", () => {
  assert.ok(project(1000) > 0);
  assert.ok(project(-1000) < 0);
  assert.equal(project(-1000), -project(1000));
});

test("project: 속도에 비례한다(선형)", () => {
  // 지수 감쇠식이지만 속도에 대해서는 1차식이라, 두 배 빠르면 두 배 간다.
  assert.ok(Math.abs(project(2000) - 2 * project(1000)) < 1e-9);
});

test("project: 기본 감속률의 실제 배율은 499", () => {
  // 0.998 / (1 - 0.998) / 1000 = 0.499. 초당 1000px 이면 499px 더 간다.
  assert.ok(Math.abs(project(1000) - 499) < 1e-9);
});

test("project: 감속률을 낮추면 덜 미끄러진다", () => {
  assert.ok(project(1000, 0.9) < project(1000, 0.998));
  assert.ok(project(1000, 0.9) > 0);
});

test("project: 감속률 1 이면 0 나눗셈으로 Infinity - 호출부가 막아야 한다", () => {
  // 실제 결함은 아니다(호출부가 기본값만 쓴다). 다만 decelerationRate 를
  // 밖에서 받게 바꾸는 순간 여기가 터진다는 것을 못으로 박아둔다.
  assert.equal(project(1000, 1), Infinity);
});

test("project: 아주 큰 속도도 유한하게 남는다", () => {
  const far = project(1e9);
  assert.ok(Number.isFinite(far));
  assert.ok(far > 1e8);
});

test("project: NaN/Infinity 는 그대로 전파된다 - 호출부에서 걸러야 한다", () => {
  assert.ok(Number.isNaN(project(NaN)));
  assert.equal(project(Infinity), Infinity);
  assert.equal(project(-Infinity), -Infinity);
});

/* ---- rubber: 경계 밖 저항 ---- */

test("rubber: 안 넘어갔으면 0", () => {
  assert.equal(rubber(0, 320), 0);
});

test("rubber: 부호를 유지한다", () => {
  assert.ok(rubber(100, 320) > 0);
  assert.ok(rubber(-100, 320) < 0);
  assert.equal(rubber(-100, 320), -rubber(100, 320));
});

test("rubber: 결과는 항상 넘어간 거리보다 작다", () => {
  for (const overshoot of [1, 10, 50, 100, 500, 5000]) {
    const damped = rubber(overshoot, 320);
    assert.ok(
      damped < overshoot,
      `overshoot=${overshoot} 에서 ${damped} 가 원본보다 크다`,
    );
  }
});

test("rubber: 상한은 dimension 이다 - 주석이 말하는 dimension*constant 가 아니다", () => {
  // 극한은 (o*d*c) / (c*o) = d 다. constant 는 얼마나 빨리 뻑뻑해지는지를
  // 정할 뿐 상한에는 안 남는다. 주석(spring.ts:106)이 176 이라고 하지만
  // 실제로는 320 까지 간다.
  const width = 320;
  assert.ok(rubber(1e9, width) > width - 0.001);
  assert.ok(rubber(1e9, width) <= width);
  // constant 를 바꿔도 상한은 그대로다. 이게 constant 가 상한이 아니라는 증거.
  assert.ok(rubber(1e9, width, 0.1) > width - 0.01);
  assert.ok(rubber(1e9, width, 0.9) > width - 0.01);
});

test("rubber: 그래도 화면 밖으로는 안 나간다 - 상한이 폭과 같다", () => {
  // 카드가 안 사라지는 것 자체는 지켜진다. 상한이 폭(320)이라 카드가
  // 딱 한 장 폭만큼 밀려나고 멈춘다. 다만 주석이 약속한 여유(176)보다
  // 두 배 가까이 나가므로, 상한을 근거로 레이아웃을 잡으면 어긋난다.
  const width = 320;
  for (const overshoot of [1e3, 1e6, 1e9]) {
    assert.ok(rubber(overshoot, width) <= width);
  }
});

test("rubber: 단조증가 - 더 끌면 더 간다", () => {
  let previous = 0;
  for (const overshoot of [1, 5, 20, 80, 200, 900]) {
    const damped = rubber(overshoot, 320);
    assert.ok(damped > previous, `overshoot=${overshoot} 에서 안 늘었다`);
    previous = damped;
  }
});

test("rubber: 작은 값에서는 거의 그대로 따라온다", () => {
  // 1px 끌었는데 저항이 크면 손가락이 안 따라오는 것으로 보인다.
  assert.ok(rubber(1, 320) > 0.5);
});

test("rubber: dimension 0 이면 0 - 폭 0 컨테이너에서도 NaN 이 아니다", () => {
  // 호출부는 parentElement?.clientWidth ?? 320 을 쓰는데, 부모가 있는데
  // clientWidth 가 0(display:none 등)이면 ?? 가 안 걸러서 0 이 들어온다.
  // 그래도 분모에 constant*|overshoot| 가 남아 0/0 이 안 된다 - 카드가
  // 안 움직일 뿐 transform 에 NaN 이 안 들어간다.
  assert.equal(rubber(100, 0), 0);
  assert.equal(rubber(-100, 0), -0);
});

test("rubber: overshoot 과 dimension 이 둘 다 0 이면 NaN", () => {
  // 유일한 0/0 자리. 다만 이 조합은 "안 넘어갔다" 라 호출부가 rubber 를
  // 부르지도 않는다(blocked 가 dx>0 / dx<0 이라 dx=0 은 제외).
  assert.ok(Number.isNaN(rubber(0, 0)));
});

test("rubber: dimension 이 크면 덜 뻑뻑하다", () => {
  assert.ok(rubber(100, 1280) > rubber(100, 320));
});

/* ---- 넘김 판정: 덱이 실제로 쓰는 식 ---- */

/** StudyDeck.endDrag 의 판정을 그대로 옮긴 것. 이 식이 상식에 맞는지 본다. */
const flips = (dragX: number, velocity: number) =>
  Math.abs(dragX + project(velocity)) > 105;

test("판정: 조금 끌고 멈추면 안 넘어간다", () => {
  assert.equal(flips(-40, 0), false);
  assert.equal(flips(-90, 0), false);
  assert.equal(flips(30, 0), false);
});

test("판정: 짧고 빠르게 튕기면 넘어간다", () => {
  // 30px 만 움직였지만 초당 600px 로 던졌다. project 가 299px 을 더 준다.
  assert.equal(flips(-30, -600), true);
  assert.equal(flips(30, 600), true);
});

test("판정: 아주 느리게 밀어도 멀리 갔으면 넘어간다", () => {
  assert.equal(flips(-140, 0), true);
});

test("판정: 던진 방향이 반대면 안 넘어간다", () => {
  // 왼쪽으로 60px 끌다가 오른쪽으로 튕기며 놓았다. 되돌아와야 한다.
  assert.equal(flips(-60, 300), false);
});

test("판정: 느린 드래그(초당 100px 이하)는 관성으로 안 넘긴다", () => {
  // 손을 그냥 얹어 옮기는 속도. 50px 끌고 놓으면 제자리여야 자연스럽다.
  assert.equal(flips(-50, -100), false);
});

test("판정: 임계값 105 의 실제 속도 문턱", () => {
  // 제자리(0px)에서 놓기만 해도 초당 211px 이면 넘어간다. 손을 안 움직이고
  // 속도만 만들 수는 없어서 실전에서는 안 걸리지만, 문턱이 이 정도로
  // 낮다는 것은 기록해둔다.
  assert.equal(flips(0, 210), false);
  assert.equal(flips(0, 211), true);
});

test("판정: NaN 속도가 오면 안 넘어간다(제자리 복귀)", () => {
  // trail 이 한 점뿐이면 (last.x - first.x) 가 0 이라 velocity 는 0 이다.
  // NaN 이 만들어질 경로는 없지만, 들어와도 조용히 제자리인지 본다.
  assert.equal(flips(-200, NaN), false);
});
