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
        {/* 코랄을 안 쓴다. 이 화면의 코랄 하나는 아래 "다음"·"문제 풀기"
            버튼이 갖는다 - 코랄은 "지금 눌러야 할 것" 이라, 누를 수 없는
            제목에 쓰면 그 뜻이 흐려진다. */}
        <h2
          id="study-heading"
          className="text-sm"
          style={{
            fontWeight: "var(--weight-black)",
            letterSpacing: "var(--tracking-tight)",
            color: "var(--foreground)",
          }}
        >
          먼저 익히기
        </h2>
        {/* 두 진행을 함께 보여준다. 묶음만 보이면 "언제 끝나지" 를 알 수
            없고, 카드만 보이면 이 판에서 몇 번 더 반복하는지 모른다. */}
        <p
          className="text-xs tabular-nums"
          style={{ color: "var(--text-dim)", fontWeight: "var(--weight-bold)" }}
        >
          {/* 묶음 수를 모르면 카드 진행만 보여준다. "1/0묶음" 이 뜨는
              것보다 낫다. */}
          {chunkCount > 0 && `${chunkIndex + 1}/${chunkCount}묶음 · `}
          {at + 1}/{cards.length}
        </p>
      </header>

      {/* 흰 카드에 담는다. 크림에는 영역별 배경이 없어서(가이드 color-base)
          맨몸으로 두면 크림 바탕 위에 뜬 글자 덩어리가 된다. 상세 화면이
          히어로를 카드로 감싼 것과 같은 이유이고, 같은 단어를 보여주는
          자리라 그쪽과 따로 놀면 안 된다.
          dv-card 만 붙이고 dv-card-press 는 안 붙인다 - 누를 수 없는 카드가
          눌리는 시늉을 하면 안 된다. 넘기는 것은 아래 버튼이 맡는다. */}
      <article
        className="dv-card mt-5 flex flex-1 flex-col px-5 pt-6 pb-6"
        style={
          {
            background: "var(--paper)",
            borderRadius: "var(--radius-2xl)",
            "--lift": "var(--lift-card)",
          } as React.CSSProperties
        }
      >
        <h3
          className="text-[clamp(1.75rem,7vw,2.25rem)]"
          style={{
            fontFamily: "var(--font-mono)",
            fontWeight: "var(--weight-bold)",
            letterSpacing: "var(--tracking-tighter)",
            lineHeight: "var(--leading-none)",
            color: "var(--foreground)",
          }}
        >
          {card.term}
        </h3>

        {card.pronunciation && (
          // 발음기호는 고정폭으로 두지 않는다. IPA 기호가 고정폭 글꼴에서
          // 깨지거나 폭이 어긋나는 경우가 있다(단어 상세와 같은 이유).
          <p
            lang="en-US"
            className="mt-3 text-sm"
            style={{ color: "var(--text-muted)" }}
          >
            {card.pronunciation}
          </p>
        )}
        {card.reading && (
          <Reading
            text={card.reading}
            className="mt-1 block text-sm"
            style={{ color: "var(--text-muted)" }}
          />
        )}

        <p
          className="mt-4 text-lg"
          style={{
            fontWeight: "var(--weight-black)",
            letterSpacing: "var(--tracking-tight)",
            lineHeight: "var(--leading-snug)",
            color: "var(--foreground)",
          }}
        >
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
            <summary
              className="inline-flex min-h-11 cursor-pointer list-none items-center gap-1 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus [&::-webkit-details-marker]:hidden"
              style={{
                color: "var(--text-muted)",
                fontWeight: "var(--weight-bold)",
              }}
            >
              자세히
              <span
                aria-hidden="true"
                className="transition-transform group-open:rotate-180"
              >
                ▾
              </span>
            </summary>
            <p
              className="mt-1 text-sm"
              style={{
                lineHeight: "var(--leading-relaxed)",
                color: "var(--text-body)",
              }}
            >
              {card.description}
            </p>
          </details>
        )}

        {card.example && (
          // 예문은 카드 안 옅은 띠에 앉힌다.
          //
          // 상세 화면은 예문을 잉크로 뒤집는데(DetailCard tone="dark") 그건
          // 카드가 따로 서 있어서 가능하다. 여기는 흰 카드 **안** 이라,
          // 뒤집으면 카드 안에 또 다른 층이 생겨 두께가 두 겹으로 읽힌다.
          // 크림은 층을 하나만 둔다 - 그래서 반전 대신 --background-deep
          // 띠로 물러난다(입력칸과 같은 값).
          <div
            className="mt-5 px-4 py-3"
            style={{
              background: "var(--background-deep)",
              borderRadius: "var(--radius-md)",
            }}
          >
            <p
              className="font-mono text-sm"
              style={{
                color: "var(--foreground)",
                letterSpacing: "var(--tracking-tighter)",
              }}
            >
              {card.example}
            </p>
            {card.example_translation && (
              <p
                className="mt-1.5 text-xs"
                style={{ color: "var(--text-muted)" }}
              >
                {card.example_translation}
              </p>
            )}
          </div>
        )}
      </article>

      {/* 이 화면의 코랄 하나. 카드를 넘기는 것이 여기서 할 일의 전부다. */}
      <button
        type="button"
        onClick={() => (last ? onDone() : setAt(at + 1))}
        className="dv-btn mt-5 flex w-full items-center justify-center px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        style={
          {
            minHeight: "var(--hit-min)",
            background: "var(--coral)",
            color: "var(--text-on-color)",
            border: 0,
            borderRadius: "var(--radius-pill)",
            fontWeight: "var(--weight-black)",
            letterSpacing: "var(--tracking-tight)",
            "--lift": "var(--lift-button)",
          } as React.CSSProperties
        }
      >
        {last ? "문제 풀기" : "다음"}
      </button>
    </section>
  );
}
