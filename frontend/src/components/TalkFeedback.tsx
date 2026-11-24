"use client";

import type { TalkResult } from "@/lib/api/talk";
import type { ListenOutcome } from "@/lib/speech";

/**
 * 마이크가 막혔을 때 다시 켜는 길. 결과 안내, 막힌 뒤 새 문장에서 보이는 한 줄
 * 안내(TalkBoard), 켜기 전 카드(MicGate), 마이크 확인(MicCheck)이 같이 쓴다 -
 * 따로 적으면 한쪽만 고쳐진다.
 *
 * 앱(TWA)에는 주소창이 없어서 주소창 자물쇠로 안내하면 따라갈 수 없다. 마이크
 * 권한은 앱이 아니라 크롬이 쥐고 있고, 막히는 자리가 둘이다.
 * - 이 사이트의 마이크(크롬 권한 창의 "허용 안함"): 폰 설정의 DeVoca 앱 정보에 있는
 *   앱 설정 링크가 크롬의 이 사이트 설정을 바로 연다. 거기서 마이크를 켠다.
 * - 크롬 앱의 마이크(안드로이드 권한 창의 "허용 안함"): 같은 설정 화면 맨 위에 경고와
 *   "Android 설정" 링크가 뜨고, 누르면 크롬 앱 정보로 가서 권한 → 마이크를 허용한다.
 * 2026-11-25 에 Android 17 에뮬레이터(한국어)로 두 경우를 거절하고 이 길로 되살려
 * 확인했다. 삼성 인터넷이 앱을 여는 경우는 확인하지 못했다.
 *
 * 앱 설정 링크의 이름은 폰마다 다르다. 안드로이드 기본 설정은 "앱 추가 설정",
 * 갤럭시는 "<앱 이름>에서 상세설정" 이다. 갤럭시 이름은 안드로이드 14~17 용 삼성 설정 앱
 * (com.android.settings)의 문자열 app_settings_link 에서 읽었다. 안드로이드 15 용부터
 * "%s에서 상세설정" 이고 %s 에 앱 이름(twa-manifest.json 의 name)이 들어간다. 안드로이드
 * 14 용은 "앱 알림 상세설정" 이라 안내에 넣지 않았다. 13 이전 용은 보지 않았다.
 *
 * 다음에 할 일(새로고침 등)은 넣지 않는다. 자리마다 누를 버튼이 달라서 각자 붙인다.
 */
export const MIC_UNBLOCK_STEPS =
  "폰 설정에서 DeVoca 앱 정보를 열고 'DeVoca에서 상세설정'(폰에 따라 '앱 추가 설정')을 눌러 마이크를 켜주세요. 그 설정 화면 맨 위에 'Android 설정' 안내가 보이면 눌러서 크롬의 마이크도 허용해주세요.";

/**
 * 막힌 뒤 주 버튼이 "새로고침" 인 자리(MicGate 의 거절 카드, TalkBoard, 결과 안내)가
 * 쓴다. 앱에는 주소창의 새로고침 버튼이 없으므로 화면의 그 버튼을 가리킨다.
 * (화면을 아래로 당겨도 새로고침된다. 2026-11-25 에뮬레이터 앱에서 확인)
 */
export const MIC_BLOCKED_HELP = `${MIC_UNBLOCK_STEPS} 그런 다음 돌아와서 '새로고침'을 눌러주세요.`;

/**
 * 한 번 읽은 결과.
 *
 * "정답/오답" 이라고 말하지 않는다. 채점이 글자 비교라 판정이 흐릿하다.
 * 제대로 읽었는데 인식기가 다르게 적어서 실패하는 경우가 있다. 흐릿한
 * 판정을 단정해서 말하면 사용자가 자기 발음을 의심하게 되고, 그게 이 기능이
 * 줄이려던 공포를 오히려 키운다.
 *
 * 실패를 네 갈래로 나눈다. 하나로 뭉치면 무엇을 고쳐야 할지 모른다.
 *
 *   소리가 안 들림    마이크·음소거를 본다
 *   못 알아들음       더 또박또박 말한다
 *   다르게 들림       무엇으로 들렸는지 보고 그 부분을 고친다
 *   통과              다음으로 간다
 *
 * 세 번째에서는 들린 것을 그대로 보여주는 것이 핵심이다. 안 보여주면
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
    case "not-started":
      // 마이크가 열린 신호(audiostart)조차 없었다. 대개 다시 읽어도 같지만
      // "같습니다" 로 단정하지 않는다 - 처음 한 번은 브라우저가 권한 창을
      // 띄운 채라 신호가 늦은 것일 수 있고, 그때는 다시 읽으면 된다.
      return {
        ...wrong,
        title: "인식을 시작하지 못했어요",
        detail:
          "한 번 더 읽어보고, 그래도 같으면 화면을 아래로 당겨 새로고침해주세요. 다른 앱이 마이크를 쓰고 있으면 닫아주세요. 크롬에서만 동작합니다.",
      };
    case "no-sound":
      // 마이크는 열렸는데 말을 한 번도 못 잡았다. 원인을 단정하지 않는다.
      // 크롬은 소리 크기가 아니라 음성 구간 검출로 신호를 보내서, 장치가
      // 엉뚱한 것인 경우와 너무 작게 말한 경우를 가를 수 없다(speech.ts 의
      // onsoundstart 주석). 기계 문제라고만 하면 작게 말한 사람이 설정을
      // 뒤지고, 발음 문제라고만 하면 장치가 틀린 사람이 계속 다시 읽는다.
      // 먼저 할 수 있는 쉬운 것을 말하고, 가르는 일은 아래 MicCheck 에 맡긴다.
      return {
        ...wrong,
        title: "말소리를 못 들었어요",
        detail:
          "마이크에 조금 더 가까이 대고 또렷하게 다시 읽어보세요. 그래도 같으면 아래 '마이크 소리 확인'으로 소리가 들어오는지 봐주세요.",
      };
    case "no-speech":
      return {
        ...wrong,
        title: "말로 안 들렸어요",
        detail:
          "소리는 들어왔는데 말로 인식되지 않았습니다. 조금 더 또렷하게 다시 읽어보세요.",
      };
    case "no-mic":
      return {
        ...wrong,
        title: "마이크를 열지 못했어요",
        detail:
          "다른 앱이 마이크를 쓰고 있을 수 있습니다. 그 앱을 닫고 다시 해보세요.",
      };
    case "denied":
      return {
        ...wrong,
        title: "마이크가 막혔어요",
        detail: MIC_BLOCKED_HELP,
      };
    case "network":
      return {
        ...wrong,
        title: "연결이 끊겼어요",
        detail: "인터넷 연결을 확인하고 다시 해보세요.",
      };
    case "silent":
    // cancelled 는 TalkBoard 가 여기까지 안 보낸다("그만" 은 안내 없이 읽기
    // 전으로 돌린다). 타입상 갈래가 있어야 해서 같은 자리에 둔다.
    case "cancelled":
      // 소리까지 들어왔는데 결과도 에러도 없이 끝난 경우. 사용자에게는
      // "못 알아들었다" 로 보이는 것이 맞다 - 내부 사정을 설명해도 할 수
      // 있는 일이 같다.
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
