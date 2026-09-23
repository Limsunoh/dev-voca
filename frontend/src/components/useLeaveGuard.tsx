"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { LEAVE_TITLE, leaveDetail, solvedToConfirm } from "@/lib/quiz-progress";

import { LeaveConfirm } from "./LeaveConfirm";

/**
 * 링크를 누르면 판이 끝나는 출구에 확인을 붙인다.
 *
 * 문제풀기의 링크 출구 셋(분류 고르개, 단어·문장 탭, "한 판 풀기")이 쓴다.
 * 셋이 같은 판단을 각자 짜면 한 곳만 고쳐진다 - 새 탭으로 여는 클릭을
 * 빼먹는 것처럼.
 *
 * **링크를 그대로 둔다.** 주소가 남아야 뒤로가기·공유·새 탭 열기가 되고
 * 자바스크립트 없이도 동작한다. 푼 것이 있을 때만 기본 이동을 막고 창을
 * 열며, 확인을 받으면 여기서 직접 옮긴다.
 *
 * 돌려주는 것: 링크의 onClick 에서 부를 guard, 그리고 화면에 한 번 그릴 창.
 */
export function useLeaveGuard({
  confirmLabel,
  beforeLeave,
}: {
  /** 창의 진행 버튼 글자. */
  confirmLabel: string;
  /** 옮기기 직전에 할 일(메뉴 닫기 등). */
  beforeLeave?: () => void;
}) {
  const router = useRouter();
  const openRef = useRef<(() => void) | null>(null);
  /** 확인을 받으면 갈 곳. */
  const pendingRef = useRef("");
  /**
   * 창을 열 때 푼 문제 수. 창 문구가 이 값을 말한다.
   *
   * 그릴 때 읽으면 안 된다 - 창은 열리기 전부터 화면에 있어서 처음 그린
   * 때의 0 이 그대로 남는다. 실제로 "푼 0문제" 가 떴다.
   */
  const [asked, setAsked] = useState(0);

  /** 막았으면 true. 링크의 기본 이동을 막은 것이다. */
  const guard = (event: React.MouseEvent, href: string): boolean => {
    const count = solvedToConfirm(event);
    if (count === 0) return false;
    event.preventDefault();
    pendingRef.current = href;
    setAsked(count);
    openRef.current?.();
    return true;
  };

  const dialog = (
    <LeaveConfirm
      openRef={openRef}
      title={LEAVE_TITLE}
      detail={leaveDetail(asked)}
      confirmLabel={confirmLabel}
      onConfirm={() => {
        beforeLeave?.();
        router.push(pendingRef.current);
      }}
    />
  );

  return { guard, dialog };
}
