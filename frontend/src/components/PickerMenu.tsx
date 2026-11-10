"use client";

import { type RefObject, useEffect, useState } from "react";

/**
 * 문제 화면의 접히는 고르개(분류, 유형)가 같이 쓰는 모양과 동작.
 *
 * 한 줄에 나란히 놓이므로 둘의 생김새가 달라지면 바로 눈에 띈다. 항목은
 * 다르다. 분류는 주소가 바뀌는 링크이고 유형은 값만 바꾸는 버튼이다.
 */

// dv-btn: 누르면 두께가 0 이 되고 그만큼 내려앉는다. :active 는 인라인 style 로
// 못 써서 globals.css 의 공통 클래스가 맡는다.
export const PICKER_BUTTON_CLASS =
  "dv-btn flex items-center gap-2 rounded-full px-4 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

export const PICKER_BUTTON_STYLE = {
  minHeight: "var(--hit-floor)",
  background: "var(--paper)",
  color: "var(--foreground)",
  fontWeight: "var(--weight-bold)",
  "--lift": "var(--lift-card)",
} as React.CSSProperties;

// 폭은 16rem 이되 화면 폭에서 양쪽 1rem 을 뺀 만큼을 넘지 않는다. 글자를 키운
// 좁은 폰에서는 16rem 이 화면보다 넓어진다. 아래 menuShift 가 이 폭으로 계산하므로
// 바꾸면 거기도 같이 바꾼다 - 어긋나도 에러는 안 난다.
export const PICKER_MENU_CLASS =
  "absolute top-full left-0 z-20 mt-2 w-64 max-w-[calc(100vw-2rem)] overflow-y-auto p-1.5";

/**
 * 메뉴를 왼쪽으로 얼마나 밀어야 화면 안에 드는지. 0 이하다.
 *
 * 줄 맨 앞이 아닌 고르개는 폰에서 메뉴가 화면 오른쪽을 넘는다. 넘치는 만큼만
 * 밀되, 화면이 메뉴보다 좁으면 왼쪽 여백 16px 을 먼저 지킨다.
 * rem 을 읽는 이유: 글자 크기를 키운 폰에서는 16rem 이 256px 보다 넓다.
 */
export function menuShift(button: HTMLElement): number {
  const left = button.getBoundingClientRect().left;
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  // innerWidth 가 아니라 clientWidth: 스크롤바가 있는 화면에서 그 폭을 빼야 한다.
  const viewport = document.documentElement.clientWidth;
  const width = Math.min(16 * rem, viewport - 2 * rem);
  const over = left + width - (viewport - 16);
  return Math.min(0, Math.max(16 - left, -over));
}

/**
 * 메뉴 판. 흐린 그림자·글래스를 쓰지 않는다(가이드 shape-lift). 떠 있는 판이라
 * 두께는 카드보다 한 급 두꺼운 --lift-sheet 를 쓴다. 아래 보기 버튼(--lift-card)과
 * 같은 두께면 어느 쪽이 위인지 안 보인다. 눌리는 판이 아니라 정적이라 인라인
 * boxShadow 로 둔다.
 */
export function pickerMenuStyle(maxHeight?: number): React.CSSProperties {
  return {
    background: "var(--paper)",
    borderRadius: "var(--radius-xl)",
    boxShadow: "var(--lift-sheet)",
    maxHeight,
  };
}

export const PICKER_ITEM_CLASS =
  "flex items-center justify-between gap-2 px-3 text-sm transition-[background-color] duration-[120ms] ease-press focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus";

/** 고른 것은 옅은 코랄 채움 + 코랄 글자. 회색 위 회색은 종이 위에서 대비가 안 남는다. */
export function pickerItemStyle(active: boolean): React.CSSProperties {
  return {
    minHeight: "var(--hit-floor)",
    borderRadius: "var(--radius-md)",
    background: active ? "var(--coral-soft)" : "transparent",
    color: active ? "var(--coral-soft-text)" : "var(--text-body)",
    fontWeight: active ? "var(--weight-black)" : "var(--weight-medium)",
  };
}

