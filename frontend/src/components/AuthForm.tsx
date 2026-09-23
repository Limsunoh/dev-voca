"use client";

import Link from "next/link";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import type { FormState } from "@/app/(auth)/actions";
import { continueAsGuestAction } from "@/app/start/actions";

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

/**
 * 비밀번호 최소 길이.
 *
 * 백엔드 `MinimumLengthValidator` 기본값(8)과 같아야 한다. 여기가 더 크면
 * 쓸 수 있는 비밀번호를 막고, 더 작으면 브라우저를 통과한 것이 서버에서
 * 거절돼 왕복만 늘어난다.
 *
 * **안내 문구가 이 숫자를 한글로 적는다**("여덟 자 이상"). 이 값을 바꾸면
 * 아래 hint 도 같이 고쳐야 한다 - 문구를 숫자로 만들어 묶을 수도 있지만,
 * 그러면 "8자 이상" 이 되어 지금 문장이 바뀐다. 이번 범위가 아니라 그대로
 * 두고 여기 적어둔다.
 */
const PASSWORD_MIN = 8;

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

        {/* 이메일 칸에 maxLength 를 걸지 않는 이유:

            백엔드가 254자에서 거절하니 미리 막고 싶지만, maxLength 는 넘는
            값을 **말없이 잘라낸다**. 붙여넣기로 재현하면 261자가 254자로
            잘려 `...aaa@exam` 이 되는데 브라우저는 그것을 유효하다고 보고
            그대로 보낸다. 사용자는 멀쩡해 보이는 주소를 앞에 두고 "유효한
            이메일 주소를 입력하세요" 를 받는다 - 무엇이 틀렸는지 알 방법이
            없고, 잘린 것이 우연히 유효한 주소가 되면 의도한 적 없는 주소로
            가입 시도가 나간다.

            안 걸면 서버가 글자 수를 말해주고 친 값은 그대로 남는다.
            **아래 이름 칸의 maxLength 와 비밀번호의 minLength 는 다르다** -
            이름은 서버가 알아서 지어주는 선택 칸이라 잘려도 피해가 작고,
            minLength 는 막기만 하고 고치지 않아 무엇을 할지 알 수 있다. */}
        <Field
          label="이메일"
          name="email"
          type="email"
          autoComplete="email"
          required
          defaultValue={state.values?.email}
        />

        {mode === "signup" && (
          <Field
            label="이름"
            name="display_name"
            type="text"
            autoComplete="nickname"
            // 백엔드 DISPLAY_NAME_MAX 와 같아야 한다. 프로필 화면도 같은 값.
            maxLength={12}
            defaultValue={state.values?.display_name}
            hint="순위표에 뜰 이름입니다. 비워두면 알아서 지어드립니다."
          />
        )}

        {/* 비밀번호는 되살리지 않는다(actions.ts 의 FormState 주석). 가입에만
            최소 길이를 건다 - 로그인은 규칙이 바뀌기 전에 만든 옛 비밀번호도
            받아야 하는데, 여기 minLength 를 걸면 그 사람이 자기 계정에
            못 들어간다. 막을 곳은 만드는 자리지 들어오는 자리가 아니다. */}
        <Field
          label="비밀번호"
          name="password"
          type="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          required
          minLength={mode === "signup" ? PASSWORD_MIN : undefined}
          hint={
            mode === "signup"
              ? "여덟 자 이상, 이메일과 너무 비슷하지 않게."
              : undefined
          }
        />

        {/* 알림 자리를 **항상 렌더한다.** 리전이 내용과 함께 새로 생기면
            화면 낭독기가 대부분 그 등장을 안 알린다 - 리전은 미리 있어야
            이후 변화를 감시한다(QuizBoard·TalkBoard 가 같은 이유로 그렇게
            한다). 안쪽만 조건부로 바꾼다.

            이번 변경으로 이게 더 중요해졌다. 전에는 실패하면 칸이 전부
            비어서 눈으로도 무언가 일어난 것을 알았는데, 이제 폼이 그대로
            남는다. 알림이 안 읽히면 화면을 못 보는 사용자에게는 **아무
            일도 안 일어난 것과 같다.** */}
        <div aria-live="polite">
          {state.error && <Notice>{state.error}</Notice>}
        </div>

        <SubmitButton label={copy.submit} pendingLabel={copy.pending} />
      </form>

      <p
        className="mt-6 text-center text-sm"
        style={{ color: "var(--text-muted)" }}
      >
        {copy.switchText}{" "}
        {/* 돌아갈 곳(next)을 들고 넘어간다. 안 들고 가면 순위표에서 로그인하러
            온 사람이 계정이 없어 가입으로 넘어가는 순간 행선지를 잃고, 가입을
            마치면 홈에 떨어진다.

            화면(login·signup page)은 이 값을 거르지 않고 그대로 받는다.
            거르는 곳은 제출할 때의 safeNext 다((auth)/actions.ts). 여기서는
            쿼리 값으로만 싣고 가는 곳은 고정이라 괜찮지만, 걸러지지 않은 이
            값을 redirect(next) 처럼 가는 곳 자체로 쓰면 밖으로 나가는 길이
            된다. */}
        <Link
          href={
            next
              ? `${copy.switchHref}?next=${encodeURIComponent(next)}`
              : copy.switchHref
          }
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
      {/* **링크가 아니라 폼 버튼이다.** 홈(/)으로 가는 링크였을 때는 홈이
          "로그인도 안 했고 게스트도 안 고른 사람" 을 시작 화면으로 돌려보내,
          거기서 "게스트로 둘러보기" 를 한 번 더 눌러야 했다. 시작 화면과 같은
          action 을 불러 게스트 표시를 남기고 곧장 홈으로 간다.

          링크(GET)로 두지 않는 이유는 action 주석에 있다 - GET 이 상태를
          바꾸면 브라우저가 미리 불러오기만 해도 게스트 선택이 굳는다. */}
      <form action={continueAsGuestAction} className="mt-2 text-center text-sm">
        <button
          type="submit"
          className="inline-flex cursor-pointer items-center px-2 underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          // 링크처럼 보이게 둔다. 밑줄은 늘 켠다 - 폰에는 hover 가 없어서
          // hover 에만 걸면 회색 글자 한 줄로만 보인다. 버튼은 기본 커서가
          // 화살표라 손가락 커서도 따로 준다.
          //
          // --text-faint(크림 위 2.51:1)로 두지 않는다 - 누를 수 있는 것이
          // 배경에 묻히면 있는 줄도 모른다. 높이는 누르는 영역만 44px
          // (--hit-floor)로 넓힌다. 주 버튼 높이(--hit-min)까지는 필요 없다.
          style={{
            minHeight: "var(--hit-floor)",
            color: "var(--text-muted)",
            background: "transparent",
            border: 0,
          }}
        >
          로그인 없이 둘러보기
        </button>
      </form>
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
  minLength,
  defaultValue,
  hint,
}: {
  label: string;
  name: string;
  type: string;
  autoComplete: string;
  required?: boolean;
  maxLength?: number;
  minLength?: number;
  /**
   * 실패하고 돌아왔을 때 되살릴 값.
   *
   * 제어 입력(value+onChange)이 아니라 defaultValue 로 충분하다. Server
   * Action 이 끝나면 React 가 폼을 초기화하는데, **그 초기화가 되돌리는
   * 자리가 defaultValue** 라서 새 값이 그대로 남는다. 두 번 연속 실패해도
   * 남는 것까지 확인했다.
   *
   * 제어 입력으로 만들면 칸마다 상태와 onChange 가 붙는데, 되살리는 것
   * 말고는 쓸 데가 없다.
   */
  defaultValue?: string;
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
        minLength={minLength}
        defaultValue={defaultValue}
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
