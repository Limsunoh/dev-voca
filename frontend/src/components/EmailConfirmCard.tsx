"use client";

import Link from "next/link";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import type { ConfirmState } from "@/app/profile/email/[token]/actions";

/**
 * 확인 링크를 열었을 때 보이는 카드.
 *
 * 버튼을 눌러야 바뀐다. 화면을 여는 것만으로 처리하면 메일 서비스의 링크
 * 검사기가 먼저 열어 사용자가 누르기도 전에 끝나고, 그러면 본인이
 * 눌렀다는 증거가 없어진다 - 확인 절차를 둔 이유가 사라진다.
 */
export function EmailConfirmCard({
  action,
  token,
}: {
  action: (prev: ConfirmState, formData: FormData) => Promise<ConfirmState>;
  token: string;
}) {
  const [state, formAction] = useActionState<ConfirmState, FormData>(
    action,
    {},
  );

  if (state.changedTo) {
    return (
      <div
        className="dv-card grid gap-4 p-5"
        style={{
          background: "var(--paper)",
          borderRadius: "var(--radius-2xl)",
          boxShadow: "var(--lift-card)",
        }}
      >
        <p
          role="status"
          className="rounded-[var(--radius-xl)] p-3 text-sm"
          style={{
            background: "var(--correct-soft)",
            color: "var(--correct-deep)",
          }}
        >
          이메일을 바꿨습니다. 이제{" "}
          <span className="font-mono">{state.changedTo}</span> 로 로그인합니다.
        </p>

        {/* 다른 기기에서 로그아웃된다는 것을 알린다. 안 알리면 폰에서
            튕긴 것을 보고 무엇이 잘못됐다고 생각한다. 이 기기가 같은 계정으로
            로그인해 있지 않았으면 쿠키를 그대로 뒀으므로 다시 로그인하라고 한다. */}
        <p className="text-xs" style={{ color: "var(--text-dim)" }}>
          {state.signedIn
            ? "안전을 위해 다른 기기에서는 로그아웃됩니다. 이 기기는 그대로 쓰시면 됩니다."
            : "바뀐 계정은 안전을 위해 모든 기기에서 로그아웃됩니다. 새 주소로 다시 로그인해 주세요."}
        </p>

        {/* 로그인을 이어 가지 않은 기기는 내정보 대신 로그인 화면으로 보낸다. 로그인이
            없거나 끊긴 기기는 로그인 폼이 뜬다. 다른 계정으로 로그인해 있던 기기는 /login 이
            그 사람의 홈으로 돌려보낸다 - 원래 그 계정으로 쓰던 중이라 그것이 맞다. */}
        <Link
          href={state.signedIn ? "/profile" : "/login"}
          className="dv-btn flex w-full items-center justify-center rounded-[var(--radius-pill)] px-4 text-center focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus sm:w-auto sm:justify-self-start sm:px-8"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--brand)",
              color: "var(--text-on-color)",
              border: 0,
              textDecoration: "none",
              "--lift": "var(--lift-button)",
              fontWeight: "var(--weight-black)",
            } as React.CSSProperties
          }
        >
          {state.signedIn ? "내정보로" : "로그인하러 가기"}
        </Link>
      </div>
    );
  }

  return (
    <form
      action={formAction}
      className="dv-card grid gap-4 p-5"
      style={{
        background: "var(--paper)",
        borderRadius: "var(--radius-2xl)",
        boxShadow: "var(--lift-card)",
      }}
    >
      <input type="hidden" name="token" value={token} />

      <p className="text-sm" style={{ color: "var(--text-body)" }}>
        아래 버튼을 누르면 이메일 변경이 끝납니다.
      </p>

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

      <ConfirmButton />
    </form>
  );
}

/**
 * 확인 버튼.
 *
 * 별도 컴포넌트인 이유: useFormStatus 는 form 안쪽에서만 상태를 읽는다.
 */
function ConfirmButton() {
  const { pending } = useFormStatus();

  return (
    <button
      type="submit"
      disabled={pending}
      className="dv-btn w-full rounded-[var(--radius-pill)] px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60 sm:w-auto sm:justify-self-start sm:px-8"
      style={
        {
          minHeight: "var(--hit-min)",
          background: "var(--brand)",
          color: "var(--text-on-color)",
          border: 0,
          "--lift": "var(--lift-button)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
        } as React.CSSProperties
      }
    >
      {pending ? "바꾸는 중" : "이메일 바꾸기"}
    </button>
  );
}
