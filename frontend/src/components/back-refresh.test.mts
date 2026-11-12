/**
 * 뒤로 가기로 돌아온 화면을 새로 받는 일(TabBar 의 onTraverseToOtherScreen)과 "홈으로"
 * 링크(HomeLink)를 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 탭과 "홈으로" 가 대부분 뒤쪽 기록으로 돌아가는 이동(traverse)이 되면서, 돌아간
 * 화면이 처음 받아 둔 서버 응답으로 그려진다. 일일공부를 푼 뒤 "홈으로" 를
 * 누르면 홈 카드가 "시작 전" 으로 남는다. 그래서 탭바가 뒤로·앞으로 가기로 홈과
 * 문제풀기에 옮겨지는 순간(Navigation API 의 currententrychange, Next 가 그 칸을
 * 되살리기 전) refresh 를 불러 받아 둔 응답을 지운다. 이 파일이 잡으려는 결함:
 *
 *   새로 안 받는다    이동 알림을 안 듣거나, 듣고도 refresh 를 안 부른다
 *   늦게 받는다       한 틱 미뤄 되살린 뒤에 부른다(Next 가 반영하지 않을 때가 있다)
 *   # 에 새로 받는다  같은 화면 안 # 이동(약관 목차)에도 refresh 해 # 이 지워진다
 *   목록을 지운다     목록·한 판 화면으로 돌아올 때도 refresh 해 스크롤이나 푸는
 *                     중인 문제를 잃는다
 *   리스너가 샌다     탭바가 사라진 뒤에도 popstate 를 들어 refresh 한다
 *   [홈, 홈]          로그인 뒤 같은 화면 두 칸을 탭바가 한 칸으로 줄이지 않는다
 *   홈으로가 쌓는다   "홈으로" 가 뒤쪽 홈으로 돌아가지 않거나, 바꿔치기가 아니다
 *
 * 브라우저 없이 본다. react 의 useEffect 를 대역으로 바꿔 TabBar 를 함수로
 * 부르고, 모아 둔 effect 를 직접 돌린다. window.navigation 은 currententrychange
 * 를 쏠 수 있는 EventTarget 대역이다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

const realReact = await import("react");

type Effect = () => void | (() => void);
let effects: Effect[] = [];

mock.module("react", {
  defaultExport: realReact.default,
  namedExports: {
    ...realReact,
    useEffect(run: Effect) {
      effects.push(run);
    },
  },
});

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
  children?: unknown;
};
function FakeLink(props: LinkProps) {
  return props;
}
mock.module("next/link", { defaultExport: FakeLink });

const { TabBar } = await import("./TabBar");
const { HomeLink } = await import("./HomeLink");
const { immersiveRoutes } = await import("@/lib/routes");

const ORIGIN = "https://dev-voca.vercel.app";

// ---------------------------------------------------------------------------
// window 대역
// ---------------------------------------------------------------------------

type Entry = { key: string; url: string; index: number; sameDocument: boolean };

/** window.navigation 대역. 듣는 리스너 수를 센다. */
class FakeNavigation extends EventTarget {
  listening = 0;
  constructor(
    readonly entries: () => Entry[],
    public currentEntry: Entry | null,
    readonly traverseTo: (key: string) => { committed: Promise<unknown>; finished: Promise<unknown> },
  ) {
    super();
  }
  addEventListener(...args: Parameters<EventTarget["addEventListener"]>) {
    if (args[0] === "currententrychange") this.listening += 1;
    super.addEventListener(...args);
  }
  removeEventListener(...args: Parameters<EventTarget["removeEventListener"]>) {
    if (args[0] === "currententrychange") this.listening -= 1;
    super.removeEventListener(...args);
  }
}

class FakeWindow {
  location: { origin: string; pathname: string; search: string; hash: string };
  navigation: FakeNavigation;
  traversals: string[] = [];

  /** urls 의 마지막이 지금 칸. otherDocument 에 든 번호는 다른 문서의 칸. */
  constructor(urls: string[], otherDocument: number[] = []) {
    const list = urls.map((u, index) => ({
      key: `k${index}`,
      url: ORIGIN + u,
      index,
      sameDocument: !otherDocument.includes(index),
    }));
    const here = new URL(urls[urls.length - 1] ?? "/", ORIGIN);
    this.location = { origin: ORIGIN, pathname: here.pathname, search: here.search, hash: here.hash };
    this.navigation = new FakeNavigation(
      () => list,
      list[list.length - 1] ?? null,
      (key: string) => {
        this.traversals.push(key);
        return { committed: Promise.resolve(), finished: Promise.resolve() };
      },
    );
  }

  get listening() {
    return this.navigation.listening;
  }

