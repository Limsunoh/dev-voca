"use client";

import Link from "next/link";
import type { ComponentProps } from "react";

import { traverseBackTo } from "@/lib/history-nav";
import { routes } from "@/lib/routes";

/**
 * 홈으로 가는 링크. 기록을 새로 쌓지 않는다.
 *
 * 뒤쪽 기록에 홈이 있으면(대개 홈에서 들어왔다) 그리로 돌아가고, 없으면
 * 바꿔치기한다. 그냥 Link 로 두면 홈 -> 일일공부 -> 홈 이 되어, 홈에서 뒤로
 * 가기가 다 푼 일일공부로 가고 앱(TWA)이 안 닫힌다(lib/history-nav.ts).
 *
 * onNavigate 는 Link 가 새 탭으로 열기와 이미 막힌 클릭을 거른 뒤에만 부른다.
 * 돌아간 홈은 탭바가 새로 받는다(TabBar). 그래서 라우터를 쓰지
 * 않는다. 결과 화면·404·오류 화면처럼 테스트가 라우터 없이 그리는 곳에서도
 * 쓸 수 있다.
 */
export function HomeLink(props: Omit<ComponentProps<typeof Link>, "href" | "replace" | "onNavigate">) {
  return (
    <Link
      {...props}
      href={routes.home}
      replace
      onNavigate={(e) => {
        if (traverseBackTo(routes.home)) e.preventDefault();
      }}
    />
  );
}
