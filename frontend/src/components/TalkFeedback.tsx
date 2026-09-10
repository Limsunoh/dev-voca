"use client";

import type { TalkResult } from "@/lib/api/talk";
import type { ListenOutcome } from "@/lib/speech";

/**
 * 한 번 읽은 결과.
 *
 * **"정답/오답" 이라고 말하지 않는다.** 채점이 글자 비교라 판정이 흐릿하다 -
 * 제대로 읽었는데 인식기가 다르게 적어서 실패하는 경우가 실제로 있다. 흐릿한
 * 판정을 단정해서 말하면 사용자가 자기 발음을 의심하게 되고, 그게 이 기능이
 * 줄이려던 공포를 오히려 키운다.
 *
 * **실패를 네 갈래로 나눈다.** 하나로 뭉치면 무엇을 고쳐야 할지 모른다.
 *
 *   소리가 안 들림    마이크·음소거를 본다
 *   못 알아들음       더 또박또박 말한다
 *   다르게 들림       무엇으로 들렸는지 보고 그 부분을 고친다
 *   통과              다음으로 간다
 *
 * 세 번째에서 **들린 것을 그대로 보여주는 것**이 핵심이다. 안 보여주면
 * 사용자가 같은 발음을 반복한다.
 */

export function TalkFeedback({
  outcome,
  result,
  /** 인식기가 준 원문. 서버가 정규화한 값 대신 이걸 보여준다. */
  heardRaw,
}: {
  outcome: ListenOutcome;
  /** 서버 채점 결과. 글자를 못 받았으면 없다. */
  result: TalkResult | null;
  heardRaw: string[];
}) {
  const view = describe(outcome, result, heardRaw);

  return (
    <div
      className="grid gap-2 rounded-[var(--radius-xl)] p-4"
      style={{ background: view.bg }}
    >
      <p
        className="text-sm"
        style={{ color: view.fg, fontWeight: "var(--weight-black)" }}
      >
        {view.title}
      </p>

      {view.detail && (
        <p className="text-sm leading-relaxed" style={{ color: view.fg }}>
          {view.detail}
        </p>
      )}

      {/* 무엇으로 들렸는지. 사용자가 자기 발음과 견줄 수 있는 유일한 단서라
          눈에 띄게 둔다. 인식기가 준 원문 그대로다 - 정규화한 값("Cache." 를
          "cache" 로 바꾼 것)을 보여주면 자기가 말한 것과 다르게 느낀다. */}
      {view.heard && (
        <p
          className="font-mono text-sm break-words"
          lang="en-US"
          style={{ color: view.fg, fontWeight: "var(--weight-bold)" }}
        >
          {view.heard}
        </p>
      )}
    </div>
  );
}

type View = {
  title: string;
  detail?: string;
  heard?: string;
  bg: string;
  fg: string;
};

function describe(
  outcome: ListenOutcome,
  result: TalkResult | null,
  heardRaw: string[],
): View {
  const wrong = {
    bg: "var(--wrong-soft)",
    fg: "var(--coral-deep)",
  };

  // 글자를 못 받은 경우가 먼저다. 서버까지 가지 않았으므로 result 가 없다.
  switch (outcome.type) {
    case "no-speech":
      return {
        ...wrong,
        title: "소리가 안 들렸어요",
        detail:
          "마이크가 켜져 있는지, 소리가 너무 작지 않은지 확인하고 다시 해보세요.",
      };
    case "no-mic":
      return {
        ...wrong,
        title: "마이크를 열지 못했어요",
        detail:
          "다른 프로그램이 마이크를 쓰고 있을 수 있습니다. 그 프로그램을 닫고 다시 해보세요.",
      };
    case "denied":
      return {
        ...wrong,
        title: "마이크가 막혔어요",
        detail:
          "주소창 왼쪽 자물쇠 아이콘에서 마이크를 허용으로 바꾸고 화면을 새로고침해주세요.",
      };
    case "network":
      return {
        ...wrong,
        title: "연결이 끊겼어요",
        detail: "인터넷 연결을 확인하고 다시 해보세요.",
      };
    case "silent":
      // 결과도 에러도 없이 끝난 경우. abort 했거나 권한 창이 떠 있는 채로
      // 시간이 다 됐다. 사용자에게는 "못 알아들었다" 로 보이는 것이 맞다 -
      // 내부 사정을 설명해도 할 수 있는 일이 같다.
      return {
        ...wrong,
        title: "잘 못 알아들었어요",
        detail: "마이크 가까이에서 조금 더 또박또박 말해보세요.",
      };
  }

  // 여기부터는 글자를 받아 서버까지 간 경우다.
  if (!result) {
    return {
      ...wrong,
      title: "채점하지 못했어요",
      detail: "잠시 후 다시 해보세요.",
    };
  }

  if (result.ok) {
    return {
      bg: "var(--correct-soft)",
      fg: "var(--correct-deep)",
      title: "잘 읽었어요",
    };
  }

  if (result.reason === "not_heard") {
    return {
      ...wrong,
      title: "소리가 안 들렸어요",
      detail: "마이크 가까이에서 다시 해보세요.",
    };
  }

  // 다르게 들린 경우. 들린 것을 보여주고, 후보 안에 정답이 있었으면
  // 그것도 함께 묻는다.
  //
  // 두 문구를 가르는 이유: "혹시 cache 를 말하셨나요" 는 "인식이 애매했구나"
  // 를, 그냥 "cash 로 들렸어요" 는 "내가 다르게 읽었구나" 를 알린다.
  // 사용자가 다음에 할 행동이 달라진다.
  return {
    ...wrong,
    title: "다시 해볼까요",
    detail: result.near
      ? `혹시 ${result.near} 를 말하려던 것이었나요? 이렇게 들렸어요.`
      : "이렇게 들렸어요.",
    heard: heardRaw[0],
  };
}
