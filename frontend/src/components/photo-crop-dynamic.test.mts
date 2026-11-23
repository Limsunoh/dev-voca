/**
 * 사진 오려 내기 창(PhotoCropper)을 깨뜨려 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - "올리기" 는 512x512 image/jpeg File 을 onDone 으로 한 번만 넘긴다.
 *     두 번 눌러도, 누른 뒤 취소·Esc 를 눌러도 onDone 은 0번 또는 1번이다.
 *   - 못 여는 형식은 "이 사진은 열 수 없습니다. ...", 1억 픽셀을 넘으면 "사진이 너무
 *     커서 열 수 없습니다. ..." 를 onClose 로 넘긴다. 정확히 1억은 연다.
 *   - 오려 낼 정사각형은 늘 사진 안에 있다. 화면에 보이는 틀과 실제로 그리는 부분이 같다.
 *   - 확대 때 붙잡은 점이 화면의 같은 자리에 남는다.
 *   - 화살표 키는 끌기와 같은 방향이다. 만드는 중에는 끌기·키가 먹지 않는다.
 *
 * 브라우저 없이 도는 방법(profile-cards-state.test 와 같은 관용구): react 의 훅만
 * 대역으로 바꿔 상태를 렌더 사이에 이어 두고, jsx 런타임을 감싸 그려진 태그의 props
 * 를 모은 뒤 그 이벤트 핸들러를 직접 부른다. Image·canvas·URL.createObjectURL 은
 * 가짜를 넣어 사진이 언제 읽히고 언제 다 그려지는지를 테스트가 정한다.
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { beforeEach, describe, it, mock } from "node:test";
import type { ReactElement } from "react";

const require = createRequire(import.meta.url);
const realReact = require("react") as typeof import("react");
const realJsx = require("react/jsx-runtime");

// ---------------------------------------------------------------------------
// react 대역: useState·useRef 는 호출 순서로 칸을 두고, useEffect 는 모아 뒀다가
// 처음 그린 뒤 한 번 돌린다(마운트). 정리 함수는 unmount() 가 부른다.
// ---------------------------------------------------------------------------

let slots: { value: unknown }[] = [];
let cursor = 0;
let changed = false;
let refs: { current: unknown }[] = [];
let refCursor = 0;
let effects: Array<() => void | (() => void)> = [];
let cleanups: Array<() => void> = [];

function useState<T>(init: T | (() => T)) {
  const i = cursor++;
  if (!slots[i]) {
    slots[i] = { value: typeof init === "function" ? (init as () => T)() : init };
  }
  const slot = slots[i];
  const set = (next: T | ((prev: T) => T)) => {
    const value = typeof next === "function" ? (next as (p: T) => T)(slot.value as T) : next;
    if (!Object.is(value, slot.value)) {
      slot.value = value;
      changed = true;
    }
  };
  return [slot.value as T, set] as const;
}

function useRef<T>(init: T) {
  const i = refCursor++;
  if (!refs[i]) refs[i] = { current: init };
  return refs[i] as { current: T };
}

mock.module("react", {
  defaultExport: realReact,
  namedExports: {
    ...realReact,
    useState,
    useRef,
    useId: () => "id",
    useEffect(fn: () => void | (() => void)) {
      effects.push(fn);
    },
  },
});

type Host = { type: string; props: Record<string, unknown> };
let hosts: Host[] = [];
const record =
  (fn: (...args: unknown[]) => unknown) =>
  (type: unknown, props: Record<string, unknown>, key?: unknown) => {
    if (typeof type === "string") hosts.push({ type, props });
    return fn(type, props, key);
  };
mock.module("react/jsx-runtime", {
  namedExports: { ...realJsx, jsx: record(realJsx.jsx), jsxs: record(realJsx.jsxs) },
});

// ---------------------------------------------------------------------------
// 브라우저 대역
// ---------------------------------------------------------------------------

class FakeImage {
  static all: FakeImage[] = [];
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  naturalWidth = 0;
  naturalHeight = 0;
  src = "";
  constructor() {
    FakeImage.all.push(this);
  }
  /** 사진을 다 읽었다. */
  load(w: number, h: number) {
    this.naturalWidth = w;
    this.naturalHeight = h;
    this.onload?.();
  }
}

