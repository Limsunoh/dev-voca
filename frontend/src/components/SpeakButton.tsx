"use client";

import { useEffect, useRef, useState } from "react";

/** 음성 하나. SpeechSynthesisVoice 에서 고를 때 쓰는 칸만. */
type VoiceLike = { lang: string };

/**
 * 영어 음성을 고른다. 미국 영어를 먼저, 없으면 다른 영어(영국 등). 없으면 null.
 *
 * 화면의 발음기호가 미국식이라 미국 영어를 먼저 고른다. 언어 표기가 기기마다
 * "en-US", "en_US", "en-us" 로 다르게 와서 맞춰 비교한다.
 *
 * 고른 음성은 "영어가 있나" 와 어느 언어로 읽을지를 정하는 데만 쓴다. 음성
 * 자체는 넘기지 않는다 - 맥·iOS 목록에는 en-US 로 표기된 장난 음성(Albert,
 * Bad News 등)이 섞여 있어 목록의 첫 en-US 가 그것일 수 있다. 언어만 주면
 * 기기가 그 언어의 기본 음성으로 읽는다.
 */
export function pickEnglishVoice<T extends VoiceLike>(voices: readonly T[]): T | null {
  const lang = (voice: VoiceLike) => voice.lang.replace("_", "-").toLowerCase();
  return (
    voices.find((voice) => lang(voice) === "en-us") ??
    voices.find((voice) => lang(voice).startsWith("en")) ??
    null
  );
}

/** 배우는 사람이 따라 듣기 좋게 조금 천천히 읽는다. 1 이 보통 빠르기다. */
const RATE = 0.9;

/** 음성 목록을 이 시간 안에 못 받으면 음성이 없는 기기로 본다(밀리초). */
const VOICE_WAIT_MS = 1500;

/**
 * 영어 소리 듣기 버튼. 폰에 들어 있는 음성(브라우저의 speechSynthesis)으로 읽는다.
 *
 * 음성 파일을 미리 만들지 않는 이유(2026-11-12 사용자 결정): 단어와 문장이 곧
 * 15,000개 가까이 되는데, 파일로 하면 하나하나 만들고 들어 보며 검수해야 하고
 * 새 콘텐츠가 들어올 때마다 다시 만들어야 한다. 기기 음성은 새 단어도 바로
 * 읽는다. 대신 목소리가 기기마다 다르고, 약어(SQL 등)를 어떻게 읽을지는
 * 기기가 정한다.
 *
 * 영어 음성이 없는 기기에서는 버튼을 숨긴다. 일상영어(TalkPrompt)가 이 기능을
 * 주된 장치로 안 쓴 이유가 "그런 기기에서는 눌러도 아무 일 없는 버튼" 이었다.
 * 처음에는 그려 두고 없다고 확인될 때만 숨긴다 - 반대로 하면 음성이 있는 대부분의
 * 기기에서 버튼이 늦게 나타나며 아래 글이 밀린다.
 */
export function SpeakButton({
  text,
  label,
}: {
  /** 읽을 영어. 단어나 문장. */
  text: string;
  /** 화면 낭독기가 읽는 이름("발음 듣기" 등). 버튼에는 그림만 있다. */
  label: string;
}) {
  const [usable, setUsable] = useState(true);
  const [speaking, setSpeaking] = useState(false);
  // 지금 읽는 문장. cancel() 로 끊은 앞 문장의 끝 알림(크롬은 error
  // "interrupted")은 새 문장을 읽기 시작한 뒤에야 온다. 그 알림이 새 문장의
  // 갈색을 끄지 않도록 지금 것에서 온 알림만 받는다. 단 아무것도 읽고 있지
  // 않으면 끈다 - 일부 크롬은 cancel() 직후의 speak() 를 버려, 새 문장에서는
  // 끝 알림이 오지 않는다. 이것으로 풀리는 것은 브라우저가 새 문장을 대기열에서
  // 뺀 경우뿐이다. 음성 엔진이 버려 speaking 이 true 로 굳으면 다시 눌러야
  // 풀린다(색만 남고 소리는 멀쩡하다).
  const current = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    const synth = window.speechSynthesis;
    // 기능 자체가 없는 브라우저. 숨기기는 다음 틱에 한다 - 효과 안에서 바로
    // 상태를 바꾸면 lint(react-hooks/set-state-in-effect)에 걸린다.
    if (!synth) {
      const none = window.setTimeout(() => setUsable(false), 0);
      return () => window.clearTimeout(none);
    }

    // 크롬은 처음 부를 때 빈 목록을 주고, 다 읽으면 voiceschanged 를 낸다.
    const check = () => {
      const voices = synth.getVoices();
      if (voices.length > 0) setUsable(pickEnglishVoice(voices) !== null);
    };
    // iOS 15 이하 사파리는 speechSynthesis 에 addEventListener 가 없다. 그대로
    // 부르면 오류로 상세 화면 전체가 오류 화면이 된다. 그 기기는 목록을 바로
    // 주므로 아래 0ms 확인만으로 된다.
    synth.addEventListener?.("voiceschanged", check);
    const first = window.setTimeout(check, 0);
    // 끝내 목록이 안 오면 음성이 하나도 없는 기기다. 알림을 못 받는 옛
    // 사파리에서 그사이 영어 없는 목록이 왔을 수도 있어 영어 여부로 본다.
    const late = window.setTimeout(() => {
      if (pickEnglishVoice(synth.getVoices()) === null) setUsable(false);
    }, VOICE_WAIT_MS);

    return () => {
      synth.removeEventListener?.("voiceschanged", check);
      window.clearTimeout(first);
      window.clearTimeout(late);
      // 읽는 중에 다른 화면으로 가면 멈춘다. 안 멈추면 다음 화면에서도
      // 앞 단어를 계속 읽는다.
      synth.cancel();
    };
  }, []);

  if (!usable) return null;

  const speak = () => {
    const synth = window.speechSynthesis;
    const voice = pickEnglishVoice(synth.getVoices());
    if (!voice) {
      setUsable(false);
      return;
    }
    // 읽는 중에 다시 누르면 처음부터 다시 읽는다. 겹쳐 쌓이면 여러 번 들린다.
    synth.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = voice.lang.replace("_", "-");
    utterance.rate = RATE;
    const done = () => {
      if (current.current === utterance || !(synth.speaking || synth.pending)) {
        setSpeaking(false);
      }
    };
    utterance.onend = done;
    utterance.onerror = done;
    current.current = utterance;
    setSpeaking(true);
    synth.speak(utterance);
  };

  return (
    <button
      type="button"
      onClick={speak}
      aria-label={label}
      // 44px(--hit-floor) 동그라미. 히어로 카드(흰 종이) 안이라 두께 없이
      // 옅은 바탕만 깐다. 읽는 동안은 갈색으로 칠해 지금 소리가 나는 줄 안다.
      className="grid size-11 shrink-0 place-items-center rounded-full transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      style={{
        background: speaking ? "var(--brand)" : "var(--background-deep)",
        color: speaking ? "var(--text-on-color)" : "var(--foreground)",
      }}
    >
      <svg
        aria-hidden
        viewBox="0 0 24 24"
        width="20"
        height="20"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M11 5 6 9H3v6h3l5 4z" />
        <path d="M15.5 8.5a5 5 0 0 1 0 7" />
        <path d="M18.5 5.5a9 9 0 0 1 0 13" />
      </svg>
    </button>
  );
}
