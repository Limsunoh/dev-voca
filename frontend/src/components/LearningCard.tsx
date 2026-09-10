import Link from "next/link";

import { Reading } from "./Reading";

/**
 * 학습 콘텐츠 카드.
 *
 * 단어에 묶지 않는다 - 나중에 문장·에러 메시지가 같은 카드를 쓴다.
 * 그래서 props 가 term/meaning 이 아니라 title/subtitle 이다.
 */
export type LearningCardProps = {
  href: string;
  title: string;
  subtitle: string;
  /** 제목 옆에 붙는 보조 문구. 단어의 발음기호 같은 것. */
  aside?: string;
  /**
   * 한글 발음. aside(발음기호) 옆에 온다.
   *
   * aside 를 ReactNode 로 넓혀 한 자리에 몰아넣지 않는 이유: 그 자리에는
   * lang="en-US" 가 걸려 있어 한글이 영어 글꼴로 그려지고 스크린리더도
   * 영어로 읽는다.
   */
  reading?: string;
  /**
   * 제목 오른쪽에 놓일 표시. 난이도 배지 같은 것.
   *
   * 문자열이 아니라 노드로 받는다. 난이도를 색으로 구분하려면 등급 숫자가
   * 필요한데, 그건 콘텐츠 타입마다 다르다. 카드가 그 사정을 알면 단어에만
   * 맞는 컴포넌트가 된다.
   */
  badge?: React.ReactNode;
  /** 아래쪽에 놓일 분류 같은 보조 표시. */
  tag?: React.ReactNode;
  /**
   * 제목을 고정폭 글꼴로 보일지. 기본은 true.
   *
   * 단어나 에러 메시지는 코드에 가까워 고정폭이 읽기 좋지만, 사람이 쓴
   * 문장은 고정폭으로 길게 늘어놓으면 오히려 읽기 어렵다.
   */
  monoTitle?: boolean;
  /**
   * 한 줄짜리로 줄여 그린다. 기본은 false.
   *
   * 목록 화면은 카드 하나에 발음·분류·난이도까지 담아 크게 그리지만, 홈처럼
   * 곁들이는 자리에서는 제목과 뜻만 있으면 되고 여러 장이 들어가야 한다.
   * 크기만 다르고 나머지(누름 반응·포커스·색)는 같아야 해서 별도 컴포넌트로
   * 나누지 않는다 - 나누면 여기 쌓인 판단(0.96 실측 같은 것)을 저쪽에서
   * 다시 밟게 된다.
   */
  compact?: boolean;
};

