"use client";

import { useEffect, useId, useRef, useState } from "react";

import { project, rubber, spring } from "@/lib/spring";

/**
 * 홈에서 아래에 붙어 올라오는 오늘 기록.
 *
 * 홈에 두는 이유: 공부하는 화면은 집중하는 자리라 곁들이가 끼면 방해가
 * 되고, 홈은 원래 오늘 상태를 훑고 어디로 갈지 정하는 자리다.
 *
 * **여는 길이 둘이다.**
 *
 *   칩을 누른다        진짜 버튼이라 키보드와 낭독기가 쓸 수 있다
 *   아래에서 위로 쓴다   손에 익은 쪽. 편의이지 유일한 길이 아니다
 *
 * dialog 를 쓰는 이유는 ExitGuard 와 같다 - 포커스 가둠, Esc 로 닫기,
 * 뒤 스크롤 잠금, 낭독기에 "대화상자" 로 알리는 것까지 브라우저가 한다.
 * div 로 만들면 그 넷을 직접 짜야 하고 대개 포커스 가둠에서 샌다.
 *
 * 다만 dialog 는 기본이 화면 가운데다. 아래에 붙이려면 여백을 직접 준다.
 */
export function RecordSheet({
  studiedDays,
  children,
}: {
  /**
   * 점수를 얻은 날의 수. 칩에 그대로 쓴다.
   *
   * **연속 일수가 아니다.** 백엔드가 세는 것은 "점수가 남은 날의 합"
   * 이라 하루 쉬어도 앞의 날들이 사라지지 않는다. 그래서 화면 어디에도
   * "연속" 이라고 쓰지 않는다 - 3일 걸러 공부한 사람에게 "3일 연속" 이
   * 뜨면 그건 틀린 숫자다.
   */
  studiedDays: number;
  children: React.ReactNode;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const stopRef = useRef<(() => void) | null>(null);
  const titleId = useId();
  const [open, setOpen] = useState(false);

  // 전역 CSS 의 reduced-motion 블록은 CSS 애니메이션만 0 으로 만든다.
  // 여기 움직임은 JS 가 transform 을 직접 써서 그 블록이 안 닿는다.
  const reduced = useRef(false);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    reduced.current = query.matches;
    const sync = () => (reduced.current = query.matches);
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  useEffect(() => () => stopRef.current?.(), []);

  const setY = (value: number) => {
    const panel = panelRef.current;
    if (panel) panel.style.transform = `translateY(${value}px)`;
  };

  const show = () => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    // showModal 은 명령형이라 open 속성으로는 못 연다. 속성으로 열면
    // ::backdrop 도 포커스 가둠도 안 붙는 그냥 보이는 상자가 된다.
    dialog.showModal();
    setOpen(true);

    const panel = panelRef.current;
    if (!panel) return;
    const height = panel.offsetHeight || 240;
    setY(height);
    if (reduced.current) {
      setY(0);
      return;
    }
    stopRef.current?.();
    // 서랍은 살짝 넘겼다 앉는다. 던져 올린 것이라 그 반동이 자연스럽다.
    stopRef.current = spring(height, 0, 0, 0.85, 0.34, setY);
  };

  const hide = () => {
    const dialog = dialogRef.current;
    const panel = panelRef.current;
    if (!dialog) return;

    const done = () => {
      dialog.close();
      setOpen(false);
    };
    if (!panel || reduced.current) {
      done();
      return;
    }
    stopRef.current?.();
    // 닫을 때는 안 튕긴다. 이미 정한 동작이라 빠를수록 좋다.
    stopRef.current = spring(
      currentY(panel),
      panel.offsetHeight || 240,
      0,
      1,
      0.3,
      setY,
      done,
    );
  };

  /* ---- 손잡이를 끌어 닫기 ---- */

  const drag = useRef<{
    id: number;
    originY: number;
    y: number;
    trail: { y: number; t: number }[];
  } | null>(null);

  const onHandleDown = (event: React.PointerEvent<HTMLElement>) => {
    const panel = panelRef.current;
    if (!panel) return;
    // 이미 한 손가락이 끌고 있으면 두 번째는 무시한다. 안 그러면 나중
    // 손가락이 앞의 상태를 덮어써서, 앞 손가락을 뗄 때 id 가 안 맞아
    // 정리가 안 되고 캡처가 남는다.
    if (drag.current) return;
    stopRef.current?.();
    stopRef.current = null;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = {
      id: event.pointerId,
      originY: event.clientY - currentY(panel),
      y: currentY(panel),
      trail: [{ y: event.clientY, t: event.timeStamp }],
    };
  };

  const onHandleMove = (event: React.PointerEvent<HTMLElement>) => {
    const state = drag.current;
    const panel = panelRef.current;
    if (!state || !panel || state.id !== event.pointerId) return;

    let next = event.clientY - state.originY;
    // 위로 넘기면 저항이 붙는다. 그대로 따라가면 시트가 화면 위로
    // 사라지고 돌아올 길이 안 보인다.
    if (next < 0) next = -rubber(-next, panel.offsetHeight || 240);
    state.y = next;
    setY(next);
    state.trail.push({ y: event.clientY, t: event.timeStamp });
    if (state.trail.length > 6) state.trail.shift();
  };

  const onHandleUp = (event: React.PointerEvent<HTMLElement>) => {
    const state = drag.current;
    const panel = panelRef.current;
    if (!state || !panel || state.id !== event.pointerId) return;
    drag.current = null;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // 이미 풀렸으면 할 일이 없다.
    }

    const first = state.trail[0];
    const last = state.trail[state.trail.length - 1];
    const span = Math.max(1, last.t - first.t);
    const velocity = ((last.y - first.y) / span) * 1000;

    // 놓은 자리가 아니라 가려던 자리로 판정한다. 아래로 튕기면 조금만
    // 내렸어도 닫는 것이 맞다.
    const height = panel.offsetHeight || 240;
    if (state.y + project(velocity) > height * 0.4) {
      hide();
      return;
    }
    stopRef.current?.();
    stopRef.current = spring(state.y, 0, velocity, 0.85, 0.34, setY);
  };

  return (
    <>
      <button
        type="button"
        onClick={show}
        aria-haspopup="dialog"
        className="ml-auto flex shrink-0 items-center gap-1 rounded-lg border-2 border-slate-950 bg-focus px-2 py-1 font-mono text-xs font-bold text-focus-on shadow-[2px_2px_0_var(--color-focus-shade)] transition-[scale] duration-[120ms] ease-press active:scale-[0.94] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        {/* 이모지를 쓰지 않는다. 자형과 폭이 플랫폼마다 달라서 각을
            세운 이 칩의 너비가 기기마다 어긋나고, 코드에 이모지를 넣지
            않는 것이 이 저장소 규칙이다. HomeTasks 의 한 글자 표식과
            같은 방식으로 맞춘다. */}
        <span aria-hidden className="tabular-nums">
          {studiedDays}
        </span>
        <span aria-hidden className="text-[10px] opacity-70">
          일
        </span>
        <span className="sr-only">{studiedDays}일 공부함 · 오늘 기록 열기</span>
      </button>

      <dialog
        ref={dialogRef}
        aria-labelledby={titleId}
        onClose={() => setOpen(false)}
        onCancel={(event) => {
          // Esc 는 브라우저가 바로 닫아버려서 내려가는 움직임이 안 보인다.
          // 막고 같은 경로로 보낸다.
          event.preventDefault();
          hide();
        }}
        onClick={(event) => {
          // 바깥(::backdrop)을 누르면 닫는다. dialog 자신이 이벤트
          // 대상이면 바깥이다 - 안쪽은 panel 이 대상이 된다.
          if (event.target === dialogRef.current) hide();
        }}
        className="m-0 mt-auto w-full max-w-md bg-transparent p-0 backdrop:bg-slate-950/70 sm:mx-auto"
      >
        <div
          ref={panelRef}
          // 열기 전에도 아래에 숨어 있어야 한다. show() 가 높이를 재서
          // 다시 넣지만, 그전 한 프레임 동안 가운데 떠 보이는 것을 막는다.
          style={{ transform: "translateY(100%)" }}
          className="rounded-t-3xl border-2 border-b-0 border-white/12 bg-slate-950/95 px-5 pt-2.5 pb-6 backdrop-blur-sm"
        >
          {/* 손잡이. 끌 수 있는 곳이라 넉넉한 세로 여백을 준다 - 4px
              막대만 잡으라고 하면 잘 안 잡힌다. */}
          <div
            onPointerDown={onHandleDown}
            onPointerMove={onHandleMove}
            onPointerUp={onHandleUp}
            onPointerCancel={onHandleUp}
            className="mx-auto w-full cursor-grab touch-none py-2 active:cursor-grabbing"
          >
            <div aria-hidden className="mx-auto h-1.5 w-10 rounded-full bg-white/25" />
          </div>

          <div className="mt-2 flex items-baseline justify-between gap-3">
            <h2
              id={titleId}
              className="font-mono text-sm font-bold tracking-tight text-slate-50"
            >
              오늘의 기록
            </h2>
            <button
              type="button"
              onClick={hide}
              className="rounded-md px-2 py-1 text-xs text-slate-400 transition hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            >
              닫기
            </button>
          </div>

          {/* 열려 있을 때만 그린다. 닫힌 시트 안의 링크가 Tab 순서에
              남아 있으면 홈에서 Tab 을 누르다 보이지 않는 곳에 걸린다. */}
          {open && <div className="mt-3">{children}</div>}
        </div>
      </dialog>
    </>
  );
}

/** 지금 화면에 그려진 세로 위치. 스프링이 여기서 이어받는다. */
function currentY(el: HTMLElement): number {
  const value = new DOMMatrixReadOnly(getComputedStyle(el).transform).m42;
  return Number.isFinite(value) ? value : 0;
}
