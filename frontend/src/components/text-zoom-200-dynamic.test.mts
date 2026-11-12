/**
 * 폰 글자 크기 200% 대응(계정 삭제 창, 필터 칩, 분류 칩, 순위표 탭, 쪽 넘기기)이
 * 다른 상태·다른 경로에서도 지켜지는지 본다. text-zoom-200-rest.test.mts 는
 * 한 가지 상태만 그려 클래스를 보는데, 여기서는 그 상태를 넓힌다.
 *
 * 실행: cd frontend && npm test
 *
 * - 모서리 반지름이 "한 줄 높이의 절반" 인지를 Tailwind 테마 값에서 직접 계산한다.
 *   padding 이나 글자 크기만 바꾸고 반지름을 안 고치면 여기서 빨개진다.
 * - 같은 성질을 다투는 클래스(rounded-full 과 rounded-[..], nowrap 과 normal)가
 *   한 요소에 같이 붙지 않는지 본다. 둘이 같이 붙으면 이기는 쪽은 클래스 순서가
 *   아니라 생성된 CSS 순서로 정해져서 눈으로 읽은 것과 다르게 그려진다(850e995).
 * - 쪽 넘기기는 1쪽·2쪽·가운데·끝 앞·끝·개수 없음 여섯 경우 모두 양옆 칸을
 *   그린다. 빈 칸을 안 그리면 flex 에서 쪽수가 가운데에서 밀려난다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DeleteDialog } from "../app/profile/DeleteAccount";
import { BOARD_KINDS, type BoardRow } from "../lib/api/leaderboards";
import { FilterChip } from "./FilterChip";
import { LeaveConfirm } from "./LeaveConfirm";
import { Leaderboard } from "./Leaderboard";
import { CategoryChip, DifficultyBadge, ExamBadge } from "./MetaBadge";
import { Pagination } from "./Pagination";

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

type Html = string;
const render = (el: Parameters<typeof renderToStaticMarkup>[0]): Html => renderToStaticMarkup(el);

/** 태그의 class 목록을 순서대로 꺼낸다. */
const classesOf = (html: Html, tag: string) =>
  [...html.matchAll(new RegExp(`<${tag} [^>]*class="([^"]*)"`, "g"))].map((m) =>
    m[1].split(/\s+/),
  );

// ---- Tailwind 테마 값(빌드가 실제로 쓰는 값)을 읽는다 ----

const themeCss =
  readFileSync(require.resolve("tailwindcss/theme.css"), "utf8") +
  // 프로젝트 값이 뒤에 와서 같은 이름이면 이긴다.
  readFileSync(join(HERE, "../app/globals.css"), "utf8");

/** "--name: 값;" 의 마지막 정의를 rem 숫자로. calc(a / b) 도 푼다. */
function themeNumber(name: string): number {
  const all = [...themeCss.matchAll(new RegExp(`${name}:\\s*([^;]+);`, "g"))];
  assert.ok(all.length, `${name} 정의를 못 찾았다`);
  const raw = all.at(-1)![1].trim();
  const calc = raw.match(/^calc\(\s*([\d.]+)\s*\/\s*([\d.]+)\s*\)$/);
  if (calc) return Number(calc[1]) / Number(calc[2]);
  const rem = raw.match(/^([\d.]+)rem$/);
  assert.ok(rem, `${name} 값을 못 읽었다: ${raw}`);
  return Number(rem[1]);
}

/** 클래스에서 한 줄짜리 칩의 높이(rem)를 계산한다: 위아래 padding + 한 줄. */
function oneLineHeightRem(cls: string[]): number {
  const py = cls.map((c) => c.match(/^py-([\d.]+)$/)?.[1]).find(Boolean);
  const size = cls.map((c) => c.match(/^text-(xs|sm|base)$/)?.[1]).find(Boolean);
  assert.ok(py && size, `py-N 이나 text-* 가 없다: ${cls.join(" ")}`);
  const spacing = themeNumber("--spacing");
  const fontSize = themeNumber(`--text-${size}`);
  const leading = themeNumber(`--text-${size}--line-height`);
  return Number(py) * spacing * 2 + fontSize * leading;
}

