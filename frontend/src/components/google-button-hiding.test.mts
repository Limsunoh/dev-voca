/**
 * 구글 버튼 자리(GoogleButton 안의 box)를 숨기는 방식.
 *
 * 실행: cd frontend && npm test
 *
 * box 를 visibility·display 로 숨기면 구글 iframe 이 크기를 알리지 않는다.
 * 우리는 iframe 이 크기를 가져야 box 를 보이게 하므로, 서로 기다리다 iframe 이
 * 0x0 으로 남고 예전 링크가 영영 걷히지 않는다(11-13 운영). 실제로 크기가
 * 생기는지는 브라우저에서만 보인다. 여기서는 숨기는 방식만 못 박는다.
 *
 * 지키는 것:
 *   - 나타나기 전: box 는 투명도 0 과 inert 로만 숨긴다. visibility·display·
 *     hidden 속성으로 숨기거나 폭·높이를 0 으로 만들지 않는다(폭을 재고 iframe
 *     이 크기를 알려야 한다). 예전 링크는 DOM 에서 box 다음에 absolute 로 놓여
 *     화면에서는 그 위를 덮는다. 기다리는 동안은 흐리고(투명도 0.5) inert 라
 *     탭을 받지 않는다. 6초가 지나거나 못 뜨는 것이 확실하면 탭을 받는데, 그
 *     상태는 google-button-loading.test.mts 가 본다.
 *   - 나타난 뒤: box 는 투명하지도 inert 도 아니고, 예전 링크는 사라진다.
 *
 * 하네스: renderToStaticMarkup 으로 그린다. "나타난 뒤" 는 useState 의 false
 * 초깃값을 true 로 바꿔 흉내 낸다(scriptReady·shown·gaveUp 모두 false 로
 * 시작하고, 서버 렌더에서는 효과가 돌지 않아 scriptReady 는 마크업에 영향이
 * 없다).
 */
import assert from "node:assert/strict";
import { describe, it, mock } from "node:test";

const realReact = await import("react");
let forceShown = false;

mock.module("react", {
  defaultExport: realReact.default,
  namedExports: {
    ...realReact,
    useState<T>(init: T) {
      if (forceShown && init === false) return [true, () => {}];
      return realReact.useState(init);
    },
  },
});
mock.module("next/script", { defaultExport: () => null });
mock.module("@/app/(auth)/google-actions", {
  namedExports: {
    prepareGoogleButton: async () => null,
    googleCredentialAction: async () => {},
  },
});

const { createElement } = realReact;
const { renderToStaticMarkup } = await import("react-dom/server");
const { GoogleButton } = await import("./GoogleButton");

function render(shown: boolean): string {
  forceShown = shown;
  try {
    return renderToStaticMarkup(
      createElement(GoogleButton, {
        context: "signup",
        consent: true,
        fallback: createElement("a", { href: "/api/auth/google?consent=1" }, "구글로 계속하기"),
      }),
    );
  } finally {
    forceShown = false;
  }
}

/** 구글이 버튼을 그려 넣는 box(바깥 div 의 첫 자식 div)의 여는 태그. */
function boxTag(html: string): string {
  const m = html.match(/^<div[^>]*>(<div[^>]*>)/);
  assert.ok(m, `box 를 찾지 못했다: ${html}`);
  return m[1];
}

function styleOf(tag: string): string {
  return tag.match(/style="([^"]*)"/)?.[1] ?? "";
}

describe("구글 버튼 자리 - 나타나기 전", () => {
  const html = render(false);
  const box = boxTag(html);
  const style = styleOf(box);

  it("투명도 0 과 inert 로 숨긴다", () => {
    assert.match(style, /(^|;)opacity:0(;|$)/);
    assert.match(box, /\sinert=""/);
  });

  it("구글 iframe 이 '안 보인다' 고 볼 방식으로는 숨기지 않는다", () => {
    assert.doesNotMatch(style, /visibility/);
    assert.doesNotMatch(style, /display:\s*none/);
    assert.doesNotMatch(style, /(^|;)(width|height|max-width|max-height):0(px)?(;|$)/);
    assert.doesNotMatch(style, /content-visibility/);
    // hidden 속성은 display: none 과 같다. inert 옆에 붙이기 쉬운 되돌림이다.
    assert.doesNotMatch(box, /\shidden(=|\s|>)/);
    const cls = box.match(/class="([^"]*)"/)?.[1] ?? "";
    for (const bad of ["hidden", "invisible", "sr-only", "collapse"]) {
      assert.ok(!cls.split(/\s+/).includes(bad), `box 에 ${bad} 클래스`);
    }
  });

  it("box 는 자리를 차지해 폭을 잴 수 있다", () => {
    assert.match(style, /min-height:var\(--hit-min\)/);
    assert.match(box, /class="[^"]*\bflex\b/);
    assert.doesNotMatch(box, /class="[^"]*\babsolute\b/);
  });

  it("예전 링크는 DOM 에서 box 다음(화면에서는 위)에 absolute 로 놓이고, 기다리는 동안은 흐리고 누를 수 없다", () => {
    const boxAt = html.indexOf(box);
    const linkAt = html.indexOf('<a href="/api/auth/google?consent=1"');
    const overlayTag = html.slice(0, linkAt).match(/<div[^>]*>$/)?.[0] ?? "";
    assert.ok(linkAt > boxAt, "예전 링크 덮개가 box 보다 뒤(위)에 있어야 한다");
    assert.match(overlayTag, /class="absolute inset-0"/);
    // 구글 버튼을 기다리는 동안 누르면 예전 방식으로 구글 화면에 간다(11-13 폰).
    assert.match(overlayTag, /\sinert=""/);
    assert.match(overlayTag, /opacity:0\.5/);
    // 보조기기에는 기다리는 중이라고 알린다.
    assert.match(html, /role="status"[^>]*>구글 로그인 버튼을 불러오는 중입니다/);
  });
});

describe("구글 버튼 자리 - 나타난 뒤", () => {
  const html = render(true);
  const box = boxTag(html);
  const style = styleOf(box);

  it("투명하지도 inert 도 아니다", () => {
    assert.doesNotMatch(style, /opacity/);
    assert.doesNotMatch(style, /visibility/);
    assert.doesNotMatch(box, /\sinert/);
  });

  it("예전 링크는 사라진다", () => {
    assert.doesNotMatch(html, /\/api\/auth\/google/);
    assert.doesNotMatch(html, /absolute inset-0/);
  });
});
