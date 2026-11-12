/**
 * 탭을 여러 번 누른 뒤 폰 뒤로 가기가 어디로 가는지(T11, 흐름 단위).
 *
 * 실행: cd frontend && npm test
 *
 * tab-bar-history.test.mts 가 링크 하나하나의 replace·onClick 을 본다면, 여기는
 * 그 링크들을 이어 눌렀을 때 기록이 어떻게 쌓이는지를 본다. 브라우저의 기록을
 * 흉내 낸 Session 위에서 진짜 TabBar 와 lib/history-nav 가 움직인다.
 *
 * Session 은 브라우저와 같게 둔다:
 *   - push 는 앞쪽 기록을 버리고 한 칸 쌓는다.
 *   - replace 는 지금 칸만 바꾼다.
 *   - traverseTo 는 칸을 옮길 뿐 기록을 지우지 않는다.
 *   - 맨 앞 칸에서 뒤로 가기는 사이트 밖(앱이 닫힌다)이다.
 *
 * 계약(앱을 일반 앱처럼):
 *   - 홈에서 탭을 몇 번 오가도 뒤로 한 번이면 홈, 한 번 더면 사이트 밖.
 *   - 탭 안의 상세는 뒤로 가기로 돌아온다. 상세에서 홈 탭이면 홈이 맨 앞 칸.
 *   - 홈이 아닌 주소로 앱을 열었으면 홈 탭이 그 칸을 바꿔치기해, 홈에서 뒤로
 *     한 번이면 사이트 밖.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";
import type { ReactNode } from "react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const ORIGIN = "https://dev-voca.vercel.app";

type Entry = { key: string; url: string; index: number; sameDocument: boolean };

/** 브라우저의 방문 기록(한 탭). */
class Session {
  private list: { key: string; path: string }[] = [];
  private at = -1;
  private seq = 0;

  constructor(first: string) {
    this.push(first);
  }

  get path(): string {
    return this.list[this.at].path;
  }
  get length(): number {
    return this.list.length;
  }
  get index(): number {
    return this.at;
  }

  push(path: string) {
    this.list = this.list.slice(0, this.at + 1);
    this.list.push({ key: `k${this.seq++}`, path });
    this.at = this.list.length - 1;
  }

  replace(path: string) {
    this.list[this.at] = { key: `k${this.seq++}`, path };
  }

  /** 뒤로 가기. 맨 앞 칸이면 사이트 밖이라 "exit". */
  back(): string {
    if (this.at === 0) return "exit";
    this.at -= 1;
    return this.path;
  }

  /** window.navigation 흉내. lib/history-nav 가 읽는 것만. */
  navigation() {
    const entries = (): Entry[] =>
      this.list.map((e, index) => ({ key: e.key, url: ORIGIN + e.path, index, sameDocument: true }));
    return {
      entries,
      get currentEntry(): Entry {
        return entries()[session.index];
      },
      traverseTo: (key: string) => {
        const to = this.list.findIndex((e) => e.key === key);
        assert.ok(to >= 0, `없는 기록 ${key}`);
        this.at = to;
        return { committed: Promise.resolve(), finished: Promise.resolve() };
      },
    };
  }
}

let session = new Session("/");

mock.module("next/navigation", {
  namedExports: {
    usePathname: () => session.path.split("?")[0],
    useRouter: () => ({
      push: (to: string) => session.push(to),
      replace: (to: string) => session.replace(to),
      refresh: () => {},
    }),
  },
});

