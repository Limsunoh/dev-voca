"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import type { EmailChangeState } from "@/app/profile/actions";

/**
 * 이메일을 바꾸는 카드.
 *
 * 접어둔 채로 시작한다. 이메일 변경은 계정당 몇 번 없는 일인데, 칸을 늘
 * 펼쳐두면 자주 쓰는 이름·사진보다 아래에서 자리만 차지한다. 게다가
 * 비밀번호 칸이 항상 떠 있으면 브라우저 비밀번호 관리자가 여기를 로그인
 * 폼으로 오해해 채워 넣는다.
 */
export function EmailCard({
  action,
  currentEmail,
  hasPassword,
}: {
  action: (
    prev: EmailChangeState,
    formData: FormData,
  ) => Promise<EmailChangeState>;
  currentEmail: string;
  /**
   * 비밀번호를 쓸 수 있는 계정인가.
   *
   * 구글로만 가입하면 비밀번호가 없다. 그 사람에게 "현재 비밀번호" 를
   * 물으면 만든 적 없는 것을 찾게 되므로, 아예 다른 안내를 보여준다.
   */
  hasPassword: boolean;
}) {
  const [state, formAction] = useActionState<EmailChangeState, FormData>(
    action,
    {},
  );

  return (
    <details
      className="dv-card p-5"
      style={{
        background: "var(--paper)",
        borderRadius: "var(--radius-2xl)",
        boxShadow: "var(--lift-card)",
      }}
    >
      <summary
        className="cursor-pointer list-none text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        style={{
          color: "var(--text-body)",
          fontWeight: "var(--weight-bold)",
        }}
      >
        이메일 바꾸기
      </summary>

      {/* 지금 주소를 접힌 자리 바로 아래 둔다. 무엇을 바꾸는지 보이지
          않으면 새 주소를 적기 전에 위로 올라가 확인하게 된다. */}
      <p className="mt-3 text-xs" style={{ color: "var(--text-dim)" }}>
        지금 주소{" "}
        <span className="font-mono" style={{ color: "var(--text-body)" }}>
          {currentEmail}
        </span>
      </p>

      {!hasPassword ? (
        // 구글 전용 계정. 여기서 폼을 보여주면 무엇을 넣어도 실패한다.
        <p className="mt-4 text-sm" style={{ color: "var(--text-muted)" }}>
          구글로 가입한 계정입니다. 이메일을 바꾸려면 비밀번호를 먼저
          설정해주세요.
        </p>
      ) : (
        <form action={formAction} className="mt-4 grid gap-4">
          {/* 브라우저 비밀번호 관리자에게 "어느 계정인가" 를 알려준다.
              없으면 아래 비밀번호 칸을 보고도 어느 항목에 붙일지 몰라
              저장을 제안하지 않거나 엉뚱한 항목에 붙인다.

              **지금 주소**를 넣는다. 새 주소를 넣으면 안 된다 - 아직 그
              주소의 계정이 아니라, 관리자가 존재하지 않는 계정으로
              항목을 만든다.

              hidden 이 아니라 sr-only 인 이유: hidden 인 칸은 힌트로
              안 읽는 브라우저가 있다. 대신 tabIndex 와 aria-hidden 으로
              사람에게는 안 걸리게 한다 - 이 칸은 관리자만 읽으면 된다. */}
          <input
            type="text"
            name="username"
            value={currentEmail}
            autoComplete="username"
            readOnly
            tabIndex={-1}
            aria-hidden="true"
            className="sr-only"
          />

          {/* id 에 em- 을 붙인다. 같은 화면에 비밀번호 변경 카드가 있고,
              둘 다 "현재 비밀번호" 칸을 가진다. id 가 겹치면 label 의 for 가
              문서에서 먼저 나온 칸을 가리켜, 아래 카드의 라벨을 눌렀는데
              위 카드로 포커스가 간다.

              name 은 그대로 둔다. 서버가 읽는 키이고, 폼이 다르므로 겹쳐도
              제출에는 섞이지 않는다. */}
          <div>
            <label
              htmlFor="em-new-email"
              className="block text-sm"
              style={{
                color: "var(--text-body)",
                fontWeight: "var(--weight-bold)",
              }}
            >
              새 이메일
            </label>
            <input
              id="em-new-email"
              name="new_email"
              type="email"
              required
              // 백엔드가 254자에서 거절한다. 여기가 더 크면 다 적고 나서
              // 실패한다.
              maxLength={254}
              autoComplete="email"
              className="mt-2 w-full rounded-[var(--radius-xl)] px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
              style={{
                minHeight: "var(--hit-floor)",
                background: "var(--surface-field)",
                color: "var(--foreground)",
                border: 0,
                boxShadow: "var(--lift-card)",
              }}
            />
          </div>

          <div>
            <label
              htmlFor="em-current-password"
              className="block text-sm"
              style={{
                color: "var(--text-body)",
                fontWeight: "var(--weight-bold)",
              }}
            >
              현재 비밀번호
            </label>
            <input
              id="em-current-password"
              name="current_password"
              type="password"
              required
              // current-password 로 둔다. new-password 로 두면 관리자가
              // 새 비밀번호를 만들라고 제안한다.
              autoComplete="current-password"
              aria-describedby="em-hint"
              className="mt-2 w-full rounded-[var(--radius-xl)] px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
              style={{
                minHeight: "var(--hit-floor)",
                background: "var(--surface-field)",
                color: "var(--foreground)",
                border: 0,
                boxShadow: "var(--lift-card)",
              }}
            />
            <p
              id="em-hint"
              className="mt-2 text-xs"
              style={{ color: "var(--text-dim)" }}
            >
              새 주소로 확인 메일을 보냅니다. 그 링크를 열어야 바뀝니다.
            </p>
          </div>

          {state.error && (
            <p
              role="alert"
              className="rounded-[var(--radius-xl)] p-3 text-sm"
              style={{
                background: "var(--wrong-soft)",
                color: "var(--coral-deep)",
              }}
            >
              {state.error}
            </p>
          )}

          {state.sentTo && !state.error && (
            // **"저장했습니다" 라고 쓰지 않는다.** 아직 안 바뀌었다.
            // 저장으로 읽히면 메일을 안 열고 떠나고, 다음 로그인에서
            // 옛 주소로 들어가려다 막힌다.
            <p
              role="status"
              className="rounded-[var(--radius-xl)] p-3 text-sm"
              style={{
                background: "var(--correct-soft)",
                color: "var(--correct-deep)",
              }}
            >
              {state.sentTo} 로 확인 메일을 보냈습니다. 메일의 링크를 열면
              변경이 끝납니다.
            </p>
          )}

          <SendButton />
        </form>
      )}
    </details>
  );
}

/**
 * 확인 메일 보내기 버튼.
 *
 * 별도 컴포넌트인 이유: useFormStatus 는 form 안쪽에서만 상태를 읽는다.
 * 폼과 같은 컴포넌트에 두면 pending 이 항상 false 다.
 */
function SendButton() {
  const { pending } = useFormStatus();

  return (
    <button
      type="submit"
      disabled={pending}
      // 흰 버튼이다. 이 화면의 코랄은 위쪽 프로필 저장이 가진다 - 둘 다
      // 코랄이면 가끔 쓰는 이메일 변경이 주된 동작으로 보인다.
      className="dv-btn w-full rounded-[var(--radius-pill)] px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60 sm:w-auto sm:justify-self-start sm:px-8"
      style={
        {
          minHeight: "var(--hit-min)",
          background: "var(--paper)",
          color: "var(--foreground)",
          border: 0,
          "--lift": "var(--lift-button-paper)",
          fontWeight: "var(--weight-bold)",
        } as React.CSSProperties
      }
    >
      {pending ? "보내는 중" : "확인 메일 보내기"}
    </button>
  );
}
