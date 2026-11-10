"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import type { ChoiceOption } from "@/lib/api/client";

import {
  PICKER_BUTTON_CLASS,
  PICKER_BUTTON_STYLE,
  PICKER_ITEM_CLASS,
  PICKER_MENU_CLASS,
  PickerFace,
  pickerItemStyle,
  pickerMenuStyle,
  usePickerMenu,
} from "./PickerMenu";
import { useLeaveGuard } from "./useLeaveGuard";

/**
 * 항목을 골라 분류가 바뀐 뒤, 새로 만들어지는 고르개가 여는 버튼에 초점을
 * 둘지.
 *
 * 컴포넌트 안에 두면 안 된다. 호출부의 key={selected} 때문에 분류가 바뀌면
 * 이 컴포넌트가 통째로 새로 만들어져 ref 도 state 도 이어지지 않는다.
 */
let refocusAfterChange = false;

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
 * 호출부는 key={selected} 를 줘야 한다. 항목을 누르는 경로는 onClick 이
 * 메뉴를 닫아주지만 브라우저 뒤로가기는 그 핸들러를 거치지 않아, 주소가
 * 바뀌었는데 메뉴가 열린 채로 남고 그 밑의 보기 버튼을 덮는다. effect 로
 * 닫으면 렌더가 한 번 더 도니 리마운트가 낫다.
 *
 * 여기서 분류를 바꾸면 판이 새로 시작된다. 위의 key 와는 다른 이야기로,
 * 호출부가 문제 판(`QuizBoard`)에도 분류를 key 로 주기 때문에 항목을
 * 누르면 그쪽도 함께 새로 만들어지고 점수가 사라진다. 되돌릴 수 없으므로
 * 푼 것이 있으면 먼저 확인을 묻는다(useLeaveGuard). 목록용 칩은
 * `CategoryFilter` 의 `toggle` 로 같은 위험을 막는다.
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
  const buttonRef = useRef<HTMLButtonElement>(null);

  // 항목을 고르면 메뉴와 함께 초점이 있던 항목도 사라진다. 여는 버튼으로
  // 돌려주지 않으면 초점이 문서 전체(body)로 떨어져 화면 낭독기가 위치를
  // 잃는다.
  const afterPick = (changed: boolean) => {
    if (changed) refocusAfterChange = true;
    setOpen(false);
    buttonRef.current?.focus();
  };

  const { guard, dialog } = useLeaveGuard({
    confirmLabel: "분류 바꾸기",
    beforeLeave: () => afterPick(true),
  });

  useEffect(() => {
    if (!refocusAfterChange) return;
    refocusAfterChange = false;
    buttonRef.current?.focus();
  }, []);

  const maxHeight = usePickerMenu(open, setOpen, boxRef, buttonRef);

  const current = options.find((o) => o.value === selected);
  const label = current ? current.label : "전체";

  const href = (value?: string) =>
    value ? `${basePath}?category=${encodeURIComponent(value)}` : basePath;

  return (
    <div ref={boxRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        // 무엇이 펼쳐지는지 연결한다. aria-expanded 만 있으면 "열렸다" 는
        // 알지만 무엇이 열렸는지는 모른다.
        aria-controls="category-picker-menu"
        className={PICKER_BUTTON_CLASS}
        style={PICKER_BUTTON_STYLE}
      >
        <PickerFace title="분류" label={label} open={open} />
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
          className={PICKER_MENU_CLASS}
          style={pickerMenuStyle(maxHeight)}
        >
          <PickerItem
            href={href()}
            active={!selected}
            onNavigate={afterPick}
            onGuard={guard}
          >
            전체
          </PickerItem>
          {options.map((option) => (
            <PickerItem
              key={option.value}
              href={href(option.value)}
              active={option.value === selected}
              onNavigate={afterPick}
              onGuard={guard}
            >
              {option.label}
            </PickerItem>
          ))}
        </nav>
      )}

      {/* 확인 창. 메뉴가 닫힌 뒤에도 남아 있어야 해서 open 밖에 둔다.
          화면 위에 따로 떠서 메뉴 자리를 밀지 않는다. */}
      {dialog}
    </div>
  );
}

function PickerItem({
  href,
  active,
  onNavigate,
  onGuard,
  children,
}: {
  href: string;
  active: boolean;
  /** 메뉴를 닫는다. 다른 분류로 옮겨 가면 changed 가 true 다. */
  onNavigate: (changed: boolean) => void;
  /** 푼 것이 있으면 이동을 막고 확인 창을 연다. 막았으면 true. */
  onGuard: (event: React.MouseEvent, href: string) => boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      onClick={(event) => {
        if (!active && onGuard(event, href)) return;
        // 새 탭으로 여는 클릭은 이 탭이 그대로라 새로 만들어지지 않는다.
        const newTab =
          event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
        onNavigate(!active && !newTab);
      }}
      // 고른 것을 색만으로 표시하지 않는다. 색각 이상이 있으면 구분이 안 된다.
      // "page" 인 이유: 이 링크를 누르면 그 분류 화면으로 가고, 지금 그
      // 화면에 있다는 뜻이다. ContentTabs 도 같은 값을 쓴다.
      aria-current={active ? "page" : undefined}
      className={PICKER_ITEM_CLASS}
      style={pickerItemStyle(active)}
    >
      {children}
      {/* 색만으로 고른 것을 표시하지 않는다. 색각 이상이 있으면 구분이 안 된다. */}
      {active && <span aria-hidden>✓</span>}
    </Link>
  );
}
