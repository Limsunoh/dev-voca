/**
 * 알약 탭의 띠(트랙) 바탕이 화면 바탕과 구분되고, 꺼진 탭 글자가 그 위에서
 * 읽히는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 대상은 익히기·문제풀기의 단어/문장 탭(ContentTabs)과 일상영어의 갈래·난이도·
 * 상황 탭(TalkTabRow) 이다. 띠가 --background-deep 이던 때는 크림 바탕과
 * 1.03:1 이라 띠가 안 보이고 꺼진 탭 글자만 떠 보였다.
 *
 * 칸의 포커스 테두리도 띠 위에 그려지므로 띠와 3:1 이상인지 본다.
 *
 * 띠 색은 그린 결과(nav 의 style)에서 읽고, 그 토큰을 globals.css 에서 끝까지
 * 풀어 계산한다. 토큰 이름을 테스트에 박아 두고 계산만 하면 컴포넌트가 다른
 * 토큰으로 돌아가도 초록불이다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it, mock } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import type { CSSProperties, ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

mock.module("next/navigation", {
  namedExports: {
    useRouter: () => ({ push() {} }),
    usePathname: () => "/",
  },
});

type LinkProps = {
  href: string;
  "aria-current"?: string;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
};

// 링크의 style 과 aria-current 를 그대로 넘긴다. 꺼진 칸·켜진 칸의 바탕과
// 글자색을 마크업에서 읽어야 한다.
mock.module("next/link", {
  defaultExport: (props: LinkProps) =>
    createElement(
      "a",
      {
        href: props.href,
        "aria-current": props["aria-current"],
        className: props.className,
        style: props.style,
      },
      props.children,
    ),
});

const { ContentTabs } = await import("./ContentTabs");
const { TalkKindTabs } = await import("./TalkKindTabs");
const { TalkLevelTabs } = await import("./TalkLevelTabs");
const { TalkSceneTabs } = await import("./TalkSceneTabs");

const HERE = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(HERE, "..", "app", "globals.css"), "utf8").replace(
  /\/\*[\s\S]*?\*\//g,
  "",
);

/* ---- 계산 (contrast-pairs.test.mts 와 같은 식) ---- */

/** var() 를 끝까지 풀어 #rrggbb 를 돌려준다. */
function token(name: string): string {
  const found = new RegExp(`${name}\\s*:\\s*([^;]+);`).exec(css);
  assert.ok(found, `${name} 가 globals.css 에 없다`);
  const value = found[1].trim();
  const ref = /^var\((--[\w-]+)\)$/.exec(value);
  return ref ? token(ref[1]) : value;
}

/** "var(--x)" 를 #rrggbb 로. 바탕이 var 가 아니면 계산할 수 없어 실패시킨다. */
function resolve(value: string): string {
  const ref = /^var\((--[\w-]+)\)$/.exec(value.trim());
  assert.ok(ref, `${value} 는 토큰이 아니다`);
  return token(ref[1]);
}

function luminance(hex: string): number {
  assert.match(hex, /^#[0-9a-f]{6}$/i, `${hex} 는 계산할 수 없는 값이다`);
  const [r, g, b] = [1, 3, 5].map((at) => {
    const channel = parseInt(hex.slice(at, at + 2), 16) / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/* ---- 그리기 ---- */

/** style="a:b;c:d" 를 객체로. */
function parseStyle(raw: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of raw.split(";")) {
    const at = part.indexOf(":");
    if (at > 0) out[part.slice(0, at).trim()] = part.slice(at + 1).trim();
  }
  return out;
}

type Tab = {
  active: boolean;
  style: Record<string, string>;
  className: string;
  label: string;
};
type Row = { name: string; track: Record<string, string>; tabs: Tab[] };

function draw(name: string, element: ReturnType<typeof createElement>): Row {
  const html = renderToStaticMarkup(element);
  const nav = /<nav [^>]*style="([^"]*)"[^>]*>/.exec(html);
  assert.ok(nav, `${name}: nav 가 없거나 style 이 없다`);
  const tabs = [...html.matchAll(/<a ([^>]*)>(.*?)<\/a>/g)].map((m) => ({
    active: /aria-current="page"/.test(m[1]),
    style: parseStyle(/style="([^"]*)"/.exec(m[1])?.[1] ?? ""),
    className: /class="([^"]*)"/.exec(m[1])?.[1] ?? "",
    label: m[2].replace(/<[^>]+>/g, ""),
  }));
  assert.ok(tabs.length >= 2, `${name}: 탭이 ${tabs.length}개다`);
  return { name, track: parseStyle(nav[1]), tabs };
}

const ROWS: Row[] = [
  draw("익히기 단어/문장", createElement(ContentTabs, { mode: "learn", current: "words" })),
  draw(
    "문제풀기 단어/문장",
    createElement(ContentTabs, { mode: "test", current: "sentences", warnOnLeave: true }),
  ),
  draw("일상영어 갈래", createElement(TalkKindTabs, { current: "daily", level: 0, scene: "" })),
  draw("일상영어 난이도", createElement(TalkLevelTabs, { kind: "daily", current: 2, scene: "" })),
  draw("일상영어 상황", createElement(TalkSceneTabs, { level: 0, current: "shopping" })),
];

