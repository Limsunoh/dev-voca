/**
 * 아래 탭이 방문 기록을 어떻게 남기는지(T11, 폰 뒤로 가기를 일반 앱처럼).
 *
 * 실행: cd frontend && npm test
 *
 * 앱(TWA)에서 폰의 뒤로 가기는 브라우저의 뒤로 가기이고, 맨 처음 기록에서 한 번
 * 더 누르면 Android 가 앱을 닫는다. 탭을 누를 때마다 기록을 쌓으면(push) 앱이
 * 안 닫힌다(11-12 사용자 지적).
 *
 * 계약:
 *   - 홈에서 다른 탭으로 나갈 때만 기록을 쌓는다(replace 가 아니다).
 *   - 그 밖(탭끼리, 지금 화면과 같은 탭, 홈에서 홈)은 바꿔치기(replace)다.
 *   - 탭을 누르면, 뒤쪽 기록에 그 탭 화면(경로가 같은 칸)이 있을 때 새로 쌓지
 *     않고 그리로 돌아간다. 홈 탭이면 홈이 첫 칸으로 남고, 상세에서 같은 탭을
 *     누르면 목록이 두 번 쌓이지 않는다. 없으면 Link 의 replace 에 맡긴다.
 *   - 돌아가기는 Link 의 onNavigate 에서 한다. 다른 곳이 이미 막은 클릭(저장
 *     안 한 내정보의 확인 창)과 새 탭으로 열기(가운데 클릭, ctrl 클릭)는 Link 가
 *     거른 뒤라 거기까지 오지 않는다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";
import type { ReactNode } from "react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

let pathname = "/";
const routerCalls: string[] = [];

mock.module("next/navigation", {
  namedExports: {
    usePathname: () => pathname,
    useRouter: () => ({
      push: (to: string) => routerCalls.push(`push ${to}`),
      replace: (to: string) => routerCalls.push(`replace ${to}`),
      refresh: () => routerCalls.push("refresh"),
    }),
  },
});

type LinkProps = {
  href: string;
  replace?: boolean;
  onClick?: unknown;
  onNavigate?: (e: { preventDefault(): void }) => void;
  children?: ReactNode;
};
let links: LinkProps[] = [];

mock.module("next/link", {
  defaultExport: (props: LinkProps) => {
    links.push(props);
    return createElement("a", { href: props.href }, props.children);
  },
});

const { TabBar } = await import("./TabBar");

const ORIGIN = "https://dev-voca.vercel.app";

function renderAt(path: string): LinkProps[] {
  pathname = path;
  links = [];
  renderToStaticMarkup(createElement(TabBar));
  return links;
}

function homeLink(list: LinkProps[]): LinkProps {
  const found = list.find((l) => l.href === "/");
  assert.ok(found, "홈 탭이 없다");
  return found;
}

/** 뒤쪽 기록을 흉내 낸다. urls 의 마지막이 지금 화면이다. */
function installHistory(urls: string[]) {
  const traversals: string[] = [];
  const list = urls.map((u, index) => ({ key: `k${index}`, url: ORIGIN + u, index, sameDocument: true }));
  (globalThis as { window?: unknown }).window = {
    location: { origin: ORIGIN },
    navigation: {
      entries: () => list,
      currentEntry: list[list.length - 1],
      traverseTo: (key: string) => {
        traversals.push(key);
        return { committed: Promise.resolve(), finished: Promise.resolve() };
      },
    },
  };
  return traversals;
}

/** Link 가 이동하기 직전에 부르는 onNavigate. 막았으면(돌아갔으면) true. */
function click(link: LinkProps) {
  let prevented = false;
  link.onNavigate?.({
    preventDefault: () => {
      prevented = true;
    },
  });
  return prevented;
}

const flush = () => new Promise((r) => setTimeout(r, 0));
const realWindow = (globalThis as { window?: unknown }).window;
after(() => {
  (globalThis as { window?: unknown }).window = realWindow;
});
beforeEach(() => {
  routerCalls.length = 0;
  (globalThis as { window?: unknown }).window = realWindow;
});

describe("탭이 기록을 남기는 방식", () => {
  it("홈에서는 다른 탭으로 나가는 링크만 기록을 쌓는다", () => {
    const list = renderAt("/");
    assert.equal(list.length, 5);
    for (const l of list) {
      assert.equal(l.replace, l.href === "/", `${l.href} 의 replace`);
    }
  });

  for (const path of ["/learn/words", "/learn/sentences/3", "/test", "/talk", "/profile", "/board"]) {
    it(`${path} 에서는 모든 탭이 바꿔치기다`, () => {
      const list = renderAt(path);
      for (const l of list) assert.equal(l.replace, true, `${l.href} 의 replace`);
      assert.equal(typeof homeLink(list).onNavigate, "function");
    });
  }
});

describe("홈이 아닌 화면에서 홈 탭", () => {
  it("뒤쪽 기록에 홈이 있으면 새로 쌓지 않고 그리로 돌아간다", async () => {
    const traversals = installHistory(["/", "/learn/words", "/learn/words/7"]);
    const link = homeLink(renderAt("/learn/words/7"));
    assert.equal(click(link), true, "Link 의 이동을 막지 않았다");
    await flush();
    assert.deepEqual(traversals, ["k0"]);
    // 새로 받는 일은 popstate 에서 한 번만(여기서 받으면 서버에 두 번 묻는다).
    assert.deepEqual(routerCalls, []);
  });

  it("뒤쪽에 홈이 없으면(홈이 아닌 주소로 앱을 열었으면) Link 에 맡긴다(바꿔치기)", () => {
    const traversals = installHistory(["/learn/words/7"]);
    const link = homeLink(renderAt("/learn/words/7"));
    assert.equal(click(link), false);
    assert.equal(link.replace, true);
    assert.deepEqual(traversals, []);
  });

  it("onClick 으로 가로채지 않는다(막힌 클릭·새 탭 열기는 Link 가 거른다)", () => {
    // onClick 에서 돌아가면 useUnsavedGuard 가 막은 클릭에도 홈으로 가서, 확인
    // 창이 뜨는 동시에 고친 내용이 사라진다. onNavigate 는 Link 가 그런 클릭과
    // 가운데·ctrl 클릭을 거른 뒤에만 부른다.
    for (const l of renderAt("/profile")) assert.equal(l.onClick, undefined, l.href);
  });
});

describe("홈이 아닌 탭", () => {
  it("상세에서 같은 탭을 누르면 뒤쪽의 목록(쿼리가 붙은)으로 돌아간다", async () => {
    // 목록은 들어가면 ?shuffle= 이 붙는다. 경로만 같으면 같은 화면으로 본다.
    const traversals = installHistory(["/", "/learn/words?shuffle=ab", "/learn/words/7"]);
    const learn = renderAt("/learn/words/7").find((l) => l.href.startsWith("/learn/words"));
    assert.ok(learn);
    assert.equal(click(learn), true);
    await flush();
    assert.deepEqual(traversals, ["k1"]);
  });

  it("지금 화면과 같은 탭이면 돌아가지 않는다(바꿔치기)", () => {
    const traversals = installHistory(["/learn/words", "/", "/learn/words"]);
    const learn = renderAt("/learn/words").find((l) => l.href.startsWith("/learn/words"));
    assert.ok(learn);
    assert.equal(click(learn), false);
    assert.equal(learn.replace, true);
    assert.deepEqual(traversals, []);
  });
});
