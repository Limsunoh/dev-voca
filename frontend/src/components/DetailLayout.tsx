import Link from "next/link";

import { Highlight } from "./Highlight";
import { Reading } from "./Reading";

/**
 * 단어·문장 상세의 공통 뼈대.
 *
 * 크림에서 층이 바뀌었다. 다크에서는 히어로를 맨몸으로 두고 뜻만 왼쪽
 * 강조선으로 세웠는데, 크림에는 영역별 배경이 없어서 맨몸 히어로가 크림
 * 바탕 위에 그냥 떠 있는 글자 덩어리가 된다.
 *
 *   히어로 카드  배지 → 큰 제목 → 발음 → 형광펜 뜻. 한 장에 담는다
 *   정보 카드    설명·예문. 예문은 반전(잉크 바탕)으로 강조점을 만든다
 *
 * 배지가 제목 위로 올라온 것도 프로토타입(DetailHero.prompt.md)을 따랐다.
 * 카드 안에서는 제목이 맨 위에 있을 이유가 없고, 배지가 먼저 오면 카드
 * 상단이 채워져 한 장으로 읽힌다.
 *
 * 두 화면이 같은 파일을 쓰는 이유: 단어에서 고친 간격이 문장에 반영되지
 * 않으면 같은 앱의 두 화면이 서로 다르게 보인다. 실제로 그렇게 벌어졌었다.
 */

/**
 * 되돌아가는 줄. 화면 맨 위에 두고 히어로보다 작게 둔다.
 *
 * 번들 BackRow 는 아이콘 버튼(34px 라운드 사각) + 이름이다. 그 모양을
 * 가져오되 통째로 하나의 링크로 둔다 - 번들은 버튼과 글자가 각각 있는데
 * 그러면 글자를 눌렀을 때 아무 일도 안 일어난다.
 */
export function DetailBack({ href, label }: { href: string; label: string }) {
  return (
    // 히트영역은 링크 전체다. 아이콘만 34px 로 두면 "단어장으로" 글자를
    // 조준해서 눌러야 한다 - 상세에서 목록으로 돌아가는 것은 자주 하는 일이다.
    <Link
      href={href}
      className="dv-card dv-card-press inline-flex min-h-11 items-center gap-2.5 rounded-full pr-4 pl-1.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      style={
        {
          background: "var(--paper)",
          color: "var(--foreground)",
          fontSize: "var(--text-sm)",
          fontWeight: "var(--weight-black)",
          // 쉬는 두께는 --lift 로. 인라인 box-shadow 는 :active 를 이긴다.
          "--lift": "var(--lift-card)",
        } as React.CSSProperties
      }
    >
      {/* 화살표만 옅은 띠에 앉혀 번들의 아이콘 버튼 모양을 남긴다. 링크
          전체가 이미 흰 알약이라 여기에 또 종이를 깔면 층이 둘이 된다. */}
      <span
        aria-hidden
        className="grid h-8 w-8 place-items-center"
        style={{
          background: "var(--background-deep)",
          borderRadius: "var(--radius-md)",
          fontSize: "var(--text-base)",
        }}
      >
        ←
      </span>
      {label}
    </Link>
  );
}

/**
 * 상세 화면 껍데기.
 *
 * 배경은 body 의 --background 하나다. 크림에는 영역별 배경이 없다
 * (가이드 color-base).
 */
export function DetailShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto w-full max-w-2xl px-5 pt-6 pb-12">{children}</main>
  );
}

/**
 * 히어로 카드. 배지·제목·발음·뜻을 한 장에 담는다.
 *
 * 목록에서 카드를 눌러 들어온 자리라, 무엇을 눌렀는지가 첫 화면에서 바로
 * 읽혀야 한다. 제목을 본문 크기로 두면 그 확인이 안 된다.
 */
