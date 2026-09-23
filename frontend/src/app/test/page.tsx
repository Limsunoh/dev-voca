import type { Metadata } from "next";
import Link from "next/link";

import { loadToday, TodayCards } from "@/components/TodayCards";
import { routes } from "@/lib/routes";
import { getCurrentUser, getToken } from "@/lib/session";

export const metadata: Metadata = {
  title: "문제풀기 | devvoca",
  description: "일일공부, 다시 보기, 한 판, 단어·문장 연습 중에 고릅니다.",
};

/**
 * 문제풀기 허브. 탭바 "문제풀기" 가 여기로 온다.
 *
 * 전에는 탭이 단어 문제로 곧장 가서, 일일공부·다시 보기·한 판으로 가는
 * 길이 탭 안에 없었다. 여기서 다섯 가지를 한 화면에 늘어놓고 고르게 한다.
 * 대신 단어 문제까지는 한 번 더 누른다.
 *
 * 위에서 아래로 오늘 할 것 → 한 판 → 연습이다. 매일 오는 이유가 되는 것을
 * 먼저 두고, 점수가 걸린 것, 걸리지 않은 것 순으로 무게를 내린다.
 *
 * 오답 노트(/mistakes) 입구도 여기 있다. 탭 안에서 갈 곳이 흩어져 있던
 * 것을 모으는 화면이라, 틀린 것을 보는 자리도 같이 둔다.
 */
export default async function TestHubPage() {
  // 둘을 같이 띄운다. 순서대로 기다리면 왕복이 그대로 두 번이다.
  const token = await getToken();
  const [user, today] = await Promise.all([getCurrentUser(), loadToday(token)]);

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col px-[var(--gutter)] pt-[22px] pb-7">
      <h1
        className="text-[length:var(--text-2xl)] tracking-[var(--tracking-tight)]"
        style={{ color: "var(--foreground)", fontWeight: "var(--weight-black)" }}
      >
        문제풀기
      </h1>

      {/* 일일공부·다시 보기는 로그인해야 쓴다. 게스트에게는 절을 통째로
          뺀다 - 제목만 남으면 비어 있는 절이 된다. */}
      {user && (
        <Section id="hub-today" title="오늘 할 것">
          <TodayCards {...today} />
          {/* 오답 노트는 푸는 곳이 아니라 틀린 것을 모아 보는 곳이다(푸는
              자리는 다시 보기). 그래서 연습이 아니라 다시 보기 옆에 둔다.
              로그인해야 보는 화면이라 이 절 안에 있으면 게스트가 눌렀다
              로그인으로 튕기는 일도 없다. */}
          <div className="mt-2.5 flex">
            <PracticeLink href={routes.mistakes} label="오답 노트" note="마지막에 틀린 단어 · 문장 모아 보기" />
          </div>
        </Section>
      )}

      <Section id="hub-round" title="한 판">
        {/* 이 화면의 유일한 코랄. 점수가 걸린 동작이라 가장 무겁다
            (한 화면에 코랄 하나 - globals.css 의 --coral 주석). 다시 보기
            숫자의 코랄 글자는 버튼이 아니라 홈 카드와 같은 표시다. */}
        <Link
          href={routes.testRound}
          className="dv-btn flex items-center justify-between px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={
            {
              "--lift": "var(--lift-button)",
              minHeight: "var(--hit-min)",
              borderRadius: "var(--radius-pill)",
              background: "var(--coral)",
              color: "var(--text-on-color)",
              fontWeight: "var(--weight-black)",
              letterSpacing: "var(--tracking-tight)",
              textDecoration: "none",
            } as React.CSSProperties
          }
        >
          한 판 풀기
          <span aria-hidden>→</span>
        </Link>
        {/* 설명을 버튼 밖에 둔다. 코랄 위 흰 글자는 3:1 대라 굵고 큰
            버튼 글자만 통과하고, 12px 설명은 못 읽힌다.

            게스트 판은 순위표에 안 오른다. 똑같이 "오른다" 고 쓰면 풀고
            나서 이름을 찾게 된다. */}
        <p className="mt-2.5 text-xs" style={{ color: "var(--text-muted)" }}>
          {user
            ? "90초 동안 푼 점수가 순위표에 오릅니다."
            : "90초 동안 풉니다. 로그인하면 점수가 순위표에 오릅니다."}
        </p>
      </Section>

      <Section id="hub-practice" title="연습">
        <div className="flex gap-2.5">
          <PracticeLink href={routes.testWords} label="단어 문제" note="뜻 보고 고르기" />
          <PracticeLink href={routes.testSentences} label="문장 문제" note="빈칸 · 상황" />
        </div>
      </Section>
    </main>
  );
}

/**
 * 절 하나. 제목은 카드 위의 작은 라벨이다(내정보의 "학습 기록" 과 같은 모양).
 * 구획선을 긋지 않는다 - 이 디자인은 영역을 카드의 두께로 가른다.
 */
function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-7" aria-labelledby={id}>
      <h2
        id={id}
        className="mb-3 text-xs tracking-[var(--tracking-wide)]"
        style={{ color: "var(--text-dim)", fontWeight: "var(--weight-black)" }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

/** 점수가 안 걸리는 곳으로 가는 흰 버튼. 연습 둘과 오답 노트가 쓴다. */
function PracticeLink({
  href,
  label,
  note,
}: {
  href: string;
  label: string;
  note: string;
}) {
  return (
    <Link
      href={href}
      className="dv-btn flex flex-1 flex-col justify-center px-4 py-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      style={
        {
          "--lift": "var(--lift-button-paper)",
          minHeight: "var(--hit-min)",
          borderRadius: "var(--radius-2xl)",
          background: "var(--paper)",
          color: "var(--foreground)",
          fontWeight: "var(--weight-bold)",
          textDecoration: "none",
        } as React.CSSProperties
      }
    >
      {label}
      <span className="mt-0.5 text-xs" style={{ color: "var(--text-muted)" }}>
        {note}
      </span>
    </Link>
  );
}
