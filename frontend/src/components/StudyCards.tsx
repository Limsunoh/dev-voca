"use client";

import { useState, useSyncExternalStore } from "react";

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
/**
 * 카드 번호를 탭에 적고 읽는다.
 *
 * **막혀도 화면은 돌아야 한다.** 사생활 보호 창이나 사이트 데이터를 막아둔
 * 브라우저에서는 이 접근 자체가 예외를 던진다. 여기서 안 막으면 학습
 * 화면이 통째로 안 뜬다 - 위치를 기억하는 편의 하나 때문에 잃기에는 큰
 * 것이다. 못 읽으면 첫 장부터 보면 된다.
 */
function read(key: string): number {
  try {
    const saved = Number(window.sessionStorage.getItem(key));
    return Number.isInteger(saved) && saved >= 0 ? saved : 0;
  } catch {
    return 0;
  }
}

/**
 * 바깥에서 값이 바뀌었다고 알려줄 일이 없다 - 이 값은 우리가 적고 우리가
 * 읽는다. 구독 해제 함수만 돌려준다.
 */
function noSubscribe(): () => void {
  return () => {};
}

function save(key: string, value: number): void {
  try {
    window.sessionStorage.setItem(key, String(value));
  } catch {
    // 못 적어도 그만이다. 이 판에서만 자리를 잃는다.
  }
}

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
  /**
   * 지금 보는 카드 번호. **새로고침해도 이어지도록 탭에 적어둔다.**
   *
   * 여덟 장을 넘기다 새로고침하면 첫 장으로 돌아갔다. 카드를 넘긴 것은
   * 서버에 안 알리므로(위 머리말) 화면이 기억하지 않으면 아무도 모른다.
   * 서버에 알리는 쪽은 왕복이 늘고, 넘긴 자리는 점수와 무관해 굳이 남길
   * 값이 아니다.
   *
   * 묶음마다 따로 적는다. 다음 묶음은 처음부터 봐야 한다.
   *
   * 탭 안에만 둔다(sessionStorage). 다른 탭이나 내일까지 들고 있으면,
   * 새 판의 같은 번호 묶음에서 엉뚱한 자리부터 시작한다.
   */
  const memoryKey = `daily-card-${chunkIndex}`;
  /**
   * **적어둔 번호는 리액트 바깥의 값이라 전용 훅으로 읽는다.**
   *
   * 첫 화면은 서버가 그려 보내는데 서버에는 브라우저 저장소가 없다. 그리는
   * 중에 그냥 읽으면 서버가 보낸 화면과 달라지고("이전" 버튼은 번호가 0 보다
   * 클 때만 그린다), 그러면 리액트가 그 자리를 처음부터 다시 그린다.
   *
   * `useSyncExternalStore` 가 바로 이런 값을 위한 것이다 - 서버 몫으로 0 을
   * 따로 받아, 서버가 그릴 때와 화면에 붙기 전까지는 그 값을 쓴다. 붙은
   * 뒤에 적어둔 번호로 한 번 바뀐다.
   *
   * 값이 바뀌었다고 알려줄 바깥 신호는 없다(우리가 적고 우리가 읽는다).
   * 그래서 구독은 빈 함수이고, 넘길 때는 아래 goTo 가 직접 다시 그리게 한다.
   */
  const saved = useSyncExternalStore(
    noSubscribe,
    () => read(memoryKey),
    () => 0,
  );
  const [picked, setPicked] = useState<number | null>(null);
  const rawAt = picked ?? saved;

  const goTo = (next: number) => {
    setPicked(next);
    save(memoryKey, next);
  };

  // 카드가 없으면 아무것도 안 그린다. 부르는 쪽이 이 경우를 거르지만,
  // 여기서도 막아야 cards[at] 이 undefined 가 되는 길이 없다.
  if (cards.length === 0) return null;

  /**
   * 실제로 그릴 번호. **한 번만 자르고 아래는 전부 이 값을 쓴다.**
   *
   * 적어둔 번호가 카드 수보다 클 수 있다. 묶음 크기는 판마다 달라질 수
   * 있는데(backend `_fit_chunks` 가 콘텐츠 수에 맞춰 줄인다) 적어두는 키는
   * 묶음 번호뿐이라, 탭을 열어둔 채 새 판을 시작하면 지난 판의 번호를
   * 읽는다.
   *
   * 카드만 자르고 표시를 안 자르면 "6/3" 이 뜨고, "이전" 도 한 번은
   * 헛돈다(4로 줄어도 같은 카드라 화면이 안 바뀐다).
   */
  const at = Math.min(rawAt, cards.length - 1);
  const card = cards[at];
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

      <div className="mt-5 flex gap-2">
        {/* **되돌아갈 길.** 없으면 잘못 넘긴 카드를 다시 볼 방법이 판을
            끝낼 때까지 없다. 첫 장에서는 안 그린다 - 눌러도 갈 곳이 없는
            버튼은 자리만 차지한다. */}
        {at > 0 && (
          <button
            type="button"
            onClick={() => goTo(at - 1)}
            className="dv-btn flex items-center justify-center px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            style={
              {
                minHeight: "var(--hit-min)",
                background: "var(--paper)",
                color: "var(--foreground)",
                border: 0,
                borderRadius: "var(--radius-pill)",
                fontWeight: "var(--weight-bold)",
                "--lift": "var(--lift-button-paper)",
              } as React.CSSProperties
            }
          >
            이전
          </button>
        )}
        {/* 이 화면의 코랄 하나. 카드를 넘기는 것이 여기서 할 일의 전부다. */}
        <button
          type="button"
          onClick={() => (last ? onDone() : goTo(at + 1))}
          className="dv-btn flex flex-1 items-center justify-center px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
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
      </div>
    </section>
  );
}