export function DetailHero({
  title,
  aside,
  reading,
  meta,
  meaning,
  mono = true,
}: {
  title: string;
  /** 제목 옆 보조 문구. 발음기호 같은 것. */
  aside?: string;
  /**
   * 한글 발음. 발음기호 아래 줄에 온다.
   *
   * aside 를 ReactNode 로 넓히지 않는 이유는 LearningCard 와 같다 -
   * 그 자리에 lang="en-US" 가 걸려 있다.
   */
  reading?: string;
  /** 난이도·분류 배지 줄. 제목 위에 온다. */
  meta?: React.ReactNode;
  /**
   * 뜻·해석. 카드 안 맨 아래에 형광펜으로 깔린다.
   *
   * 다크에서는 카드 밖 별도 블록(DetailMeaning)이었다. 프로토타입이
   * 히어로 안으로 넣었고 그쪽을 따랐다 - 뜻은 이 화면에 들어온 목적이라
   * 제목과 한 덩이로 보이는 편이 맞다. 밖에 두면 크림 바탕 위 맨몸
   * 문단이 되어 아래 정보 카드들보다 오히려 약해 보인다.
   */
  meaning?: string;
  /** 제목을 고정폭으로 둘지. 단어는 true, 사람이 쓴 문장은 false. */
  mono?: boolean;
}) {
  return (
    // 조각마다 따로 올라온다. 카드 하나에 걸면 통째로 밀려 올라와서 그냥
    // 화면이 이동한 것으로 보인다.
    //
    // dv-card 만 붙이고 dv-card-press 는 안 붙인다. 누를 수 없는 카드가
    // 눌리는 시늉을 하면 안 된다.
    <header
      className="dv-card mt-4 px-5 pt-6 pb-6"
      style={
        {
          background: "var(--paper)",
          borderRadius: "var(--radius-2xl)",
          "--lift": "var(--lift-card)",
        } as React.CSSProperties
      }
    >
      {meta && <div className="rise flex flex-wrap gap-1.5">{meta}</div>}

      {/* 글자 수로 크기를 가른다. vw 만 쓰면 화면 폭만 보고 내용 길이를
          몰라서, 짧은 단어와 긴 에러 메시지가 같은 크기로 나온다.

          짧은 것은 크게 - 카드를 채워야 제목답다.
          긴 것은 작게 - 폰에서 다섯 줄 220px 를 먹으면 제목이 아니라 글
          덩어리가 된다("IntegrityError: UNIQUE constraint failed..." 가
          실제로 그랬다).

          경계를 24자로 둔 이유: 390px 폰에서 고정폭 48px 로 두 줄에 들어가는
          한계가 그 근처다. 카드 좌우 padding 40px 이 빠져 다크였을 때보다
          약간 좁아졌지만, --text-hero 가 clamp 로 12vw 를 물고 있어 그만큼
          같이 줄어든다. */}
      <h1
        className={`rise text-balance ${meta ? "mt-4" : ""}`}
        style={{
          fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)",
          fontWeight: mono ? "var(--weight-bold)" : "var(--weight-black)",
          letterSpacing: mono
            ? "var(--tracking-tighter)"
            : "var(--tracking-tight)",
          color: "var(--foreground)",
          ...(mono
            ? title.length <= 24
              ? { fontSize: "var(--text-hero)", lineHeight: 1.02 }
              : { fontSize: "clamp(1.5rem,7vw,2rem)", lineHeight: 1.15 }
            : title.length <= 40
              ? { fontSize: "clamp(1.75rem,8vw,2.25rem)", lineHeight: 1.08 }
              : { fontSize: "clamp(1.375rem,6vw,1.75rem)", lineHeight: 1.25 }),
        }}
      >
        {title}
      </h1>

      {aside && (
        // 발음기호는 고정폭으로 두지 않는다. IPA 기호가 고정폭 글꼴에서
        // 깨지거나 폭이 어긋난다(디자인 가이드 type-ipa).
        <p
          lang="en-US"
          className="rise mt-2.5 [animation-delay:60ms]"
          style={{ fontSize: "var(--text-base)", color: "var(--text-muted)" }}
        >
          {aside}
        </p>
      )}

      {reading && (
        <Reading
          text={reading}
          className="rise mt-1 block [animation-delay:80ms]"
          style={{ fontSize: "var(--text-base)", color: "var(--text-muted)" }}
        />
      )}

      {meaning && (
        // 형광펜은 홈의 "오늘의 단어" 와 같은 것을 쓴다. 두 화면 다 뜻을
        // 칠하는 자리라, 각자 그라디언트를 적으면 한쪽만 고쳐진다.
        //
        // 색은 기본(초록)이다. 코랄은 "지금 여기" 와 주요 동작이 쓰는
        // 색이고 이 화면에서는 맨 아래 "문제 풀기" 버튼이 그것을 갖는다.
        <p
          className="rise mt-5 text-pretty [animation-delay:120ms]"
          style={{
            fontSize: "var(--text-xl)",
            fontWeight: "var(--weight-black)",
            letterSpacing: "-0.035em",
            lineHeight: "var(--leading-snug)",
            color: "var(--foreground)",
          }}
        >
          <Highlight>{meaning}</Highlight>
        </p>
      )}
    </header>
  );
}

