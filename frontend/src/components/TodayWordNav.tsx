import Link from "next/link";

import { routes } from "@/lib/routes";

/**
 * 오늘의 개발영어 묶음 안에서 앞뒤로 넘기는 줄. 단어 상세 맨 아래에 둔다.
 *
 * 홈은 오늘의 단어 하나와 아래 여섯 개를 한 묶음으로 보여준다. 이 줄이 없으면
 * 한 단어를 읽은 뒤 다음 것을 보려고 홈으로 돌아가 다시 골라야 한다.
 *
 * 넘길 때 방문 기록을 쌓지 않는다(replace). 일곱 개를 다 넘긴 뒤 뒤로 가기를
 * 일곱 번 눌러야 홈에 닿으면 안 된다. 한 번이면 묶음에 들어오기 전 화면이다.
 */
export function TodayWordNav({
  words,
  index,
}: {
  words: { id: number }[];
  index: number;
}) {
  const previous = words[index - 1];
  const next = words[index + 1];

  return (
    <nav
      aria-label="오늘의 개발영어"
      className="rise mt-5 flex items-center gap-2.5 [animation-delay:400ms]"
    >
      <Step word={previous} side="previous" />
      <p
        className="min-w-16 shrink-0 text-center text-sm tabular-nums"
        style={{ color: "var(--text-muted)", fontWeight: "var(--weight-bold)" }}
      >
        {index + 1} / {words.length}
      </p>
      <Step word={next} side="next" />
    </nav>
  );
}

/** 이전·다음 버튼 하나. 끝이면 자리만 지키고 누를 수 없다. */
function Step({
  word,
  side,
}: {
  word: { id: number } | undefined;
  side: "previous" | "next";
}) {
  const content =
    side === "previous" ? (
      <>
        <span aria-hidden>←</span> 이전
      </>
    ) : (
      <>
        다음 <span aria-hidden>→</span>
      </>
    );
  const shape = "flex flex-1 items-center justify-center gap-1.5 px-4";
  const base = {
    minHeight: "var(--hit-min)",
    borderRadius: "var(--radius-pill)",
    fontWeight: "var(--weight-black)",
    letterSpacing: "var(--tracking-tight)",
  } as const;

  if (!word) {
    // 첫 장의 "이전", 마지막 장의 "다음". 빼 버리면 남은 버튼이 줄 전체로
    // 늘어나 장마다 버튼 자리가 바뀐다. 자리만 지키는 것이라 화면 낭독기에는
    // 숨긴다 - span 에 aria-disabled 를 달아도 "누를 수 없음" 으로 읽히지 않는다.
    return (
      <span
        aria-hidden
        className={shape}
        style={{ ...base, color: "var(--text-faint)", background: "var(--background-deep)" }}
      >
        {content}
      </span>
    );
  }

  return (
    <Link
      href={routes.todayWord(word.id)}
      replace
      className={`dv-btn ${shape} focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus`}
      style={
        {
          ...base,
          background: "var(--paper)",
          color: "var(--foreground)",
          // 쉬는 두께는 --lift 로. 인라인 box-shadow 는 :active 를 이긴다.
          "--lift": "var(--lift-button-paper)",
        } as React.CSSProperties
      }
    >
      {content}
    </Link>
  );
}
