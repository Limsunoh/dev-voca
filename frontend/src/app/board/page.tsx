import type { Metadata } from "next";

import { BoardScreen } from "@/app/board/BoardScreen";

export const metadata: Metadata = {
  title: "순위표 · devvoca",
  description: "이번 주 최고점, 전체 최고점, 꾸준함 순위.",
};

/** 종류를 안 주면 이번 주. 가장 자주 보는 것이 기본이다. */
export default function BoardPage() {
  return <BoardScreen kind="weekly" />;
}