  /**
   * to 로 옮겨진 것처럼 currententrychange 를 쏜다. 브라우저처럼 주소를 먼저
   * 바꾸고 알린다. type 은 이동 종류(뒤로·앞으로 가기는 traverse).
   */
  popTo(to: string, type = "traverse") {
    const l = this.location;
    const from = ORIGIN + l.pathname + l.search + l.hash;
    const at = new URL(to, ORIGIN);
    Object.assign(l, { pathname: at.pathname, search: at.search, hash: at.hash });
    this.navigation.dispatchEvent(
      Object.assign(new Event("currententrychange"), { navigationType: type, from: { url: from } }),
    );
  }
}

const realWindow = (globalThis as { window?: unknown }).window;
after(() => {
  (globalThis as { window?: unknown }).window = realWindow;
});

function install(win: FakeWindow): FakeWindow {
  (globalThis as { window?: unknown }).window = win;
  return win;
}

/** path 에서 탭바를 그리고 effect 를 돌린다. cleanup 들을 돌려준다. */
function mountTabBar(path: string): (() => void)[] {
  pathname = path;
  effects = [];
  TabBar();
  return effects.map((run) => run()).filter((c): c is () => void => typeof c === "function");
}

// refresh 는 바로 부른다. 뒤늦게 부르는 일이 없는지 볼 때 기다리는 시간.
const tick = () => new Promise((r) => setTimeout(r, 5));

beforeEach(() => {
  routerCalls.length = 0;
  effects = [];
  (globalThis as { window?: unknown }).window = realWindow;
});

// ---------------------------------------------------------------------------

describe("뒤로 가기로 돌아온 화면을 새로 받는다(TabBar)", () => {
  it("뒤로 가기로 홈에 오면 그 자리에서(되살리기 전) 한 번 새로 받는다", async () => {
    const win = install(new FakeWindow(["/", "/talk"]));
    mountTabBar("/talk");
    win.popTo("/");
    // 미루지 않는다. Next 가 popstate 에서 되살린 뒤에 부르면 응답을 반영하지 않을
    // 때가 있다(11-12, 일일공부 뒤 홈 탭 4번 중 1번 "시작 전").
    assert.deepEqual(routerCalls, ["refresh"]);
    await tick();
    assert.deepEqual(routerCalls, ["refresh"]);
  });

  it("탭바가 숨는 화면(로그인·약관)에서도 듣는다. 거기서 홈으로 돌아가도 새로 받는다", async () => {
    for (const hidden of ["/privacy", "/terms", "/delete-account", "/login"]) {
      routerCalls.length = 0;
      const win = install(new FakeWindow(["/", hidden]));
      const cleanups = mountTabBar(hidden);
      win.popTo("/");
      await tick();
      assert.deepEqual(routerCalls, ["refresh"], hidden);
      cleanups.forEach((c) => c());
    }
  });

  for (const route of immersiveRoutes) {
    it(`한 판 화면(${route})으로 돌아오면 새로 받지 않는다(푸는 문제가 다시 그려진다)`, async () => {
      const win = install(new FakeWindow(["/", "/test", route, "/board"]));
      mountTabBar("/board");
      win.popTo(route);
      await tick();
      assert.deepEqual(routerCalls, []);
    });
  }

  it("한 판 화면 아래의 다른 주소(허브·안내)로 돌아오면 새로 받는다", async () => {
    const win = install(new FakeWindow(["/", "/test", "/test/words"]));
    mountTabBar("/test/words");
    win.popTo("/test");
    await tick();
    assert.deepEqual(routerCalls, ["refresh"]);
  });

  // 목차(LegalDoc 의 #링크)를 누르면 같은 문서 안 # 이동이다. 여기서 refresh 하면
  // Next 가 주소를 자기가 아는 주소로 바꿔치기해 # 이 지워지고
  // (/privacy#items -> /privacy#changes), 뒤로 가기가 엉뚱한 절로 튄다. 누를
  // 때마다 서버에도 두 번 묻는다(11-12 브라우저로 확인).
  it("같은 화면 안의 # 이동(경로·쿼리 그대로)에는 새로 받지 않는다", async () => {
    const win = install(new FakeWindow(["/", "/privacy#changes"]));
    mountTabBar("/privacy");
    win.popTo("/privacy#items", "push");
    win.popTo("/privacy#changes");
    await tick();
    assert.deepEqual(routerCalls, []);
  });

  it("뒤로·앞으로 가기가 아닌 이동(링크·바꿔치기)에는 새로 받지 않는다", async () => {
    const win = install(new FakeWindow(["/", "/talk"]));
    mountTabBar("/talk");
    win.popTo("/learn/words", "push");
    win.popTo("/test", "replace");
    await tick();
    assert.deepEqual(routerCalls, []);
  });

  it("목록 등 카드가 없는 화면으로 돌아올 때는 새로 받지 않는다(스크롤을 지킨다)", async () => {
    // 지우면 되살릴 때 "불러오는 중" 이 먼저 그려져 보던 스크롤 위치를 잃는다.
    const win = install(new FakeWindow(["/learn/words?cat=a", "/learn/words?cat=b"]));
    mountTabBar("/learn/words");
    win.popTo("/learn/words?cat=a");
    win.popTo("/talk");
    win.popTo("/board");
    await tick();
    assert.deepEqual(routerCalls, []);
  });

  it("Navigation API 가 없는 브라우저에서는 듣지 않는다(탭이 돌아가지 않아 새로 받을 일도 없다)", () => {
    const win = new FakeWindow(["/", "/talk"]);
    (globalThis as { window?: unknown }).window = { location: win.location };
    const cleanups = mountTabBar("/talk");
    assert.doesNotThrow(() => cleanups.forEach((c) => c()));
  });

  it("탭바가 사라지면(cleanup) 더 듣지 않는다", async () => {
    const win = install(new FakeWindow(["/", "/talk"]));
    const cleanups = mountTabBar("/talk");
    assert.equal(win.listening, 1);
    cleanups.forEach((c) => c());
    assert.equal(win.listening, 0);
    win.popTo("/");
    await tick();
    assert.deepEqual(routerCalls, []);
  });
});

