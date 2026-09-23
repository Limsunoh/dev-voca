"use client";

import Link from "next/link";

import { useLeaveGuard } from "./useLeaveGuard";

/**
 * 누르면 지금 문제 판이 끝나는 링크. 푼 것이 있으면 먼저 확인을 묻는다.
 *
 * 문제풀기 머리의 "한 판 풀기" 가 쓴다. 이 페이지는 서버 컴포넌트라
 * 클릭을 가로챌 수 없어서 이 조각만 클라이언트로 뺐다.
 */
export function LeaveLink({
  href,
  confirmLabel,
  className,
  style,
  children,
}: {
  href: string;
  /** 창의 진행 버튼 글자. */
  confirmLabel: string;
  className?: string;
  style?: React.CSSProperties;
  children: React.ReactNode;
}) {
  const { guard, dialog } = useLeaveGuard({ confirmLabel });

  return (
    <>
      <Link
        href={href}
        onClick={(event) => guard(event, href)}
        className={className}
        style={style}
      >
        {children}
      </Link>
      {dialog}
    </>
  );
}