export function LearningCard({
  href,
  title,
  subtitle,
  aside,
  reading,
  badge,
  tag,
  monoTitle = true,
  compact = false,
}: LearningCardProps) {
  return (
    <Link
      href={href}
      // 흰 종이 + 아래 3px 두께. 크림 리디자인의 핵심이라 카드가 이 시스템의
      // 기준점이다(디자인 가이드 shape-lift).
      //
      // 반투명을 버렸다. 다크에서는 뒤의 그라디언트가 비쳐야 목록이 한 화면으로
      // 읽혔지만, 크림에는 영역별 배경 자체가 없다(가이드 color-base:
      // "그라디언트·영역별 배경 없음. 카드의 두께가 화면을 만든다").
      // 여기서 반투명을 유지하면 크림 위에 크림이라 카드 경계가 사라진다.
      //
      // 테두리도 버렸다. 두께가 경계를 맡으므로 테두리를 같이 두면 신호가
      // 둘이 되고, 눌러서 두께가 0 이 될 때 테두리만 남아 카드가 납작해진
      // 게 아니라 색이 바랜 것처럼 보인다.
      //
      // 누르면 두께만큼(3px) 내려앉는다. 이게 없으면 폰에서 이 카드는 완전히
      // 무반응이다 - hover 는 터치에 없어서 탭한 순간부터 다음 화면이 뜰
      // 때까지 손가락 아래에서 아무 일도 일어나지 않는다.
      //
      // **scale 을 쓰지 않는다.** 다크에서는 0.96 으로 줄였는데, 크림은
      // 누름이 "내려앉음" 이다(가이드 motion-press). 두 개를 겹치면 카드가
      // 작아지면서 가라앉아 물러나 보인다.
      //
      // 쉬는 두께를 box-shadow 가 아니라 --lift 변수로 준다. 인라인 style 의
      // 선언은 클래스 규칙을 이기므로(같은 !important 급이 아니면 인라인이
      // 항상 우선), box-shadow 를 여기 직접 적으면 globals.css 의
      // .dv-card-press:active 가 그리는 --lift-none 이 무시된다. 그러면
      // transform 만 걸려서 카드가 두께를 그대로 단 채 3px 내려가 바닥을
      // 뚫고 들어간 것처럼 보인다. 변수로 넘기면 클래스가 그 변수를 덮어쓸
      // 수 있어 눌림이 제대로 그려진다.
      className={`dv-card dv-card-press block focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
        compact ? "px-4 py-3.5" : "px-4.5 pt-4.5 pb-4"
      }`}
      style={
        {
          background: "var(--paper)",
          borderRadius: "var(--radius-2xl)",
          "--lift": "var(--lift-card)",
        } as React.CSSProperties
      }
    >
      {/* compact 는 한 줄짜리라 제목과 뜻이 세로로 딱 붙는다. 기준선을 위로
          맞추면 오른쪽 배지가 제목 위로 떠 보인다. */}
      <div
        className={`flex justify-between gap-3 ${
          compact ? "items-center" : "items-start"
        }`}
      >
        {/* min-w-0 이 없으면 flex 항목이 내용보다 작아지지 못한다. 제목에
            줄바꿀 곳이 없는 긴 문자열(에러 메시지 안의 URL 같은 것)이 오면
            카드가 화면 밖으로 밀려 나가 페이지에 가로 스크롤이 생긴다.
            데스크톱에서는 여백이 넉넉해 드러나지 않고 폰에서만 보인다.
            글자를 끊는 쪽은 globals.css 의 base 규칙이 맡는다. */}
        <div className="min-w-0">
          <h2
            className={compact ? "text-[0.9375rem]" : "text-xl"}
            style={{
              // 고정폭 제목은 자간을 더 조인다. JetBrains Mono 는 글자마다
              // 폭이 같아 기본 자간으로 두면 단어가 흩어져 보인다.
              fontFamily: monoTitle ? "var(--font-mono)" : "var(--font-sans)",
              fontWeight: monoTitle
                ? "var(--weight-bold)"
                : "var(--weight-black)",
              letterSpacing: monoTitle
                ? "var(--tracking-tighter)"
                : "var(--tracking-tight)",
              color: "var(--foreground)",
              lineHeight: "var(--leading-tight)",
            }}
          >
            {title}
          </h2>

          {/* 발음 줄. compact 에서는 통째로 뺀다 - 홈에 여러 장이 들어가는
              자리라 제목과 뜻만 있으면 된다. */}
          {!compact && (aside || reading) && (
            <div
              className="mt-1.5 flex flex-wrap gap-x-2.5 text-sm"
              style={{ color: "var(--text-muted)" }}
            >
              {/* 발음기호는 고정폭으로 두지 않는다. IPA 기호가 고정폭 글꼴에서
                  깨지거나 폭이 어긋난다(디자인 가이드 type-ipa). 이 줄이
                  --font-sans 상속만 받고 아무 글꼴도 안 적는 것이 그래서다. */}
              {aside && <span lang="en-US">{aside}</span>}
              {reading && (
                <Reading
                  text={reading}
                  style={{ color: "var(--text-muted)" }}
                />
              )}
            </div>
          )}

          {/* compact 에서는 한 줄로 자른다. 두 줄이 되면 카드 높이가 제각각이라
              목록이 고르지 않게 보인다. 뜻 전체는 눌러서 상세로 가면 있다. */}
          <p
            className={compact ? "mt-0.5 truncate text-xs" : "mt-2.5 text-base"}
            style={{
              color: compact ? "var(--text-muted)" : "var(--text-body)",
              // 뜻은 카드에서 제목 다음으로 읽히는 줄이라 굵게 세운다.
              // compact 은 곁들이는 자리라 평범한 굵기로 물러난다.
              fontWeight: compact
                ? "var(--weight-regular)"
                : "var(--weight-bold)",
            }}
          >
            {subtitle}
          </p>
        </div>
        {badge}
      </div>

      {/* 칩이 여럿 올 수 있다(분류 + 정처기). 줄바꿈과 간격을 여기서 준다 -
          호출부가 조각(<>...</>)으로 넘기면 칩 사이가 붙어버린다. */}
      {!compact && tag && (
        <div className="mt-3 flex flex-wrap gap-1.5">{tag}</div>
      )}
    </Link>
  );
}