type Draw = { sx: number; sy: number; sw: number; sh: number; dw: number; dh: number };
let draws: Draw[] = [];
let canvases: { width: number; height: number }[] = [];
/** toBlob 이 아직 돌려주지 않은 콜백. 테스트가 정한 때에 부른다. */
let pendingBlobs: Array<{ cb: (b: Blob | null) => void; type: string }> = [];
let noContext = false;

const created: string[] = [];
const revoked: string[] = [];

const g = globalThis as Record<string, unknown>;
g.Image = FakeImage;
g.document = {
  createElement(tag: string) {
    assert.equal(tag, "canvas");
    const canvas = {
      width: 0,
      height: 0,
      getContext: () =>
        noContext
          ? null
          : {
              fillStyle: "",
              imageSmoothingQuality: "",
              fillRect() {},
              drawImage(
                _img: unknown,
                sx: number,
                sy: number,
                sw: number,
                sh: number,
                _dx: number,
                _dy: number,
                dw: number,
                dh: number,
              ) {
                draws.push({ sx, sy, sw, sh, dw, dh });
              },
            },
      toBlob(cb: (b: Blob | null) => void, type: string) {
        pendingBlobs.push({ cb, type });
      },
    };
    canvases.push(canvas);
    return canvas;
  },
};
URL.createObjectURL = () => {
  const url = `blob:fake/${created.length}`;
  created.push(url);
  return url;
};
URL.revokeObjectURL = (url: string) => {
  revoked.push(url);
};

const { renderToStaticMarkup } = await import("react-dom/server");
const { createElement } = realReact;
const { PhotoCropper, clampView, panView, zoomView, MAX_ZOOM } = await import("./PhotoCropper");
type View = { zoom: number; cx: number; cy: number };
type Size = { w: number; h: number };

const CANNOT_OPEN = "이 사진은 열 수 없습니다. 다른 사진을 골라주세요.";
const TOO_BIG = "사진이 너무 커서 열 수 없습니다. 다른 사진을 골라주세요.";
const FRAME = 300;

// ---------------------------------------------------------------------------
// 도구
// ---------------------------------------------------------------------------

let element: ReactElement;
let done: File[] = [];
let closed: Array<string | undefined> = [];
const dialog = { opened: 0, closedCount: 0, showModal() { this.opened++; }, close() { this.closedCount++; } };
const frameNode = {
  getBoundingClientRect: () => ({ width: FRAME, left: 0, top: 0 }),
  setPointerCapture() {},
};

/** 상태가 가라앉을 때까지 다시 그리고, ref 를 가짜 노드에 붙인다. */
function draw(): void {
  for (let pass = 0; pass < 20; pass += 1) {
    cursor = 0;
    refCursor = 0;
    changed = false;
    hosts = [];
    effects = [];
    renderToStaticMarkup(element);
    for (const h of hosts) {
      const ref = h.props.ref as { current: unknown } | undefined;
      if (!ref) continue;
      if (h.type === "dialog") ref.current = dialog;
      else if (h.type === "div") ref.current = frameNode;
      else if (h.type === "img") ref.current = { tag: "img" };
    }
    if (!changed) return;
  }
  throw new Error("렌더가 가라앉지 않는다");
}

function mount(file = new File(["x"], "big.jpg", { type: "image/jpeg" })): void {
  slots = [];
  refs = [];
  cleanups = [];
  draws = [];
  canvases = [];
  pendingBlobs = [];
  noContext = false;
  done = [];
  closed = [];
  FakeImage.all = [];
  created.length = 0;
  revoked.length = 0;
  dialog.opened = 0;
  dialog.closedCount = 0;
  element = createElement(PhotoCropper, {
    file,
    onClose: (error?: string) => closed.push(error),
    onDone: (photo: File) => done.push(photo),
  });
  draw();
  for (const fn of effects) {
    const c = fn();
    if (typeof c === "function") cleanups.push(c);
  }
  draw();
}

