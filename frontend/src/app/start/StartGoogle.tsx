"use client";

import {
  ConsentChecks,
  GoogleNameNote,
  googleConsentHref,
  useConsent,
} from "@/app/(auth)/ConsentChecks";

/**
 * 시작 화면의 구글 가입.
 *
 * 여기서 새 계정이 만들어질 수 있어 체크박스를 둔다. 세 항목을 켜기 전에는
 * 링크 대신 잠긴 버튼을 그린다. 게스트로 둘러보기는 계정을 만들지 않아서
 * 체크가 필요 없다.
 *
 * 체크 상태가 필요해서 페이지와 나눈 클라이언트 컴포넌트다.
 */
export function StartGoogle() {
  const consent = useConsent();

  const className =
    "dv-btn flex w-full items-center justify-center rounded-[var(--radius-pill)] px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus aria-disabled:opacity-60";
  const style = {
    minHeight: "var(--hit-min)",
    background: "var(--coral)",
    color: "var(--text-on-color)",
    border: 0,
    "--lift": "var(--lift-button)",
    fontWeight: "var(--weight-black)",
    letterSpacing: "var(--tracking-tight)",
  } as React.CSSProperties;

  return (
    <>
      <ConsentChecks {...consent} />
      <div className="text-center">
        <GoogleNameNote />
      </div>
      {consent.ready ? (
        <a href={googleConsentHref()} className={className} style={style}>
          구글로 시작하기
        </a>
      ) : (
        // disabled 가 아니라 aria-disabled 다. 눌렀을 때 이유를 알려 줘야 해서
        // 포커스와 클릭을 받아야 한다. 동의 전에 진행되지 않는 것은 같다.
        <button
          type="button"
          aria-disabled="true"
          onClick={consent.guide}
          className={className}
          style={style}
        >
          구글로 시작하기
        </button>
      )}
    </>
  );
}
