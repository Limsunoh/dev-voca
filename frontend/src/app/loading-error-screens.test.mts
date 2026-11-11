/**
 * 루트 대기 화면(loading.tsx)과 오류 화면 둘(error.tsx, global-error.tsx).
 *
 * 실행: cd frontend && npm test
 *
 * 계약.
 *   1. 대기 화면은 role=status 와 "불러오는 중" 글자를 갖는다. 점 깜빡임은
 *      읽어 주지 않는다(aria-hidden) - 움직임을 줄인 사용자에게는 글자가 신호다.
 *   2. error.tsx 는 한국어 안내와 "다시 시도" 버튼, 홈 링크를 갖는다.
 *      버튼은 unstable_retry 를 부른다(Next 16 의 이름. reset 이 아니다).
 *   3. global-error.tsx 는 루트 layout 을 대신하므로 html(lang=ko)·body·title·
 *      viewport meta 를 직접 그린다. 홈 링크는 페이지를 새로 받는 a 다.
 *   4. 오류 메시지(백엔드 주소·스택이 들어 있을 수 있다)는 화면에 안 나온다.
 *
 * renderToStaticMarkup 으로 그린다(detail-back-link.test.mts 와 같다). 효과
 * (useEffect)는 서버 렌더에서 안 돌아서, 버튼은 그려진 요소의 onClick 을 직접 부른다.
 * 컴포넌트를 렌더 밖에서 함수로 부르면 훅이 터지므로 감싼 컴포넌트 안에서 부른다.
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { createElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { routes } from "@/lib/routes";

const { default: Loading } = await import("./loading");
const { default: RootError } = await import("./error");
const { default: GlobalError } = await import("./global-error");

const SECRET = "connect ECONNREFUSED 10.0.0.5:8000 at Traceback";
const leaky = Object.assign(new Error(SECRET), { digest: "abc123" });

/** 그려진 트리에서 type 이 button 인 요소를 모두 찾는다(함수 컴포넌트는 펼쳐 본다). */
function findButtons(node: ReactNode): ReactElement<{ onClick?: () => void; children?: ReactNode }>[] {
  const out: ReactElement<{ onClick?: () => void; children?: ReactNode }>[] = [];
  const walk = (n: ReactNode): void => {
    if (Array.isArray(n)) return n.forEach(walk);
    if (!n || typeof n !== "object" || !("props" in n)) return;
    const el = n as ReactElement<{ children?: ReactNode; onClick?: () => void }>;
    if (el.type === "button") out.push(el);
    walk(el.props.children);
  };
  walk(node);
  return out;
}

/** 렌더 중에 컴포넌트를 함수로 불러 그 결과 트리를 꺼낸다. */
function treeOf<P extends object>(Component: (p: P) => ReactNode, props: P): ReactNode {
  let tree: ReactNode = null;
  const Probe = () => {
    tree = Component(props);
    return null;
  };
  renderToStaticMarkup(createElement(Probe));
  return tree;
}