function unmount(): void {
  for (const c of cleanups) c();
  cleanups = [];
}

function image(): FakeImage {
  assert.equal(FakeImage.all.length, 1, "사진을 한 번만 읽어야 한다");
  return FakeImage.all[0];
}

function open(w: number, h: number): void {
  image().load(w, h);
  draw();
}

function button(text: string): Record<string, unknown> {
  const found = hosts.filter((h) => h.type === "button" && h.props.children === text);
  assert.equal(found.length, 1, `"${text}" 버튼이 하나가 아니다`);
  return found[0].props;
}

function click(text: string): void {
  (button(text).onClick as () => void)();
  draw();
}

function frame(): Record<string, unknown> {
  const found = hosts.filter((h) => h.type === "div" && h.props.role === "group");
  assert.equal(found.length, 1);
  return found[0].props;
}

function dialogProps(): Record<string, unknown> {
  return hosts.find((h) => h.type === "dialog")!.props;
}

function esc(): { prevented: boolean } {
  const ev = { prevented: false, preventDefault() { this.prevented = true; } };
  (dialogProps().onCancel as (e: unknown) => void)(ev);
  draw();
  return ev;
}

function key(name: string): void {
  (frame().onKeyDown as (e: unknown) => void)({ key: name, preventDefault() {} });
  draw();
}

function pointer(
  kind: "Down" | "Move" | "Up",
  id: number,
  x: number,
  y: number,
  extra: Record<string, unknown> = {},
): void {
  (frame()[`onPointer${kind}`] as (e: unknown) => void)({
    pointerId: id,
    clientX: x,
    clientY: y,
    pointerType: "touch",
    button: 0,
    currentTarget: frameNode,
    ...extra,
  });
  draw();
}

/** 그려진 사진의 style(%)에서 틀 가운데에 오는 원본 점과 확대 배율을 거꾸로 구한다. */
function shownView(size: Size): View {
  const img = hosts.find((h) => h.type === "img");
  assert.ok(img, "사진이 그려지지 않았다");
  const style = img.props.style as Record<string, string>;
  const pct = (v: string) => Number.parseFloat(v) / 100;
  const width = pct(style.width); // 틀 폭 대비 사진 폭
  const short = Math.min(size.w, size.h);
  const zoom = (width * short) / size.w;
  // 틀 가운데(0.5)가 사진의 어디인가.
  const cx = ((0.5 - pct(style.left)) / width) * size.w;
  const cy = ((0.5 - pct(style.top)) / (pct(style.height))) * size.h;
  return { zoom, cx, cy };
}

function slider(): Record<string, unknown> {
  return hosts.find((h) => h.type === "input" && h.props.type === "range")!.props;
}

function resolveBlobs(blob: Blob | null = new Blob(["jpg"], { type: "image/jpeg" })): void {
  const list = pendingBlobs;
  pendingBlobs = [];
  for (const p of list) p.cb(blob);
  draw();
}

const near = (a: number, b: number, eps = 1e-6) =>
  assert.ok(Math.abs(a - b) <= eps * Math.max(1, Math.abs(a), Math.abs(b)), `${a} != ${b}`);

// ---------------------------------------------------------------------------
// 사진 열기
// ---------------------------------------------------------------------------

