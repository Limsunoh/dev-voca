/**
 * 폰 글자 크기 200% 에서 깨지던 세 곳(아래 탭바, 일상영어 탭 세 줄, 확인 창)의
 * 구조 규칙을 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 글자 크기 200% 면 Chrome 이 페이지를 확대해 360폭 폰이 180px 폭처럼
 * 그려진다. 실제 폭은 브라우저로만 잴 수 있어서, 여기서는 그 폭에서 버티게
 * 해 주는 클래스가 빠지지 않았는지와, 보통 크기(360폭)에서 모양이 바뀌지
 * 않는다는 계산을 본다. 숫자는 클래스 문자열에서 읽어 직접 계산한다 - 구현이
 * 쓰는 값을 다시 import 해서 기대값을 만들면 둘이 같이 틀려도 초록불이다.
 */
import assert from "node:assert/strict";
import { describe, it, mock } from "node:test";
import { createElement } from "react";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

mock.module("next/navigation", {
  namedExports: { usePathname: () => "/talk" },
});

mock.module("next/link", {
  defaultExport: (props: {
    href: string;
    className?: string;
    style?: Record<string, string>;
    children?: ReactNode;
  }) =>
    createElement(
      "a",
      { href: props.href, className: props.className, style: props.style },
      props.children,
    ),
});

const { TabBar } = await import("./TabBar");
const { TalkKindTabs, TalkTabRow } = await import("./TalkKindTabs");
const { TalkLevelTabs } = await import("./TalkLevelTabs");
const { TalkSceneTabs } = await import("./TalkSceneTabs");
const { LeaveConfirm } = await import("./LeaveConfirm");

const classesOf = (html: string, tag: string) =>
  [...html.matchAll(new RegExp(`<${tag} [^>]*class="([^"]*)"`, "g"))].map((m) =>
    m[1].split(/\s+/),
  );

describe("탭바: 다섯 칸 최소 폭 합이 탭 줄을 넘지 않는다", () => {
  const html = renderToStaticMarkup(createElement(TabBar));
  const items = classesOf(html, "li");

  it("칸마다 44px 바닥과 탭 줄 비율 상한을 같이 건다", () => {
    assert.ok(items.length >= 5, `탭이 ${items.length}개`);
    for (const cls of items) {
      const min = cls.find((c) => c.startsWith("min-w-"));
      // 비율 상한이 빠져 min-w-[44px] 로 돌아가면 180px 폭에서 5 x 44 = 220px 라
      // 내정보 칸이 화면 밖으로 밀린다.
      assert.match(min ?? "", /^min-w-\[min\(44px,\d+(\.\d+)?%\)\]$/, cls.join(" "));
    }
  });

  it("칸 수 x 비율 상한 <= 100% (탭이 늘면 상한도 같이 줄여야 한다)", () => {
    const pct = items.map((cls) =>
      Number(cls.find((c) => c.startsWith("min-w-"))!.match(/,(\d+(?:\.\d+)?)%/)![1]),
    );
    const total = pct.reduce((a, b) => a + b, 0);
    assert.ok(total <= 100, `칸 ${items.length}개의 최소 폭 합이 ${total}%`);
  });

  it("보통 크기 360폭에서는 비율 상한이 44px 보다 커서 칸 바닥이 그대로 44px 이다", () => {
    // ul 은 max-w-md(448px) 이고 360폭에서는 화면 폭 그대로다.
    for (const cls of items) {
      const p = Number(cls.find((c) => c.startsWith("min-w-"))!.match(/,(\d+(?:\.\d+)?)%/)![1]);
      assert.ok((360 * p) / 100 >= 44, `360 x ${p}% = ${(360 * p) / 100}px < 44px`);
    }
  });

  it("라벨은 음절 사이에서 꺾고([word-break:normal]) 줄 길이를 고른다(text-balance) - 링크와 준비 중 칸 모두", () => {
    // 둘 중 하나만 있으면 비상 꺾기가 끝 글자에서 잘라 "문제풀/기" 가 된다.
    // break-normal 은 overflow-wrap 안전망까지 꺼서 쓰지 않는다.
    const cells = [...classesOf(html, "a"), ...classesOf(html, "span").filter((c) => c.includes("text-balance"))];
    assert.ok(cells.length >= 5, `칸 ${cells.length}개`);
    for (const cls of cells) {
      for (const need of ["[word-break:normal]", "text-balance", "text-center"]) {
        assert.ok(cls.includes(need), `${need} 없음: ${cls.join(" ")}`);
      }
      assert.ok(!cls.includes("break-normal"), `break-normal 이 안전망을 끈다: ${cls.join(" ")}`);
    }
  });
});

