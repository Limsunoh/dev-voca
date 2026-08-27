import Link from "next/link";

import { Reading } from "./Reading";

/**
 * 단어·문장 상세의 공통 뼈대.
 *
 * 전에는 두 화면이 각자 문단을 위에서부터 흘려 썼다. 제목도 본문도 왼쪽에
 * 같은 크기로 붙어서 어디가 중요한지 안 보였고, 화면 아래 절반이 비었는데
 * 내용은 위에 몰려 있었다 - 앱이 아니라 블로그 글로 읽혔다.
 *
 * 그래서 두 층으로 나눈다.
 *
 *   히어로   제목·발음·배지. 화면 위쪽을 채우고 배경 빛을 정면으로 받는다
 *   카드     뜻·설명·예문. 각각 구획된 상자에 담아 무엇이 한 덩이인지 보인다
 *
 * 두 화면이 같은 파일을 쓰는 이유: 단어에서 고친 간격이 문장에 반영되지
 * 않으면 같은 앱의 두 화면이 서로 다르게 보인다. 실제로 그렇게 벌어졌었다.
 */

/** 되돌아가는 줄. 화면 맨 위에 두고 히어로보다 작게 둔다. */
export function DetailBack({ href, label }: { href: string; label: string }) {
  return (
    // 본문보다 작게 두지 않는다. 상세에서 목록으로 돌아가는 것은 자주 하는
    // 일이라 잔글씨로 두면 매번 조준해서 눌러야 한다. 화살표도 같이 키운다.
    <Link
      href={href}
      className="-ml-1 inline-flex min-h-12 items-center gap-2 rounded-lg px-1 text-base font-medium text-slate-300 transition-[scale,color] duration-[120ms] ease-press hover:text-slate-100 active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
    >
      <span aria-hidden className="text-lg leading-none">
        ←
      </span>
      {label}
    </Link>
  );
}

/**
 * 상세 화면 껍데기.
 *
 * 배경은 [id]/layout.tsx 가 깐다. 여기서 깔면 이 컴포넌트를 쓰는 화면만
 * 배경을 받고, 같은 자리의 error·not-found 는 못 받는다.
 */
export function DetailShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto w-full max-w-2xl px-5 pt-8 pb-12">{children}</main>
  );
}

/**
 * 히어로. 제목이 화면 위쪽을 차지한다.
 *
 * 목록에서 카드를 눌러 들어온 자리라, 무엇을 눌렀는지가 첫 화면에서 바로
 * 읽혀야 한다. 제목을 본문 크기로 두면 그 확인이 안 된다.
 */
export function DetailHero({
  title,
  aside,
  reading,
  meta,
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
  /** 난이도·분류 배지 줄. */
  meta?: React.ReactNode;
  /** 제목을 고정폭으로 둘지. 단어는 true, 사람이 쓴 문장은 false. */
  mono?: boolean;
}) {
  return (
    // 조각마다 따로 올라온다. header 하나에 걸면 통째로 밀려 올라와서 그냥
    // 화면이 이동한 것으로 보인다. 제목·발음·배지가 차례로 서면 무엇부터
    // 읽어야 하는지가 같이 전달된다.
    //
    <header>
      {/* 글자 수로 크기를 가른다. vw 만 쓰면 화면 폭만 보고 내용 길이를
          몰라서, 짧은 단어와 긴 에러 메시지가 같은 크기로 나온다.

          짧은 것은 크게 - 화면을 채워야 제목답다.
          긴 것은 작게 - 폰에서 다섯 줄 220px 를 먹으면 제목이 아니라 글
          덩어리가 된다("IntegrityError: UNIQUE constraint failed..." 가
          실제로 그랬다).

          경계를 24자로 둔 이유: 390px 폰에서 고정폭 48px 로 두 줄에 들어가는
          한계가 그 근처다. */}
      <h1
        className={`rise text-balance font-bold text-slate-50 ${
          mono
            ? `font-mono tracking-tighter ${
                title.length <= 24
                  ? "text-[clamp(2.75rem,13vw,4rem)] leading-[1.02]"
                  : "text-[clamp(1.5rem,7vw,2.25rem)] leading-[1.15]"
              }`
            : `tracking-tight ${
                title.length <= 40
                  ? "text-[clamp(2rem,9vw,2.75rem)] leading-[1.1]"
                  : "text-[clamp(1.5rem,6vw,2rem)] leading-[1.2]"
              }`
        }`}
      >
        {title}
      </h1>

      {aside && (
        // 발음기호는 고정폭으로 두지 않는다. IPA 기호가 고정폭 글꼴에서
        // 깨지거나 폭이 어긋나는 경우가 있다.
        <p
          lang="en-US"
          className="rise mt-3 text-lg text-slate-300 [animation-delay:60ms]"
        >
          {aside}
        </p>
      )}

      {reading && (
        <Reading
          text={reading}
          className="rise mt-1.5 block text-lg text-slate-400 [animation-delay:80ms]"
        />
      )}

      {meta && (
        <div className="rise mt-4 flex flex-wrap items-center gap-2 [animation-delay:120ms]">
          {meta}
        </div>
      )}
    </header>
  );
}

