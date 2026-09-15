/**
 * 판정 연출(.vx)의 CSS 계약 검증.
 *
 * 실행: cd frontend && npm test
 *
 * **형제 파일과 나눠 맡는다.** `components/reaction-overlay.test.mts` 는
 * "연출을 **어디에** 두었나"(조건 가지 밖인가, 어느 화면이 어둡게 까나)를
 * 보고, 여기는 "그 층이 **어떻게 돌다 사라지나**" 를 본다. 겹치는 검사는
 * 한쪽에만 둔다 - vx-out 이 있는지와 무대 정지점 수는 그쪽에 있다.
 *
 * **왜 CSS 를 글자로 검사하나.** 이 연출의 결함은 화면을 봐야만 보이는데
 * 이 저장소에는 브라우저를 띄우는 테스트 판이 없다. 그렇다고 아무 그물도
 * 안 두면 아래 넷은 **지워도 빌드가 통과하고 타입도 통과한다.**
 *
 *     --duration-verdict   서버의 REACTION_PAUSE_MS 와 같아야 한다. 다르면
 *                          짧은 쪽은 빈 화면을 기다리고 긴 쪽은 판정 글자
 *                          구간(74~92%)이 잘린 채 다음 문제가 뜬다
 *     bottom               TabBar 가 내보내는 --tabbar-height 와 짝이다.
 *                          한쪽만 바꾸면 탭바 있는 화면에서 무대가 탭바를 밟는다
 *     pointer-events       이 층은 화면을 꽉 채운다. 끄지 않으면 연출이 도는
 *                          1초 동안 보기 버튼이 안 눌린다
 *     vx-spot 의 배경 전환   66% 까지 바탕색, 70% 부터 판정색. 이 전환이
 *                          맞았는지 틀렸는지를 알리는 주된 신호다
 *
 * 글자 검사라 "연출이 예쁜가" 는 못 본다. 못 보는 것을 보려는 것이 아니라
 * **없어진 것을 알아채려는 것**이다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

const css = readFileSync(join(HERE, "globals.css"), "utf8");
const tabBar = readFileSync(join(HERE, "../components/TabBar.tsx"), "utf8");
const sessionPy = readFileSync(
  join(HERE, "../../../backend/apps/learning/session.py"),
  "utf8",
);

/** `여는 이름 {` 부터 짝이 맞는 `}` 까지의 알맹이. 중첩을 세어 자른다. */
function body(source: string, opener: string): string {
  const at = source.indexOf(opener);
  assert.notEqual(at, -1, `${opener} 를 못 찾았다`);
  const from = source.indexOf("{", at);
  let depth = 0;
  for (let i = from; i < source.length; i++) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(from + 1, i);
    }
  }
  throw new Error(`${opener} 의 끝을 못 찾았다`);
}

/** 키프레임 알맹이를 `정지점 → 선언` 쌍으로 쪼갠다. */
function stops(keyframes: string): { at: string; decls: string }[] {
  return [...keyframes.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    at: m[1].replace(/\s+/g, " ").trim(),
    decls: m[2],
  }));
}

describe(".vx 층", () => {
  // 앞의 줄바꿈으로 최상위 규칙만 잡는다. reduced-motion 블록 안의 `.vx` 는
  // 들여쓰기가 있어 안 걸린다.
  const vx = body(css, "\n.vx {");

  it("걷는 애니메이션이 연출과 같은 길이로 돈다", () => {
    // 짧으면 사람이 아직 서 있는데 층이 먼저 사라지고, 길면 다음 문제 위에
    // 남는다. vx-out 이 붙어 있는지 자체는 형제 파일이 본다.
    assert.match(vx, /animation-duration:\s*var\(--duration-verdict\)/);
    assert.match(vx, /animation-fill-mode:\s*both/);
  });

  it("vx-out 이 마지막에 투명해진다", () => {
    // 마지막이 opacity 0 이 아니면 이름만 붙어 있고 아무것도 안 걷힌다.
    const last = stops(body(css, "@keyframes vx-out {")).at(-1);
    assert.ok(last, "@keyframes vx-out 에 정지점이 없다");
    assert.match(last.at, /100%/);
    assert.match(last.decls, /opacity:\s*0/);
  });

  it("탭바 높이만큼 위로 올린다", () => {
    assert.match(vx, /bottom:\s*var\(--tabbar-height,\s*0px\)/);
    // 짝. TabBar 가 이 이름으로 안 내보내면 늘 기본값 0 으로 떨어져
    // 일일학습·복습에서 무대가 탭바를 밟는다.
    assert.match(tabBar, /--tabbar-height\s*:/);
  });

  it("보기 버튼을 덮지 않는다", () => {
    assert.match(vx, /pointer-events:\s*none/);
  });
});

describe("무대는 닿는 순간에 판정색으로 넘어간다", () => {
  const spot = stops(body(css, "@keyframes vx-spot {"));

  it("66% 까지 바탕색, 70% 부터 판정색", () => {
    const before = spot.find((s) => s.at.includes("66%"));
    const after = spot.find((s) => s.at.includes("70%"));
    assert.ok(before && after, "66% · 70% 정지점이 있어야 한다");
    assert.match(before.decls, /background:\s*var\(--background\)/);
    assert.match(after.decls, /background:\s*var\(--vx-color\)/);
    // 무대가 불투명해야 그 색이 보인다. 이 두 줄이 없으면 전환이 opacity
    // 0.012 에서 일어나 아무도 못 본다.
    assert.match(before.decls, /opacity:\s*1/);
    assert.match(after.decls, /opacity:\s*1/);
  });
});

describe("연출 길이는 서버와 같은 값이다", () => {
  it("선언이 한 곳뿐이다", () => {
    // 두 곳에 두면 캐스케이드에서 뒤가 이겨, 앞의 줄을 고친 사람에게
    // 아무 일도 안 일어난다.
    const declared = css.match(/--duration-verdict\s*:/g) ?? [];
    assert.equal(declared.length, 1, `선언이 ${declared.length}곳이다`);
  });

  it("서버의 REACTION_PAUSE_MS 와 같다", () => {
    // 판 모드는 답마다 이만큼 마감을 미루고 화면도 이만큼 멈춘다. 둘이
    // 다르면 차이만큼 매 문제 쌓인다.
    const inCss = css.match(/--duration-verdict\s*:\s*(\d+)ms/);
    const inPy = sessionPy.match(/^REACTION_PAUSE_MS = (\d+)$/m);
    assert.ok(inCss, "--duration-verdict 를 ms 로 적어야 짝을 맞출 수 있다");
    assert.ok(inPy, "session.REACTION_PAUSE_MS 를 못 찾았다");
    assert.equal(inCss[1], inPy[1]);
  });
});
