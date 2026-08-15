import Link from "next/link";

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
};

export function LearningCard({
  href,
  title,
  subtitle,
  aside,
  badge,
  tag,
  monoTitle = true,
}: LearningCardProps) {
  return (
    <Link
      href={href}
      // 카드를 불투명하게 채우면 뒤의 배경 그라디언트가 통째로 가려진다.
      // 반투명으로 두면 배경이 비쳐서 목록 전체가 한 화면으로 읽힌다.
      // backdrop-blur 는 일부러 쓰지 않는다 - 목록에 카드가 스무 개씩
      // 깔리는데 카드마다 백드롭 필터를 걸면 폰에서 스크롤이 끊긴다.
      className="group block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-slate-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus dark:border-white/12 dark:bg-slate-950/45 dark:hover:border-white/25"
    >
      <div className="flex items-start justify-between gap-3">
        {/* min-w-0 이 없으면 flex 항목이 내용보다 작아지지 못한다. 제목에
            줄바꿀 곳이 없는 긴 문자열(에러 메시지 안의 URL 같은 것)이 오면
            카드가 화면 밖으로 밀려 나가 페이지에 가로 스크롤이 생긴다.
            데스크톱에서는 여백이 넉넉해 드러나지 않고 폰에서만 보인다.
            글자를 끊는 쪽은 globals.css 의 base 규칙이 맡는다. */}
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-2">
          <h2
            className={`text-xl font-semibold text-slate-900 group-hover:underline dark:text-slate-50 ${
              monoTitle ? "font-mono" : ""
            }`}
          >
            {title}
          </h2>
          {aside && (
            // 발음기호는 고정폭으로 두지 않는다. IPA 기호가 고정폭 글꼴에서
            // 깨지거나 폭이 어긋나는 경우가 있다.
            <span
              lang="en-US"
              className="text-base text-slate-500 dark:text-slate-300"
            >
              {aside}
            </span>
          )}
        </div>
        {badge}
      </div>

      <p className="mt-1.5 text-lg text-slate-700 dark:text-slate-200">
        {subtitle}
      </p>

      {tag && <div className="mt-3">{tag}</div>}
    </Link>
  );
}