describe("loading.tsx", () => {
  const html = renderToStaticMarkup(createElement(Loading));

  it("role=status 와 aria-live=polite 는 글자에 있다(main 랜드마크를 덮지 않는다)", () => {
    assert.match(html, /<p[^>]*role="status"[^>]*aria-live="polite"[^>]*>불러오는 중입니다<\/p>/);
    assert.doesNotMatch(html, /<main[^>]*role=/);
  });

  it("불러오는 중 글자가 있다", () => {
    assert.match(html, /불러오는 중입니다/);
  });

  it("점 묶음은 aria-hidden 이고 점이 셋", () => {
    assert.match(html, /<div[^>]*aria-hidden="true"/);
    assert.equal((html.match(/animate-pulse/g) ?? []).length, 3);
  });

  it("움직임을 줄인 사용자에게는 점 깜빡임을 끈다", () => {
    assert.equal((html.match(/motion-reduce:animate-none/g) ?? []).length, 3);
  });

  it("300ms 뒤에 나타난다(빠른 이동에서 번쩍이지 않게)", () => {
    assert.match(html, /\[animation-delay:300ms\]/);
    assert.match(html, /class="rise /);
  });
});

describe("경로 안 이동용 loading.tsx 일곱", () => {
  // 같은 경로 조각 안의 이동은 루트 대기 화면이 안 뜬다(loading.tsx 머리 주석).
  // 그래서 이 폴더들에 루트 것을 다시 내보낸다. 빈 화면이나 다른 것을 내보내면
  // 그 이동에서 다시 "멈춘 앱" 이 된다.
  const folders = ["learn", "learn/words", "learn/sentences", "test/(hub)", "test/daily", "test/review", "board"];

  it("test 폴더와 몰입 화면 폴더에는 두지 않는다(문제 화면 진입 장막이 대기 화면 위에서 소모된다)", () => {
    for (const folder of ["test", "test/round", "test/words", "test/sentences"]) {
      assert.equal(existsSync(new URL(`./${folder}/loading.tsx`, import.meta.url)), false, folder);
    }
  });

  for (const folder of folders) {
    it(`${folder}/loading.tsx 는 루트 Loading 그대로다`, async () => {
      const { default: Nested } = await import(`./${folder}/loading.tsx`);
      assert.equal(Nested, Loading);
    });
  }
});

describe("error.tsx", () => {
  let retried = 0;
  const props = { error: leaky, unstable_retry: () => void (retried += 1) };
  const html = renderToStaticMarkup(createElement(RootError, props));

  it("한국어 제목과 안내", () => {
    assert.match(html, /<h1[^>]*>문제가 생겼습니다<\/h1>/);
    assert.match(html, /화면을 불러오지 못했습니다/);
  });

  it("다시 시도 버튼(type=button)과 홈 링크", () => {
    assert.match(html, /<button type="button"[^>]*>다시 시도<\/button>/);
    assert.match(html, new RegExp(`<a[^>]*href="${routes.home}"[^>]*>홈으로</a>`));
  });

  it("오류 메시지·digest 가 화면에 안 나온다", () => {
    assert.doesNotMatch(html, /ECONNREFUSED|10\.0\.0\.5|Traceback|abc123/);
  });

  it("다시 시도는 unstable_retry 를 한 번 부른다", () => {
    const [button] = findButtons(treeOf(RootError, props));
    assert.ok(button, "버튼을 못 찾았다");
    button.props.onClick?.();
    assert.equal(retried, 1);
  });
});

describe("global-error.tsx", () => {
  let retried = 0;
  const props = { error: leaky, unstable_retry: () => void (retried += 1) };
  const html = renderToStaticMarkup(createElement(GlobalError, props));

  it("html lang=ko 와 body 를 직접 그린다", () => {
    assert.match(html, /<html lang="ko"/);
    assert.match(html, /<body[^>]*>/);
  });

  it("title 이 있다(metadata 를 못 쓰는 파일)", () => {
    assert.match(html, /<title>문제가 생겼습니다<\/title>/);
  });

  it("제목·안내·다시 시도 버튼", () => {
    assert.match(html, /<h1[^>]*>문제가 생겼습니다<\/h1>/);
    assert.match(html, /화면을 불러오지 못했습니다/);
    assert.match(html, /<button type="button"[^>]*>다시 시도<\/button>/);
  });

  it("홈 링크는 페이지를 통째로 새로 받는 a href=/ 다(다시 그려도 같은 오류가 날 때)", () => {
    assert.match(html, /<a href="\/"[^>]*>홈으로<\/a>/);
  });

  it("viewport meta 를 직접 둔다(layout 의 것이 같이 사라진다)", () => {
    assert.match(html, /<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/);
  });

  it("body 가 한글을 낱말 단위로 끊는다(globals.css 의 keep-all 이 안 온다)", () => {
    assert.match(html, /<body[^>]*style="[^"]*word-break:keep-all/);
  });

  it("CSS 변수에 기대지 않는다(globals.css 가 안 온다)", () => {
    assert.doesNotMatch(html, /var\(--/);
  });

  it("오류 메시지·digest 가 화면에 안 나온다", () => {
    assert.doesNotMatch(html, /ECONNREFUSED|10\.0\.0\.5|Traceback|abc123/);
  });

  it("버튼 두께와 갈색 버튼 글자 크기가 globals.css 의 값과 같다", () => {
    // globals.css 가 안 오는 파일이라 값을 손으로 옮겨 적었다. 토큰 쪽을 바꾸고
    // 여기를 잊으면 이 화면만 납작한 버튼이 된다.
    const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8");
    const token = (name: string): string => {
      const m = css.match(new RegExp(`${name}:\\s*([^;]+);`));
      assert.ok(m, `${name} 토큰을 못 찾았다`);
      return m[1].trim();
    };
    const lift = token("--lift-button").replace("var(--brand-deep)", token("--brand-deep"));
    const liftPaper = token("--lift-button-paper");
    const styleOf = (open: RegExp): string => html.match(open)?.[1] ?? "";
    const retryStyle = styleOf(/<button[^>]*style="([^"]*)"/);
    const homeStyle = styleOf(/<a href="\/"[^>]*style="([^"]*)"/);
    assert.ok(retryStyle.includes(`box-shadow:${lift};`), `다시 시도: ${retryStyle}`);
    assert.ok(homeStyle.includes(`box-shadow:${liftPaper};`), `홈으로: ${homeStyle}`);
    assert.match(css, /\.dv-btn\[style\*="--lift-button\)"\]\s*\{\s*font-size:\s*19px/);
    // font:inherit 묶음은 앞에 온 font-size 를 지운다. 그래서 순서까지 본다.
    assert.match(retryStyle, /font:inherit;.*font-size:19px;/, `다시 시도: ${retryStyle}`);
  });

  it("다시 시도는 unstable_retry 를 한 번 부른다", () => {
    const [button] = findButtons(treeOf(GlobalError, props));
    assert.ok(button, "버튼을 못 찾았다");
    button.props.onClick?.();
    assert.equal(retried, 1);
  });
});
