import Link from "next/link";
import type { ReactNode } from "react";

/**
 * 홈의 작은 통계 카드. 가로로 둘이 나란히 선다.
 *
 * **카드 하나에 숫자 하나다.** 이전에는 "일일공부 / 4/10문제까지 풀었습니다"
 * 처럼 문장으로 알렸는데, 홈에서 알고 싶은 것은 "얼마나 남았나" 하나라
 * 문장을 읽어야 답이 나오는 형태였다. 숫자를 크게 두면 훑는 것만으로
 * 끝난다.
 *
 * 단위(`unit`)를 숫자와 분리해 받는 이유: 크기와 색이 달라야 숫자가
 * 먼저 읽힌다. "4/10" 을 통째로 넘기면 10 이 4 만큼 커진다.
 */
export function StatCard({
  href,
  label,
  value,
  unit,
  tone = "ink",
  footer,
}: {
  href: string;
  label: string;
  value: ReactNode;
  unit?: string;
  /** coral 이면 숫자가 코랄. 지금 손대야 할 것을 하나만 고를 때 쓴다. */
  tone?: "ink" | "coral";
  footer?: ReactNode;
}) {
  return (
    <Link
      href={href}
      className="dv-card dv-card-press flex-1 p-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      style={
        {
          "--lift": "var(--lift-card)",
          background: "var(--paper)",
          borderRadius: "var(--radius-2xl)",
          textDecoration: "none",
          color: "var(--foreground)",
        } as React.CSSProperties
      }
    >
      <p
        className="text-xs"
        style={{
          fontWeight: "var(--weight-black)",
          color: "var(--text-dim)",
        }}
      >
        {label}
      </p>

      {/* tabular-nums: 자릿수가 바뀔 때 숫자가 좌우로 흔들리지 않는다.
          4/10 에서 10/10 으로 갈 때 카드 폭은 그대로인데 글자만 움직이면
          같은 자리에서 두 번 읽게 된다. */}
      <p
        className="mt-2 tabular-nums"
        style={{
          fontSize: "var(--text-2xl)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
          color: tone === "coral" ? "var(--coral)" : "var(--foreground)",
        }}
      >
        {value}
        {unit && (
          <span
            className="ml-px"
            style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)" }}
          >
            {unit}
          </span>
        )}
      </p>

      {footer && <div className="mt-2.5">{footer}</div>}
    </Link>
  );
}

/**
 * 진행 점.
 *
 * 숫자(4/10)와 같은 것을 말하지만 **모양으로 한 번 더** 알린다. 숫자는
 * 읽어야 알고 점은 보면 안다 - 홈은 훑는 화면이라 후자가 먼저 닿는다.
 *
 * 색만으로 가르지 않는다. 채워진 점이 왼쪽부터 이어지므로 위치 자체가
 * 진행을 말하고, 색은 거기에 얹히는 두 번째 단서다.
 */
export function ProgressDots({ total, done }: { total: number; done: number }) {
  // **개수가 많으면 막대 하나로 바꾼다.** 홈의 통계 카드는 폰에서 폭이
  // 140px 인데, 점 사이 간격이 5px 이라 25개면 간격만 120px 이라 점 하나가
  // 0.8px 이 되고 40개면 아예 음수가 된다. 일일공부는 10·25·40 문제 세
  // 길이가 있어서 5분 코스로만 보면 안 드러난다.
  //
  // 경계를 12 로 둔다. 그 이상은 점을 세는 것이 읽는 방법이 아니고,
  // 차오르는 막대가 같은 것을 더 빨리 알린다.
  if (total > 12) {
    const 비율 = total > 0 ? Math.min(done / total, 1) : 0;
    return (
      <div
        className="h-[7px] w-full overflow-hidden"
        style={{
          borderRadius: "var(--radius-pill)",
          background: "var(--sand-deep)",
        }}
        aria-hidden="true"
      >
        <div
          className="h-full"
          style={{
            width: `${비율 * 100}%`,
            borderRadius: "var(--radius-pill)",
            background: "var(--green)",
          }}
        />
      </div>
    );
  }

  return (
    <div className="flex gap-[5px]" aria-hidden="true">
      {Array.from({ length: total }, (_, i) => (
        <i
          key={i}
          className="h-[7px] flex-1"
          style={{
            borderRadius: "var(--radius-pill)",
            background: i < done ? "var(--green)" : "var(--sand-deep)",
          }}
        />
      ))}
    </div>
  );
}
