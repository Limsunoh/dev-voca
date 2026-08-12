"use client";

import Link from "next/link";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import type { FormState } from "@/app/(auth)/actions";

/**
 * 로그인·가입 폼.
 *
 * 둘의 구조가 같아 한 컴포넌트로 쓴다 - 이메일·비밀번호를 받아 서버로
 * 넘기고, 실패하면 그 자리에 이유를 보여준다. 다른 것은 제목과 버튼 문구,
 * 그리고 가입에만 있는 이름 칸뿐이다.
 *
 * 클라이언트 컴포넌트인 이유: 제출 중 버튼을 잠그고 에러를 그 자리에
 * 보여주려면 상태가 필요하다. 다만 실제 제출은 Server Action 이 받으므로
 * 토큰은 브라우저를 거치지 않는다.
 */

type Props = {
  mode: "login" | "signup";
  action: (prev: FormState, formData: FormData) => Promise<FormState>;
  /** 로그인 후 돌아갈 곳. */
  next?: string;
};

const COPY = {
  login: {
    title: "로그인",
    submit: "로그인",
    pending: "로그인하는 중",
    switchText: "계정이 없으신가요?",
    switchLabel: "가입하기",
    switchHref: "/signup",
  },
  signup: {
    title: "가입하기",
    submit: "가입하기",
    pending: "가입하는 중",
    switchText: "이미 계정이 있으신가요?",
    switchLabel: "로그인",
    switchHref: "/login",
  },
} as const;

export function AuthForm({ mode, action, next }: Props) {
  const [state, formAction] = useActionState<FormState, FormData>(action, {});
  const copy = COPY[mode];

  return (
    <div className="mx-auto w-full max-w-sm">
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
        {copy.title}
      </h1>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
        로그인하면 푼 문제와 틀린 단어가 기기를 옮겨도 이어집니다.
      </p>

      <form action={formAction} className="mt-8 grid gap-4">
        {next && <input type="hidden" name="next" value={next} />}

        <Field
          label="이메일"
          name="email"
          type="email"
          autoComplete="email"
          required
        />

        {mode === "signup" && (
          <Field
            label="이름"
            name="display_name"
            type="text"
            autoComplete="nickname"
            hint="화면에 보일 이름입니다. 비워두면 이메일 앞부분을 씁니다."
          />
        )}

        <Field
          label="비밀번호"
          name="password"
          type="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          required
          hint={
            mode === "signup"
              ? "여덟 자 이상, 이메일과 너무 비슷하지 않게."
              : undefined
          }
        />

        {state.error && (
          <p
            role="alert"
            className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
          >
            {state.error}
          </p>
        )}

        <SubmitButton label={copy.submit} pendingLabel={copy.pending} />
      </form>

      <p className="mt-6 text-center text-sm text-slate-600 dark:text-slate-400">
        {copy.switchText}{" "}
        <Link
          href={copy.switchHref}
          className="font-medium text-slate-900 underline underline-offset-4 dark:text-slate-100"
        >
          {copy.switchLabel}
        </Link>
      </p>
    </div>
  );
}

function Field({
  label,
  name,
  type,
  autoComplete,
  required,
  hint,
}: {
  label: string;
  name: string;
  type: string;
  autoComplete: string;
  required?: boolean;
  hint?: string;
}) {
  const hintId = hint ? `${name}-hint` : undefined;

  return (
    <div>
      <label
        htmlFor={name}
        className="block text-sm font-medium text-slate-700 dark:text-slate-300"
      >
        {label}
        {!required && (
          // 밝은 배경에서는 slate-500, 어두운 배경에서는 slate-400 이라야
          // 양쪽 다 읽힌다. 아래 hint 도 같은 짝을 쓴다.
          <span className="ml-1 font-normal text-slate-500 dark:text-slate-400">
            (선택)
          </span>
        )}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        autoComplete={autoComplete}
        required={required}
        aria-describedby={hintId}
        className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
      {hint && (
        <p id={hintId} className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {hint}
        </p>
      )}
    </div>
  );
}

/**
 * 제출 버튼.
 *
 * 별도 컴포넌트인 이유: useFormStatus 는 form 안쪽에서만 상태를 읽는다.
 * 폼과 같은 컴포넌트에 두면 pending 이 항상 false 로 나온다.
 */
function SubmitButton({
  label,
  pendingLabel,
}: {
  label: string;
  pendingLabel: string;
}) {
  const { pending } = useFormStatus();

  return (
    <button
      type="submit"
      disabled={pending}
      className="mt-2 w-full rounded-md bg-slate-900 px-4 py-2.5 font-medium text-white transition hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 disabled:opacity-60 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
    >
      {pending ? pendingLabel : label}
    </button>
  );
}
