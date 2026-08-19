import Link from "next/link";

/**
 * 난이도·분류 같은 부가 정보 표시.
 *
 * 목록 카드와 상세 화면이 같은 것을 쓴다. 두 벌로 두면 한쪽만 고쳐지고
 * 같은 정보가 화면마다 다르게 보인다.
 */

/**
 * 난이도 배지.
 *
 * 셋을 같은 회색으로 두면 "쉬움" 인지 "어려움" 인지 글자를 읽어야 안다.
 * 목록에서는 훑어보는 게 목적이라 그 전에 눈에 들어와야 한다.
 *
 * 색만으로 구분하지는 않는다 - 라벨 글자가 그대로 남아 있어서 색각 이상이
 * 있어도 뜻이 전달된다. 색은 훑어볼 때를 돕는 보조 수단이다.
 *
 * 강조색(--focus)과 겹치지 않는 색을 쓴다. 강조색은 "지금 여기" 를 뜻하고
 * 난이도는 콘텐츠의 성질이라, 같은 색이면 두 가지가 섞여 읽힌다.
 */
export function DifficultyBadge({
  level,
  label,
}: {
  /** 백엔드 Difficulty 값. 1 쉬움 / 2 보통 / 3 어려움. */
  level: number;
  label: string;
}) {
  // 모르는 값이 와도 회색으로 뜬다. 화면이 비지 않는 쪽을 고른다.
  const tone =
    {
      1: "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
      2: "border-amber-400/30 bg-amber-400/10 text-amber-200",
      3: "border-rose-400/30 bg-rose-400/10 text-rose-200",
    }[level] ?? "border-white/15 bg-white/5 text-slate-200";

  return (
    // 여기는 shrink-0 을 유지한다. 라벨이 choices 로 닫혀 있어 "어려움" 3자가
    // 최대이고, 목록 카드에서는 제목 오른쪽에 놓여서 긴 제목에 눌리면 안 된다.
    <span
      className={`shrink-0 rounded-full border px-2.5 py-0.5 text-sm font-medium ${tone}`}
    >
      {label}
    </span>
  );
}

/**
 * 분류 표시.
 *
 * 링크로 만들면 그 분류만 모아 볼 수 있다. 다만 상세에서는 눌러서 목록으로
 * 나가는 동작이라, 밑줄 없는 작은 회색 글자로 두면 눌리는 줄 모른다.
 * 칩 모양을 줘서 누를 수 있는 것으로 보이게 한다.
 */
export function CategoryChip({
  label,
  href,
}: {
  label: string;
  /** 없으면 누를 수 없는 표시로만 쓴다. */
  href?: string;
}) {
  // 빈 라벨이 오면 글자 없는 빈 알약이 그려진다. 호출부마다 막지 않고
  // 여기서 한 번 막는다.
  if (!label) return null;

  // shrink-0 을 쓰지 않는다. 분류 라벨은 "CS 기초(Computer Science)" 처럼
  // 길 수 있는데, 줄어들지 못하게 막으면 칸보다 넓어졌을 때 그대로 화면
  // 밖으로 나간다. 부모가 flex-wrap 이라 줄바꿈으로 해결되는 자리다.
  // 기본 글꼴에서는 안 드러나고 글자를 200% 로 키운 사용자에게만 보인다.
  const shape =
    "inline-flex min-w-0 items-center gap-1 rounded-full px-2.5 py-0.5 text-sm";

  // 누를 수 있는 것과 없는 것을 모양으로 가른다. hover 로만 다르게 두면
  // 터치에서는 구분할 단서가 하나도 없다 - 같은 줄에 두 종류가 나란히
  // 서는 화면(문장 상세)이 실제로 있다.
  if (!href) {
    return <span className={`${shape} bg-white/8 text-slate-300`}>{label}</span>;
  }

  return (
    <Link
      href={href}
      className={`${shape} border border-white/25 text-slate-100 underline decoration-white/30 underline-offset-4 transition-[scale,border-color,text-decoration-color] duration-[120ms] ease-press hover:border-white/50 hover:decoration-white/70 active:scale-[0.97] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus`}
    >
      {label}
    </Link>
  );
}
