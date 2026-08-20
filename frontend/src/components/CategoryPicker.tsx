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
        className="flex min-h-11 items-center gap-2 rounded-full border border-white/40 px-4 text-sm text-slate-200 transition-[scale,border-color] duration-[120ms] ease-press hover:border-white/60 active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        <span className="text-slate-400">분류</span>
        <span className="font-medium">{label}</span>
        {/* 화살표가 열림 상태를 말한다. 글자만으로는 눌러야 뭐가 되는지 모른다. */}
        <span
          aria-hidden
          className={`text-xs transition-transform duration-[120ms] ease-press ${
            open ? "rotate-180" : ""
          }`}
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
          className="absolute top-full left-0 z-20 mt-2 max-h-72 w-64 overflow-y-auto rounded-xl border border-white/12 bg-slate-950/95 p-1.5 shadow-[0_12px_32px_-8px_rgb(0_0_0/0.8)] backdrop-blur-sm"
        >
          <PickerItem href={href()} active={!selected} onNavigate={() => setOpen(false)}>
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
      className={`flex min-h-11 items-center justify-between gap-2 rounded-lg px-3 text-sm transition-[background-color] duration-[120ms] ease-press focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus ${
        active
          ? "bg-white/10 font-medium text-slate-50"
          : "text-slate-300 hover:bg-white/5"
      }`}
    >
      {children}
      {active && <span aria-hidden>✓</span>}
    </Link>
  );
}
