/**
 * 폰 글자 크기 200% 에서 남아 있던 곳(계정 삭제 창, 필터 칩과 분류 칩, 순위표
 * 탭, 목록의 쪽 넘기기 줄)의 구조 규칙을 본다. 앞의 세 곳은
 * text-zoom-200.test.mts 에 있다.
 *
 * 실행: cd frontend && npm test
 *
 * 글자 크기 200% 면 Chrome 이 페이지를 확대해 360폭 폰이 180px 폭처럼
 * 그려진다. 실제 폭은 브라우저로만 잴 수 있어서, 여기서는 그 폭에서 버티게
 * 해 주는 클래스가 빠지지 않았는지를 본다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DeleteDialog } from "../app/profile/DeleteAccount";
import { FilterChip } from "./FilterChip";
import { LeaveConfirm } from "./LeaveConfirm";
import { Leaderboard } from "./Leaderboard";
import { CategoryChip, DifficultyBadge, ExamBadge } from "./MetaBadge";
import { Pagination } from "./Pagination";

const classesOf = (html: string, tag: string) =>
  [...html.matchAll(new RegExp(`<${tag} [^>]*class="([^"]*)"`, "g"))].map((m) =>
    m[1].split(/\s+/),
  );

const render = (el: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(el);

describe("계정 삭제 창: 확인 창(LeaveConfirm)과 같은 세 가지로 버틴다", () => {
  const del = render(
    createElement(DeleteDialog, {
      action: async () => ({}),
      hasPassword: true,
      email: "someone@example.com",
      onClose: () => {},
    }),
  );
  const leave = render(
    createElement(LeaveConfirm, {
      openRef: { current: null },
      title: "저장하지 않고 나갈까요?",
      detail: "바꾼 이름이 저장되지 않습니다.",
      confirmLabel: "나가기",
      onConfirm: () => {},
    }),
  );
  const padOf = (html: string) => classesOf(html, "dialog")[0].find((c) => c.startsWith("p-"));
  // 버튼 줄은 첫 버튼을 바로 감싼 div 다.
  const rowOf = (html: string) => html.match(/<div class="([^"]*)"><button/)?.[1].split(/\s+/);
  const flexOf = (html: string) =>
    classesOf(html, "button").map((cls) => cls.find((c) => /^flex-(\[|1$)/.test(c)));

  it("창 안쪽 여백이 같다 - p-6 이면 180px 에서 버튼 칸이 좁아 한 글자씩 꺾인다", () => {
    assert.match(padOf(leave) ?? "", /^p-\[clamp\(/);
    assert.equal(padOf(del), padOf(leave));
  });

  it("버튼 줄이 확인 창과 같다(flex-wrap)", () => {
    const row = rowOf(del);
    assert.ok(row?.includes("flex-wrap"), row?.join(" "));
    assert.deepEqual(row, rowOf(leave));
  });

  it("두 버튼의 기본 폭이 확인 창과 같다 - flex-1 이면 쌓이지 못하고 눌린다", () => {
    const [cancel, submit] = flexOf(del);
    assert.equal(cancel, flexOf(leave)[0]);
    assert.equal(submit, cancel);
  });
});

describe("필터 칩: 칩 하나가 줄보다 길면 칩 안에서 꺾는다", () => {
  const props: Parameters<typeof FilterChip>[0] = {
    href: "/x",
    active: false,
    children: "코드 리뷰(Code Review)",
  };
  const cls = classesOf(render(createElement(FilterChip, props)), "a")[0];

  it("whitespace-nowrap 이 없고 줄 폭에 묶이며(max-w-full) 꺾인 줄은 가운데로 모은다", () => {
    assert.ok(!cls.includes("whitespace-nowrap"), cls.join(" "));
    for (const need of ["max-w-full", "text-center"]) {
      assert.ok(cls.includes(need), `${need} 없음: ${cls.join(" ")}`);
    }
  });

  it("모서리가 한 줄 높이의 절반이다 - 알약이면 두 줄일 때 양 끝이 부푼다", () => {
    assert.ok(!cls.includes("rounded-full"), cls.join(" "));
    // py-2 위아래(0.5rem x 2) + text-sm 한 줄(Tailwind 기본 1.25rem) = 2.25rem
    assert.ok(cls.includes("py-2") && cls.includes("text-sm"), cls.join(" "));
    assert.ok(cls.includes("rounded-[1.125rem]"), cls.join(" "));
  });
});

describe("분류 칩: 줄을 바꾸고, 난이도·정처기 배지는 한 줄 그대로다", () => {
  const span = classesOf(render(createElement(CategoryChip, { label: "코드 리뷰(Code Review)" })), "span")[0];
  const link = classesOf(
    render(createElement(CategoryChip, { label: "코드 리뷰(Code Review)", href: "/learn/words?category=x" })),
    "a",
  )[0];

  it("누를 수 없는 칩과 링크 칩 모두 whitespace-nowrap 이 없다", () => {
    // whitespace-normal 을 덧붙여 nowrap 을 "떼는" 방식은 안 된다. 둘이 같이
    // 붙으면 생성된 CSS 순서로 nowrap 이 이겨 한 번도 줄을 안 바꿨다.
    for (const cls of [span, link]) {
      assert.ok(!cls.includes("whitespace-nowrap"), cls.join(" "));
      assert.ok(!cls.includes("whitespace-normal"), cls.join(" "));
      for (const need of ["min-w-0", "text-center"]) {
        assert.ok(cls.includes(need), `${need} 없음: ${cls.join(" ")}`);
      }
    }
  });

  it("모서리가 한 줄 높이의 절반이다(py-1.5 x 2 + text-xs 한 줄 1rem = 1.75rem)", () => {
    for (const cls of [span, link]) {
      assert.ok(!cls.includes("rounded-full"), cls.join(" "));
      assert.ok(cls.includes("py-1.5") && cls.includes("text-xs"), cls.join(" "));
      assert.ok(cls.includes("rounded-[0.875rem]"), cls.join(" "));
    }
  });

  it("난이도·정처기는 줄을 안 바꾸고 안 줄어든다", () => {
    const badges = [
      classesOf(render(createElement(DifficultyBadge, { level: 3, label: "어려움" })), "span")[0],
      classesOf(render(createElement(ExamBadge, { subjectLabel: "3과목 데이터베이스 구축" })), "span")[0],
    ];
    for (const cls of badges) {
      for (const need of ["whitespace-nowrap", "shrink-0", "rounded-full"]) {
        assert.ok(cls.includes(need), `${need} 없음: ${cls.join(" ")}`);
      }
    }
  });
});

describe("순위표 탭: 세 칩이 한 줄에 안 들어가면 다음 줄로 간다", () => {
  const html = render(createElement(Leaderboard, { board: { kind: "all_time", rows: [], me: null }, isGuest: false }));
  const nav = html.match(/<nav aria-label="순위표 종류" class="([^"]*)"/)?.[1].split(/\s+/);

  it("탭 줄이 flex-wrap 이다", () => {
    assert.ok(nav?.includes("flex-wrap"), nav?.join(" "));
  });

  it("칩 라벨은 짧아 칩 안에서는 꺾지 않는다", () => {
    // 탭 줄(nav) 안의 링크만 센다. 빈 표의 "문제 풀러 가기" 버튼은 밖에 있다.
    const tabRow = html.match(/<nav aria-label="순위표 종류"[\s\S]*?<\/nav>/)?.[0] ?? "";
    const tabs = classesOf(tabRow, "a");
    assert.equal(tabs.length, 3);
    for (const cls of tabs) assert.ok(cls.includes("whitespace-nowrap"), cls.join(" "));
  });
});

describe("쪽 넘기기 줄: 한 줄에 안 들어가면 다음 줄로 간다", () => {
  // 가운데 쪽이라 처음·이전·쪽수·다음·끝이 다 있다. 180px 폭에서 약 280px 이다.
  const html = render(
    createElement(Pagination, {
      basePath: "/learn/words",
      filters: {},
      currentPage: 3,
      hasPrevious: true,
      hasNext: true,
      count: 1045,
      pageLength: 20,
    }),
  );
  const nav = html.match(/<nav aria-label="페이지 이동" class="([^"]*)"/)?.[1].split(/\s+/);
  const sides = [...html.matchAll(/<div class="([^"]*)"><a /g)].map((m) => m[1].split(/\s+/));

  it("줄이 flex-wrap 이다 - 3칸 격자(grid)는 줄을 못 바꿔 화면을 넓힌다", () => {
    assert.ok(nav?.includes("flex") && nav.includes("flex-wrap"), nav?.join(" "));
    assert.ok(!nav?.includes("grid"), nav?.join(" "));
  });

  it("양옆이 같은 비율(flex-1)이라 한 줄일 때 가운데 쪽수가 움직이지 않는다", () => {
    assert.equal(sides.length, 2, html);
    for (const cls of sides) assert.ok(cls.includes("flex-1"), cls.join(" "));
  });

  it("좁은 화면(320px 미만)에서는 쪽수가 첫 줄에 혼자 가운데로 간다 - 꺾일 때 쪽마다 자리가 바뀌지 않게", () => {
    const count = html.match(/<span class="([^"]*)"[^>]*>3 \/ 53<\/span>/)?.[1].split(/\s+/);
    assert.ok(count, html);
    for (const need of ["max-[20rem]:order-first", "max-[20rem]:basis-full", "max-[20rem]:text-center"]) {
      assert.ok(count.includes(need), `${need} 없음: ${count.join(" ")}`);
    }
  });
});