function radiusRem(cls: string[]): number {
  const r = cls.map((c) => c.match(/^rounded-\[([\d.]+)rem\]$/)?.[1]).filter(Boolean);
  assert.equal(r.length, 1, `rounded-[Nrem] 이 하나여야 한다: ${cls.join(" ")}`);
  return Number(r[0]);
}

/** 같은 성질을 정하는 클래스가 둘 이상 붙었는지. */
function assertNoConflict(cls: string[]) {
  const groups: Record<string, RegExp> = {
    모서리: /^rounded(-|$)(?!(t|b|l|r|s|e|tl|tr|bl|br|ss|se|es|ee)-)/,
    "공백 처리": /^whitespace-/,
    "글자 줄바꿈": /^text-(wrap|nowrap|balance|pretty)$/,
    "flex 기본 폭": /^(flex-(1|auto|initial|none|\[.*\])|basis-)/,
  };
  for (const [what, re] of Object.entries(groups)) {
    const hit = cls.filter((c) => re.test(c));
    assert.ok(hit.length <= 1, `${what} 클래스가 둘 이상이다(${hit.join(", ")}): ${cls.join(" ")}`);
  }
}

/** 줄을 바꿔야 하는 칩에 붙으면 안 되는 것. 하나라도 있으면 200% 에서 화면을 넓힌다. */
const PINS_ONE_LINE = ["whitespace-nowrap", "whitespace-pre", "text-nowrap", "truncate", "shrink-0", "w-max", "min-w-max"];

const LONG = "CS 기초(Computer Science)";

// ---- 칩 ----

describe("필터 칩: 켜짐·꺼짐 어느 쪽이든 줄을 바꿀 수 있다", () => {
  const chips = [false, true].map((active) => {
    const props: Parameters<typeof FilterChip>[0] = { href: "/x", active, children: LONG };
    return classesOf(render(createElement(FilterChip, props)), "a")[0];
  });

  it("켜진 칩과 꺼진 칩의 클래스가 같다 - 모양이 갈리면 나란히 선 칩 높이가 어긋난다", () => {
    assert.deepEqual(chips[1], chips[0]);
  });

  it("한 줄로 묶는 클래스가 없다", () => {
    for (const cls of chips) {
      for (const pin of PINS_ONE_LINE) assert.ok(!cls.includes(pin), `${pin}: ${cls.join(" ")}`);
    }
  });

  it("같은 성질을 다투는 클래스가 없다", () => {
    for (const cls of chips) assertNoConflict(cls);
  });

  it("모서리 반지름이 테마 값으로 계산한 한 줄 높이의 절반이다", () => {
    for (const cls of chips) assert.equal(radiusRem(cls), oneLineHeightRem(cls) / 2, cls.join(" "));
  });
});

describe("분류 칩: 링크든 아니든, 어느 화면에서 부르든 줄을 바꿀 수 있다", () => {
  const plain = classesOf(render(createElement(CategoryChip, { label: LONG })), "span")[0];
  const link = classesOf(render(createElement(CategoryChip, { label: LONG, href: "/learn/words?category=cs" })), "a")[0];

  it("한 줄로 묶는 클래스가 없다", () => {
    for (const cls of [plain, link]) {
      for (const pin of PINS_ONE_LINE) assert.ok(!cls.includes(pin), `${pin}: ${cls.join(" ")}`);
    }
  });

  it("같은 성질을 다투는 클래스가 없다(rounded-full 이 남아 있으면 CSS 순서로 알약이 이길 수 있다)", () => {
    for (const cls of [plain, link]) assertNoConflict(cls);
  });

  it("모서리 반지름이 테마 값으로 계산한 한 줄 높이의 절반이다", () => {
    for (const cls of [plain, link]) assert.equal(radiusRem(cls), oneLineHeightRem(cls) / 2, cls.join(" "));
  });

  it("빈 라벨이면 아무것도 그리지 않는다(빈 알약 방지는 그대로다)", () => {
    assert.equal(render(createElement(CategoryChip, { label: "" })), "");
  });
});