describe("PhotoCropper: 사진을 못 열 때", () => {
  beforeEach(() => mount());

  it("창을 띄우자마자 showModal 이다", () => {
    assert.equal(dialog.opened, 1);
  });

  it("못 여는 형식 -> 열 수 없다는 안내를 한 번 넘기고 올리지 않는다", () => {
    image().onerror!();
    draw();
    assert.deepEqual(closed, [CANNOT_OPEN]);
    assert.equal(done.length, 0);
  });

  it("크기가 0 인 사진 -> 열 수 없다는 안내", () => {
    open(0, 0);
    assert.deepEqual(closed, [CANNOT_OPEN]);
  });

  it("1억 픽셀을 넘으면 너무 크다는 안내", () => {
    open(10_001, 10_000);
    assert.deepEqual(closed, [TOO_BIG]);
    assert.equal(done.length, 0);
  });

  it("정확히 1억 픽셀은 연다", () => {
    open(10_000, 10_000);
    assert.deepEqual(closed, []);
    assert.equal(button("올리기").disabled, false);
  });

  it("다 읽기 전에는 올리기 버튼이 꺼져 있고 눌러도 아무 일 없다", () => {
    assert.equal(button("올리기").disabled, true);
    click("올리기");
    assert.equal(canvases.length, 0);
    assert.equal(done.length, 0);
  });

  it("onerror 뒤에 onload 가 늦게 와도 안내는 한 번뿐이다", () => {
    const img = image();
    img.onerror!();
    img.load(4000, 3000);
    draw();
    assert.equal(closed.length, 1);
  });

  it("닫으면 만든 blob 주소를 거둔다", () => {
    open(4000, 3000);
    unmount();
    assert.equal(created.length, 1);
    assert.deepEqual(revoked, created);
  });
});

// ---------------------------------------------------------------------------
// 올리기와 중복
// ---------------------------------------------------------------------------

describe("PhotoCropper: 올리기", () => {
  beforeEach(() => {
    mount();
    open(4000, 3000);
  });

  it("512x512 image/jpeg File 을 한 번 넘기고 창을 닫는다", () => {
    click("올리기");
    assert.equal(canvases.length, 1);
    assert.equal(canvases[0].width, 512);
    assert.equal(canvases[0].height, 512);
    assert.equal(pendingBlobs[0].type, "image/jpeg");
    resolveBlobs();
    assert.equal(done.length, 1);
    assert.ok(done[0] instanceof File);
    assert.equal(done[0].type, "image/jpeg");
    assert.equal(closed.length, 0);
    assert.ok(dialog.closedCount >= 1);
  });

  it("그리는 부분은 정사각형이고 사진 안이다", () => {
    click("올리기");
    const d = draws[0];
    assert.equal(d.sw, d.sh);
    assert.equal(d.dw, 512);
    assert.ok(d.sx >= 0 && d.sy >= 0 && d.sx + d.sw <= 4000 && d.sy + d.sh <= 3000, JSON.stringify(d));
  });

  it("만드는 중에는 버튼이 꺼지고 '만드는 중' 이 된다", () => {
    click("올리기");
    assert.equal(button("만드는 중").disabled, true);
  });

  it("다시 그리기 전에 두 번 눌러도 onDone 은 한 번", () => {
    const onClick = button("올리기").onClick as () => void;
    onClick();
    onClick();
    resolveBlobs();
    assert.equal(done.length, 1);
  });

  it("올리기 뒤 그림이 끝나기 전에 취소 -> 올리지 않는다", () => {
    click("올리기");
    click("취소");
    resolveBlobs();
    assert.equal(done.length, 0);
    assert.deepEqual(closed, [undefined]);
  });

  it("올리기 뒤 Esc -> 올리지 않고, 브라우저가 닫게 두지 않는다", () => {
    click("올리기");
    const ev = esc();
    assert.equal(ev.prevented, true);
    resolveBlobs();
    assert.equal(done.length, 0);
    assert.deepEqual(closed, [undefined]);
  });

  it("Esc 뒤 올리기 핸들러가 불려도(옛 렌더) 올리지 않는다", () => {
    const onClick = button("올리기").onClick as () => void;
    esc();
    onClick();
    resolveBlobs();
    assert.equal(done.length, 0);
    assert.equal(closed.length, 1);
  });

  it("올린 뒤 취소·Esc 를 더 눌러도 onClose 가 나가지 않는다", () => {
    click("올리기");
    resolveBlobs();
    (button("취소").onClick as () => void)();
    esc();
    assert.equal(done.length, 1);
    assert.equal(closed.length, 0);
  });

  it("canvas 가 사진을 못 만들면(null) 열 수 없다는 안내, 올리지 않는다", () => {
    click("올리기");
    resolveBlobs(null);
    assert.equal(done.length, 0);
    assert.deepEqual(closed, [CANNOT_OPEN]);
  });

  it("2d 컨텍스트가 없으면 열 수 없다는 안내", () => {
    noContext = true;
    click("올리기");
    assert.deepEqual(closed, [CANNOT_OPEN]);
    assert.equal(done.length, 0);
  });

  it("보이는 틀과 실제로 그리는 부분이 같다(옮기고 키운 뒤)", () => {
    (slider().onChange as (e: unknown) => void)({ currentTarget: { value: "2.5" } });
    draw();
    pointer("Down", 1, 100, 100);
    pointer("Move", 1, 160, 70);
    pointer("Up", 1, 160, 70);
    const v = shownView({ w: 4000, h: 3000 });
    click("올리기");
    const d = draws[0];
    near(d.sw, 3000 / v.zoom);
    near(d.sx + d.sw / 2, v.cx);
    near(d.sy + d.sh / 2, v.cy);
  });
});

