"use client";

import { useEffect, useRef } from "react";

/** 글자를 치는 칸. 라디오·체크박스·파일 칸은 초점이 옮겨도 잃는 것이 없다. */
const TYPING = "input:not([type=radio],[type=checkbox],[type=file]), textarea";

/**
 * 제출에 실패하면 오류 문구를 보이게 한다. 돌려준 ref 를 문구에 붙인다.
 *
 * 저장 버튼은 보내는 동안 꺼져서 초점을 잃는다. 그때는 문구로 초점을 옮겨
 * 키보드와 화면 낭독기 사용자가 결과를 바로 알게 한다.
 *
 * 입력칸에 초점이 있으면 뺏지 않고 화면만 움직인다. 응답을 기다리며 계속
 * 치거나 다른 칸으로 옮겨 간 사람의 글자가 끊기면 안 되고, 폰에서는 키보드가
 * 닫힌다. 내용은 role="alert" 가 읽어 준다.
 *
 * 어느 쪽이든 탭바 높이는 html 의 scroll-padding-bottom 이 비켜 주므로 아래쪽
 * 칸에서 Enter 를 눌러도 문구가 탭바 뒤에 숨지 않는다.
 *
 * 결과 객체를 통째로 본다. 같은 문구가 또 나와도 객체는 새것이라 다시 옮긴다.
 */
export function useFocusOnError(state: { error?: string }) {
  const ref = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (!state.error) return;
    if (document.activeElement?.matches(TYPING)) {
      ref.current?.scrollIntoView({ block: "nearest" });
    } else {
      ref.current?.focus();
    }
  }, [state]);

  return ref;
}
