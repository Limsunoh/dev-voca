"use client";

import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import type { PasswordField, PasswordState } from "@/app/profile/actions";

type Passwords = Record<PasswordField, string>;

const EMPTY: Passwords = {
  current_password: "",
  new_password: "",
  new_password_confirm: "",
};

/**
 * 결과를 받은 뒤 세 칸에 남길 값.
 *
 * 성공하면 셋 다 비운다. 실패하면 틀린 칸만 비운다 - 현재 비밀번호가
 * 틀렸으면 그 칸만, 확인 값이 다르면 확인 칸만. 새 비밀번호가 규칙에
 * 걸렸으면 확인 칸도 같이 비운다. 새 값을 다시 정해야 하니 옛 확인 값은
 * 어차피 안 맞는다. 칸 탓이 아닌 실패(연결 끊김 등)는 아무것도 안 비운다.
 */
export function passwordsAfter(
  state: PasswordState,
  values: Passwords,
): Passwords {
  if (state.saved) return EMPTY;

  switch (state.field) {
    case "current_password":
      return { ...values, current_password: "" };
    case "new_password":
      return { ...values, new_password: "", new_password_confirm: "" };
    case "new_password_confirm":
      return { ...values, new_password_confirm: "" };
    default:
      return values;
  }
}

/**
 * 비밀번호 변경 카드. 처음 설정하는 경우도 같이 받는다.
 *
 * **두 흐름이 한 화면이다.** 비밀번호를 이미 가진 사람에게는 현재
 * 비밀번호를 묻고, 구글로만 가입한 사람에게는 묻지 않는다. 후자는 댈 수
 * 있는 값이 없어서, 칸을 그리면 영영 비밀번호를 만들 수 없다.
 *
 * 그 판정을 화면에서 하지 않고 hasPassword 로 받는다. 서버가 아는 값이고
 * (has_usable_password), 화면이 짐작할 근거가 없다 - 구글 사진이 있는지로
 * 가늠하면 이메일로 가입한 뒤 구글을 붙인 사람이 잘못 걸린다.
 *
 * 'use client' 인 이유는 ProfileForm 과 같다. useActionState 로 서버가
 * 돌려준 결과를 받아 입력칸을 정리한다(passwordsAfter).
 *
 * page.tsx 에 직접 붙지 않는다. 지금 세 기능이 그 파일에 절을 추가하려
 * 해서, 각자 카드만 만들고 배치는 한 곳에서 한 번에 한다.
 *
 * **입력칸 id 에 pw- 를 붙인다.** 같은 화면에 이메일 변경 카드가 들어오고
 * 그쪽도 "현재 비밀번호" 칸을 가지는데, 둘 다 id 를 current_password 로
 * 두면 한 문서에 같은 id 가 둘이 된다. 그때 label 의 for 는 **문서에서
 * 처음 나온 칸**을 가리켜서, 이 카드의 "현재 비밀번호" 라벨을 눌렀을 때
 * 포커스가 이메일 카드의 칸으로 간다(브라우저에서 재현해 확인했다).
 * name 은 서버가 읽는 키라 그대로 둔다 - 폼이 다르므로 겹쳐도 상관없다.
 */
