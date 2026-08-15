import Link from "next/link";

import { contentPath, learningModes } from "@/lib/routes";

/**
 * 학습 모드 탭(익히기 / 문제풀기 / 말하기).
 *
 * 아직 익히기만 동작한다. 나머지를 감추지 않고 "준비 중"으로 두는 이유는
 * 이 서비스가 단어장 하나로 끝나지 않는다는 걸 알리기 위해서다.
 *
 * 링크는 지금 보고 있는 콘텐츠를 유지한다. 문장을 보다 모드를 바꿨는데
 * 단어로 떨어지면 사용자가 흐름을 잃는다.
 *
 * 준비 중인 모드는 링크가 아니라 span 이다. 비활성 링크를 a 로 두면
 * 키보드 탭으로 옮겨갈 수 있는데 눌러도 아무 일이 안 일어나 혼란스럽다.
 */
export function ModeTabs({
  current,
  content,
}: {
  /** 지금 모드의 slug. */
  current: string;
  /** 지금 콘텐츠의 slug. 모드를 바꿔도 이걸 유지한다. */
  content: string;
}) {
  return (
    <nav aria-label="학습 모드" className="flex flex-wrap gap-2">
      {learningModes.map((mode) => {
        const active = mode.slug === current;

        if (!mode.ready) {
          return (
            <span
              key={mode.slug}
              // 마우스를 올리면 왜 못 누르는지 알려준다.
              title="준비 중입니다"
              // 어두운 배경에서 slate-600 은 대비가 2.5:1 이라 읽히지 않는다.
              // 준비 중이라도 그런 모드가 있다는 걸 알리려고 남긴 자리라,
              // 안 보이면 둘 자리가 없는 것과 같다.
              className="cursor-default rounded-full border border-dashed border-slate-300 px-3 py-1 text-sm text-slate-400 dark:border-slate-500 dark:text-slate-300"
            >
              {mode.label}
              <span className="ml-1 text-xs">준비 중</span>
            </span>
          );
        }

        return (
          <Link
            key={mode.slug}
            href={contentPath(mode.slug, content)}
            // 선택된 항목은 색만으로 구분하지 않는다. 색각 이상이 있으면 구분이 안 된다.
            aria-current={active ? "page" : undefined}
            className={
              active
                ? "rounded-full bg-slate-900 px-3 py-1 text-sm text-white dark:bg-slate-100 dark:text-slate-900"
                : "rounded-full border border-slate-200 px-3 py-1 text-sm text-slate-600 hover:border-slate-400 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-500"
            }
          >
            {mode.label}
          </Link>
        );
      })}
    </nav>
  );
}
