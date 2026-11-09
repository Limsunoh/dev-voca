"use client";

import { useState } from "react";

import {
  BUTTON,
  CORAL,
  ConsentSheet,
  PAPER,
  type SheetChoice,
} from "@/app/(auth)/ConsentSheet";

/**
 * 시작 화면의 두 버튼. 누르면 필수 항목 시트가 올라온다.
 *
 * 앱을 열자마자 약관 체크박스부터 보이지 않게, 고른 뒤에 묻는다.
 */
export function StartChoices() {
  const [choice, setChoice] = useState<SheetChoice | null>(null);

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

      <ConsentSheet choice={choice} onClose={() => setChoice(null)} />
    </>
  );
}
