/**
 * 문제풀기의 네 출구를 **실제로 그리고, 클릭 처리기를 직접 불러서** 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 형제 leave-confirm.test.mts 는 출구가 판단 함수를 거치는지를 원문으로
 * 본다. 여기는 그 판단이 **실제 클릭에서** 어떻게 갈리는지를 본다 - 원문
 * 검사는 "함수를 부르긴 하는데 조건이 뒤집힌 것" 을 못 잡는다.
 *
 * 브라우저 없이 클릭을 흉내 내는 방법: next/link 를 대역으로 바꿔 링크에
 * 넘긴 props(onClick 포함)를 모아 두고, renderToStaticMarkup 으로 그린 뒤
 * 모은 onClick 에 가짜 이벤트를 넣는다. 서버 렌더에서는 그린 뒤의 setState
 * 가 아무 일도 안 하고 useImperativeHandle 도 안 돌아 창이 실제로 열리지는
 * 않는다. 그래서 "막았는가" 는 preventDefault 가 불렸는지로 본다 - Next 의
 * Link 는 onClick 뒤에 defaultPrevented 를 보고 이동을 건너뛴다.
 *
 * 분류 고르개(CategoryPicker)의 항목은 메뉴를 열어야 그려져서 여기서 누를
 * 수 없다. 그 판단은 LeaveLink·ContentTabs 와 같은 useLeaveGuard 를 거치므로
 * 훅을 직접 붙잡아 본다.
 */