// ---------------------------------------------------------------------------
// 끌기·키·두 손가락
// ---------------------------------------------------------------------------

describe("PhotoCropper: 옮기기", () => {
  const LAND = { w: 4000, h: 3000 };
  const PORT = { w: 3000, h: 4000 };

  it("오른쪽으로 끌면 사진이 오른쪽으로 간다(틀 가운데의 원본 점이 왼쪽으로)", () => {
    mount();
    open(LAND.w, LAND.h);
    const before = shownView(LAND);
    pointer("Down", 1, 100, 100);
    pointer("Move", 1, 130, 100);
    assert.ok(shownView(LAND).cx < before.cx);
  });

  it("오른쪽 화살표는 오른쪽으로 끈 것과 같다", () => {
    mount();
    open(LAND.w, LAND.h);
    key("ArrowRight");
    const byKey = shownView(LAND);
    mount();
    open(LAND.w, LAND.h);
    pointer("Down", 1, 100, 100);
    pointer("Move", 1, 112, 100);
    const byDrag = shownView(LAND);
    near(byKey.cx, byDrag.cx);
    assert.ok(byKey.cx < LAND.w / 2);
  });

  it("왼쪽·위·아래 화살표도 끌기와 같은 방향", () => {
    mount();
    open(LAND.w, LAND.h);
    key("ArrowLeft");
    assert.ok(shownView(LAND).cx > LAND.w / 2);

    mount();
    open(PORT.w, PORT.h);
    key("ArrowDown");
    const down = shownView(PORT).cy;
    assert.ok(down < PORT.h / 2, "아래 화살표 -> 사진이 아래로 -> 가운데 점은 위로");
    key("ArrowUp");
    key("ArrowUp");
    assert.ok(shownView(PORT).cy > PORT.h / 2);
  });

  it("상관없는 키는 아무것도 안 바꾼다", () => {
    mount();
    open(LAND.w, LAND.h);
    const before = shownView(LAND);
    key("Enter");
    key("a");
    assert.deepEqual(shownView(LAND), before);
  });

  it("만드는 중에는 끌기도 키도 먹지 않는다", () => {
    mount();
    open(LAND.w, LAND.h);
    click("올리기");
    const before = shownView(LAND);
    key("ArrowRight");
    pointer("Down", 1, 100, 100);
    pointer("Move", 1, 200, 100);
    assert.deepEqual(shownView(LAND), before);
  });

  it("마우스 오른쪽 단추로는 끌기가 시작되지 않는다", () => {
    mount();
    open(LAND.w, LAND.h);
    const before = shownView(LAND);
    pointer("Down", 1, 100, 100, { pointerType: "mouse", button: 2 });
    pointer("Move", 1, 200, 100, { pointerType: "mouse", button: 2 });
    assert.deepEqual(shownView(LAND), before);
  });

  it("두 손가락을 벌리면 커지고, 두 손가락 가운데 아래의 원본 점이 그 자리에 남는다", () => {
    mount();
    open(LAND.w, LAND.h);
    const short = Math.min(LAND.w, LAND.h);
    /** 틀 왼쪽 위에서 x px 인 화면 점 아래의 원본 x 좌표. */
    const under = (v: View, x: number) => v.cx + (x - FRAME / 2) * (short / v.zoom / FRAME);
    pointer("Down", 1, 170, 150);
    pointer("Down", 2, 190, 150);
    const start = shownView(LAND);
    // 한 손가락씩 움직인다. 움직일 때마다 새 가운데 점 아래의 원본 점이 그대로여야 한다.
    const steps: Array<[number, number, number]> = [
      [1, 160, 175], // 1번을 160 으로: 거리 30, 가운데 175
      [2, 200, 180], // 2번을 200 으로: 거리 40, 가운데 180
    ];
    for (const [id, x, mid] of steps) {
      const before = shownView(LAND);
      pointer("Move", id, x, 150);
      const after = shownView(LAND);
      assert.ok(after.zoom > before.zoom);
      near(under(before, mid), under(after, mid));
    }
    near(shownView(LAND).zoom, 2 * start.zoom);

    // 손가락 하나를 떼면 남은 손가락은 끌기로 돌아간다(튀지 않는다).
    pointer("Up", 1, 160, 150);
    const lifted = shownView(LAND);
    pointer("Move", 2, 205, 150);
    const panned = shownView(LAND);
    near(panned.zoom, lifted.zoom);
    near(panned.cx, lifted.cx - 5 * (short / lifted.zoom / FRAME));
  });

  it("막대를 끝까지 올려도 MAX_ZOOM 에서 멈추고 틀은 사진 안이다", () => {
    mount();
    open(LAND.w, LAND.h);
    (slider().onChange as (e: unknown) => void)({ currentTarget: { value: "99" } });
    draw();
    const v = shownView(LAND);
    near(v.zoom, MAX_ZOOM);
    assert.equal(slider().max, MAX_ZOOM);
    click("올리기");
    const d = draws[0];
    assert.ok(d.sx >= 0 && d.sx + d.sw <= LAND.w + 1e-6);
  });
});

