"use client";

import { useEffect, useId, useImperativeHandle, useRef } from "react";

/**
 * 되돌릴 수 없는 이동을 확인받는 창.
 *
 * 문제풀기의 네 출구(홈·"한 판 풀기"·분류 고르개·단어/문장 탭)와 한 판
 * 모드의 나가기가 모두 이 창을 쓴다. 창을 여러 벌 두면 문구와 동작이
 * 갈린다 - 실제로 두 벌이던 때 홈 창만 "새 판이 시작됩니다" 라고 거짓을
 * 말했다.
 *
 * **dialog 를 쓴다.** 포커스 가둠, Esc 닫기, 뒤 스크롤 막기, 낭독기에
 * "대화상자" 로 알리는 것까지 브라우저가 해준다. div 로 만들면 그 넷을
 * 직접 짜야 하고 대개 포커스 가둠에서 샌다. 화면 안에 한 줄 띄우는 방식도
 * 안 쓴다 - 포커스가 누른 자리에 남아서 낭독기에는 아무 일도 안 일어난
 * 것이 되고, 글이 끼어들며 아래 항목이 밀려 두 번째 누름이 엉뚱한 곳에
 * 떨어진다(한 번 그렇게 만들었다가 걷어냈다).
 *
 * window.confirm 은 쓰지 않는다. 문구를 다듬을 수 없고 화면 밖에 뜬다.
 */
export function LeaveConfirm({
  title,
  detail,
  note,
  confirmLabel,
  onConfirm,
  openRef,
}: {
  /** 창 제목. 무엇을 묻는지. */
  title: string;
  /** 잃는 것을 구체적으로. 숫자를 말해야 정직하다. */
  detail: string;
  /** 본문 아래 덧붙일 것(한 판 모드의 "시간은 흐릅니다"). */
  note?: React.ReactNode;
  /** 진행하는 쪽 버튼 글자. */
  confirmLabel: string;
  /** 사용자가 진행을 고른 뒤 할 일. 창은 이미 닫힌 뒤다. */
  onConfirm: () => void;
  /**
   * 창을 여는 방법을 받아갈 자리.
   *
   * 여는 쪽이 버튼일 수도 링크일 수도 있어서 이 컴포넌트가 직접 안 그린다.
   * 호출부가 이 ref 로 여는 방법을 꺼내 쓴다.
   */
  openRef: React.RefObject<(() => void) | null>;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  // 제목·본문과 잇는다. 고정 문자열로 두면 한 화면에 이 창이 둘 이상일 때
  // id 가 겹쳐 낭독기가 엉뚱한 글을 읽는다.
  const titleId = useId();
  // 본문도 잇는다. 제목만 이으면 낭독기가 "지금 판을 끝낼까요? 대화상자"
  // 까지만 읽고, 정작 잃는 문제 수는 안 읽는다.
  const detailId = useId();

  // showModal() 은 명령형이라 open 속성으로는 못 연다. 속성으로 열면
  // ::backdrop 도 포커스 가둠도 안 붙는 그냥 보이는 상자가 된다.
  //
  // 렌더 중에 ref 를 건드리면 안 되므로(리액트 규칙) 이 훅으로 넘긴다 -
  // 부모에게 "이 창을 여는 방법" 하나만 내주는 것이 이 훅의 용도다.
  useImperativeHandle(openRef, () => () => dialogRef.current?.showModal(), []);

  // 열린 채로 사라지면 닫는다. 안 닫으면 모달이 걸어둔 inert 가 풀리지 않은
  // 것처럼 보이고 포커스가 body 로 떨어진다 - 창을 연 채 뒤로가기를 누르면
  // 그렇게 된다(ExitGuard 가 먼저 겪고 고친 것을 여기로 옮겼다).
  useEffect(() => {
    const dialog = dialogRef.current;
    return () => dialog?.close();
  }, []);

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      aria-describedby={detailId}
      // 폭을 정해 둔다. 최대 폭만 주면 본문이 짧을 때 창이 좁아져 "계속
      // 풀기" 가 두 줄로 꺾인다(실측: 239px).
      //
      // m-auto 를 반드시 준다. dialog 의 기본값(margin: auto)을 Tailwind
      // 리셋이 지워서, 안 주면 화면 왼쪽 위에 붙는다(실측: top 0, left 0).
      //
      // backdrop 은 잉크(#191512) 72%. 크림 화면에 순검정이 한 번도 안
      // 나와서, 순검정을 깔면 다른 앱이 덮은 것처럼 보인다.
      className="pop m-auto w-[min(22rem,calc(100vw-2rem))] p-6 backdrop:bg-[rgb(25_21_18/0.72)]"
      style={{
        background: "var(--paper)",
        color: "var(--foreground)",
        borderRadius: "var(--radius-sheet)",
        border: 0,
        // 시트라 카드보다 두껍다. 누르는 것이 아니라 누를 것을 담는
        // 그릇이라 :active 가 없어 인라인 boxShadow 로 둔다.
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
        {title}
      </h2>
      <p
        id={detailId}
        className="mt-2 text-sm"
        style={{
          lineHeight: "var(--leading-relaxed)",
          color: "var(--text-muted)",
        }}
      >
        {detail}
      </p>
      {note}

      <div className="mt-6 flex gap-2">
        {/* 되돌아가는 쪽을 먼저, 코랄로 둔다. 실수로 연 사람이 대부분이라
            손가락이 먼저 닿는 자리에 그쪽이 있어야 한다. */}
        <button
          type="button"
          onClick={() => dialogRef.current?.close()}
          className="dv-btn flex flex-1 items-center justify-center px-4 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--coral)",
              color: "var(--text-on-color)",
              border: 0,
              borderRadius: "var(--radius-pill)",
              fontWeight: "var(--weight-black)",
              "--lift": "var(--lift-button)",
            } as React.CSSProperties
          }
        >
          계속 풀기
        </button>
        {/* 진행하는 쪽은 흰 알약에 코랄 글자. 채우면 코랄이 둘이 되어
            어느 쪽을 권하는지 사라진다. */}
        <button
          type="button"
          onClick={() => {
            dialogRef.current?.close();
            onConfirm();
          }}
          className="dv-btn flex flex-1 items-center justify-center px-4 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
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
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