/**
 * 뜻. 히어로 바로 아래에서 답을 준다.
 *
 * 카드에 넣지 않고 맨몸으로 두는 이유: 이게 이 화면에 들어온 목적이라
 * 상자에 담아 다른 정보와 동급으로 만들면 안 된다. 왼쪽 강조선만 준다.
 */
export function DetailMeaning({ children }: { children: React.ReactNode }) {
  return (
    <p className="rise mt-7 border-l-[3px] border-focus/70 pl-4 text-pretty text-2xl leading-snug font-semibold tracking-tight text-slate-50 [animation-delay:200ms]">
      {children}
    </p>
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
  raised = false,
  children,
}: {
  label: string;
  /** 등장 순서. 위에서부터 80ms 씩 늘린다. */
  delay: string;
  /**
   * 더 띄울지. 예문처럼 실제로 보러 온 것에만 준다.
   *
   * 카드가 전부 같은 높이로 앉아 있으면 무엇이 중요한지 표현이 없다.
   * 그림자 세기로 순서를 만든다.
   */
  raised?: boolean;
  children: React.ReactNode;
}) {
  // 그림자를 검정이 아니라 배경 색조(청록)로 낸다. 순수 검정 그림자는 어느
  // 배경에서나 같은 회색을 만들어 화면과 따로 논다. 광원은 배경이 위에서
  // 내려오는 것과 맞춰 아래(+Y) 한 방향으로 통일한다.
  //
  // inset 한 줄은 카드 윗변에 얇은 빛을 남긴다. 유리 조각처럼 두께가
  // 생겨서, 테두리만 있을 때보다 확실히 떠 보인다.
  const depth = raised
    ? "shadow-[0_1px_0_0_rgb(255_255_255/0.07)_inset,0_12px_32px_-10px_rgb(4_32_31/0.85)]"
    : "shadow-[0_1px_0_0_rgb(255_255_255/0.05)_inset,0_6px_18px_-8px_rgb(4_32_31/0.6)]";

  return (
    <section
      className={`rise mt-4 rounded-2xl border border-white/12 bg-slate-950/55 p-5 ${depth} ${delay}`}
    >
      {/* 라벨에 강조색을 쓰지 않는다. --focus 는 "지금 여기" 를 뜻하는
          색이라(MetaBadge 참고) 고정 라벨에 쓰면 그 의미가 흐려진다.
          uppercase 도 뺐다 - 한글에는 아무 효과가 없으면서 자간만 벌어져
          읽기 나빠진다. 대신 굵기로 본문과 가른다. */}
      <h2 className="text-xs font-semibold tracking-wide text-slate-400">
        {label}
      </h2>
      <div className="mt-3 text-[1.0625rem] leading-relaxed text-slate-200">
        {children}
      </div>
    </section>
  );
}
