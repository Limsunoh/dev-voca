"use client";

import { CategoryChip, DifficultyBadge } from "@/components/MetaBadge";
import { Reading } from "@/components/Reading";
import { SpeakButton } from "@/components/SpeakButton";
import { alignParts } from "@/lib/talk-parts";
import type { TalkPrompt as Prompt } from "@/lib/api/talk";

/**
 * 읽을 것을 보여주는 카드.
 *
 * 본보기는 발음기호와 한글 발음이다. 이 두 칸은 검수까지 끝난 채로 DB 에
 * 있다.
 *
 * 소리 듣기 버튼(SpeakButton, 폰 음성)도 둔다(2026-11-12 운영자 요청). 이
 * 화면은 사람이 소리내어 말하는 곳이라 글만 보고는 어떻게 소리내는지 모를 수
 * 있다. 다만 주된 본보기는 여전히 위의 두 칸이다 - 영어 음성이 하나도 없는
 * 기계가 있고, 그런 기계에서는 버튼이 숨는다(SpeakButton 머리말).
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
  /**
   * 마이크로 듣는 중인가. 그동안은 소리 듣기 버튼을 감춘다.
   *
   * 듣는 중에 눌리면 폰이 읽은 소리를 마이크가 받아, 사람이 말한 것이 아니라
   * 폰 음성을 채점한다(거의 늘 통과로 나온다).
   *
   * 지우지 않고 감추는(invisible) 이유: 자리는 그대로 두고 누를 수도, 초점을
   * 받을 수도, 화면 낭독기가 읽을 수도 없게 한다. 지우면 글자 200%(버튼이
   * 줄을 차지하는 폭)에서 읽을 때마다 카드가 56px 줄었다 늘어 아래 버튼이
   * 출렁이고, 영어 음성이 없는 기기에서는 다시 만들어진 버튼이 1.5초 보였다
   * 숨는다. 읽던 소리는 TalkBoard 의 listen() 이 먼저 멈춘다.
   */
  listening = false,
}: {
  prompt: Prompt;
  wrongAt?: number[] | null;
  listening?: boolean;
}) {
  // 셋(글자·발음기호·한글발음)을 낱말 단위로 짝짓는다. 하나라도 개수가
  // 어긋나면 null 이고, 그때는 쪼개지 않고 그린다. 엉뚱한 자리를 강조하면
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
      className="relative grid gap-3 p-6 text-center"
      style={{
        background: "var(--paper)",
        borderRadius: "var(--radius-2xl)",
        boxShadow: "var(--lift-card)",
      }}
    >
      {/* 난이도. 일상 표현은 발음, 개발 용어는 개념이 어려운 정도다(TalkLevelTabs 머리말).

          위에 두는 이유: 읽기 전에 알아야 마음의 준비가 된다. 아래에 두면
          다 읽고 나서 "아 이게 어려운 거였구나" 가 된다.

          알약을 여기서 손으로 그리지 않는다. 크림 배경에 크림 채움이면
          카드 위에서 사실상 안 보인다. 단어장·목록이 쓰는 DifficultyBadge
          에 난이도별 색(초록·앰버·장미)이 들어 있으니 그것을 쓴다. 같은
          정보를 화면마다 다르게 그리지 않는다. */}
      {/* 상황 배지를 난이도 옆에 둔다. "전체" 에서 읽을 때 지금 것이 어느
          상황에서 쓰는 말인지 알려준다. 상황이 없는 것(개발 용어, 상황을
          비운 표현)은 CategoryChip 이 빈 이름에서 아무것도 안 그린다.

          목록 카드가 분류를 그리는 그 칩이다. 이 카드에서는 누를 곳이
          없어서 링크 없이 쓴다. */}
      {/* px-10: 오른쪽 위 소리 버튼(아래)과 겹치지 않게 양옆을 비운다. 한쪽만
          비우면 배지가 가운데에서 비켜 보인다. 화면이 좁아 버튼이 줄로 내려가면
          (max-[20rem], 아래 주석) 비울 필요가 없다. */}
      <p className="flex flex-wrap items-center justify-center gap-2 px-10 max-[20rem]:px-0">
        <DifficultyBadge
          level={prompt.difficulty}
          label={prompt.difficulty_label}
        />
        <CategoryChip label={prompt.scene_label} />
      </p>

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

      {/* 소리 듣기. 카드 오른쪽 위 구석, 배지와 같은 줄에 띄워 둔다.

          줄을 따로 두지 않는 이유: 카드가 44px 버튼 한 줄만큼 길어지면 세로가
          짧은 폰(375x667, 폴드 8 접은 416x657)에서 주 버튼 "읽기" 가 아래
          탭바 밑으로 밀려 스크롤해야 보인다. 띄워 두면 카드 높이가 그대로다.

          화면 폭이 20rem(320px) 아래면 띄우지 않고 읽을 글자 아래 가운데에
          한 줄로 둔다. 폰 글자 크기 200% 는 페이지 확대라 360폭 폰이 180px
          폭으로 그려진다(CODE_INSIGHTS 11-12). 그 폭에서 띄워 두면 배지에 남는
          자리가 20px 뿐이라 난이도 배지가 버튼 밑으로 들어간다. 그 크기에서는
          어차피 화면이 스크롤되니 줄을 하나 쓰는 편이 낫다. 우리가 보는 폰은
          가장 좁은 것이 360px 이라 평소에는 띄운 채다.

          화면 낭독기 순서는 읽을 글자 바로 뒤라 "이것을 듣기" 로 이어진다.

          key 로 문제마다 새로 만든다. 같은 버튼을 다음 문제에 그대로 쓰면
          읽던 앞 문제 소리가 다음 문제 위에서 계속 나온다. 새로 만들면
          앞 버튼이 사라지며 읽던 것을 멈춘다(SpeakButton 의 정리 단계). */}
      <div
        className={`absolute top-4 right-4 max-[20rem]:static max-[20rem]:flex max-[20rem]:justify-center${
          listening ? " invisible" : ""
        }`}
      >
        <SpeakButton key={prompt.id} text={prompt.term} label="발음 듣기" />
      </div>

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

          발음 표기보다 크게 둔다. 곁다리로 보고 제일 작게(text-xs) 제일
          흐리게(--text-dim) 두면, IPA 와 한글 발음이 뜻보다 커서 제일
          필요한 것이 제일 안 보인다.

          읽을 글자 다음으로 큰 자리를 준다. 순서는 이렇다.

              읽을 글자   --text-2xl  무엇을 소리내나
              뜻          --text-xl   무슨 말인가
              한글 발음   text-sm     어떻게 소리내나
              발음기호    text-sm     (아는 사람에게만)

          --text-xl 은 이 저장소가 토큰 주석에 "21px 뜻" 이라고 적어둔
          값이다. 숫자를 새로 고르지 않고 그것을 쓴다. */}
      {prompt.meaning && (
        <p
          className="text-[length:var(--text-xl)] break-words"
          style={{ color: "var(--text-body)" }}
        >
          {prompt.meaning}
        </p>
      )}
    </section>
  );
}