describe("난이도·정처기 배지: 보통 크기의 한 줄 알약 그대로다", () => {
  const badges = [
    ...[1, 2, 3, 9].map((level) => render(createElement(DifficultyBadge, { level, label: "보통" }))),
    render(createElement(ExamBadge, { subjectLabel: "3과목 데이터베이스 구축" })),
    render(createElement(ExamBadge, { subjectLabel: "" })),
  ].map((html) => classesOf(html, "span")[0]);

  it("알약 모서리·한 줄·안 줄어듦이 다 있고 다투는 클래스가 없다", () => {
    for (const cls of badges) {
      for (const need of ["rounded-full", "whitespace-nowrap", "shrink-0"]) {
        assert.ok(cls.includes(need), `${need} 없음: ${cls.join(" ")}`);
      }
      assertNoConflict(cls);
    }
  });

  it("분류 칩과 높이가 같다(같은 py·text 크기) - 한 카드에 나란히 서도 어긋나지 않는다", () => {
    const chip = classesOf(render(createElement(CategoryChip, { label: "Git" })), "span")[0];
    for (const cls of badges) assert.equal(oneLineHeightRem(cls), oneLineHeightRem(chip));
  });
});

// ---- 계정 삭제 창 ----

describe("계정 삭제 창: 비밀번호 계정과 구글 계정 모두 확인 창과 같은 틀이다", () => {
  const draw = (hasPassword: boolean) =>
    render(
      createElement(DeleteDialog, {
        action: async () => ({}),
        hasPassword,
        email: "a-very-long-address-for-zoom@example.com",
        onClose: () => {},
      }),
    );
  const leave = render(
    createElement(LeaveConfirm, {
      openRef: { current: null },
      title: "t",
      detail: "d",
      confirmLabel: "나가기",
      onConfirm: () => {},
    }),
  );

  for (const hasPassword of [true, false]) {
    const html = draw(hasPassword);
    const label = hasPassword ? "비밀번호 계정" : "구글 계정(이메일 확인)";

    it(`${label}: dialog 클래스 전체가 확인 창과 같다(폭·여백·위치)`, () => {
      assert.deepEqual(classesOf(html, "dialog")[0], classesOf(leave, "dialog")[0]);
    });

    it(`${label}: 버튼 둘의 클래스가 서로 같고 flex-1 이 남지 않았다`, () => {
      const [cancel, submit] = classesOf(html, "button");
      const strip = (cls: string[]) => cls.filter((c) => !c.startsWith("disabled:"));
      assert.deepEqual(strip(cancel), strip(submit));
      assert.ok(!cancel.includes("flex-1"), cancel.join(" "));
      assertNoConflict(cancel);
      // 확인 창 버튼과 disabled: 만 빼고 같다.
      assert.deepEqual(strip(cancel), classesOf(leave, "button")[0]);
    });

    it(`${label}: 쌓이면 취소가 위에 온다(DOM 에서 취소가 먼저)`, () => {
      const order = [...html.matchAll(/<button [^>]*>([^<]*)<\/button>/g)].map((m) => m[1]);
      assert.deepEqual(order, ["취소", "삭제"]);
    });
  }

  it("구글 계정의 이메일 라벨은 아무 데서나 꺾일 수 있다 - 긴 주소가 180px 창을 넘지 않게", () => {
    const html = draw(false);
    const labelCls = classesOf(html, "label")[0];
    assert.ok(labelCls.includes("[overflow-wrap:anywhere]"), labelCls.join(" "));
  });
});

// ---- 순위표 탭 ----