import assert from "node:assert/strict";
import { beforeEach, describe, it, mock } from "node:test";
import { createElement, Fragment } from "react";
import type { ComponentProps, ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

// ---------------------------------------------------------------------------
// Next 런타임 대역. 컴포넌트를 import 하기 전에 등록해야 한다.
// ---------------------------------------------------------------------------

/** router.push 로 간 곳. 확인 없이 옮기는지 본다. */
const pushed: string[] = [];

mock.module("next/navigation", {
  namedExports: {
    useRouter: () => ({ push: (to: string) => pushed.push(to) }),
    usePathname: () => "/test/words",
  },
});

type LinkProps = {
  href: string;
  onClick?: (event: FakeClick) => void;
  children?: ReactNode;
};

/** 이번 렌더에서 그려진 링크들. */
let links: LinkProps[] = [];

mock.module("next/link", {
  defaultExport: (props: LinkProps) => {
    links.push(props);
    return createElement("a", { href: props.href }, props.children);
  },
});

const { clearSolved, markSolved } = await import("@/lib/quiz-progress");
const { ContentTabs } = await import("./ContentTabs");
const { LeaveLink } = await import("./LeaveLink");
const { ExitGuard } = await import("./ExitGuard");
const { CategoryPicker } = await import("./CategoryPicker");
const { LeaveConfirm } = await import("./LeaveConfirm");
const { useLeaveGuard } = await import("./useLeaveGuard");

// ---------------------------------------------------------------------------
// 도구
// ---------------------------------------------------------------------------

type FakeClick = {
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
  button: number;
  prevented: boolean;
  preventDefault: () => void;
};

const click = (over: Partial<FakeClick> = {}): FakeClick => {
  const event: FakeClick = {
    metaKey: false,
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
    button: 0,
    prevented: false,
    preventDefault() {
      event.prevented = true;
    },
    ...over,
  };
  return event;
};

/** 그리고, 그 렌더에서 나온 링크를 돌려준다. */
const draw = (element: ReturnType<typeof createElement>) => {
  links = [];
  const html = renderToStaticMarkup(element);
  return { html, links: [...links] };
};

const linkTo = (list: LinkProps[], href: string) => {
  const found = list.find((l) => l.href === href);
  assert.ok(found, `${href} 링크가 없다`);
  return found;
};

/**
 * "한 판 풀기" 링크. children 을 인자로 넘기면(린트 규칙) 타입 검사가 props 에
 * children 이 없다고 해서 props 만 넓혀 둔다.
 */
const roundLink = () =>
  createElement(
    LeaveLink,
    { href: "/test/round", confirmLabel: "한 판 풀기" } as ComponentProps<typeof LeaveLink>,
    "한 판 풀기",
  );

/** dialog 개수. */
const dialogs = (html: string) => (html.match(/<dialog\b/g) ?? []).length;

beforeEach(() => {
  clearSolved();
  pushed.length = 0;
});

// ---------------------------------------------------------------------------
// 단어·문장 탭
// ---------------------------------------------------------------------------

describe("단어·문장 탭", () => {
  const tabs = (warnOnLeave: boolean) =>
    draw(createElement(ContentTabs, { mode: "test", current: "words", warnOnLeave }));

  it("문제풀기에서 푼 것이 있으면 다른 탭 클릭을 막는다", () => {
    markSolved(3);
    const { links } = tabs(true);
    const other = links.find((l) => !l.href.endsWith("/words"));
    assert.ok(other?.onClick);
    const event = click();
    other.onClick(event);
    assert.equal(event.prevented, true);
    // 확인 전에는 옮기지 않는다.
    assert.deepEqual(pushed, []);
  });

  it("지금 켜진 탭을 누르면 막지 않는다", () => {
    // 같은 곳으로 가는 것이라 판이 안 끝난다. 막으면 헛된 창이 뜬다.
    markSolved(3);
    const { links } = tabs(true);
    const self = links.find((l) => l.href.endsWith("/words"));
    const event = click();
    self?.onClick?.(event);
    assert.equal(event.prevented, false);
  });

  it("익히기 화면(warnOnLeave 없음)에서는 푼 수가 있어도 막지 않고 창도 안 그린다", () => {
    markSolved(3);
    const { html, links } = tabs(false);
    for (const link of links) {
      const event = click();
      link.onClick?.(event);
      assert.equal(event.prevented, false, link.href);
    }
    assert.equal(dialogs(html), 0, "잃을 것이 없는 화면에 숨은 창을 두지 않는다");
  });

  it("문제풀기에서 창을 하나만 그린다", () => {
    assert.equal(dialogs(tabs(true).html), 1);
  });

  it("보조키를 여러 개 같이 눌러도 막지 않는다", () => {
    markSolved(3);
    const { links } = tabs(true);
    const other = links.find((l) => !l.href.endsWith("/words"));
    const event = click({ ctrlKey: true, shiftKey: true, metaKey: true, altKey: true });
    other?.onClick?.(event);
    assert.equal(event.prevented, false);
  });
});

// ---------------------------------------------------------------------------
// "한 판 풀기" 링크
// ---------------------------------------------------------------------------

describe("\"한 판 풀기\" 링크", () => {
  const leaveLink = () => draw(roundLink());

  it("푼 것이 없으면 그냥 간다", () => {
    const { links } = leaveLink();
    const event = click();
    linkTo(links, "/test/round").onClick?.(event);
    assert.equal(event.prevented, false);
  });

  it("푼 것이 있으면 막는다", () => {
    markSolved(1);
    const { links } = leaveLink();
    const event = click();
    linkTo(links, "/test/round").onClick?.(event);
    assert.equal(event.prevented, true);
    assert.deepEqual(pushed, []);
  });

  it("가운데 버튼·오른쪽 버튼은 막지 않는다", () => {
    markSolved(1);
    const { links } = leaveLink();
    for (const button of [1, 2]) {
      const event = click({ button });
      linkTo(links, "/test/round").onClick?.(event);
      assert.equal(event.prevented, false, `button ${button}`);
    }
  });

  it("클릭 순간의 값을 본다 - 그린 뒤에 풀어도 막는다", () => {
    // 링크는 판보다 먼저 그려진다. 그릴 때 읽은 0 을 붙들면 영영 안 묻는다.
    const { links } = leaveLink();
    markSolved(4);
    const event = click();
    linkTo(links, "/test/round").onClick?.(event);
    assert.equal(event.prevented, true);
  });

  it("판이 사라진 뒤에는 막지 않는다", () => {
    markSolved(4);
    const { links } = leaveLink();
    clearSolved();
    const event = click();
    linkTo(links, "/test/round").onClick?.(event);
    assert.equal(event.prevented, false);
  });
});

// ---------------------------------------------------------------------------
// useLeaveGuard (분류 고르개가 쓰는 판단)
// ---------------------------------------------------------------------------

describe("useLeaveGuard", () => {
  /** 훅이 내준 guard 를 붙잡는다. 훅은 컴포넌트 안에서만 부를 수 있다. */
  const grab = () => {
    let guard: ((event: never, href: string) => boolean) | undefined;
    function Probe() {
      const hook = useLeaveGuard({ confirmLabel: "분류 바꾸기" });
      guard = hook.guard as never;
      return hook.dialog;
    }
    const html = renderToStaticMarkup(createElement(Probe));
    assert.ok(guard);
    return { guard, html };
  };

  it("막았는지를 돌려주는 값과 preventDefault 가 일치한다", () => {
    // CategoryPicker 는 돌려받은 값으로 메뉴를 닫을지 정한다. 둘이 어긋나면
    // 막았는데 메뉴가 닫히거나, 안 막았는데 메뉴가 남는다.
    const { guard } = grab();
    for (const solved of [0, 1, 99]) {
      markSolved(solved);
      for (const over of [{}, { ctrlKey: true }, { button: 1 }]) {
        const event = click(over);
        const blocked = guard(event as never, "/test/words?category=db");
        assert.equal(blocked, event.prevented, `${solved} ${JSON.stringify(over)}`);
      }
    }
  });

  it("아주 큰 수도 막는다", () => {
    const { guard } = grab();
    markSolved(Number.MAX_SAFE_INTEGER);
    const event = click();
    assert.equal(guard(event as never, "/x"), true);
  });

  it("창은 처음 그릴 때 닫혀 있다", () => {
    // open 속성으로 그리면 backdrop·포커스 가둠 없는 그냥 보이는 상자가 된다.
    const { html } = grab();
    assert.equal(dialogs(html), 1);
    assert.doesNotMatch(html, /<dialog[^>]*\bopen\b/);
  });
});

// ---------------------------------------------------------------------------
// 홈 버튼
// ---------------------------------------------------------------------------

describe("홈 버튼(ExitGuard)", () => {
  const exit = (props: Record<string, unknown>) =>
    draw(createElement(ExitGuard, { to: "/", label: "홈", ...props })).html;

  it("묻는 설정이 없으면 창을 안 그린다", () => {
    assert.equal(dialogs(exit({})), 0);
  });

  it("confirm 이면 창을 하나 그린다", () => {
    assert.equal(dialogs(exit({ confirm: true })), 1);
  });

  it("confirmWhenSolved 이면 창을 하나 그린다", () => {
    assert.equal(dialogs(exit({ confirmWhenSolved: true })), 1);
  });

  it("둘 다 켜도 창은 하나다", () => {
    assert.equal(dialogs(exit({ confirm: true, confirmWhenSolved: true })), 1);
  });

  it("한 판 모드는 딴 점수를 말하고, 음수·0 이면 일반 문구다", () => {
    assert.match(exit({ confirm: true, score: 7 }), /딴 7점이 사라지고/);
    for (const score of [0, -2]) {
      const html = exit({ confirm: true, score });
      assert.doesNotMatch(html, /딴 -?\d+점/, `score ${score}`);
      assert.match(html, /점수가 적용되지 않습니다/, `score ${score}`);
    }
  });

  it("한 판 모드 문구에 푼 문제 수가 섞이지 않는다", () => {
    // 한 판 모드는 푼 수가 아니라 점수를 잃는다. 문제풀기 문구가 새면 안 된다.
    markSolved(5);
    assert.doesNotMatch(exit({ confirm: true }), /문제가 사라/);
  });

  it("시간이 걸린 판이면 시간이 흐른다고 알리고, 아니면 안 알린다", () => {
    assert.match(exit({ confirm: true, countdown: true }), /시간은 흐릅니다/);
    assert.doesNotMatch(exit({ confirm: true }), /시간은 흐릅니다/);
  });

  it("버튼 글자를 그린다", () => {
    assert.match(exit({ confirmWhenSolved: true }), /<button[^>]*>[\s\S]*?홈<\/button>/);
  });
});

// ---------------------------------------------------------------------------
// 확인 창
// ---------------------------------------------------------------------------

describe("확인 창(LeaveConfirm)", () => {
  const confirmBox = (note?: ReactNode) =>
    createElement(LeaveConfirm, {
      openRef: { current: null },
      title: "제목",
      detail: "설명",
      note,
      confirmLabel: "가기",
      onConfirm: () => {},
    });

  it("덧붙일 말이 없으면 문단은 설명 하나뿐이다", () => {
    const html = renderToStaticMarkup(confirmBox());
    assert.equal((html.match(/<p\b/g) ?? []).length, 1);
  });

  it("덧붙일 말이 false 여도 아무것도 안 그린다", () => {
    // ExitGuard 는 countdown && (...) 를 넘긴다. false 가 글자로 새면 안 된다.
    const html = renderToStaticMarkup(confirmBox(false));
    assert.equal((html.match(/<p\b/g) ?? []).length, 1);
    assert.doesNotMatch(html, /false/);
  });

  it("덧붙일 말은 버튼보다 앞에 온다", () => {
    const html = renderToStaticMarkup(
      confirmBox(createElement("p", null, "덧붙임")),
    );
    assert.ok(html.indexOf("덧붙임") < html.indexOf("계속 풀기"));
  });

  it("버튼 둘 다 form 을 보내지 않는다", () => {
    // type 이 빠지면 폼 안에 놓였을 때 submit 이 된다.
    const html = renderToStaticMarkup(confirmBox());
    const buttons = html.match(/<button[^>]*>/g) ?? [];
    assert.equal(buttons.length, 2);
    for (const b of buttons) assert.match(b, /type="button"/);
  });

  it("한 화면에 둘을 그려도 id 가 겹치지 않는다", () => {
    const html = renderToStaticMarkup(
      createElement(Fragment, null, confirmBox(), confirmBox()),
    );
    const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]);
    assert.equal(ids.length, 4);
    assert.equal(new Set(ids).size, 4, ids.join(" "));
  });
});

