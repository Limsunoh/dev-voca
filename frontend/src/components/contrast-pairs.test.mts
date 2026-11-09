/**
 * 작은 글자의 색 대비를 globals.css 의 값으로 직접 계산해 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 토큰 값 하나만 바뀌어도 눈으로는 "조금 흐려진" 정도라 안 보인다. 그래서 글자와
 * 바탕 짝을 적어 WCAG 공식으로 계산하고, 그 짝이 실제 화면에 그대로 쓰이는지
 * 그려서 본다. 값은 주석이 아니라 CSS 에서 읽는다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it, mock } from "node:test";
import { fileURLToPath } from "node:url";

mock.module("next/navigation", {
  namedExports: {
    useRouter: () => ({ push() {} }),
    useSearchParams: () => new URLSearchParams(),
  },
});

const { createElement } = await import("react");
const { renderToStaticMarkup } = await import("react-dom/server");
const { BoardRowItem } = await import("./BoardRow");
const { FilterPanel } = await import("./FilterPanel");
const { SearchInput } = await import("./SearchInput");

const HERE = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(HERE, "..", "app", "globals.css"), "utf8").replace(
  /\/\*[\s\S]*?\*\//g,
  "",
);

/* ---- 계산 ---- */

/** var() 를 끝까지 풀어 #rrggbb 를 돌려준다. */
function token(name: string): string {
  const found = new RegExp(`${name}\\s*:\\s*([^;]+);`).exec(css);
  assert.ok(found, `${name} 가 globals.css 에 없다`);
  const value = found[1].trim();
  const ref = /^var\((--[\w-]+)\)$/.exec(value);
  return ref ? token(ref[1]) : value;
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

const WHITE = "#ffffff";

/* ---- 그리기 ---- */

type El = { type: unknown; props: Record<string, unknown> };

const isElement = (node: unknown): node is El =>
  typeof node === "object" && node !== null && "type" in node && "props" in node;

function flatten(node: unknown, out: El[] = []): El[] {
  if (Array.isArray(node)) {
    for (const child of node) flatten(child, out);
  } else if (isElement(node)) {
    out.push(node);
    flatten(node.props.children, out);
  }
  return out;
}

const styleOf = (el: El) => (el.props.style ?? {}) as Record<string, string>;
const classOf = (el: El) => String(el.props.className ?? "");

function row(rank: number, isMe = false): El[] {
  return flatten(
    BoardRowItem({
      row: {
        rank,
        display_name: "철수",
        avatar: null,
        score: 100,
        entries: 3,
        is_me: isMe,
      } as never,
      kind: "weekly",
    }),
  );
}

/** 등수 칸. 폭 w-7 인 span 이다. */
function rankCell(rank: number): El {
  const cell = row(rank).find((el) => classOf(el).includes("w-7"));
  assert.ok(cell, "등수 칸이 없다");
  return cell;
}

const circleOf = (cell: El) => flatten(cell.props.children).find((el) => classOf(el).includes("rounded-full"));

/* ---- 테스트 ---- */

describe("색 대비 4.5:1", () => {
  const PAIRS: [string, () => string, () => string][] = [
    ["--coral-soft-text / --coral-soft", () => token("--coral-soft-text"), () => token("--coral-soft")],
    ["흰색 / --coral-deep", () => WHITE, () => token("--coral-deep")],
    ["--text-muted / 흰색", () => token("--text-muted"), () => WHITE],
    ["--foreground / --medal-1", () => token("--foreground"), () => token("--medal-1")],
    ["--foreground / --medal-2", () => token("--foreground"), () => token("--medal-2")],
    ["--foreground / --medal-3", () => token("--foreground"), () => token("--medal-3")],
    // 내 줄이 4위 아래면 등수가 코랄 바탕 위 --text-muted 다.
    ["--text-muted / --coral-soft", () => token("--text-muted"), () => token("--coral-soft")],
    // 내정보·이메일·일상영어의 오류 상자와 문제풀기의 정답 안내가 쓰는 짝이다.
    ["--coral-deep / --wrong-soft", () => token("--coral-deep"), () => token("--wrong-soft")],
  ];

  for (const [name, text, back] of PAIRS) {
    it(name, () => {
      const ratio = contrast(text(), back());
      assert.ok(ratio >= 4.5, `${name} 는 ${ratio.toFixed(2)}:1 이다`);
    });
  }

  it("계산식이 맞다: 흑백은 21:1", () => {
    assert.equal(Math.round(contrast("#000000", WHITE)), 21);
  });

  it("--coral-soft-text 는 --coral-deep 과 다른 값이다", () => {
    // --coral-deep 은 이 바탕에서 4.5 에 못 미쳐 따로 만든 토큰이다.
    assert.notEqual(token("--coral-soft-text"), token("--coral-deep"));
    assert.ok(contrast(token("--coral-deep"), token("--coral-soft")) < 4.5);
  });
});

describe("순위표 줄의 등수", () => {
  for (const rank of [1, 2, 3]) {
    it(`${rank}위 숫자는 잉크색이고 메달 색은 동그라미 바탕에만 쓴다`, () => {
      const cell = rankCell(rank);
      assert.equal(styleOf(cell).color, "var(--foreground)");
      const circle = circleOf(cell);
      assert.ok(circle, "동그라미가 없다");
      assert.equal(styleOf(circle).background, `var(--medal-${rank})`);
      assert.equal(circle.props.children, rank);
      assert.equal(styleOf(circle).color, undefined, "동그라미 안 글자색을 따로 주면 안 된다");
    });

    it(`${rank}위 줄 어디에도 메달 색 글자가 없다`, () => {
      for (const el of row(rank, true)) {
        assert.doesNotMatch(String(styleOf(el).color ?? ""), /medal/);
      }
    });
  }

  for (const rank of [4, 10, 20]) {
    it(`${rank}위는 동그라미 없이 숫자만 --text-muted 로 쓴다`, () => {
      const cell = rankCell(rank);
      assert.equal(circleOf(cell), undefined);
      assert.equal(cell.props.children, rank);
      assert.equal(styleOf(cell).color, "var(--text-muted)");
    });
  }

  it("상위 셋은 색 말고 크기로도 갈린다", () => {
    assert.equal(styleOf(rankCell(1)).fontSize, "var(--text-md)");
    assert.equal(styleOf(rankCell(4)).fontSize, "var(--text-sm)");
  });
});

describe("내 줄의 '나' 표시", () => {
  const me = (isMe: boolean) => row(5, isMe).find((el) => el.props.children === "나");

  it("--coral-soft-text 로 쓴다", () => {
    const mark = me(true);
    assert.ok(mark, "'나' 표시가 없다");
    assert.equal(styleOf(mark).color, "var(--coral-soft-text)");
  });

  it("내 줄이 아니면 안 그린다", () => {
    assert.equal(me(false), undefined);
  });

  it("'나' 가 얹히는 바탕이 --coral-soft 다", () => {
    const li = row(5, true).find((el) => el.type === "li") as El;
    assert.equal(styleOf(li).background, "var(--coral-soft)");
  });
});

describe("필터 배지", () => {
  const badge = (active: (string | undefined)[]) =>
    flatten(FilterPanel({ active, children: null })).find((el) =>
      classOf(el).includes("min-w-[18px]"),
    );

  it("바탕이 --coral-deep 이고 글자는 흰색 토큰이다", () => {
    const found = badge(["git"]);
    assert.ok(found, "배지가 없다");
    assert.equal(styleOf(found).background, "var(--coral-deep)");
    assert.equal(styleOf(found).color, "var(--text-on-color)");
    assert.equal(token("--text-on-color").toLowerCase(), WHITE);
  });

  it("조건이 없으면 안 그린다", () => {
    assert.equal(badge([undefined]), undefined);
  });
});

describe("검색창 안내 글자", () => {
  const html = renderToStaticMarkup(createElement(SearchInput, { basePath: "/learn/words" }));
  const input = /<input[^>]*>/.exec(html)?.[0] ?? "";

  it("입력칸 클래스에 placeholder 색이 있다", () => {
    assert.ok(
      input.split(/class="/)[1]?.split('"')[0].split(/\s+/).includes(
        "placeholder:text-[color:var(--text-muted)]",
      ),
      `입력칸: ${input}`,
    );
  });

  it("입력칸은 투명이고 그 바탕이 흰 종이다", () => {
    // 위 대비 계산의 바탕이 흰색인 근거다. 바탕이 바뀌면 계산도 바뀌어야 한다.
    assert.match(input, /bg-transparent/);
    assert.ok(token("--paper").toLowerCase() === WHITE);
    const box = /<div[^>]*style="[^"]*background:var\(--paper\)[^"]*"[^>]*>(?:(?!<\/div>)[\s\S])*<input/.exec(html);
    assert.ok(box, "입력칸을 감싼 흰 바탕이 없다");
  });
});
