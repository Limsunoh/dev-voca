/**
 * 로그인·가입 화면의 "로그인 없이 둘러보기" 가 필수 항목을 건너뛰지 않는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 전에는 홈(/)으로 가는 링크였다. 홈은 로그인도 안 했고 게스트도 안 고른
 * 사람을 /start 로 돌려보내서, 거기서 "게스트로 둘러보기" 를 한 번 더 눌러야
 * 했다. 그 다음에는 게스트 action 을 바로 부르는 폼이었는데, 그러면 시작 화면이
 * 묻는 두 항목을 여기로 돌아서 건너뛸 수 있었다. 지금은 시트를 여는 버튼이다.
 *
 * 어떤 action 이 걸렸는지 보는 방법: "use server" 파일은 Next 런타임 밖에서
 * import 할 수 없어 대역으로 갈아끼운다. 대역 함수에 $$FORM_ACTION 을 달면
 * React 서버 렌더가 서버 액션처럼 그 값을 form 의 action 속성으로 쓴다.
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

// 구글 버튼(GoogleButton)이 부르는 서버 액션. 실제 파일은 서버 전용 모듈을 불러
// 테스트에서 읽히지 않는다. 준비가 null 이면 버튼은 예전 링크를 그대로 보인다.
mock.module("@/app/(auth)/google-actions", {
  namedExports: {
    prepareGoogleButton: async () => null,
    googleCredentialAction: async () => {},
  },
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

      it("시트를 여는 버튼이고, 묻기 전에는 게스트 action 이 그려지지 않는다", () => {
        assert.match(html, /<button[^>]*type="button"[^>]*>로그인 없이 둘러보기</);
        assert.doesNotMatch(html, new RegExp(`action="${GUEST_MARK}"`));
      });
    });
  }
});
