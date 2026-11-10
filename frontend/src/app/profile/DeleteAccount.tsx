"use client";

import { useActionState, useEffect, useId, useRef, useState } from "react";

import type { DeleteAccountState } from "@/app/profile/actions";

type Props = {
  action: (
    prev: DeleteAccountState,
    formData: FormData,
  ) => Promise<DeleteAccountState>;
  /** 비밀번호를 쓸 수 있는 계정인가. 아니면 이메일을 다시 입력받는다. */
  hasPassword: boolean;
  email: string;
};

/**
 * 계정 삭제 버튼과 확인 창.
 *
 * 누르는 곳은 버튼과 창의 삭제, 두 번뿐이다. 다시 묻는 창을 더하거나 잃는
 * 것을 부풀리면 나가려는 사람을 붙잡는 화면이 된다.
 *
 * LeaveConfirm 을 쓰지 않는 이유: 그 창은 누르는 순간 닫힌다. 여기는 비밀번호를
 * 틀리면 창에 남아서 다시 쳐야 한다. 모양과 버튼 순서는 LeaveConfirm 과 같다.
 */
export function DeleteAccount(props: Props) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="dv-btn w-full rounded-[var(--radius-pill)] px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus sm:w-auto sm:px-8"
        style={
          {
            minHeight: "var(--hit-min)",
            background: "var(--paper)",
            color: "var(--coral-deep)",
            border: 0,
            "--lift": "var(--lift-button-paper)",
            fontWeight: "var(--weight-bold)",
          } as React.CSSProperties
        }
      >
        계정 삭제
      </button>
      {/* 열 때마다 새로 그린다. 창을 닫았다 다시 열면 지난 오류가 없어야 한다. */}
      {open && <DeleteDialog {...props} onClose={() => setOpen(false)} />}
    </>
  );
}

function DeleteDialog({
  action,
  hasPassword,
  email,
  onClose,
}: Props & { onClose: () => void }) {
  const [state, formAction, pending] = useActionState(action, {});
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const detailId = useId();
  const inputId = useId();
  const errorId = useId();
  const hintId = useId();
  const showError = Boolean(state.error) && !pending;
  const describedBy = [hasPassword && hintId, showError && errorId]
    .filter(Boolean)
    .join(" ");

  // 개발 모드(StrictMode)는 이 효과를 두 번 돌린다. 이미 열린 창에 다시
  // showModal 을 부르면 브라우저에 따라 예외가 난다.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  // 실패하면 다시 칠 칸으로 돌아온다. 제출 동안 버튼이 꺼져 포커스를 잃는다.
  useEffect(() => {
    if (state.error) inputRef.current?.focus();
  }, [state]);

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      aria-describedby={detailId}
      // 삭제를 보낸 뒤에는 닫히지 않게 다시 연다. 닫혀도 삭제는 진행되어서
      // 취소된 줄 알게 된다. cancel 을 막는 것으로는 부족하다. 크롬은 Esc 를
      // 연달아 누르면 두 번째부터 막지 못하게 한다.
      onClose={() => {
        if (pending) dialogRef.current?.showModal();
        else onClose();
      }}
      className="pop m-auto w-[min(22rem,calc(100vw-2rem))] p-6 backdrop:bg-[rgb(25_21_18/0.72)]"
      style={{
        background: "var(--paper)",
        color: "var(--foreground)",
        borderRadius: "var(--radius-sheet)",
        border: 0,
        boxShadow: "var(--lift-sheet)",
      }}
    >
      <h2
        id={titleId}
        style={{
          fontSize: "var(--text-lg)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
          color: "var(--foreground)",
        }}
      >
        계정을 삭제할까요?
      </h2>
      <p
        id={detailId}
        className="mt-2 text-sm"
        style={{
          lineHeight: "var(--leading-relaxed)",
          color: "var(--text-muted)",
        }}
      >
        점수, 오답 노트, 순위 기록이 함께 지워지고 되돌릴 수 없습니다.
      </p>

      <form action={formAction} className="mt-4">
        <label
          htmlFor={inputId}
          className="block text-sm [overflow-wrap:anywhere]"
          style={{ color: "var(--text-body)", fontWeight: "var(--weight-bold)" }}
        >
          {hasPassword
            ? "현재 비밀번호를 입력해주세요"
            : `가입한 이메일(${email})을 입력해주세요`}
        </label>
        <input
          ref={inputRef}
          id={inputId}
          name={hasPassword ? "current_password" : "email"}
          type={hasPassword ? "password" : "email"}
          autoComplete={hasPassword ? "current-password" : "off"}
          required
          aria-invalid={showError ? true : undefined}
          aria-describedby={describedBy || undefined}
          className="mt-1 w-full rounded-[var(--radius-xl)] px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={{
            minHeight: "var(--hit-floor)",
            background: "var(--surface-field)",
            color: "var(--foreground)",
            border: "1px solid var(--text-muted)",
          }}
        />
        {/* 비밀번호 재설정 기능이 없어서, 잊은 사람이 지울 길을 여기서 알린다. */}
        {hasPassword && (
          <p
            id={hintId}
            className="mt-1.5 text-xs"
            style={{ color: "var(--text-muted)" }}
          >
            비밀번호를 모르면 가입한 이메일로 vhtmxjooo@gmail.com 에 삭제를
            요청해주세요.
          </p>
        )}
        {/* 알림 자리는 항상 그린다. 내용과 함께 새로 생기면 화면 낭독기가
            그 등장을 대부분 안 읽는다. 제출 동안 지워 두어야, 같은 오류가
            다시 나도 새 소식으로 읽힌다. */}
        <div aria-live="polite">
          {showError && (
            <p
              id={errorId}
              className="mt-2 text-sm"
              style={{ color: "var(--coral-deep)" }}
            >
              {state.error}
            </p>
          )}
        </div>

        <div className="mt-6 flex gap-2">
          <button
            type="button"
            disabled={pending}
            onClick={() => dialogRef.current?.close()}
            className="dv-btn flex flex-1 items-center justify-center px-4 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60"
            style={
              {
                minHeight: "var(--hit-min)",
                background: "var(--brand)",
                color: "var(--text-on-color)",
                border: 0,
                borderRadius: "var(--radius-pill)",
                fontWeight: "var(--weight-black)",
                "--lift": "var(--lift-button)",
              } as React.CSSProperties
            }
          >
            취소
          </button>
          <button
            type="submit"
            disabled={pending}
            className="dv-btn flex flex-1 items-center justify-center px-4 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60"
            style={
              {
                minHeight: "var(--hit-min)",
                background: "var(--paper)",
                color: "var(--coral-deep)",
                border: 0,
                borderRadius: "var(--radius-pill)",
                fontWeight: "var(--weight-black)",
                "--lift": "var(--lift-button-paper)",
              } as React.CSSProperties
            }
          >
            {pending ? "삭제하는 중" : "삭제"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
