"use client";

import { useState } from "react";

import { CategoryChip } from "@/components/MetaBadge";
import { Reading } from "@/components/Reading";
import type { StudyCard } from "@/lib/api/daily";

/**
 * 일일공부의 학습 단계. 카드를 한 장씩 넘긴다.
 *
 * **문제 앞에 놓인다.** 모르는 단어가 4지선다로 나오면 찍고 넘어가는데,
 * 그건 이미 아는 것을 확인하는 것이지 배우는 것이 아니다. 이 앱의 타겟
 * (영어가 약한 주니어)에게는 먼저 보여줘야 한다.
 *
 * 카드는 서버가 골라 보낸다 - 틀린 것, 안 본 것, 오래된 것 순이다
 * (backend daily_study._pick_for_study). 화면은 순서를 다시 정하지 않는다.
 *
 * **넘긴 것을 서버에 알리지 않는다.** 문제가 이미 같이 와 있어서, 다
 * 넘기면 그 자리에서 문제로 간다. 알리면 왕복이 늘고 그 요청은 점수와
 * 무관해 되돌리기를 막을 이유도 없다.
 */
export function StudyCards({
  cards,
  chunkIndex,
  chunkCount,
  onDone,
}: {
  cards: StudyCard[];
  /** 지금 몇 번째 묶음인가(0부터). */
  chunkIndex: number;
  chunkCount: number;
  /** 마지막 카드에서 넘기면 부른다. */
  onDone: () => void;
}) {
  const [at, setAt] = useState(0);

  // 카드가 없으면 아무것도 안 그린다. 부르는 쪽이 이 경우를 거르지만,
  // 여기서도 막아야 cards[at] 이 undefined 가 되는 길이 없다.
  if (cards.length === 0) return null;

  const card = cards[Math.min(at, cards.length - 1)];
  const last = at >= cards.length - 1;

  return (
    <section aria-labelledby="study-heading" className="flex flex-1 flex-col">
      <header className="flex items-baseline justify-between gap-3">
        <h2 id="study-heading" className="text-sm font-semibold text-focus">
          먼저 익히기
        </h2>
        {/* 두 진행을 함께 보여준다. 묶음만 보이면 "언제 끝나지" 를 알 수
            없고, 카드만 보이면 이 판에서 몇 번 더 반복하는지 모른다. */}
        <p className="text-xs text-slate-400 tabular-nums">
          {/* 묶음 수를 모르면 카드 진행만 보여준다. "1/0묶음" 이 뜨는
              것보다 낫다. */}
          {chunkCount > 0 && `${chunkIndex + 1}/${chunkCount}묶음 · `}
          {at + 1}/{cards.length}
        </p>
      </header>

      <article className="mt-6 flex flex-1 flex-col">
        <h3 className="font-mono text-[clamp(1.75rem,7vw,2.25rem)] leading-none font-bold tracking-tighter text-slate-50">
          {card.term}
        </h3>

        {card.pronunciation && (
          // 발음기호는 고정폭으로 두지 않는다. IPA 기호가 고정폭 글꼴에서
          // 깨지거나 폭이 어긋나는 경우가 있다(단어 상세와 같은 이유).
          <p lang="en-US" className="mt-3 text-sm text-slate-300">
            {card.pronunciation}
          </p>
        )}
        {card.reading && (
          <Reading text={card.reading} className="mt-1 block text-sm text-slate-400" />
        )}

        <p className="mt-4 text-lg leading-snug font-semibold text-slate-100">
          {card.meaning}
        </p>

        {/* 분류는 목록·상세와 같은 칩으로 보여준다. 여기만 다른 모양이면
            같은 단어가 화면마다 다르게 보인다. 누를 수 있게는 하지 않는다 -
            학습 중에 목록으로 빠지면 판이 끊긴다. */}
        <div className="mt-3">
          <CategoryChip label={card.category_label} />
        </div>

        {card.description && (
          // 설명은 접어둔다. 다 펼치면 카드 한 장이 길어져 넘기는 속도가
          // 떨어지는데, 이 단계는 훑는 것이 목적이다. details 를 쓰는 이유는
          // FilterPanel 과 같다 - 브라우저가 여닫으므로 상태를 안 들고 있다.
          <details className="group mt-4">
            <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-xs text-slate-400 transition-colors hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus [&::-webkit-details-marker]:hidden">
              자세히
              <span aria-hidden="true" className="transition-transform group-open:rotate-180">
                ▾
              </span>
            </summary>
            <p className="mt-2 text-sm leading-relaxed text-slate-300">
              {card.description}
            </p>
          </details>
        )}

        {card.example && (
          <div className="mt-5 rounded-xl border border-white/10 bg-slate-950/30 px-4 py-3">
            <p className="font-mono text-sm text-slate-100">{card.example}</p>
            {card.example_translation && (
              <p className="mt-1.5 text-xs text-slate-400">
                {card.example_translation}
              </p>
            )}
          </div>
        )}
      </article>

      <button
        type="button"
        onClick={() => (last ? onDone() : setAt(at + 1))}
        className="mt-6 flex min-h-12 w-full items-center justify-center rounded-full bg-focus px-5 font-semibold text-focus-on transition-[scale] duration-[120ms] ease-press active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        {last ? "문제 풀기" : "다음"}
      </button>
    </section>
  );
}
