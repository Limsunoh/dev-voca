"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import type { ChoiceOption } from "@/lib/api/client";

/**
 * 접히는 분류 고르개.
 *
 * 문제풀이 화면에서 칩을 줄줄이 늘어놓으면 폰에서 네 줄을 먹는다. 그만큼
 * 문제와 보기가 아래로 밀려서, 정작 풀어야 할 것이 화면 밖으로 나간다.
 * 여기서는 지금 고른 것 하나만 보이고, 누르면 나머지가 펼쳐진다.
 *
 * 목록 화면은 지금처럼 칩을 다 펼쳐 두는 게 맞다 - 거기는 훑어보며 좁히는
 * 자리라 무엇이 있는지 한눈에 보여야 한다. 여기는 하나 고르고 끝이다.
 *
 * 항목이 버튼이 아니라 링크인 이유: 고른 분류가 URL 에 남아야 뒤로가기와
 * 공유가 그대로 되고, 자바스크립트 없이도 동작한다.
 *
 * **호출부에서 key={selected} 를 줄 것.** 항목을 누르는 경로는 onClick 이
 * 메뉴를 닫아주지만 브라우저 뒤로가기는 그 핸들러를 거치지 않아, 주소가
 * 바뀌었는데 메뉴가 열린 채로 남고 그 밑의 보기 버튼을 덮는다. effect 로
 * 닫으면 렌더가 한 번 더 도니 리마운트가 낫다.
 *
 * **여기서 분류를 바꾸면 판이 새로 시작된다.** 위의 key 와는 다른 이야기다 -
 * 호출부가 문제 판(`QuizBoard`)에도 분류를 key 로 주기 때문에, 항목을
 * 누르면 그쪽이 함께 새로 만들어지고 점수가 사라진다. 되돌릴 수 없는데
 * 확인 절차가 없다. 목록용 칩은 `CategoryFilter` 의 `toggle` 로 같은
 * 위험을 막는다. 판 상태를 끌어올려야 하는 일이라 따로 다룬다.
 */