// ---------------------------------------------------------------------------
// 문제풀기 한 화면
// ---------------------------------------------------------------------------

describe("문제풀기 한 화면에 네 출구를 같이 그리면", () => {
  const page = () =>
    draw(
      createElement(
        Fragment,
        null,
        createElement(ExitGuard, { to: "/", label: "홈", confirmWhenSolved: true }),
        roundLink(),
        createElement(ContentTabs, { mode: "test", current: "words", warnOnLeave: true }),
        createElement(CategoryPicker, {
          options: [{ value: "db", label: "DB" }],
          basePath: "/test/words",
        }),
      ),
    ).html;

  it("창이 넷이고 모두 닫혀 있다", () => {
    const html = page();
    assert.equal(dialogs(html), 4);
    assert.doesNotMatch(html, /<dialog[^>]*\bopen\b/);
  });

  it("aria 로 잇는 id 가 모두 다르고 전부 제자리를 가리킨다", () => {
    // 겹치면 낭독기가 다른 창의 제목·문제 수를 읽는다.
    const html = page();
    const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]);
    assert.equal(new Set(ids).size, ids.length, `겹친 id: ${ids.join(" ")}`);
    const refs = [...html.matchAll(/aria-(?:labelledby|describedby)="([^"]+)"/g)].map(
      (m) => m[1],
    );
    assert.equal(refs.length, 8);
    for (const ref of refs) assert.ok(ids.includes(ref), `${ref} 가 가리킬 곳이 없다`);
  });
});
