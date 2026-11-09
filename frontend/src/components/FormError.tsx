"use client";

import { useFocusOnError } from "@/components/useFocusOnError";

/**
 * 폼 결과의 오류 상자. 내정보의 폼들이 같이 쓴다.
 *
 * 알림 자리(aria-live)는 항상 그린다. 내용과 함께 새로 생기면 화면 낭독기가
 * 그 등장을 대부분 안 읽는다. contents 라 비어 있을 때 부모의 gap 을 차지하지
 * 않는다.
 */
export function FormError({ state }: { state: { error?: string } }) {
  const errorRef = useFocusOnError(state);

  return (
    <div aria-live="polite" className="contents">
      {state.error && (
        <p
          role="alert"
          ref={errorRef}
          tabIndex={-1}
          className="rounded-[var(--radius-xl)] p-3 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={{
            background: "var(--wrong-soft)",
            color: "var(--coral-deep)",
          }}
        >
          {state.error}
        </p>
      )}
    </div>
  );
}
