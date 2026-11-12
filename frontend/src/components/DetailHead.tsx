"use client";

import { useId, useState } from "react";

/**
 * 단어 상세의 머리: 맨 위 줄(되돌아가기 + "발음 자세히") 과 히어로 카드, 그리고
 * 펼친 발음 설명.
 *
 * 발음 설명은 접어둔다. 목록에서 훑을 때는 필요 없고, 상세에서도 "왜 그렇게
 * 읽는지" 가 궁금한 사람만 연다. 펼친 채로 두면 뜻보다 먼저 눈에 들어와 읽는
 * 순서가 뒤집힌다.
 *
 * 여는 버튼은 맨 위 줄, 되돌아가기 옆에 둔다. 전에는 뜻 카드와 설명 카드 사이에
 * 한 줄을 따로 차지해서, 폰 첫 화면에서 설명 카드가 그만큼 아래로 밀렸다
 * (2026-11-12 사용자 요청 "맨 위 홈 버튼 옆으로, 한눈에 보이게"). 맨 위 줄은
 * 되돌아가기 하나뿐이라 옆자리가 비어 있다.
 *
 * 펼친 설명은 히어로 카드 바로 아래, 버튼이 있던 원래 자리에 온다. 맨 위 줄
 * 아래에 두면 설명이 단어 제목과 발음보다 먼저 읽힌다 - 설명하는 대상보다
 * 설명이 앞선다. 겹쳐 띄우지 않고 아래 내용을 민다. 겹치면 아래 카드를 가린다.
 * 그래서 이 컴포넌트가 히어로를 children 으로 받아 그 사이에 둔다.
 *
 * details/summary 를 쓰지 않는다. 펼친 내용이 summary 와 같은 details 안에
 * 그려져서, 버튼과 내용을 떨어뜨려 둘 수 없다. 대신 aria-expanded 와
 * aria-controls 로 열림을 알린다.
 *
 * back 은 페이지(서버)가 만든 되돌아가기 버튼을 그대로 받는다. 여기서 다시
 * 만들면 되돌아가기 주소 규칙(목록·홈)이 두 곳으로 갈린다.
 */
export function DetailHead({
  back,
  note,
  children,
}: {
  back: React.ReactNode;
  /** 발음 설명. 비어 있으면 버튼도 설명도 안 그린다. */
  note: string;
  /** 히어로 카드. 맨 위 줄과 펼친 설명 사이에 온다. */
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const noteId = useId();

  return (
    <>
      {/* 글자를 키우면 둘이 한 줄에 안 들어갈 수 있어 줄을 바꾼다. */}
      <div className="flex flex-wrap items-center gap-2">
        {back}
        {note && (
          <button
            type="button"
            aria-expanded={open}
            aria-controls={noteId}
            onClick={() => setOpen((was) => !was)}
            // 되돌아가기와 같은 흰 알약 + 두께, 같은 높이(min-h-11). 두 버튼이
            // 한 줄에 나란히 서므로 높이가 다르면 바로 보인다. 글자 굵기는 한
            // 단계 낮춘다(되돌아가기는 black). 이 줄의 주된 동작은 되돌아가기다.
            className="dv-card dv-card-press flex min-h-11 items-center gap-2 rounded-full px-3.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            style={
              {
                background: "var(--paper)",
                color: "var(--foreground)",
                fontSize: "var(--text-sm)",
                fontWeight: "var(--weight-bold)",
                "--lift": "var(--lift-card)",
              } as React.CSSProperties
            }
          >
            발음 자세히
            {/* 열리면 삼각형을 뒤집는다(rotate-180, 0.15초). 열림은
                aria-expanded 가 이미 알려서 화면 낭독기에는 숨긴다. */}
            <span
              aria-hidden
              className={`text-[0.625rem] transition-transform duration-150 ${open ? "rotate-180" : ""}`}
              style={{ color: "var(--text-faint)" }}
            >
              ▼
            </span>
          </button>
        )}
      </div>

      {children}

      {note && (
        // 닫혀 있어도 그려 둔다(hidden). aria-controls 가 가리킬 자리가 늘 있다.
        <p
          id={noteId}
          hidden={!open}
          className="mt-3.5 px-1 text-pretty"
          style={{
            color: "var(--text-body)",
            lineHeight: "var(--leading-relaxed)",
          }}
        >
          {note}
        </p>
      )}
    </>
  );
}