describe("같은 화면 두 칸을 한 칸으로(TabBar 의 stepOffRepeat)", () => {
  it("홈에서 로그인해 [홈, 홈] 이 되면 앞 칸으로 돌아간다", () => {
    const win = install(new FakeWindow(["/", "/"]));
    mountTabBar("/");
    assert.deepEqual(win.traversals, ["k0"]);
  });

  it("다른 화면이 이어진 보통 기록에서는 움직이지 않는다", () => {
    const win = install(new FakeWindow(["/", "/learn/words?shuffle=ab", "/learn/words/7"]));
    mountTabBar("/learn/words/7");
    assert.deepEqual(win.traversals, []);
  });

  it("앞 칸이 다른 문서면 움직이지 않는다(페이지를 통째로 다시 받는다)", () => {
    const win = install(new FakeWindow(["/", "/"], [0]));
    mountTabBar("/");
    assert.deepEqual(win.traversals, []);
  });
});

describe("홈으로 링크(HomeLink)", () => {
  function link(extra: Record<string, unknown> = {}): LinkProps {
    // HomeLink 는 Link 요소를 돌려준다. 그 요소의 props 가 Link 에 넘어가는 값이다.
    const element = HomeLink({ children: "홈으로", ...extra } as never) as unknown as { props: LinkProps };
    return element.props;
  }

  function navigate(props: LinkProps): boolean {
    let prevented = false;
    props.onNavigate?.({
      preventDefault: () => {
        prevented = true;
      },
    });
    return prevented;
  }

  it("홈을 가리키고 바꿔치기다(기록을 쌓지 않는다)", () => {
    const props = link();
    assert.equal(props.href, "/");
    assert.equal(props.replace, true);
  });

  it("뒤쪽 기록에 홈이 있으면 그리로 돌아가고 Link 의 이동은 막는다", () => {
    const win = install(new FakeWindow(["/", "/test", "/test/daily"]));
    assert.equal(navigate(link()), true);
    assert.deepEqual(win.traversals, ["k0"]);
  });

  it("홈이 다른 문서의 칸이어도 돌아간다(홈이 첫 칸으로 남는다)", () => {
    const win = install(new FakeWindow(["/", "/nope"], [0]));
    assert.equal(navigate(link()), true);
    assert.deepEqual(win.traversals, ["k0"]);
  });

  it("뒤쪽에 홈이 없으면(약관을 새 탭으로 열었다) Link 의 바꿔치기에 맡긴다", () => {
    const win = install(new FakeWindow(["/privacy"]));
    assert.equal(navigate(link()), false);
    assert.deepEqual(win.traversals, []);
  });

  it("주소가 \"/\" 인 칸만 홈이다(\"/?x=1\" 같은 쿼리는 같은 홈, \"/test\" 는 아니다)", () => {
    const win = install(new FakeWindow(["/test", "/?from=push", "/test/daily"]));
    assert.equal(navigate(link()), true);
    assert.deepEqual(win.traversals, ["k1"]);
  });

  it("부르는 쪽이 준 onClick 을 그대로 넘긴다(가로채지 않는다)", () => {
    const onClick = () => {};
    assert.equal(link({ onClick }).onClick, onClick);
  });
});