export function CategoryPicker({
  options,
  basePath,
  selected,
}: {
  options: ChoiceOption[];
  basePath: string;
  /** 지금 고른 분류. 없으면 전체. */
  selected?: string;
}) {
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  /**
   * 메뉴가 쓸 수 있는 최대 높이. 열 때 재고 화면이 바뀌면 다시 잰다.
   *
   * 고정값(전에는 288px)을 쓰면 그 숫자가 실제 여유와 어긋나 항목이 숨거나
   * 메뉴가 화면을 넘는다. 이 버튼은 문제 카드 위에 얹히는 자리라 위치가
   * 화면마다 다르고 스크롤에 따라서도 움직인다. 같은 화면의 QuizBoard 도
   * 탭바 높이를 상수로 두지 않고 재는데 이유가 같다.
   *
   * undefined 로 시작하고 effect 가 페인트 뒤에 채우므로, **제한 없이
   * 그려지는 첫 프레임이 있다.** 지금은 분류가 여덟 개여서 어떤 측정값보다
   * 작아 눈에 안 보인다. 분류가 늘어 화면을 넘기면 그 프레임이 드러나므로,
   * 그때는 useLayoutEffect 로 바꿔야 한다.
   */
  const [maxHeight, setMaxHeight] = useState<number | undefined>();

  const current = options.find((o) => o.value === selected);
  const label = current ? current.label : "전체";

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
      if (event.key === "Escape") setOpen(false);
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
  }, [open]);

  // 버튼 아래로 남은 높이를 잰다. 24px 은 메뉴 아래에 남기는 틈이다 -
  // 0 으로 두면 마지막 항목이 화면 맨 끝에 붙어 더 없다는 것이 안 보인다.
  //
  // resize 를 듣는 이유: 폰을 돌리면 높이가 절반으로 줄어드는데, 그때 잰
  // 값이 그대로면 메뉴가 화면을 넘어 아래쪽 항목에 닿지 못한다.
  //
  // **scroll 도 듣는다.** 이 화면은 스스로 문서를 내린다 - 보기를 고르면
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
      // 움직이고 absolute 라 문서 높이에도 기여하지 않는다) - 키보드로
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
  }, [open]);

  const href = (value?: string) =>
    value ? `${basePath}?category=${encodeURIComponent(value)}` : basePath;

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        // 무엇이 펼쳐지는지 연결한다. aria-expanded 만 있으면 "열렸다" 는
        // 알지만 무엇이 열렸는지는 모른다.
        aria-controls="category-picker-menu"
        // dv-btn: 누르면 두께가 0 이 되고 그만큼 내려앉는다. :active 는
        // 인라인 style 로 못 써서 globals.css 의 공통 클래스가 맡는다.
        className="dv-btn flex items-center gap-2 rounded-full px-4 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        style={
          {
            minHeight: "var(--hit-floor)",
            background: "var(--paper)",
            color: "var(--foreground)",
            fontWeight: "var(--weight-bold)",
            "--lift": "var(--lift-card)",
          } as React.CSSProperties
        }
      >
        {/* --text-dim 은 흰 종이 위 3.85:1 로 본문 대비에 못 미친다. */}
        <span style={{ color: "var(--text-muted)" }}>분류</span>
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
      </button>

      {open && (
        // 목록을 흐름 위에 띄운다. 자리를 차지하면 펼칠 때마다 문제와 보기가
        // 아래로 밀려서, 고르는 동안 화면이 출렁인다.
        //
        // nav 로 두고 이름을 준다. 그냥 div 면 스크린리더에서 맥락 없는
        // 링크 나열로 읽힌다 - 목록 화면의 CategoryFilter 가 같은 이유로
        // 이미 nav + aria-label 을 쓴다.
        <nav
          id="category-picker-menu"
          aria-label="분류 고르기"
          // 흐린 그림자·글래스를 쓰지 않는다(가이드 shape-lift). 떠 있는
          // 판이라 두께는 카드보다 한 급 두꺼운 --lift-sheet 를 쓴다 -
          // 아래 보기 버튼(--lift-card)과 같은 두께면 어느 쪽이 위인지
          // 안 보인다. 눌리는 판이 아니라 정적이라 인라인 boxShadow 로 둔다.
          className="absolute top-full left-0 z-20 mt-2 w-64 overflow-y-auto p-1.5"
          style={{
            background: "var(--paper)",
            borderRadius: "var(--radius-xl)",
            boxShadow: "var(--lift-sheet)",
            // 고정 높이를 쓰지 않는 이유는 위 maxHeight 선언에 있다.
            maxHeight,
          }}
        >
          <PickerItem
            href={href()}
            active={!selected}
            onNavigate={() => setOpen(false)}
          >
            전체
          </PickerItem>
          {options.map((option) => (
            <PickerItem
              key={option.value}
              href={href(option.value)}
              active={option.value === selected}
              onNavigate={() => setOpen(false)}
            >
              {option.label}
            </PickerItem>
          ))}
        </nav>
      )}
    </div>
  );
}

function PickerItem({
  href,
  active,
  onNavigate,
  children,
}: {
  href: string;
  active: boolean;
  onNavigate: () => void;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      // 고른 것을 색만으로 표시하지 않는다. 색각 이상이 있으면 구분이 안 된다.
      // "page" 인 이유: 이 링크를 누르면 그 분류 화면으로 가고, 지금 그
      // 화면에 있다는 뜻이다. ContentTabs 도 같은 값을 쓴다.
      aria-current={active ? "page" : undefined}
      className="flex items-center justify-between gap-2 px-3 text-sm transition-[background-color] duration-[120ms] ease-press focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus"
      style={{
        minHeight: "var(--hit-floor)",
        borderRadius: "var(--radius-md)",
        // 고른 것은 옅은 코랄 채움 + 코랄 글자. 회색 위 회색으로 두면
        // 종이 위에서 대비가 거의 안 남는다.
        background: active ? "var(--coral-soft)" : "transparent",
        color: active ? "var(--coral-deep)" : "var(--text-body)",
        fontWeight: active ? "var(--weight-black)" : "var(--weight-medium)",
      }}
    >
      {children}
      {/* 색만으로 고른 것을 표시하지 않는다. 색각 이상이 있으면 구분이 안 된다. */}
      {active && <span aria-hidden>✓</span>}
    </Link>
  );
}
