"use client";

import { Reading } from "@/components/Reading";
import { alignParts } from "@/lib/talk-parts";
import type { TalkPrompt as Prompt } from "@/lib/api/talk";

/**
 * 읽을 것을 보여주는 카드.
 *
 * 본보기를 **발음기호와 한글 발음으로** 그린다. 소리로 들려주는 쪽
 * (speechSynthesis)을 주된 장치로 못 쓰기 때문이다 - 영어 음성이 하나도
 * 설치돼 있지 않은 기계가 실제로 있다. 그런 기계에서는 "들어보기" 가 눌러도
 * 아무 일도 안 하는 버튼이 된다.
 *
 * 대신 이 두 칸은 검수까지 끝난 채로 DB 에 있다. 없는 것을 만들어내지 않고
 * 이미 있는 것을 쓴다.
 */

export function TalkPromptCard({
  prompt,
  /**
   * 어긋난 낱말 자리. 채점 뒤에만 들어온다.
   *
   * null 은 "자리를 못 짚음" 이라 강조하지 않는다. 빈 배열과 뜻이 다르다 -
   * 빈 배열은 어긋난 자리가 없다는 뜻이다.
   */
  wrongAt,
}: {
  prompt: Prompt;
  wrongAt?: number[] | null;
}) {
  // 셋(글자·발음기호·한글발음)을 낱말 단위로 짝짓는다. 하나라도 개수가
  // 어긋나면 null 이고, 그때는 통째로 그린다 - 엉뚱한 자리를 강조하면
  // 사용자가 멀쩡한 낱말을 고치려 든다.
  const parts = alignParts(
    prompt.term,
    prompt.pronunciation,
    prompt.reading,
  );
  const wrong = new Set(wrongAt ?? []);
  const canHighlight = parts !== null && wrong.size > 0;

  return (
    <section
      className="grid gap-3 p-6 text-center"
      style={{
        background: "var(--paper)",
        borderRadius: "var(--radius-2xl)",
        boxShadow: "var(--lift-card)",
      }}
    >
      {/* 읽을 글자. 이 화면에서 가장 큰 것이어야 한다 - 사용자가 보는 것이
          이것 하나다. 고정폭인 이유는 단어·에러 메시지에 고정폭을 쓰는
          이 저장소의 관례를 따른 것이다(LearningCard 의 monoTitle). */}
      <p
        className="font-mono text-[length:var(--text-2xl)] break-words"
        lang="en-US"
        style={{
          color: "var(--foreground)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tighter)",
        }}
      >
        {canHighlight
          ? parts.map((part, i) => (
              <span key={i}>
                {i > 0 && " "}
                <span
                  style={
                    wrong.has(i)
                      ? {
                          // 틀린 자리를 색으로만 알리지 않는다. 색을 구분하기
                          // 어려운 사람에게는 아무 표시도 없는 것과 같다.
                          // 밑줄을 함께 둔다.
                          color: "var(--coral-deep)",
                          textDecoration: "underline",
                          textDecorationThickness: "3px",
                          textUnderlineOffset: "4px",
                        }
                      : undefined
                  }
                >
                  {part.word}
                </span>
              </span>
            ))
          : prompt.term}
      </p>

      {/* 발음기호는 받은 값을 그대로 그린다. 이 저장소의 다섯 화면이 이미
          그렇게 그리고 있어서(슬래시째) 여기서만 벗기면 어긋난다.

          고정폭을 쓰지 않는다 - 일부 발음기호가 고정폭에서 폭이 어긋나거나
          깨진다(LearningCard 의 aside 가 일부러 font-mono 없이 렌더되는
          것과 같은 이유). lang 을 붙이는 것은 한글 폰트가 IPA 를 잘못
          그리는 것을 막는다. */}
      {prompt.pronunciation && (
        <p
          className="text-sm break-words"
          lang="en-US"
          style={{ color: "var(--text-muted)" }}
        >
          {prompt.pronunciation}
        </p>
      )}

      {/* 한글 발음. "한글만 읽어도 통한다" 가 이 칸의 목적이라, 발음기호를
          못 읽는 사람에게는 이쪽이 본보기다.

          빌 수 있다 - 개발 용어의 발음은 별도 명령으로 붓는 것이라 픽스처를
          안 부은 환경에서는 빈 문자열이다. 그때는 이 줄을 안 그린다. */}
      {prompt.reading && (
        <Reading
          text={prompt.reading}
          className="text-sm break-words"
          style={{ color: "var(--text-body)" }}
        />
      )}

      {/* 뜻. 무엇을 읽는지 모른 채 소리만 흉내내면 남는 것이 없다.

          발음보다 작고 흐리게 둔다 - 이 화면에서 주인공은 읽을 글자이고,
          뜻은 "그게 무슨 말인지" 를 확인하는 곁다리다. */}
      {prompt.meaning && (
        <p className="text-xs" style={{ color: "var(--text-dim)" }}>
          {prompt.meaning}
        </p>
      )}
    </section>
  );
}
