"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { traverseBackTo } from "@/lib/history-nav";

import { LeaveConfirm } from "./LeaveConfirm";

/**
 * 저장 안 한 변경이 있을 때, 화면을 떠나기 전에 묻는다.
 *
 * 두 길을 막는다.
 *
 *     새로고침·탭 닫기·다른 사이트   beforeunload. 브라우저 자기 창이 뜨고
 *                                     문구는 못 바꾼다. iOS Safari 는 이
 *                                     창을 안 띄운다.
 *     앱 안 링크(탭바 등)            문서에 클릭을 캡처로 받아 이동을 멈추고
 *                                     LeaveConfirm 을 연다.
 *
 * 링크마다 붙이지 않고 문서에서 한 번에 받는다. 떠나는 링크는 대부분
 * 탭바에 있고, 탭바는 모든 화면이 같이 쓴다. 화면 하나 때문에 탭바에
 * 확인을 넣으면 다른 화면의 동작까지 바뀐다. 캡처 단계라 링크 자신의
 * onClick(Next 의 Link)보다 먼저 돌고, 여기서 막으면 Link 는 이미 막힌
 * 클릭으로 보고 이동하지 않는다.
 *
 * 뒤로가기는 못 막는다. App Router 에는 이동을 멈추는 방법이 없다.
 *
 * 문제풀기의 useLeaveGuard 와 따로 둔다. 그쪽은 "푼 문제 수" 로 물을지를
 * 정하고 출구 링크가 직접 부르는 방식이라, 판단도 거는 자리도 다르다.
 */
export function useUnsavedGuard({
  dirty,
  title,
  detail,
  confirmLabel,
  cancelLabel,
}: {
  /** 저장 안 한 변경이 있나. false 면 아무것도 걸지 않는다. */
  dirty: boolean;
  title: string;
  /** 잃는 것. LeaveConfirm 과 같이, 무엇이 사라지는지 구체적으로. */
  detail: string;
  confirmLabel: string;
  cancelLabel: string;
}) {
  const router = useRouter();
  const openRef = useRef<(() => void) | null>(null);
  /** 확인을 받으면 갈 곳. */
  const pendingRef = useRef("");
  /** 그 링크가 아래 탭이었나. 탭은 기록을 쌓지 않는다(TabBar). */
  const fromTabRef = useRef(false);
  /**
   * 창에서 "나가기" 를 눌렀나. 이동이 페이지를 내리는 쪽으로 떨어지면
   * (Next 밖 경로, 새 배포 뒤 등) beforeunload 창이 한 번 더 뜨는 것을 막는다.
   */
  const leavingRef = useRef(false);

  useEffect(() => {
    if (!dirty) return;
    // 떠나기로 했다가 화면이 그대로 남은 경우(이동이 막혔거나 뒤로가기로
    // 돌아옴) 다시 지킨다.
    leavingRef.current = false;

    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (leavingRef.current) return;
      event.preventDefault();
      // 옛 브라우저는 returnValue 를 채워야 묻는다.
      event.returnValue = "";
    };

    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return;
      // 새 탭·새 창으로 여는 클릭은 이 화면을 안 떠난다.
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }

      const target = event.target;
      if (!(target instanceof Element)) return;
      const link = target.closest("a[href]");
      if (!(link instanceof HTMLAnchorElement)) return;
      if (link.target && link.target !== "_self") return;
      if (link.hasAttribute("download")) return;

      const url = new URL(link.href, window.location.href);
      // 밖으로 나가는 링크는 페이지를 내리므로 beforeunload 가 받는다.
      if (url.origin !== window.location.origin) return;
      // 같은 화면을 가리키는 링크(# 이동, 지금 탭 다시 누르기)는 떠나는
      // 것이 아니다.
      if (
        url.pathname === window.location.pathname &&
        url.search === window.location.search
      ) {
        return;
      }

      event.preventDefault();
      pendingRef.current = url.pathname + url.search + url.hash;
      fromTabRef.current = link.closest("[data-tabbar]") !== null;
      openRef.current?.();
    };

    window.addEventListener("beforeunload", onBeforeUnload);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      document.removeEventListener("click", onClick, true);
    };
  }, [dirty]);

  return (
    <LeaveConfirm
      openRef={openRef}
      title={title}
      detail={detail}
      confirmLabel={confirmLabel}
      cancelLabel={cancelLabel}
      onConfirm={() => {
        leavingRef.current = true;
        // 아래 탭이었으면 탭처럼 간다. 지나온 기록에 그 화면이 있으면 돌아가고,
        // 없으면 바꿔치기한다. 쌓으면 [홈, 내정보, 홈] 이 되어 앱(TWA)에서 홈의
        // 뒤로 가기가 내정보로 간다(lib/history-nav.ts). 이 확인은 내정보에만
        // 걸려서, 홈에서 나갈 때만 쌓는 탭의 규칙은 따로 볼 일이 없다.
        if (!fromTabRef.current) {
          router.push(pendingRef.current);
        } else if (!traverseBackTo(new URL(pendingRef.current, window.location.href).pathname)) {
          router.replace(pendingRef.current);
        }
      }}
    />
  );
}
