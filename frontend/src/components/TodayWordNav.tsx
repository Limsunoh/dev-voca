import Link from "next/link";

import { routes } from "@/lib/routes";

/**
 * 오늘의 단어 묶음 안에서 앞뒤로 넘기는 줄. 단어 상세 맨 아래에 둔다.
 *
 * 홈은 오늘의 단어 하나와 그 아래 몇 개를 한 묶음으로 보여준다(로그인했으면
 * 일일공부 단어 2~7개, 게스트는 7개). 이 줄이 없으면 한 단어를 읽은 뒤 다음
 * 것을 보려고 홈으로 돌아가 다시 골라야 한다. 묶음의 순서는 홈이 주소에
 * 실어 준다(routes.todayWord).
 *
 * 넘길 때 방문 기록을 쌓지 않는다(replace). 다 넘긴 뒤 뒤로 가기를 묶음
 * 개수만큼 눌러야 홈에 닿으면 안 된다. 한 번이면 묶음에 들어오기 전 화면이다.
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
  const ids = words.map((one) => one.id);

  return (
    // 한 줄에 안 들어가면 줄을 바꾼다. 폰 글자 크기 200% 면 360폭 폰이 180px
    // 폭처럼 그려지는데(본문 140px), 이전·쪽수·다음이 한 줄에 약 240px 이라
    // 화면이 넓어지고 아래 탭바까지 밀렸다. 쪽 넘기기 줄(Pagination)과 같은 방법이다.
    <nav
      aria-label="오늘의 개발영어"
      className="rise mt-5 flex flex-wrap items-center gap-2.5 [animation-delay:400ms]"
    >
      <Step word={previous} side="previous" ids={ids} />
      {/* 20rem(320px) 보다 좁으면 "n / 7" 을 첫 줄에 혼자 가운데로 올리고 버튼은
          그 아래에 둔다. 그대로 두면 버튼이 꺾이는 자리에 따라 숫자가 버튼
          사이 어디쯤에 끼어 읽는 순서가 흐트러진다. 보통 폰(360px 이상)은
          그대로 한 줄이다. */}
      <p
        className="min-w-16 shrink-0 text-center text-sm tabular-nums whitespace-nowrap max-[20rem]:order-first max-[20rem]:basis-full"
        style={{ color: "var(--text-muted)", fontWeight: "var(--weight-bold)" }}
      >
        {index + 1} / {words.length}
      </p>
      <Step word={next} side="next" ids={ids} />
    </nav>
  );
}

/** 이전·다음 버튼 하나. 끝이면 자리만 지키고 누를 수 없다. */
function Step({
  word,
  side,
  ids,
}: {
  word: { id: number } | undefined;
  side: "previous" | "next";
  /** 묶음 순서. 넘긴 상세도 같은 순서를 주소에 싣는다. */
  ids: number[];
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
  // whitespace-nowrap 이 있어야 버튼이 다음 줄로 간다. 없으면 body 의
  // overflow-wrap: anywhere 때문에 "이전" 이 "이/전" 으로 꺾일 수 있어 버튼의
  // 최소 폭이 한 글자 폭까지 줄고, 그러면 flex-wrap 이 줄을 바꾸는 대신 글자를
  // 꺾는다. 묶어 두면 좁아질 때 버튼이 통째로 다음 줄로 간다.
  const shape = "flex flex-1 items-center justify-center gap-1.5 px-4 whitespace-nowrap";
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
    //
    // 좁은 화면에서도 숨기지 않는다. 글자 115~150% 쯤은 버튼 둘이 아직 나란히
    // 들어가는 폭이라, 숨기면 첫·끝 장만 버튼이 줄 전체로 늘어 장마다 자리가
    // 바뀐다. 200% 에서는 버튼이 한 줄씩 쌓여 이 칸도 회색 줄 하나가 된다.
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
      href={routes.todayWord(word.id, ids)}
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