export function PasswordCard({
  action,
  hasPassword,
  email,
}: {
  /** 서버 액션. profile/actions.ts 의 changePasswordAction. */
  action: (prev: PasswordState, formData: FormData) => Promise<PasswordState>;
  /**
   * 쓸 수 있는 비밀번호가 이미 있나.
   *
   * false 면 현재 비밀번호 칸을 아예 그리지 않는다. disabled 로 두지
   * 않는 이유: 그러면 빈 값이 폼에 실려 서버가 400 으로 막는다.
   */
  hasPassword: boolean;
  /**
   * 로그인한 계정의 이메일. 화면에 그리지 않고 비밀번호 관리자에게만
   * 알려준다 - 아래 username 칸 주석 참고.
   */
  email: string;
}) {
  const [state, formAction] = useActionState<PasswordState, FormData>(
    action,
    {},
  );

  // **세 칸을 상태로 든다(제어 입력).** 값을 칸에 맡겨 두면 React 가 폼
  // 액션이 끝날 때마다 폼을 통째로 비운다 - 실패해도 그렇다. 그래서 현재
  // 비밀번호 하나 틀려도 새 비밀번호 두 칸까지 다시 쳐야 했다. 상태로
  // 들면 그 비우기가 이 값을 못 건드리고, 무엇을 비울지를 여기서 정한다.
  //
  // 값은 브라우저 안에만 있다. 서버 결과에 비밀번호를 실어 되돌려 받는
  // 방식(로그인 폼이 이메일에 쓰는 defaultValue)은 쓰지 않는다 - 그러면
  // 비밀번호가 서버 응답에 실려 다시 내려온다. 다만 React 는 제어 입력의
  // 값을 input 의 value 속성에도 적어 두어서, 친 동안은 개발자 도구에서
  // 속성으로 보인다. 결과를 받으면 비운 칸은 속성도 같이 비워진다.
  const [values, setValues] = useState<Passwords>(EMPTY);

  // 결과가 새로 올 때 한 번만 정리한다. 같은 오류가 두 번 나도 결과
  // 객체는 매번 새것이라 두 번째에도 다시 비운다.
  const [handled, setHandled] = useState(state);
  if (state !== handled) {
    setHandled(state);
    setValues(passwordsAfter(state, values));
  }

  const bind = (field: PasswordField) => ({
    name: field,
    value: values[field],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) => {
      const next = event.target.value;
      setValues((prev) => ({ ...prev, [field]: next }));
    },
  });

  // 바깥을 감싸지 않는다. 이 카드는 page.tsx 의 "계정" 절 안에 EmailCard 와
  // 형제로 놓이므로, 여기서 section 을 또 두면 절 안에 절이 생기고 h2 가
  // "계정" 과 형제 레벨이 되어 낭독기에서 하위로 안 읽힌다. 간격도 바깥의
  // grid gap 이 정하게 둔다 - 여기서 mt-8 을 들고 오면 두 카드 사이만
  // 벌어져 나머지와 리듬이 어긋난다.
  return (
    <form
      action={formAction}
      className="grid gap-4 p-5"
      style={{
        background: "var(--paper)",
        borderRadius: "var(--radius-2xl)",
        boxShadow: "var(--lift-card)",
      }}
    >
      {/* h3 다. 바깥 "계정" 절의 h2 아래라 한 단계 낮춰야 낭독기에서
          하위 항목으로 읽힌다. EmailCard 는 details 의 summary 가 같은
          역할을 한다. */}
      <h3
        className="text-sm"
        style={{
          color: "var(--text-body)",
          fontWeight: "var(--weight-bold)",
        }}
      >
        {hasPassword ? "비밀번호 바꾸기" : "비밀번호 설정하기"}
      </h3>

      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        {hasPassword
          ? "바꾸면 이 기기만 로그인 상태로 남고 다른 기기는 로그아웃됩니다."
          : "구글로 가입한 계정입니다. 비밀번호를 정하면 이메일로도 로그인할 수 있습니다."}
      </p>

      {/* 비밀번호 관리자에게 "어느 계정의 비밀번호인가" 를 알려준다.
            이 화면에는 이메일 칸이 없어서 관리자가 참조할 것이 없고, 그러면
            새 비밀번호를 저장하지 않거나 엉뚱한 항목에 붙인다. 다른 기기가
            전부 끊긴 직후라 그때 관리자에서 못 찾으면 특히 나쁘다.

            hidden 이 아니라 sr-only 다. hidden 인 칸은 브라우저가 힌트로
            안 읽는 경우가 있다. tabIndex 를 빼고 aria-hidden 을 붙이는 것은
            이 칸이 사람에게는 아무 의미가 없기 때문이다 - 안 붙이면 키보드로
            넘길 때 빈 칸을 지나가고 낭독기가 읽는다.

            **이 값도 폼에 실려 서버 액션까지 간다.** 액션이 필요한 키만
            꺼내 쓰므로 무해하지만(username 은 안 읽는다), 나중에 폼 전체를
            그대로 서버에 넘기는 코드를 쓰면 서버가 모르는 키가 함께 간다. */}
      <input
        type="text"
        name="username"
        value={email}
        autoComplete="username"
        readOnly
        tabIndex={-1}
        aria-hidden="true"
        className="sr-only"
      />

      {/* 비밀번호가 있는 사람에게만 현재 비밀번호를 묻는다. 위 주석 참고. */}
      {hasPassword && (
        <div>
          <label
            htmlFor="pw-current"
            className="block text-sm"
            style={{
              color: "var(--text-body)",
              fontWeight: "var(--weight-bold)",
            }}
          >
            현재 비밀번호
          </label>
          <input
            id="pw-current"
            {...bind("current_password")}
            type="password"
            required
            autoComplete="current-password"
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
      )}

      <div>
        <label
          htmlFor="pw-new"
          className="block text-sm"
          style={{
            color: "var(--text-body)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          새 비밀번호
        </label>
        <input
          id="pw-new"
          {...bind("new_password")}
          type="password"
          required
          // 브라우저에 "새 비밀번호" 라고 알려준다. current-password 로
          // 두면 저장된 옛 비밀번호가 자동으로 채워진다.
          autoComplete="new-password"
          aria-describedby="pw-new-hint"
          className="mt-2 w-full rounded-[var(--radius-xl)] px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={{
            minHeight: "var(--hit-floor)",
            background: "var(--surface-field)",
            color: "var(--foreground)",
            border: 0,
            boxShadow: "var(--lift-card)",
          }}
        />
        {/* 규칙을 미리 알려준다. 서버가 막은 뒤에 알려주면 사용자는
              몇 번을 다시 적는다. 문구는 Django 검사기 기본값에 맞춘 것이고,
              서버가 최종 판정을 한다 - 여기 적힌 것이 규칙 그 자체는 아니다. */}
        <p
          id="pw-new-hint"
          className="mt-1 text-xs"
          style={{ color: "var(--text-muted)" }}
        >
          8자 이상이고, 너무 흔하거나 이메일과 비슷하면 쓸 수 없습니다.
        </p>
      </div>

      <div>
        <label
          htmlFor="pw-new-confirm"
          className="block text-sm"
          style={{
            color: "var(--text-body)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          새 비밀번호 확인
        </label>
        {/* 확인 칸은 서버로 보내지 않고 액션에서 대조만 한다. 오타 하나로
              다른 기기가 전부 끊기고 새 비밀번호도 모르는 상태가 되는 것을
              막는 자리다. */}
        <input
          id="pw-new-confirm"
          {...bind("new_password_confirm")}
          type="password"
          required
          autoComplete="new-password"
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

      {/* 결과는 같은 화면의 다른 카드(이름·이메일)와 같은 채움 상자로
            보인다. 색 글자만 두던 때는 이 카드만 모양이 달라 같은 화면의
            알림으로 안 읽혔다.

            알림 자리(aria-live)는 **항상 그린다.** 리전이 내용과 함께 새로
            생기면 화면 낭독기가 대부분 그 등장을 안 알린다(AuthForm 과 같은
            이유). 이제 실패해도 칸이 남아서, 알림이 안 읽히면 화면을 못 보는
            사용자에게는 아무 일도 안 일어난 것과 같다. */}
      <div aria-live="polite">
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
        {state.saved && (
          <p
            className="rounded-[var(--radius-xl)] p-3 text-sm"
            style={{
              background: "var(--correct-soft)",
              color: "var(--correct-deep)",
            }}
          >
            {state.created
              ? "비밀번호를 설정했습니다. 이제 이메일로도 로그인할 수 있습니다."
              : "비밀번호를 바꿨습니다. 다른 기기는 로그아웃했습니다."}
          </p>
        )}
      </div>

      <SubmitButton hasPassword={hasPassword} />
    </form>
  );
}

/**
 * 저장 버튼.
 *
 * 별도 컴포넌트인 이유는 ProfileForm 의 SaveButton 과 같다 - useFormStatus
 * 는 form 안쪽 컴포넌트에서만 pending 을 읽는다. 같은 컴포넌트에 두면
 * 항상 false 다.
 *
 * **fontSize 를 인라인으로 주지 않는다.** 코랄 버튼은 globals.css 가
 * [style*="--lift-button)"] 로 골라 19px 로 올리는데, 인라인 font-size 가
 * 있으면 그 규칙이 덮여 16px 로 남고 흰 글자 대비가 3.37:1 이 된다.
 * boxShadow 도 같은 이유로 인라인에 두지 않는다 - 누를 때 내려앉는
 * :active 가 죽는다. 두께는 --lift 변수로 넘긴다.
 */
function SubmitButton({ hasPassword }: { hasPassword: boolean }) {
  const { pending } = useFormStatus();
  const label = hasPassword ? "비밀번호 바꾸기" : "비밀번호 설정";

  return (
    <button
      type="submit"
      disabled={pending}
      // 흰 버튼이다. 이 화면의 코랄은 위쪽 프로필 저장이 가진다 - 계정
      // 절의 버튼까지 코랄이면 화면에 주된 동작이 셋이 되어 어느 것부터
      // 할 일인지가 사라진다. 같은 절의 이메일 카드와도 이래야 짝이 맞는다.
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
      {pending ? "저장하는 중" : label}
    </button>
  );
}
