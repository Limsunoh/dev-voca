/**
 * 키보드 포커스 테두리가 빠졌던 세 자리가 다시 테두리를 잃지 않는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 1. 익히기 목록(/learn/words, /learn/sentences)의 검색칸. 입력칸 자체는
 *    outline-none 이라(칸 안에 작은 상자가 하나 더 생기지 않게) 테두리를
 *    감싼 흰 칸이 has-[:focus-visible] 로 대신 그린다. 흰 칸 쪽 클래스가
 *    빠지면 Tab 으로 들어가도 아무 표시가 없다. 850e995 에서 한 번 그렇게
 *    빠졌다.
 * 2. 로그인·가입 화면 아래 "가입하기"/"로그인" 전환 링크. 클래스가 없으면
 *    브라우저 기본 테두리가 나와 앱의 다른 링크와 색이 달라진다.
 * 3. 처리방침·약관(/privacy, /terms)의 링크 전부. 링크마다 클래스를 달지 않고
 *    LegalDoc 의 바깥 main 이 [&_a:focus-visible] 로 안쪽 a 전부에 준다.
 *    그래서 "main 에 클래스가 있다" 와 "모든 링크가 그 main 안에 있다" 를
 *    같이 본다. 본문에 끼워 넣는 ContactEmail 같은 링크도 여기서 덮인다.
 *
 * 색 클래스가 outline-focus 하나뿐인지는 focus-ring.test.mts 가 본다.
 * 여기는 "이 자리에 테두리가 있다" 만 본다.
 */
import assert from "node:assert/strict";
import { describe, it, mock } from "node:test";

// AuthForm 이 import 하는 "use server" 파일은 Next 밖에서 못 읽어 대역으로
// 바꾼다. SearchInput 은 라우터 훅을 쓴다. 둘 다 import 전에 등록한다.
mock.module("@/app/start/actions", {
  namedExports: { continueAsGuestAction: async () => {} },
});
mock.module("next/navigation", {
  namedExports: {
    useRouter: () => ({ push() {} }),
    useSearchParams: () => new URLSearchParams(),
  },
});

const { createElement } = await import("react");
const { renderToStaticMarkup } = await import("react-dom/server");
const { AuthForm } = await import("./AuthForm");
const { SearchInput } = await import("./SearchInput");
const { default: TermsPage } = await import("../app/terms/page");
const { default: PrivacyPage } = await import("../app/privacy/page");

/** 여는 태그 하나의 class 를 낱말 목록으로. */
function classesOf(tag: string): string[] {
  // 속성 안의 & 는 &amp; 로 나온다([&_a:...] 같은 클래스).
  const raw = (/\sclass="([^"]*)"/.exec(tag)?.[1] ?? "").replaceAll("&amp;", "&");
  return raw.split(/\s+/).filter(Boolean);
}

/** 키보드 포커스 때 outline-focus 색 테두리를 그리는 클래스 묶음.
 *  prefix 는 "focus-visible:" 또는 "has-[:focus-visible]:". */
function ringClasses(prefix: string): string[] {
  return ["outline", "outline-2", "outline-focus"].map((name) => `${prefix}${name}`);
}

function assertRing(tag: string, prefix: string) {
  const classes = classesOf(tag);
  const missing = ringClasses(prefix).filter((name) => !classes.includes(name));
  assert.deepEqual(missing, [], `빠진 클래스: ${missing.join(" ")}\n태그: ${tag}`);
}

