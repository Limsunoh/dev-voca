import { ContentTabs } from "@/components/ContentTabs";

/**
 * 학습 화면 공통 머리말.
 *
 * 콘텐츠 탭(단어/문장)만 둔다. 모드(익히기/문제풀기)는 아래 탭바가 맡는다 -
 * 여기에도 두면 같은 이동 수단이 한 화면에 두 번 나온다.
 */
export function LearnHeader({
  mode,
  content,
  title,
  description,
}: {
  /** 지금 모드의 slug. 예: learn */
  mode: string;
  /** 지금 콘텐츠의 slug. 예: words */
  content: string;
  title: string;
  description: string;
}) {
  return (
    <header>
      <ContentTabs mode={mode} current={content} />

      <h1 className="mt-6 text-2xl font-bold text-slate-100">{title}</h1>
      <p className="mt-1 text-slate-300">{description}</p>
    </header>
  );
}