describe("일상영어 탭 세 줄: 폭이 모자라면 줄을 바꾼다", () => {
  const navOf = (html: string) => {
    const m = html.match(/<nav [^>]*class="([^"]*)"[^>]*style="([^"]*)"/);
    assert.ok(m, "nav 를 못 찾았다");
    return { cls: m[1].split(/\s+/), style: m[2] };
  };
  const kind = navOf(renderToStaticMarkup(createElement(TalkKindTabs, { current: "daily", level: 0, scene: "" })));
  const level = navOf(renderToStaticMarkup(createElement(TalkLevelTabs, { kind: "daily", current: 0, scene: "" })));
  const scene = navOf(renderToStaticMarkup(createElement(TalkSceneTabs, { level: 0, current: "" })));

  it("세 줄 모두 글자 길이만큼(inline-flex)이되 화면 폭을 안 넘고(max-w-full) 줄을 바꾼다", () => {
    for (const [name, nav] of [["갈래", kind], ["난이도", level], ["상황", scene]] as const) {
      // flex-wrap 이 없으면 칸이 눌려 "어려움" 이 한 글자씩 꺾이고 화면 밖으로
      // 넘친다. 세 줄이 같은 모양이어야 위아래로 붙어 섰을 때 어긋나지 않는다.
      for (const need of ["inline-flex", "max-w-full", "flex-wrap"]) {
        assert.ok(nav.cls.includes(need), `${name}: ${need} 없음 (${nav.cls.join(" ")})`);
      }
      // flex 와 inline-flex 가 같이 있으면 어느 쪽이 이길지 CSS 순서에 달린다.
      assert.ok(!nav.cls.includes("flex"), `${name}: flex 와 inline-flex 가 같이 있다`);
    }
  });

  it("세 줄 모서리가 같은 값(한 줄 높이의 절반)이다 - 알약 9999px 이면 두 줄일 때 양 끝이 부푼다", () => {
    for (const nav of [kind, level, scene]) {
      assert.match(nav.style, /border-radius:calc\(var\(--hit-floor\) \/ 2 \+ 0\.25rem\)/, nav.style);
    }
  });

  it("어느 탭이 부르든 TalkTabRow 는 줄을 바꾼다", () => {
    const html = renderToStaticMarkup(
      createElement(TalkTabRow, {
        label: "시험",
        items: [{ key: 1, href: "/x", label: "어려움", active: true }],
      }),
    );
    assert.ok(navOf(html).cls.includes("flex-wrap"));
  });
});

describe("확인 창: 좁으면 버튼을 쌓고 넓으면 같은 폭으로 나란히 둔다", () => {
  const render = (cancelLabel?: string) =>
    renderToStaticMarkup(
      createElement(LeaveConfirm, {
        openRef: { current: null },
        title: "저장하지 않고 나갈까요?",
        detail: "바꾼 이름이 저장되지 않습니다.",
        confirmLabel: "나가기",
        cancelLabel,
        onConfirm: () => {},
      }),
    );
  const html = render("계속 고치기");
  const rows = classesOf(html, "div").filter((c) => c.includes("gap-2"));
  const buttons = classesOf(html, "button");
  const dialog = classesOf(html, "dialog")[0];

  it("버튼 줄이 flex-wrap 이다", () => {
    assert.equal(rows.length, 1);
    assert.ok(rows[0].includes("flex") && rows[0].includes("flex-wrap"), rows[0].join(" "));
  });

  it("두 버튼의 flex 값이 같다 - 나란히 설 때 같은 폭이 된다", () => {
    assert.equal(buttons.length, 2);
    const flex = buttons.map((cls) => cls.filter((c) => /^flex-(\[|1$|auto$)/.test(c)));
    assert.deepEqual(flex[0], flex[1]);
    // 늘어날 수(grow)가 있어야 쌓였을 때 창 폭을 다 채운다.
    assert.match(flex[0][0] ?? "", /^flex-\[1_1_[\d.]+rem\]$/, flex[0].join(" "));
  });

  it("보통 크기 360폭에서 두 버튼이 한 줄에 들어간다(basis x 2 + gap <= 창 안쪽)", () => {
    const basisRem = Number(buttons[0].find((c) => c.startsWith("flex-["))!.match(/_([\d.]+)rem\]/)![1]);
    const pad = dialog.find((c) => c.startsWith("p-["));
    // clamp(최소,Nvw,최대) 를 360 에서 계산한다.
    const m = pad?.match(/^p-\[clamp\(([\d.]+)rem,([\d.]+)vw,([\d.]+)rem\)\]$/);
    assert.ok(m, `여백 클래스: ${pad}`);
    const [lo, vw, hi] = [Number(m[1]) * 16, Number(m[2]), Number(m[3]) * 16];
    const padPx = Math.min(hi, Math.max(lo, (360 * vw) / 100));
    assert.equal(hi, 24, "보통 크기 여백(24px)이 바뀌었다");
    assert.equal(padPx, 24, "360폭 보통 크기에서 여백이 24px 이 아니다");
    const width = Math.min(22 * 16, 360 - 32);
    assert.ok(dialog.includes("w-[min(22rem,calc(100vw-2rem))]"), dialog.join(" "));
    const inner = width - 2 * padPx;
    assert.ok(basisRem * 16 * 2 + 8 <= inner, `${basisRem * 16 * 2 + 8}px > 창 안쪽 ${inner}px`);
  });

  it("200%(180px) 에서는 여백이 최소값으로 줄어 쌓인다(basis x 2 + gap > 창 안쪽)", () => {
    const basisRem = Number(buttons[0].find((c) => c.startsWith("flex-["))!.match(/_([\d.]+)rem\]/)![1]);
    const m = dialog.find((c) => c.startsWith("p-["))!.match(/clamp\(([\d.]+)rem,([\d.]+)vw/)!;
    const padPx = Math.max(Number(m[1]) * 16, (180 * Number(m[2])) / 100);
    assert.equal(padPx, 16);
    // 창은 180-32=148px 을 원하지만 dialog 의 기본 최대 폭(화면 - 2em - 6px)에
    // 걸려 142px 이 된다. 실제로 그렇게 잰다.
    const inner = Math.min(180 - 32, 180 - 32 - 6) - 2 * padPx;
    assert.ok(basisRem * 16 * 2 + 8 > inner, "180px 에서도 나란히 서려 한다");
  });

  it("되돌아가는 쪽이 cancelLabel 대로 먼저 온다(쌓이면 위)", () => {
    assert.ok(html.indexOf("계속 고치기") < html.indexOf("나가기"));
    assert.ok(render().indexOf("계속 풀기") < render().indexOf("나가기"));
  });
});