const SCREEN = token("--background");

/** 바꾸기 전 띠 색. --background-deep 은 입력칸도 써서 값이 바뀔 수 있으니
 *  토큰에서 읽지 않고 그때 값을 적어 둔다. */
const OLD_TRACK = "#fbf3e4";

/** 포커스 테두리 색. 칸의 class(outline-focus, outline-focus-pill)에서 읽는다. */
function focusColor(className: string): string {
  const found = /(?:^|\s)focus-visible:outline-(focus(?:-[\w-]+)?)(?=\s|$)/.exec(className);
  assert.ok(found, "포커스 테두리 색이 없다");
  return token(`--${found[1]}`);
}

/* ---- 테스트 ---- */

describe("알약 탭 띠", () => {
  for (const row of ROWS) {
    describe(row.name, () => {
      it("켜진 칸이 정확히 하나다", () => {
        assert.equal(row.tabs.filter((t) => t.active).length, 1);
      });

      it("띠 바탕은 알약 토큰(--surface-pill)이다", () => {
        assert.equal(row.track.background, "var(--surface-pill)");
      });

      it("띠가 크림 화면 바탕과 1.1:1 이상 갈린다", () => {
        const ratio = contrast(resolve(row.track.background), SCREEN);
        assert.ok(ratio >= 1.1, `띠 / 화면 바탕이 ${ratio.toFixed(3)}:1 이다`);
        // 띠가 바탕보다 어두워야 '파인 홈' 으로 읽힌다. 밝으면 흰 칸과 섞인다.
        assert.ok(luminance(resolve(row.track.background)) < luminance(SCREEN));
      });

      it("꺼진 칸은 바탕 없이 --text-muted 글자이고 띠 위에서 4.5:1 이상이다", () => {
        const track = resolve(row.track.background);
        for (const tab of row.tabs.filter((t) => !t.active)) {
          // 꺼진 칸에 색을 깔면 그 색이 실제 바탕이 되어 위 계산이 틀린다.
          assert.ok(
            tab.style.background === undefined || tab.style.background === "transparent",
            `${tab.label}: 꺼진 칸 바탕이 ${tab.style.background} 다`,
          );
          assert.equal(tab.style.color, "var(--text-muted)", tab.label);
          const ratio = contrast(resolve(tab.style.color), track);
          assert.ok(ratio >= 4.5, `${tab.label}: ${ratio.toFixed(2)}:1 이다`);
        }
      });

      it("켜진 칸은 흰 종이이고 띠와 갈리며 글자는 4.5:1 이상이다", () => {
        const tab = row.tabs.find((t) => t.active);
        assert.ok(tab);
        assert.equal(tab.style.background, "var(--paper)");
        const paper = resolve(tab.style.background);
        const track = resolve(row.track.background);
        // 켜진 칸은 그림자(--lift-card)도 함께 쓴다. 색 차이만으로 갈리지 않게.
        assert.equal(tab.style["box-shadow"], "var(--lift-card)");
        const lift = contrast(paper, track);
        assert.ok(lift >= 1.15, `흰 칸 / 띠가 ${lift.toFixed(3)}:1 이다`);
        assert.ok(contrast(resolve(tab.style.color), paper) >= 4.5);
      });

      it("포커스 테두리가 띠 위에서 3:1 이상이다", () => {
        // 테두리는 칸 밖 2~4px, 즉 띠 안쪽 여백 위에 그려진다.
        const track = resolve(row.track.background);
        for (const tab of row.tabs) {
          const ratio = contrast(focusColor(tab.className), track);
          assert.ok(ratio >= 3, `${tab.label}: ${ratio.toFixed(2)}:1 이다`);
        }
      });
    });
  }

  it("다섯 줄의 띠 바탕이 모두 같다", () => {
    assert.equal(new Set(ROWS.map((r) => r.track.background)).size, 1);
  });

  it("옛 띠 색은 화면 바탕과 안 갈렸다 - 기준이 실제로 거른다", () => {
    // 위 1.1 기준이 옛 값을 거르지 못하면 이 테스트 묶음은 회귀를 못 잡는다.
    assert.ok(contrast(OLD_TRACK, SCREEN) < 1.1);
    assert.ok(contrast(token("--paper"), OLD_TRACK) < 1.15);
  });

  it("앱 공통 포커스 색은 새 띠 위에서 3:1 에 못 미친다 - 진한 코랄을 쓴 이유", () => {
    // 이게 3:1 을 넘게 되면(--focus 를 바꾸면) 탭만 따로 둘 이유가 없다.
    assert.ok(
      contrast(token("--focus"), token("--surface-pill")) < 3,
      "--focus 가 sand 위에서 3:1 을 넘었다 - --focus-pill 예외를 지울 때다",
    );
  });
});