// ---------------------------------------------------------------------------
// 계산 함수: 무작위 표본(씨앗 고정)으로 불변식을 본다
// ---------------------------------------------------------------------------

/** 씨앗을 고정한 난수. 돌릴 때마다 같은 표본이 나와 흔들리지 않는다. */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}

const SIZES: Size[] = [
  { w: 4000, h: 3000 },
  { w: 3000, h: 4000 },
  { w: 1, h: 1 },
  { w: 1, h: 10_000 },
  { w: 10_000, h: 3 },
  { w: 512, h: 512 },
  { w: 7, h: 13 },
];

function assertInside(v: View, size: Size): void {
  const half = Math.min(size.w, size.h) / v.zoom / 2;
  const eps = 1e-9 * Math.max(size.w, size.h);
  assert.ok(v.zoom >= 1 && v.zoom <= MAX_ZOOM, `zoom ${v.zoom}`);
  assert.ok(v.cx - half >= -eps && v.cx + half <= size.w + eps, `cx ${v.cx} half ${half} w ${size.w}`);
  assert.ok(v.cy - half >= -eps && v.cy + half <= size.h + eps, `cy ${v.cy} half ${half} h ${size.h}`);
}

describe("clampView·panView·zoomView: 틀은 늘 사진 안", () => {
  it("아무 값이나 넣어도 clampView 결과는 사진 안이고, 두 번 해도 같다", () => {
    const r = rng(1);
    for (const size of SIZES) {
      for (let i = 0; i < 500; i++) {
        const v = {
          zoom: r() * 10 - 3,
          cx: (r() - 0.5) * size.w * 6,
          cy: (r() - 0.5) * size.h * 6,
        };
        const c = clampView(v, size);
        assertInside(c, size);
        assert.deepEqual(clampView(c, size), c);
      }
    }
  });

  it("끌기를 아무리 이어도 사진 안이고, 끈 방향과 반대로 가운데 점이 움직인다", () => {
    const r = rng(2);
    for (const size of SIZES) {
      let v = clampView({ zoom: 1 + r() * 3, cx: size.w / 2, cy: size.h / 2 }, size);
      for (let i = 0; i < 300; i++) {
        const dx = (r() - 0.5) * 2000;
        const dy = (r() - 0.5) * 2000;
        const next = panView(v, size, dx, dy, FRAME);
        assertInside(next, size);
        if (dx > 0) assert.ok(next.cx <= v.cx + 1e-9);
        if (dx < 0) assert.ok(next.cx >= v.cx - 1e-9);
        if (dy > 0) assert.ok(next.cy <= v.cy + 1e-9);
        v = next;
      }
    }
  });

  it("확대·축소를 이어도 사진 안이다", () => {
    const r = rng(3);
    for (const size of SIZES) {
      let v = clampView({ zoom: 1, cx: size.w / 2, cy: size.h / 2 }, size);
      for (let i = 0; i < 300; i++) {
        v = zoomView(v, size, r() * 8 - 2, (r() - 0.5) * FRAME * 3, (r() - 0.5) * FRAME * 3, FRAME);
        assertInside(v, size);
      }
    }
  });

  it("가장자리에 안 걸리면 붙잡은 점 아래의 원본 점이 그대로다", () => {
    const r = rng(4);
    const size = { w: 4000, h: 3000 };
    let checked = 0;
    for (let i = 0; i < 2000; i++) {
      const v = clampView({ zoom: 1 + r() * 3, cx: r() * size.w, cy: r() * size.h }, size);
      const zoom = 1 + r() * 3;
      const ax = (r() - 0.5) * FRAME;
      const ay = (r() - 0.5) * FRAME;
      const next = zoomView(v, size, zoom, ax, ay, FRAME);
      // 가장자리에 걸렸는지: 묶지 않은 값과 같으면 안 걸린 것이다.
      const s0 = 3000 / v.zoom / FRAME;
      const s1 = 3000 / next.zoom / FRAME;
      const free = { zoom, cx: v.cx + ax * (s0 - s1), cy: v.cy + ay * (s0 - s1) };
      if (Math.abs(free.cx - next.cx) > 1e-9 || Math.abs(free.cy - next.cy) > 1e-9) continue;
      near(v.cx + ax * s0, next.cx + ax * s1);
      near(v.cy + ay * s0, next.cy + ay * s1);
      checked++;
    }
    assert.ok(checked > 500, `걸리지 않은 표본이 너무 적다: ${checked}`);
  });

  it("같은 배율로 zoomView 하면 아무것도 안 바뀐다", () => {
    const size = { w: 4000, h: 3000 };
    const v = clampView({ zoom: 2, cx: 1500, cy: 1200 }, size);
    assert.deepEqual(zoomView(v, size, 2, 80, -40, FRAME), v);
  });

  it("확대 끝(MAX_ZOOM)에서 더 키우면 가운데가 밀리지 않는다", () => {
    const size = { w: 4000, h: 3000 };
    const v = clampView({ zoom: MAX_ZOOM, cx: 2000, cy: 1500 }, size);
    assert.deepEqual(zoomView(v, size, MAX_ZOOM * 3, 120, 120, FRAME), v);
  });
});