/**
 * 정보 카드 하나. 설명·예문처럼 덩이진 내용을 담는다.
 *
 * 제목을 카드 안 작은 라벨로 두고 본문과 확실히 다르게 만든다. 전에는
 * 본문과 같은 크기라 "설명" 이라는 글자가 설명의 첫 줄처럼 읽혔다.
 */
export function DetailCard({
  label,
  delay,
  tone = "paper",
  children,
}: {
  label: string;
  /** 등장 순서. 위에서부터 80ms 씩 늘린다. */
  delay: string;
  /**
   * 반전 여부. 예문처럼 실제로 보러 온 것에만 dark 를 준다.
   *
   * 카드가 전부 흰 종이면 무엇이 중요한지 표현이 없다. 다크에서는 그것을
   * 그림자 세기로 냈는데, 크림은 두께가 3~4px 두 단계뿐이라 그 차이가
   * 안 보인다. 대신 잉크 바탕으로 뒤집는다 - 크림 화면에서 유일하게
   * 어두운 면이라 페이지를 훑으면 여기서 눈이 멈춘다(가이드 shape-lift 의
   * --lift-dark 가 이 자리를 위해 있다).
   */
  tone?: "paper" | "dark";
  children: React.ReactNode;
}) {
  const dark = tone === "dark";

  return (
    <section
      className={`rise dv-card mt-3.5 p-5 ${delay}`}
      style={
        {
          background: dark ? "var(--surface-card-dark)" : "var(--paper)",
          color: dark ? "var(--background)" : "var(--text-body)",
          borderRadius: "var(--radius-2xl)",
          // 반전 카드는 두께도 진하다. 흰 카드와 같은 10% 검정을 쓰면
          // 잉크 바탕에 묻혀 두께가 사라진다.
          "--lift": dark ? "var(--lift-dark)" : "var(--lift-card)",
        } as React.CSSProperties
      }
    >
      {/* 라벨에 강조색을 쓰지 않는다. --coral 은 "지금 여기" 를 뜻하는
          색이라(MetaBadge 참고) 고정 라벨에 쓰면 그 의미가 흐려진다.
          uppercase 도 없다 - 한글에는 아무 효과가 없으면서 자간만 벌어져
          읽기 나빠진다. 대신 굵기(900)로 본문과 가른다. */}
      <h2
        style={{
          fontSize: "var(--text-xs)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-wide)",
          color: dark ? "var(--text-on-dark)" : "var(--text-dim)",
        }}
      >
        {label}
      </h2>
      <div
        className="mt-2.5"
        style={{
          fontSize: "var(--text-base)",
          lineHeight: "var(--leading-relaxed)",
        }}
      >
        {children}
      </div>
    </section>
  );
}

/**
 * 상세 맨 아래 주요 동작. "이 단어로 문제 풀기".
 *
 * 이 화면의 코랄 하나를 여기가 갖는다 - 읽고 나서 할 일이 그것뿐이고,
 * 없으면 상세가 막다른 화면이 된다(목록으로 되돌아가는 길만 있다).
 */
export function DetailAction({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="dv-btn rise mt-5 flex w-full items-center justify-center px-5 [animation-delay:440ms] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      style={
        {
          background: "var(--coral)",
          color: "var(--text-on-color)",
          borderRadius: "var(--radius-pill)",
          minHeight: "var(--hit-min)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
          // 쉬는 두께는 --lift 로. 인라인 box-shadow 는 :active 를 이긴다.
          "--lift": "var(--lift-button)",
        } as React.CSSProperties
      }
    >
      {children}
    </Link>
  );
}
