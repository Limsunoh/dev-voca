"use client";

import Link from "next/link";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import type { FormState } from "@/app/(auth)/actions";
import { routes } from "@/lib/routes";

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
 *
 * 색·그림자·모서리는 CSS 변수로 쓴다. 크림 토큰이 Tailwind 유틸로 전부
 * 나가 있지 않고, 나가 있는 것만 골라 쓰면 같은 파일 안에서 색을 두 가지
 * 방식으로 적게 된다. 레이아웃만 Tailwind 로 둔다.
 */

type Props = {
  mode: "login" | "signup";
  action: (prev: FormState, formData: FormData) => Promise<FormState>;
  /** 로그인 후 돌아갈 곳. */
  next?: string;
  /** 구글 로그인이 실패해 돌아온 경우. */
  googleFailed?: boolean;
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

/**
 * 알림 상자(구글 실패·폼 에러).
 *
 * 테두리가 아니라 옅은 채움으로 구분한다. 이 디자인은 경계를 테두리가
 * 아니라 채움과 두께로 만든다 - 크림 바탕에 1px 선을 그으면 그것만
 * 다른 시대의 화면처럼 보인다.
 */
function Notice({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="alert"
      className="rounded-[var(--radius-xl)] p-3 text-sm"
      style={{
        background: "var(--amber-soft)",
        color: "var(--amber-deep)",
      }}
    >
      {children}
    </p>
  );
}

export function AuthForm({ mode, action, next, googleFailed }: Props) {
  const [state, formAction] = useActionState<FormState, FormData>(action, {});
  const copy = COPY[mode];

  const googleHref = next
    ? `/api/auth/google?next=${encodeURIComponent(next)}`
    : "/api/auth/google";

  return (
    <div className="mx-auto w-full max-w-sm">
      <h1
        className="text-[length:var(--text-2xl)] tracking-[var(--tracking-tight)]"
        style={{
          color: "var(--foreground)",
          fontWeight: "var(--weight-black)",
        }}
      >
        {copy.title}
      </h1>
      <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>
        로그인하면 푼 문제와 틀린 단어가 기기를 옮겨도 이어집니다.
      </p>

      {googleFailed && (
        <div className="mt-6">
          <Notice>구글 로그인을 마치지 못했습니다. 다시 시도해주세요.</Notice>
        </div>
      )}

      {/* 링크지만 버튼처럼 보인다. 누르면 구글 동의 화면으로 간다.
          코랄이 아니라 흰 버튼인 이유: 한 화면에 코랄은 하나뿐이고,
          그 자리는 아래 제출 버튼이 가진다. */}
      <a
        href={googleHref}
        className="dv-btn mt-6 flex w-full items-center justify-center gap-2.5 rounded-[var(--radius-pill)] px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        style={
          {
            minHeight: "var(--hit-min)",
            background: "var(--paper)",
            color: "var(--foreground)",
            "--lift": "var(--lift-button-paper)",
            fontWeight: "var(--weight-bold)",
          } as React.CSSProperties
        }
      >
        <GoogleMark />
        구글로 계속하기
      </a>

      <div className="mt-6 flex items-center gap-3">
        <span
          className="h-px flex-1"
          style={{ background: "var(--sand-deep)" }}
        />
        <span className="text-xs" style={{ color: "var(--text-dim)" }}>
          또는
        </span>
        <span
          className="h-px flex-1"
          style={{ background: "var(--sand-deep)" }}
        />
      </div>

      <form action={formAction} className="mt-6 grid gap-4">
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
            // 백엔드 DISPLAY_NAME_MAX 와 같아야 한다. 프로필 화면도 같은 값.
            maxLength={12}
            hint="순위표에 뜰 이름입니다. 비워두면 알아서 지어드립니다."
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

        {state.error && <Notice>{state.error}</Notice>}

        <SubmitButton label={copy.submit} pendingLabel={copy.pending} />
      </form>

      <p
        className="mt-6 text-center text-sm"
        style={{ color: "var(--text-muted)" }}
      >
        {copy.switchText}{" "}
        <Link
          href={copy.switchHref}
          className="underline underline-offset-4"
          style={{
            color: "var(--coral-deep)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          {copy.switchLabel}
        </Link>
      </p>

      {/* 이 화면에서는 아래 탭바를 숨긴다(한 가지 일만 하는 화면이라).
          그래서 여기에 나가는 문이 없으면 막다른 곳이 된다 - 전에는 화면
          맨 위 devvoca 로고가 그 역할을 했는데 앱 셸로 바꾸며 없앴다.
          가입 없이 둘러보려던 사람이 갇히지 않게 한 줄 남긴다. */}
      <p className="mt-4 text-center text-sm">
        <Link
          href={routes.home}
          className="underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          // 링크는 --text-faint(크림 위 2.51:1)로 두지 않는다. 누를 수
          // 있는 것이 배경에 묻히면 있는 줄도 모른다.
          style={{ color: "var(--text-muted)" }}
        >
          로그인 없이 둘러보기
        </Link>
      </p>
    </div>
  );
}

/**
 * 구글 로고.
 *
 * 구글 브랜드 규정상 색과 모양을 바꾸지 않는다.
 */
function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.9 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"
      />
    </svg>
  );
}

function Field({
  label,
  name,
  type,
  autoComplete,
  required,
  maxLength,
  hint,
}: {
  label: string;
  name: string;
  type: string;
  autoComplete: string;
  required?: boolean;
  maxLength?: number;
  hint?: string;
}) {
  const hintId = hint ? `${name}-hint` : undefined;

  return (
    <div>
      <label
        htmlFor={name}
        className="block text-sm"
        style={{ color: "var(--text-body)", fontWeight: "var(--weight-bold)" }}
      >
        {label}
        {!required && (
          <span
            className="ml-1"
            style={{
              color: "var(--text-muted)",
              fontWeight: "var(--weight-regular)",
            }}
          >
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
        maxLength={maxLength}
        aria-describedby={hintId}
        // 흰 바탕이 아니라 --surface-field 다. 크림(#FFF6E9) 위에 흰
        // 입력칸을 놓으면 경계가 거의 안 보인다. 여기에 카드 두께까지
        // 얹어서 "눌러서 쓰는 칸" 임을 두 겹으로 알린다.
        // ProfileForm 과 같은 값이다.
        className="mt-1 w-full rounded-[var(--radius-xl)] px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        style={{
          minHeight: "var(--hit-floor)",
          background: "var(--surface-field)",
          color: "var(--foreground)",
          border: 0,
          boxShadow: "var(--lift-card)",
        }}
      />
      {hint && (
        <p
          id={hintId}
          className="mt-1.5 text-xs"
          style={{ color: "var(--text-dim)" }}
        >
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
      // 이 화면의 유일한 코랄. 주된 동작이 무엇인지 색 하나로 정한다.
      className="dv-btn mt-2 w-full rounded-[var(--radius-pill)] px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60"
      style={
        {
          minHeight: "var(--hit-min)",
          background: "var(--coral)",
          color: "var(--text-on-color)",
          border: 0,
          "--lift": "var(--lift-button)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
        } as React.CSSProperties
      }
    >
      {pending ? pendingLabel : label}
    </button>
  );
}