type LinkProps = {
  href: string;
  replace?: boolean;
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
const { stepOffRepeat } = await import("@/lib/history-nav");

const flush = () => new Promise((r) => setTimeout(r, 0));
const realWindow = (globalThis as { window?: unknown }).window;
after(() => {
  (globalThis as { window?: unknown }).window = realWindow;
});

function open(first: string) {
  session = new Session(first);
  (globalThis as { window?: unknown }).window = {
    location: { origin: ORIGIN },
    navigation: session.navigation(),
  };
}

beforeEach(() => open("/"));

/** 지금 화면의 탭바에서 href 로 시작하는 탭을 누른다. Link 가 하는 일까지 흉내 낸다. */
async function tap(href: string) {
  links = [];
  renderToStaticMarkup(createElement(TabBar));
  const link = links.find((l) => (href === "/" ? l.href === "/" : l.href.startsWith(href)));
  assert.ok(link, `${session.path} 에 ${href} 탭이 없다`);
  let prevented = false;
  link.onNavigate?.({
    preventDefault: () => {
      prevented = true;
    },
  });
  if (!prevented) {
    if (link.replace) session.replace(link.href);
    else session.push(link.href);
  }
  await flush();
}

/** 탭바가 아닌 화면 안의 링크(목록의 카드 등). 기본 Link 처럼 쌓는다. */
function follow(path: string) {
  session.push(path);
}

describe("탭을 오간 뒤 뒤로 가기", () => {
  it("홈에서 탭을 여러 번 오가도 기록은 두 칸이고, 뒤로 한 번이면 홈, 한 번 더면 밖", async () => {
    for (const t of ["/learn", "/test", "/talk", "/profile", "/learn"]) await tap(t);
    assert.equal(session.length, 2);
    assert.equal(session.back(), "/");
    assert.equal(session.back(), "exit");
  });

  it("다른 탭에서 홈 탭을 누른 뒤 다시 나가도 뒤로 한 번이면 홈", async () => {
    await tap("/learn");
    await tap("/talk");
    await tap("/");
    assert.equal(session.path, "/");
    assert.equal(session.index, 0, "홈이 맨 앞 칸이 아니다");
    await tap("/test");
    assert.equal(session.back(), "/");
    assert.equal(session.back(), "exit");
  });

  it("홈에서 홈 탭을 눌러도 기록이 늘지 않는다", async () => {
    await tap("/");
    await tap("/");
    assert.equal(session.length, 1);
    assert.equal(session.back(), "exit");
  });
});

describe("탭 안의 상세", () => {
  it("목록 -> 상세 -> 뒤로 -> 목록 -> 뒤로 -> 홈 -> 뒤로 -> 밖", async () => {
    await tap("/learn");
    follow("/learn/words/7");
    assert.equal(session.back(), "/learn/words");
    assert.equal(session.back(), "/");
    assert.equal(session.back(), "exit");
  });

  it("상세에서 홈 탭이면 홈이 맨 앞 칸이라 뒤로 한 번이면 밖", async () => {
    await tap("/learn");
    follow("/learn/words/7");
    await tap("/");
    assert.equal(session.path, "/");
    assert.equal(session.back(), "exit");
  });

  it(
    "상세에서 다른 탭으로 가도 뒤로 한 번이면 홈",
    {
      todo:
        "지금은 목록 칸이 남아 뒤로 가기가 /learn/words 로 간다. 탭끼리는 지금 칸만 " +
        "바꿔치기해서, 홈 다음에 쌓인 탭 안의 칸(목록·허브)이 그대로 남는다.",
    },
    async () => {
      await tap("/learn");
      follow("/learn/words/7");
      await tap("/talk");
      assert.equal(session.back(), "/");
    },
  );
});

describe("홈이 아닌 주소로 앱을 연 경우", () => {
  for (const first of ["/learn/words/783", "/talk", "/board"]) {
    it(`${first} 에서 탭을 오간 뒤 홈 탭이면 홈 하나만 남는다`, async () => {
      open(first);
      await tap("/learn");
      await tap("/");
      assert.equal(session.path, "/");
      assert.equal(session.length, 1);
      assert.equal(session.back(), "exit");
    });
  }
});

describe("로그인처럼 지금 칸을 바꿔치기하는 이동 뒤", () => {
  // 로그인하면 로그인 화면의 칸이 돌아갈 주소로 바뀐다. TabBar 가 화면이 바뀔
  // 때마다 stepOffRepeat 을 부른다(effect 라 여기서는 직접 부른다).
  it("홈 -> 로그인 -> 홈: 같은 홈 두 칸이 한 칸이 되어 뒤로 한 번이면 밖", async () => {
    follow("/login");
    session.replace("/");
    assert.equal(session.length, 2);
    stepOffRepeat();
    await flush();
    assert.equal(session.path, "/");
    assert.equal(session.back(), "exit");
  });

  it("홈 -> 문제풀기 -> 순위표 -> 로그인 -> 순위표: 뒤로 두 번이면 홈", async () => {
    await tap("/test");
    follow("/board");
    follow("/login?next=/board");
    session.replace("/board");
    stepOffRepeat();
    await flush();
    assert.equal(session.path, "/board");
    assert.equal(session.back(), "/test");
    assert.equal(session.back(), "/");
  });
});