describe("순위표 탭 줄: 세 종류 모두, 손님이든 회원이든 줄을 바꾼다", () => {
  const row: BoardRow = {
    rank: 1,
    display_name: "아주아주긴이름을가진사용자",
    avatar: { type: "preset", key: "a1" },
    score: 1234,
    entries: 5,
    is_me: true,
  };
  for (const kind of BOARD_KINDS) {
    for (const isGuest of [false, true]) {
      for (const rows of [[], [row]] as BoardRow[][]) {
        const name = `${kind} ${isGuest ? "손님" : "회원"} ${rows.length ? "기록 있음" : "빈 표"}`;
        it(name, () => {
          const html = render(
            createElement(Leaderboard, {
              board: { kind, rows, me: null },
              isGuest,
            }),
          );
          const nav = html.match(/<nav aria-label="순위표 종류" class="([^"]*)"/)?.[1].split(/\s+/);
          assert.ok(nav?.includes("flex-wrap"), nav?.join(" "));
          const tabRow = html.match(/<nav aria-label="순위표 종류"[\s\S]*?<\/nav>/)?.[0] ?? "";
          const tabs = classesOf(tabRow, "a");
          assert.equal(tabs.length, BOARD_KINDS.length);
          for (const cls of tabs) assertNoConflict(cls);
        });
      }
    }
  }
});

// ---- 쪽 넘기기 ----

describe("쪽 넘기기: 어느 쪽에 있든 양옆 칸과 쪽수 셋이 같은 순서로 선다", () => {
  const COUNT = 1045;
  const SIZE = 20;
  const LAST = Math.ceil(COUNT / SIZE);
  const cases: [string, number, boolean, boolean, number | undefined][] = [
    ["1쪽", 1, false, true, COUNT],
    ["2쪽", 2, true, true, COUNT],
    ["가운데 쪽", 27, true, true, COUNT],
    ["끝 앞 쪽", LAST - 1, true, true, COUNT],
    ["끝 쪽", LAST, true, false, COUNT],
    ["개수를 안 넘기는 화면", 3, true, true, undefined],
  ];

  /** nav 바로 아래 자식만 꺼낸다(태그와 class). */
  const children = (html: Html) => {
    const inner = html.match(/<nav aria-label="페이지 이동"[^>]*>([\s\S]*)<\/nav>/)?.[1] ?? "";
    const out: { tag: string; cls: string[] }[] = [];
    let depth = 0;
    for (const m of inner.matchAll(/<(\/?)(div|span|a)\b([^>]*)>/g)) {
      if (m[1]) { depth--; continue; }
      if (depth === 0) out.push({ tag: m[2], cls: (m[3].match(/class="([^"]*)"/)?.[1] ?? "").split(/\s+/) });
      depth++;
    }
    return out;
  };

  for (const [name, currentPage, hasPrevious, hasNext, count] of cases) {
    it(name, () => {
      const html = render(
        createElement(Pagination, {
          basePath: "/learn/words",
          filters: {},
          currentPage,
          hasPrevious,
          hasNext,
          count,
          pageLength: SIZE,
        }),
      );
      const navCls = html.match(/<nav aria-label="페이지 이동" class="([^"]*)"/)?.[1].split(/\s+/) ?? [];
      assert.ok(!navCls.some((c) => c.startsWith("grid")), navCls.join(" "));
      assert.ok(navCls.includes("flex-wrap"), navCls.join(" "));

      const kids = children(html);
      // 빈 칸도 그려야 쪽수가 가운데에 남는다(1쪽은 왼쪽, 끝 쪽은 오른쪽이 빈다).
      assert.deepEqual(kids.map((k) => k.tag), ["div", "span", "div"], html);
      for (const side of [kids[0], kids[2]]) assert.ok(side.cls.includes("flex-1"), side.cls.join(" "));
      // 좁을 때 쪽수가 첫 줄로 올라가는 세 클래스가 모든 경우에 붙는다.
      for (const need of ["max-[20rem]:order-first", "max-[20rem]:basis-full", "max-[20rem]:text-center"]) {
        assert.ok(kids[1].cls.includes(need), `${need} 없음: ${kids[1].cls.join(" ")}`);
      }
      assert.ok(kids[1].cls.includes("whitespace-nowrap"), kids[1].cls.join(" "));
    });
  }
});
