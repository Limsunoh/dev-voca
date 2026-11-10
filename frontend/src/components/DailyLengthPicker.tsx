"use client";

import { useActionState } from "react";

import type { DailyLengthState } from "@/app/start/daily/actions";
import { DAILY_LENGTHS, type DailyLength } from "@/lib/daily-length";

/**
 * 하루 공부량 세 칸. 누르면 바로 저장한다.
 *
 * 처음 묻는 화면(/start/daily)과 내정보가 같이 쓴다. 저장 버튼을 따로 두지
 * 않는다 - 고를 것이 셋뿐이라 고르는 것이 곧 저장이다.
 *
 * 흰 카드 셋을 나란히 둔다. 일일공부의 길이 고르기(DailyStudyBoard)와 같은
 * 모양이다. 코랄로 채우지 않는 이유도 같다 - 셋 다 같은 자격의 선택지라
 * 하나만 코랄이면 그것을 권하는 것이 된다. 지금 고른 것은 테두리로 표시한다.
 */
export function DailyLengthPicker({
  action,
  current,
  from,
}: {
  action: (prev: DailyLengthState, formData: FormData) => Promise<DailyLengthState>;
  current: DailyLength | "" | null;
  from: "start" | "profile";
}) {
  const [state, formAction, pending] = useActionState(action, {});

  return (
    <form action={formAction}>
      <input type="hidden" name="from" value={from} />
      <div className="flex flex-col gap-2.5">
        {DAILY_LENGTHS.map((one) => {
          const chosen = one.value === current;
          return (
            <button
              key={one.value}
              type="submit"
              name="length"
              value={one.value}
              disabled={pending}
              aria-pressed={chosen}
              // 처음 묻는 화면은 제목까지 가운데 정렬이라 글자도 가운데에 둔다.
              // 내정보는 "지금 공부량" 표시가 오른쪽에 붙어 양끝 정렬이다.
              className={`dv-card dv-card-press flex items-center px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60 ${
                from === "start" ? "justify-center" : "justify-between text-left"
              }`}
              style={
                {
                  minHeight: 56,
                  background: "var(--paper)",
                  border: chosen ? "2px solid var(--foreground)" : "2px solid transparent",
                  borderRadius: "var(--radius-2xl)",
                  "--lift": "var(--lift-card)",
                } as React.CSSProperties
              }
            >
              <span
                style={{
                  fontSize: "var(--text-md)",
                  fontWeight: "var(--weight-black)",
                  letterSpacing: "var(--tracking-tight)",
                  color: "var(--foreground)",
                }}
              >
                {one.label}
              </span>
              {chosen && (
                <span
                  className="text-sm"
                  style={{ color: "var(--text-muted)", fontWeight: "var(--weight-bold)" }}
                >
                  지금 공부량
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* role="alert" 는 붙인다. 버튼을 누르고 아무 반응이 없으면 저장된 줄
          안다 - 실패는 소리 내어 알려야 한다. */}
      {state.error && (
        <p role="alert" className="mt-3 text-sm" style={{ color: "var(--wrong-deep)" }}>
          {state.error}
        </p>
      )}
      {state.saved && !pending && (
        <p role="status" className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
          저장했습니다.
        </p>
      )}
    </form>
  );
}
