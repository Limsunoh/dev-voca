"use client";

import { type ReactNode, useEffect, useId, useRef, useState } from "react";

import {
  ConsentChecks,
  GoogleNameNote,
  googleConsentHref,
  useConsent,
} from "@/app/(auth)/ConsentChecks";
import { continueAsGuestAction } from "@/app/start/actions";

const BUTTON =
  "dv-btn flex w-full items-center justify-center rounded-[var(--radius-pill)] px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus aria-disabled:opacity-60";

const CORAL = {
  minHeight: "var(--hit-min)",
  background: "var(--coral)",
  color: "var(--text-on-color)",
  border: 0,
  "--lift": "var(--lift-button)",
  fontWeight: "var(--weight-black)",
  letterSpacing: "var(--tracking-tight)",
} as React.CSSProperties;

const PAPER = {
  minHeight: "var(--hit-min)",
  background: "var(--paper)",
  color: "var(--foreground)",
  border: 0,
  "--lift": "var(--lift-button-paper)",
  fontWeight: "var(--weight-bold)",
} as React.CSSProperties;

/** 열린 직후 이 시간(ms) 안의 탭은 버린다. 보통 이중탭 간격보다 길게 잡았다. */
const OPEN_GUARD_MS = 400;

/**
 * 시작 화면의 두 버튼과, 누르면 아래에서 올라오는 필수 항목 시트.
 *
 * 앱을 열자마자 약관 체크박스부터 보이지 않게, 고른 뒤에 묻는다.
 *
 * 구글은 새 계정이 만들어질 수 있어 세 항목이고 서버도 막는다
 * (GoogleLoginView). 게스트는 계정이 없어 동의를 저장할 곳이 없으므로 두
 * 항목을 화면에서만 묻는다. 로그인·가입 화면의 "로그인 없이 둘러보기" 는
 * 묻지 않는다.
 */
export function StartChoices() {
  const [choice, setChoice] = useState<"google" | "guest" | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const openedAt = useRef(0);
  const titleId = useId();

  // 내용이 그려진 뒤에 연다. 먼저 열면 초점이 들어갈 칸이 아직 없다.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (choice && dialog && !dialog.open) {
      openedAt.current = performance.now();
      dialog.showModal();
    }
  }, [choice]);

  // 열린 채로 화면을 떠나도 닫는다(LeaveConfirm 과 같은 이유).
  useEffect(() => {
    const dialog = dialogRef.current;
    return () => dialog?.close();
  }, []);

  const close = () => dialogRef.current?.close();

  return (
    <>
      {/* 구글을 먼저 둔다. 점수와 순위가 남는 쪽이 본래 모습이다. */}
      <button
        type="button"
        onClick={() => setChoice("google")}
        className={BUTTON}
        style={CORAL}
      >
        구글로 시작하기
      </button>
      <button
        type="button"
        onClick={() => setChoice("guest")}
        className={BUTTON}
        style={PAPER}
      >
        게스트로 둘러보기
      </button>

      <dialog
        ref={dialogRef}
        aria-labelledby={titleId}
        onClose={() => setChoice(null)}
        // 여는 버튼을 빠르게 두 번 누르면 둘째 탭이 막 올라온 시트의 체크박스에
        // 닿는다. 누르지 않은 동의가 켜지면 안 되므로 열린 직후의 탭은 버린다.
        // 처리된 시각이 아니라 누른 시각(timeStamp)으로 잰다. 느린 폰에서는
        // 처리가 밀려 이미 시간이 지난 것으로 잡힌다.
        onClickCapture={(event) => {
          if (event.timeStamp - openedAt.current < OPEN_GUARD_MS) {
            event.preventDefault();
            event.stopPropagation();
          }
        }}
        // 바깥(backdrop)을 누르면 닫는다. 여백은 안쪽 div 에 줘야 시트 안을
        // 누른 것이 dialog 자신을 누른 것으로 잡히지 않는다.
        onClick={(event) => {
          if (event.target === event.currentTarget) close();
        }}
        // m-auto 는 dialog 기본값을 Tailwind 리셋이 지워서 다시 준다. mb-0 으로
        // 바닥에 붙이고, 펼친 폴드에서는 max-w-md 로 본문 폭에 맞춘다.
        className="rise m-auto mb-0 w-full max-w-md backdrop:bg-[rgb(25_21_18/0.72)]"
        style={{
          background: "var(--paper)",
          color: "var(--foreground)",
          border: 0,
          borderRadius: "var(--radius-sheet) var(--radius-sheet) 0 0",
        }}
      >
        <div
          className="grid gap-4 p-6"
          style={{
            paddingBottom: "max(1.5rem, env(safe-area-inset-bottom))",
          }}
        >
          {choice === "google" && (
            <GoogleStep titleId={titleId} onCancel={close} />
          )}
          {choice === "guest" && (
            <GuestStep titleId={titleId} onCancel={close} />
          )}
        </div>
      </dialog>
    </>
  );
}

type StepProps = { titleId: string; onCancel: () => void };

export function GoogleStep({ titleId, onCancel }: StepProps) {
  const consent = useConsent();

  return (
    <>
      <SheetTitle id={titleId}>구글로 시작하기 전에</SheetTitle>
      <ConsentChecks {...consent} />
      <GoogleNameNote />
      {consent.ready ? (
        <a href={googleConsentHref()} className={BUTTON} style={CORAL}>
          구글로 계속하기
        </a>
      ) : (
        <LockedButton onClick={consent.guide}>구글로 계속하기</LockedButton>
      )}
      <CancelButton onClick={onCancel} />
    </>
  );
}

export function GuestStep({ titleId, onCancel }: StepProps) {
  const consent = useConsent(false);

  return (
    <>
      <SheetTitle id={titleId}>둘러보기 전에</SheetTitle>
      <ConsentChecks {...consent} />
      {consent.ready ? (
        <form action={continueAsGuestAction}>
          <button type="submit" className={BUTTON} style={CORAL}>
            둘러보기
          </button>
        </form>
      ) : (
        <LockedButton onClick={consent.guide}>둘러보기</LockedButton>
      )}
      <CancelButton onClick={onCancel} />
    </>
  );
}

function SheetTitle({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2
      id={id}
      style={{
        fontSize: "var(--text-lg)",
        fontWeight: "var(--weight-black)",
        letterSpacing: "var(--tracking-tight)",
      }}
    >
      {children}
    </h2>
  );
}

// disabled 가 아니라 aria-disabled 다. 눌렀을 때 이유를 알려 줘야 해서
// 포커스와 클릭을 받아야 한다. 동의 전에 진행되지 않는 것은 같다.
function LockedButton({
  onClick,
  children,
}: {
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-disabled="true"
      onClick={onClick}
      className={BUTTON}
      style={CORAL}
    >
      {children}
    </button>
  );
}

function CancelButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={BUTTON}
      // 흰 시트 위의 흰 알약은 아래 두께만 떠 보여서 두께를 뺀다.
      style={{ ...PAPER, "--lift": "var(--lift-none)" } as React.CSSProperties}
    >
      취소
    </button>
  );
}