/** 여는 버튼의 글자: 이름, 지금 값, 화살표. */
export function PickerFace({
  title,
  label,
  open,
}: {
  title: string;
  label: string;
  open: boolean;
}) {
  return (
    <>
      {/* --text-dim 은 흰 종이 위 3.85:1 로 본문 대비에 못 미친다. */}
      <span style={{ color: "var(--text-muted)" }}>{title}</span>
      <span>{label}</span>
      {/* 화살표가 열림 상태를 말한다. 글자만으로는 눌러야 뭐가 되는지 모른다. */}
      <span
        aria-hidden
        className={`text-xs transition-transform duration-[120ms] ease-press ${
          open ? "rotate-180" : ""
        }`}
        style={{ color: "var(--text-dim)" }}
      >
        ▼
      </span>
    </>
  );
}

/**
 * 열린 메뉴를 닫는 조건과, 메뉴가 쓸 수 있는 최대 높이.
 *
 * 높이는 열 때 재고 화면이 바뀌면 다시 잰다. 고정값(전에는 288px)을 쓰면 그
 * 숫자가 실제 여유와 어긋나 항목이 숨거나 메뉴가 화면을 넘는다. 이 버튼은 문제
 * 카드 위에 얹히는 자리라 위치가 화면마다 다르고 스크롤에 따라서도 움직인다.
 * 같은 화면의 QuizBoard 도 탭바 높이를 상수로 두지 않고 재는데 이유가 같다.
 *
 * undefined 로 시작하고 effect 가 페인트 뒤에 채우므로, 제한 없이 그려지는 첫
 * 프레임이 있다. 지금은 항목이 적어 어떤 측정값보다 작아 눈에 안 보인다. 항목이
 * 늘어 화면을 넘기면 그 프레임이 드러나므로, 그때는 useLayoutEffect 로 바꿔야 한다.
 */