describe("검색칸의 포커스 테두리", () => {
  for (const basePath of ["/learn/words", "/learn/sentences"]) {
    describe(basePath, () => {
      const html = renderToStaticMarkup(createElement(SearchInput, { basePath }));
      const inputAt = html.indexOf("<input");
      const input = /<input[^>]*>/.exec(html)?.[0] ?? "";
      // 입력칸 바로 앞의 마지막 div 가 입력칸을 감싼 흰 칸이다.
      const wrapper = [...html.slice(0, inputAt).matchAll(/<div[^>]*>/g)].at(-1)?.[0] ?? "";

      it("입력칸이 그려진다 - 아래 검사가 빈 문자열로 통과하지 않는다", () => {
        assert.ok(inputAt > 0, html);
        assert.ok(wrapper, `감싼 div 가 없다: ${html}`);
      });

      it("입력칸은 outline-none 이다 - 테두리는 흰 칸이 맡는다", () => {
        assert.ok(classesOf(input).includes("outline-none"), input);
      });

      it("감싼 흰 칸이 안쪽 포커스를 받아 outline-focus 테두리를 그린다", () => {
        assertRing(wrapper, "has-[:focus-visible]:");
      });

      it("흰 칸 테두리는 둥근 모서리 바깥으로 띄운다", () => {
        assert.ok(classesOf(wrapper).includes("has-[:focus-visible]:outline-offset-2"), wrapper);
      });

      it("검색 버튼도 자기 테두리를 갖는다", () => {
        const button = /<button[^>]*type="submit"[^>]*>/.exec(html)?.[0] ?? "";
        assertRing(button, "focus-visible:");
      });
    });
  }
});

describe("로그인·가입 전환 링크의 포커스 테두리", () => {
  async function noopAction(): Promise<{ error: null }> {
    return { error: null };
  }

  const CASES: Array<[string, "login" | "signup", string | undefined, string]> = [
    ["로그인 화면의 가입하기", "login", undefined, "/signup"],
    ["가입 화면의 로그인", "signup", undefined, "/login"],
    ["next 가 붙은 로그인 화면", "login", "/board", "/signup?next=%2Fboard"],
  ];

  for (const [label, mode, next, href] of CASES) {
    it(label, () => {
      const html = renderToStaticMarkup(
        createElement(AuthForm, { mode, action: noopAction as never, next, googleFailed: false }),
      );
      const link = new RegExp(`<a[^>]*href="${href.replace(/[?]/g, "\\?")}"[^>]*>`).exec(html)?.[0];
      assert.ok(link, `${href} 링크가 없다: ${html}`);
      assertRing(link, "focus-visible:");
      assert.ok(classesOf(link).includes("focus-visible:outline-offset-2"), link);
    });
  }
});

describe("처리방침·약관 링크의 포커스 테두리", () => {
  const PAGES: Array<[string, () => unknown]> = [
    ["/terms", TermsPage],
    ["/privacy", PrivacyPage],
  ];

  for (const [path, Page] of PAGES) {
    describe(path, () => {
      const html = renderToStaticMarkup(createElement(Page as () => null));
      const mainOpen = /<main[^>]*>/.exec(html);
      const mainStart = mainOpen?.index ?? -1;
      const mainEnd = html.indexOf("</main>");
      const anchors = [...html.matchAll(/<a\s[^>]*>/g)];

      it("바깥 main 이 안쪽 링크에 outline-focus 테두리를 준다", () => {
        assert.ok(mainOpen, `main 이 없다: ${html.slice(0, 300)}`);
        assertRing(mainOpen[0], "[&_a:focus-visible]:");
        assert.ok(classesOf(mainOpen[0]).includes("[&_a:focus-visible]:outline-offset-2"), mainOpen[0]);
      });

      it("링크가 실제로 있다 - 목차·메일 주소·글꼴 라이선스까지", () => {
        assert.ok(anchors.length >= 15, `링크 ${anchors.length}개`);
        assert.ok(anchors.some((m) => m[0].includes('href="mailto:')), "메일 주소 링크가 없다");
        assert.ok(anchors.some((m) => m[0].includes('href="#')), "목차 링크가 없다");
        assert.ok(anchors.some((m) => m[0].includes("openfontlicense.org")), "글꼴 라이선스 링크가 없다");
      });

      it("모든 링크가 그 main 안에 있다 - 밖에 있으면 테두리를 못 받는다", () => {
        const outside = anchors
          .filter((m) => m.index! < mainStart || m.index! > mainEnd)
          .map((m) => m[0]);
        assert.deepEqual(outside, []);
      });

      it("링크가 스스로 테두리를 끄지 않는다", () => {
        const off = anchors.map((m) => m[0]).filter((tag) => /\boutline-none\b/.test(tag));
        assert.deepEqual(off, []);
      });
    });
  }
});
