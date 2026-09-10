import Link from "next/link";

import { routes } from "@/lib/routes";

/**
 * 없는 순위표 종류.
 *
 * 이 파일이 없으면 Next 기본 영문 404 가 뜬다 - 한글 화면 한가운데
 * 영어 문구가 나온다. learn/words 와 learn/sentences 가 같은 이유로
 * 각자 두고 있다.
 */
export default function BoardNotFound() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center px-4 py-10 text-center">
      <p
        style={{
          color: "var(--foreground)",
          fontWeight: "var(--weight-bold)",
        }}
      >
        그런 순위표는 없습니다.
      </p>
      <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
        이번 주, 전체, 꾸준함 세 가지가 있습니다.
      </p>
      <div className="mt-6">
        {/* 흰 알약 + 두께. 이 화면에는 할 일이 하나뿐이지만 막다른 곳에서
            돌아가는 동작이라 코랄까지 쓰지 않는다 - 코랄은 앞으로 나아가는
            자리(문제 풀러 가기)에 남긴다. */}
        <Link
          href={routes.board()}
          className="dv-btn inline-flex items-center rounded-[var(--radius-pill)] px-5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={
            {
              minHeight: "var(--hit-floor)",
              background: "var(--paper)",
              color: "var(--foreground)",
              fontWeight: "var(--weight-black)",
              "--lift": "var(--lift-button-paper)",
            } as React.CSSProperties
          }
        >
          순위표로
        </Link>
      </div>
    </main>
  );
}