export function usePickerMenu(
  open: boolean,
  setOpen: (open: boolean) => void,
  boxRef: RefObject<HTMLDivElement | null>,
  buttonRef: RefObject<HTMLButtonElement | null>,
): number | undefined {
  const [maxHeight, setMaxHeight] = useState<number | undefined>();

  // 바깥을 누르거나 포커스가 나가면 닫는다. 열어둔 채로 두면 이 메뉴가
  // 첫째·둘째 보기 버튼을 덮는다 - 포커스가 그 뒤로 가면 지금 무엇을
  // 고르는지 안 보인 채로 Enter 를 누르게 된다.
  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: PointerEvent) {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false);
    }
    // Esc 로도 닫는다. 키보드로 연 사람에게 닫을 방법이 없으면 갇힌다.
    function onKeyDown(event: KeyboardEvent) {
      // 확인 창 안에서 누른 Esc 는 창만 닫는다. 여기까지 올라와 메뉴도
      // 닫으면, 창이 포커스를 돌려줄 링크가 메뉴와 함께 사라져 포커스가
      // 문서 맨 앞으로 떨어진다.
      if ((event.target as Element | null)?.closest?.("dialog")) return;
      if (event.key === "Escape") {
        setOpen(false);
        // 메뉴 항목에 있던 초점이 항목과 함께 사라지지 않게 돌려준다.
        buttonRef.current?.focus();
      }
    }
    // Tab 으로 메뉴 밖으로 나가면 닫는다. pointerdown 만 들으면 마우스로는
    // 닫히는데 키보드로는 열린 채 남아서, 가려진 버튼 위에 포커스가 선다.
    function onFocusIn(event: FocusEvent) {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false);
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("focusin", onFocusIn);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("focusin", onFocusIn);
    };
  }, [open, setOpen, boxRef, buttonRef]);

  // 버튼 아래로 남은 높이를 잰다. 24px 은 메뉴 아래에 남기는 틈이다.
  // 0 으로 두면 마지막 항목이 화면 맨 끝에 붙어 더 없다는 것이 안 보인다.
  //
  // resize 를 듣는 이유: 폰을 돌리면 높이가 절반으로 줄어드는데, 그때 잰
  // 값이 그대로면 메뉴가 화면을 넘어 아래쪽 항목에 닿지 못한다.
  //
  // scroll 도 듣는다. 이 화면은 스스로 문서를 내린다. 보기를 고르면
  // 해설이 붙고 QuizBoard 가 "다음 문제" 버튼이 보이도록 스크롤한다. 그때
  // 버튼이 위로 올라가는데 잰 값이 그대로면 메뉴가 화면 아래로 넘친다.
  // 채점은 분류를 바꾸지 않으니(page.tsx 의 key 는 분류에만 걸린다) 그 사이
  // 메뉴가 열린 채 남을 수 있다.
  //
  // 스로틀은 안 걸었다. 도는 것이 rect 읽기 한 번이다.
  useEffect(() => {
    if (!open) return;

    function measure() {
      const box = boxRef.current;
      if (!box) return;
      // 메뉴는 버튼 바로 아래(mt-2 = 8px)에 붙는다. 그 클래스를 바꾸면
      // 이 숫자도 같이 바꿔야 한다 - 어긋나도 에러는 안 난다.
      const top = box.getBoundingClientRect().bottom + 8;
      // innerHeight 를 안 쓰는 이유: iOS 사파리는 주소창이 펴진 높이를
      // 주므로 그 차이만큼 메뉴 아래가 주소창에 가려 눌리지 않는다.
      //
      // offsetTop 을 더하는 것은 좌표계를 맞추기 위해서다. 위 rect 는
      // 레이아웃 기준인데 visualViewport 의 height 는 "보이는 영역" 만의
      // 높이여서, 핀치 줌이나 키보드로 그 영역이 안에서 밀리면 두 값의
      // 기준점이 달라진다. offsetTop 을 더하면 "보이는 영역의 아래 끝" 을
      // 레이아웃 좌표로 말한 값이 되어 rect 와 같은 자를 쓴다.
      const vv = window.visualViewport;
      const vh = vv ? vv.offsetTop + vv.height : window.innerHeight;
      // 하한 120px: 가로로 눕힌 폰처럼 화면이 낮으면 남은 높이가 0 에
      // 가까워져 메뉴가 없는 것처럼 보인다. 대신 이 창이 화면을 넘으면
      // 넘친 만큼은 어떤 스크롤로도 안 보인다(메뉴 안 스크롤은 창 안에서만
      // 움직이고 absolute 라 문서 높이에도 기여하지 않는다). 키보드로
      // 넘어간 항목에 포커스가 가면 안 보이는 채로 Enter 를 누르게 된다.
      // 항목 두어 개라도 보이는 쪽을 택한 대가다.
      setMaxHeight(Math.max(120, vh - top - 24));
    }

    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, { passive: true });
    // 주소창이 접히고 펴지는 순간은 window 의 resize 를 안 쏘는 기기가 있다.
    // 높이를 visualViewport 에서 읽으니 리스너도 그쪽에 붙여야 짝이 맞다.
    // scroll 까지 듣는 이유는 위에서 쓰는 offsetTop 이 그때 바뀌기 때문이다.
    // vv 쪽 scroll 에 passive 를 안 붙인 것은 빠뜨린 게 아니다 - 취소할 수
    // 없는 이벤트라 붙여도 같다.
    const vv = window.visualViewport;
    vv?.addEventListener("resize", measure);
    vv?.addEventListener("scroll", measure);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure);
      vv?.removeEventListener("resize", measure);
      vv?.removeEventListener("scroll", measure);
    };
  }, [open, boxRef]);

  return maxHeight;
}
