/**
 * 로그인·가입 화면의 "로그인 없이 둘러보기" 가 게스트 action 을 부르는 폼인지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 전에는 홈(/)으로 가는 링크였다. 홈은 로그인도 안 했고 게스트도 안 고른
 * 사람을 /start 로 돌려보내서, 거기서 "게스트로 둘러보기" 를 한 번 더 눌러야
 * 했다. 지금은 /start 와 같은 continueAsGuestAction 을 부르는 폼 버튼이다.
 *
 * 어떤 action 이 걸렸는지 보는 방법: "use server" 파일은 Next 런타임 밖에서
 * import 할 수 없어 대역으로 갈아끼운다. 대역 함수에 $$FORM_ACTION 을 달면
 * React 서버 렌더가 서버 액션처럼 그 값을 form 의 action 속성으로 쓴다. 그래서
 * 마크업에 표시 경로가 찍혀 있으면 "그 버튼이 그 action 을 부른다" 는 뜻이다.
 */
import assert from "node:assert/strict";
import { describe, it, mock } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

// ---------------------------------------------------------------------------
// 게스트 action 대역. AuthForm 을 import 하기 전에 등록해야 한다.
// ---------------------------------------------------------------------------

const GUEST_MARK = "/__guest_action__";

async function fakeGuestAction(): Promise<void> {}
Object.assign(fakeGuestAction, {
  $$FORM_ACTION: () => ({ name: undefined, action: GUEST_MARK, encType: undefined, method: "POST", data: null }),
});

mock.module("@/app/start/actions", {
  namedExports: { continueAsGuestAction: fakeGuestAction },
});

const { AuthForm } = await import("./AuthForm");

async function noopAction(): Promise<{ error: null }> {
  return { error: null };
}

function render(mode: "login" | "signup", next?: string): string {
  return renderToStaticMarkup(
    createElement(AuthForm, { mode, action: noopAction as never, next, googleFailed: false }),
  );
}

const CASES: Array<[string, "login" | "signup", string | undefined]> = [
  ["로그인", "login", undefined],
  ["가입", "signup", undefined],
  ["next 가 붙은 로그인", "login", "/board"],
];

describe("로그인 없이 둘러보기", () => {
  for (const [label, mode, next] of CASES) {
    describe(label, () => {
      const html = render(mode, next);

      it("링크가 아니다 (GET 으로 홈에 보내면 /start 를 한 번 더 거친다)", () => {
        assert.doesNotMatch(html, /<a[^>]*>로그인 없이 둘러보기</);
      });

      it("게스트 action 을 부르는 폼의 submit 버튼이다", () => {
        const form = html.match(/<form[^>]*action="([^"]*)"[^>]*>((?:(?!<\/form>).)*)<\/form>/g) ?? [];
        const guest = form.find((f) => f.includes("로그인 없이 둘러보기"));
        assert.ok(guest, "버튼을 감싼 form 을 못 찾았다");
        assert.match(guest, new RegExp(`action="${GUEST_MARK}"`));
        assert.match(guest, /<button[^>]*type="submit"[^>]*>로그인 없이 둘러보기</);
      });
    });
  }
});
