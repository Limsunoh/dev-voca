"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { MicCheck } from "@/components/MicCheck";
import { MicGate } from "@/components/MicGate";
import { MIC_BLOCKED_HELP, TalkFeedback } from "@/components/TalkFeedback";
import { TalkPromptCard } from "@/components/TalkPrompt";
import type { TalkKind, TalkPrompt, TalkResult } from "@/lib/api/talk";
import type { TalkLevel, TalkScene } from "@/lib/routes";
import {
  listenOnce,
  readMicState,
  type ListenOutcome,
  type ListenStage,
  type MicState,
} from "@/lib/speech";

/**
 * 소리내어 읽기 한 판.
 *
 * 흐름이 전부 클라이언트 상태다. 서버에 남는 진행이 없다 - 점수를 안 매기고
 * 순위표에도 안 올리므로 이어서 볼 것이 없다. 판정이 흐릿한 기능이라
 * 점수부터 붙이면 억울한 실패가 기록으로 남는다.
 *
 * 화면이 지나는 자리는 넷이다.
 *
 *   gate     마이크를 켜기 전. 왜 필요한지 먼저 말한다
 *   ready    읽을 것이 떠 있고 누르기를 기다린다
 *   listening 듣는 중
 *   done     결과가 떠 있다
 */

type Phase = "gate" | "ready" | "listening" | "done";

/**
 * 듣는 동안 보여줄 말.
 *
 * **마이크가 열렸는지를 말해준다.** 이게 없으면 사용자는 소리가 들어가는지
 * 모른 채 8초를 말하고, 실패해도 자기 발음을 탓한다. 실제로 그렇게 됐다 -
 * 크롬에서 인식기가 시작조차 안 했는데 화면은 "듣고 있어요" 였다.
 */
const STAGE_LABEL: Record<ListenStage, string> = {
  starting: "마이크를 여는 중이에요",
  open: "말씀하세요",
  sound: "소리가 들어오고 있어요",
  speech: "듣고 있어요",
};

/**
 * 최근에 낸 것을 몇 개까지 기억할까.
 *
 * 크게 잡을수록 안 겹치지만 풀이 그만큼 좁아져 "다 봤습니다" 가 빨라진다.
 *
 * **통보다 클 수 있다.** 상황 탭이 생기면서 난이도 x 상황 칸이 2개(인사·
 * 어려움)까지 작아졌다. 15칸 중 9칸이 12개 이하라, 그 칸에서는 한 바퀴
 * 돌면 뺄 목록이 통 전체를 덮는다. 그때 목록을 줄이는 일은 loadPrompt 의
 * 404 처리가 한다 - 이 값을 칸마다 맞추면 큰 칸에서 같은 것이 너무 자주
 * 나온다.
 *
 * 근거가 바뀐 것이 두 번째다. 처음에는 "표현이 60개", 난이도 필터 뒤에는
 * "가장 작은 통(어려움 23개)보다 작게" 였다.
 */
const RECENT_KEEP = 12;

/**
 * 이번 방문에서 "시작하기" 를 한 번이라도 눌렀는지.
 *
 * 갈래·난이도·상황 탭을 바꾸면 페이지가 이 컴포넌트를 key 로 통째로 새로 만든다
 * (app/talk/page.tsx - 옛 문제와 뺄 목록을 비우려는 것이다). 그러면 상태가
 * 처음으로 돌아가 소개 화면이 다시 뜨고, 방금 시작한 사람이 탭 하나 바꿀
 * 때마다 "시작하기" 를 또 눌러야 했다.
 *
 * 컴포넌트 상태가 아니라 모듈 변수에 두는 이유가 그것이다 - 새로 만들어져도
 * 이 값은 남는다. 새로고침하면 모듈이 다시 읽혀 사라지므로, 기억하는 범위는
 * "앱 안에서 이동하는 동안" 이다. 저장소에 남기지 않는 것은 일부러다. 소개
 * 화면에 녹음이 어디로 가는지 안내가 있어서, 새로 들어온 방문에는 한 번은
 * 보여주는 편이 맞다.
 */
let startedThisVisit = false;

/**
 * 이번 방문에서 마이크가 막혔는지(결과 "denied"). 막히면 주 버튼이
 * "새로고침" 이 된다.
 *
 * startedThisVisit 과 같은 이유로 모듈 변수다 - 갈래·난이도·상황 탭을 바꾸면
 * 이 컴포넌트가 새로 만들어지는데, 그때 잊으면 주 버튼이 "읽기" 로 돌아가
 * 누르고 또 막힌다. 권한은 새로고침해야 풀리고, 새로고침하면 이 값도
 * 사라진다.
 */
let micBlockedThisVisit = false;

/**
 * 소개 화면을 건너뛰고 곧장 이어가도 되나.
 *
 * "prompt" 도 넣는다. 사파리는 한 번 허락해도 사이트 설정에 "허용" 으로
 * 고정하지 않으면 권한 조회가 "prompt" 로 답할 수 있어서, granted 만 보면
 * 아이폰에서는 안 고쳐질 수 있다. 소개 안내는 이번 방문에 이미 읽었다.
 *
 * 대가: 권한이 정말 "prompt" 로 돌아갔으면 권한 창을 인식기가 띄우게 되고,
 * 창이 떠 있는 동안 시작 감시가 먼저 끊어 "인식을 시작하지 못했어요" 가
 * 한 번 뜬다(TalkFeedback 이 그 경우를 안내한다). 거절·마이크 없음 같은
 * 나머지는 소개 화면이 맞는 안내를 해야 하므로 넣지 않는다.
 */
function canResume(mic: MicState | null): boolean {
  return startedThisVisit && (mic === "granted" || mic === "prompt");
}

export function TalkBoard({
  kind,
  level,
  scene,
}: {
  kind: TalkKind;
  /** 고른 난이도. 0 이면 전체에서 낸다. */
  level: TalkLevel;
  /** 고른 상황. 빈 문자열이면 전체에서 낸다. */
  scene: TalkScene;
}) {
  const [mic, setMic] = useState<MicState | null>(null);
  const [phase, setPhase] = useState<Phase>("gate");
  const [prompt, setPrompt] = useState<TalkPrompt | null>(null);
  const [result, setResult] = useState<TalkResult | null>(null);
  const [outcome, setOutcome] = useState<ListenOutcome | null>(null);
  /**
   * 듣기가 어디까지 갔나. **말하는 도중에** 보여주려고 상태로 둔다.
   *
   * 예전에는 "듣고 있어요" 한 줄만 떴다. 그러면 마이크가 안 열렸는지,
   * 열렸는데 소리가 안 들어오는지, 잘 들어오는지를 구분할 수가 없다 -
   * 8초를 말한 뒤에야 실패 문구를 본다.
   */
  const [stage, setStage] = useState<ListenStage>("starting");
  const [heardRaw, setHeardRaw] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [errorSeq, setErrorSeq] = useState(0);
  const [busy, setBusy] = useState(false);
  // 결과 한 번만 보고 정하지 않는 이유: "다음" 으로 새 문장을 받는 순간
  // 주 버튼이 다시 "읽기" 로 돌아가고 누르면 또 막힌다. 값은 모듈 변수
  // (micBlockedThisVisit)에 두고, 화면을 다시 그리려고 상태로도 든다.
  const [micBlocked, setMicBlocked] = useState(micBlockedThisVisit);

  // 듣기를 끊는 함수. 화면을 떠나거나 "그만" 을 누를 때 부른다.
  // 안 끊으면 인식기가 살아남아 다음 판에 옛 결과가 끼어든다.
  // 방금 낸 것들. 서버에 빼달라고 넘긴다.
  const recentRef = useRef<number[]>([]);
  // 몇 개까지 뺄까. 처음엔 RECENT_KEEP 이고, 칸이 그보다 작다는 것을 알게
  // 되면(아래 404 처리) 칸 크기 - 1 로 줄어든다. 탭을 바꾸면 이 컴포넌트가
  // 새로 만들어지므로 칸마다 처음부터 다시 잰다.
  const keepRef = useRef(RECENT_KEEP);
  const stopRef = useRef<(() => void) | null>(null);

  // 마이크 상태를 먼저 읽는다. **권한 창은 안 뜬다.**
  useEffect(() => {
    let alive = true;
    readMicState().then((state) => {
      if (alive) setMic(state);
    });
    return () => {
      alive = false;
    };
  }, []);

  // 화면을 떠날 때 듣기를 끊는다.
  useEffect(() => {
    return () => stopRef.current?.();
  }, []);

  const loadPrompt = useCallback(async () => {
    setBusy(true);
    // 오류는 받은 뒤에 지운다. 먼저 지우면 오류에 매달린 "다시 불러오기"
    // 버튼이 누르는 순간 사라져 포커스가 날아간다.
    setResult(null);
    setOutcome(null);
    setHeardRaw([]);
    try {
      const res = await fetch("/api/talk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "start",
          kind,
          // 0 은 안 보낸다. 서버가 없으면 전체에서 낸다.
          ...(level ? { level } : {}),
          ...(scene ? { scene } : {}),
          // 방금 낸 것들을 빼달라고 한다. 안 보내면 무작위로 다시 뽑아서
          // 같은 것이 연달아 나온다. 난이도를 고르면 뽑는 통이 더 좁아져
          // 체감이 커진다. 문제풀기가 같은 방식을 쓴다(QuizBoard).
          exclude: recentRef.current,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        // 404 는 "낼 것이 없다" 는 뜻이다(다 봤거나 아직 데이터가 없다).
        // 실패로 다루면 사용자가 다시 눌러보게 되는데 결과가 같다.
        // 404 일 때 서버가 준 문구를 그대로 쓴다. 난이도를 골라서 빈
        // 것인지 통째로 빈 것인지를 서버만 알고, 사용자가 할 일이 다르다
        // (난이도를 바꾼다 / 나중에 온다).
        //
        // **작은 칸에서는 뺄 목록 때문에 빈 것이다.** 인사·어려움(2개)은
        // 두 번 만에 뺄 목록이 칸 전체를 덮는다. 목록을 그대로 두면 "다음"
        // 을 몇 번 눌러도 같은 요청이라 같은 404 가 나고, 탭을 바꾸거나
        // 새로고침하기 전에는 못 빠져나온다.
        //
        // 이때 뺄 목록의 길이가 곧 칸 크기다. 그래서 404 를 한 번 보여준
        // 뒤 이후로는 "칸 크기 - 1" 개만 뺀다 - 다음 "다음" 부터 그 칸을
        // 처음부터 다시 돌고, 방금 본 것은 곧바로 또 나오지 않는다(칸에
        // 하나뿐이면 달리 낼 것이 없어 그것이 계속 나온다). 목록만
        // 한 번 비우고 길이는 그대로 두면, 2개짜리 칸에서 한 바퀴 돌 때마다
        // 다시 차서 "다 봤습니다" 가 한 번 걸러 한 번씩 뜬다(실측).
        if (res.status === 404 && recentRef.current.length > 0) {
          keepRef.current = recentRef.current.length - 1;
          recentRef.current = recentRef.current.slice(0, keepRef.current);
        }
        setError(
          res.status === 404
            ? (data?.detail ??
              "지금 낼 것이 없습니다. 다른 갈래를 보거나 나중에 다시 와주세요.")
            : (data?.detail ?? "불러오지 못했습니다."),
        );
        setErrorSeq((n) => n + 1);
        return;
      }
      const next = data as TalkPrompt;
      // 방금 낸 것을 기억한다. 최근 것만 들고 있는다 - 다 모으면 뺄 것이
      // 풀 전체가 되어 "낼 것이 없습니다" 가 뜬다.
      recentRef.current = [next.id, ...recentRef.current].slice(
        0,
        keepRef.current,
      );
      setError(null);
      setPrompt(next);
      setPhase("ready");
    } catch {
      setError("서버에 연결할 수 없습니다.");
      setErrorSeq((n) => n + 1);
    } finally {
      setBusy(false);
    }
  }, [kind, level, scene]);

  // 갈래·난이도·상황이 바뀌어도 여기서 다시 받지 않는다. 페이지가
  // key={`${kind}-${level}-${scene}`} 로 이 컴포넌트를 통째로 새로 만들기 때문이다
  // (app/talk/page.tsx) - 상태가 처음부터 다시 시작하므로 옛 단어가 남을
  // 자리가 없고, 이미 낸 것을 빼는 목록도 같이 비워진다.
  //
  // 대신 이번 방문에 이미 시작했으면 소개 화면을 건너뛰고 곧장 받는다
  // (canResume). 소개 화면을 가리는 것은 아래 렌더가 한다 - 여기서
  // phase 를 바꾸면 효과가 그린 뒤에 돌아 소개 화면이 한 프레임 번쩍인다.
  // ref 는 allow() 가 마이크 상태를 바꿀 때 이 효과가 같은 것을 한 번 더
  // 받지 않게 막는다(allow 가 먼저 세운다).
  const resumedRef = useRef(false);
  useEffect(() => {
    if (!canResume(mic) || resumedRef.current) return;
    resumedRef.current = true;
    void loadPrompt();
  }, [mic, loadPrompt]);

  async function allow() {
    setBusy(true);
    try {
      // 여기서 처음으로 권한 창이 뜬다. 사용자가 왜 필요한지 읽고 누른 뒤다.
      //
      // 인식기를 바로 시작하지 않고 getUserMedia 로 묻는 이유: 인식기는
      // 권한 창이 떠 있는 동안 아무 이벤트도 안 줘서, 사용자가 창을 무시하면
      // 화면이 멈춘 것처럼 보인다. 이쪽은 약속이 거절되면 곧바로 알려준다.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // 곧바로 끈다. 여기서는 권한만 받으면 되고, 실제 듣기는 인식기가 한다.
      // 안 끄면 탭에 녹음 표시가 계속 남아서 듣고 있는 것처럼 보인다.
      stream.getTracks().forEach((track) => track.stop());
      // 위 효과가 같은 문제를 한 번 더 받지 않게 먼저 표시한다.
      resumedRef.current = true;
      startedThisVisit = true;
      setMic("granted");
      // 먼저 넘어간다. 소개 화면에 머문 채 받다가 실패하면 오류 문구가
      // 그려질 자리가 없다 - 오류는 아래 읽기 화면에만 있다.
      setPhase("ready");
      await loadPrompt();
    } catch {
      // 거절했거나 마이크를 못 열었다. 상태를 다시 읽어 맞는 안내를 그린다.
      setMic(await readMicState());
    } finally {
      setBusy(false);
    }
  }

  function listen() {
    if (!prompt) return;
    // 건너뛰기·다음이 실패해 떠 있던 오류를 지운다. 안 지우면 새 결과
    // 옆에 지난 오류가 같이 남는다.
    setError(null);
    setPhase("listening");
    setResult(null);
    setOutcome(null);
    setHeardRaw([]);
    setStage("starting");

    stopRef.current = listenOnce(async (heardOutcome) => {
      stopRef.current = null;

      // "그만" 을 눌렀다. 실패가 아니므로 안내를 띄우지 않고 읽기 전으로 돌린다.
      if (heardOutcome.type === "cancelled") {
        setPhase("ready");
        return;
      }

      setOutcome(heardOutcome);
      if (heardOutcome.type === "denied") {
        micBlockedThisVisit = true;
        setMicBlocked(true);
      }

      if (heardOutcome.type !== "heard") {
        // 글자를 못 받았으면 서버에 갈 것이 없다.
        setPhase("done");
        return;
      }

      setHeardRaw(heardOutcome.heard);
      try {
        const res = await fetch("/api/talk", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "grade",
            token: prompt.token,
            heard: heardOutcome.heard,
          }),
        });
        const data = await res.json();
        setResult(res.ok ? (data as TalkResult) : null);
      } catch {
        setResult(null);
      } finally {
        setPhase("done");
      }
    }, setStage);
  }

  function stopListening() {
    stopRef.current?.();
    stopRef.current = null;
  }

  // 마이크 상태를 아직 못 읽었다. 잠깐이라 자리만 잡아둔다 - 여기서 뭔가를
  // 그리면 곧바로 다른 것으로 바뀌어 깜빡인다.
  if (mic === null) return <div className="min-h-40" />;

  if (phase === "gate" && !canResume(mic)) {
    return <MicGate state={mic} onAllow={allow} pending={busy} />;
  }

  return (
    <div className="grid gap-4">
      {/* 통과했으면 강조하지 않는다. **ok 를 먼저 본다** - 통과인데
          wrong_at 이 null 로 오는 경우가 있고(낱말 경계만 어긋난 것을
          살릴 때), wrong_at 만 보면 그 둘을 못 가른다. */}
      {prompt && (
        <TalkPromptCard
          prompt={prompt}
          wrongAt={result && !result.ok ? result.wrong_at : null}
        />
      )}

      {/* 듣는 중을 알리는 자리.

          **aria-live 를 항상 렌더한다.** 내용과 함께 만들어지는 리전은
          읽히지 않는다(QuizBoard 가 같은 이유로 그렇게 한다).

          움직임만으로 알리지 않는다. 감소 모션에서는 반복 애니메이션이
          멈추는 게 아니라 0.01ms 로 무한 반복해서 사실상 안 보인다
          (globals.css 의 감소 모션 주석). 그래서 글자로도 말한다. */}
      <div aria-live="polite" className="min-h-6 text-center">
        {/* 문제를 받는 동안. 첫 문제는 카드가 없어 잠긴 버튼만 보이고,
            건너뛰기·다음은 옛 문장이 그대로 보여서 눌렸는지 모른다. */}
        {busy && (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            불러오는 중이에요
          </p>
        )}
        {phase === "listening" && (
          <p
            className="text-sm"
            style={{ color: "var(--coral-deep)", fontWeight: "var(--weight-black)" }}
          >
            {STAGE_LABEL[stage]}
          </p>
        )}
      </div>

      {phase === "done" && outcome && (
        <TalkFeedback outcome={outcome} result={result} heardRaw={heardRaw} />
      )}

      {/* 막힌 뒤 결과 안내가 안 보이는 동안 - 새 문장을 받는 중이거나 받은
          뒤, 받기에 실패한 뒤 - 주 버튼이 왜 "새로고침" 인지 한 줄로 알린다.
          결과 안내가 보일 때는 그쪽이 같은 말을 하므로 빠진다. */}
      {micBlocked && !(phase === "done" && outcome) && (
        <p className="text-center text-sm" style={{ color: "var(--coral-deep)" }}>
          마이크가 막혀 있어요. {MIC_BLOCKED_HELP}
        </p>
      )}

      {/* 소리가 안 들어왔을 때만 띄운다.
          평소에는 자리만 차지하고, 정작 필요한 순간에는 그 자리에 있다.
          듣는 중에는 안 띄운다 - 같은 마이크를 둘이 동시에 열면 한쪽이
          소리를 못 받는 기기가 있어서, 진단하려다 대상을 망가뜨린다. */}
      {phase === "done" && outcome?.type === "no-sound" && <MicCheck />}

      {error && (
        <p
          // 실패할 때마다 새 요소로 붙인다. 같은 문구로 또 실패하면 그대로
          // 남아 있어 스크린리더가 다시 안 읽는다.
          key={errorSeq}
          role="alert"
          className="rounded-[var(--radius-xl)] p-3 text-sm"
          style={{ background: "var(--wrong-soft)", color: "var(--coral-deep)" }}
        >
          {error}
        </p>
      )}

      <div className="grid gap-2 sm:flex sm:justify-center">
        {/* 읽을 것을 못 받았으면(error && !prompt) 읽기를 아예 빼고 아래
            "다시 불러오기" 만 남긴다. 잠긴 코랄이 옆에 있으면 누를 수 없는
            쪽이 먼저 눈에 든다. 마이크가 막혔으면 "새로고침" 은 남긴다 -
            문장을 받아 와도 새로고침 전에는 읽을 수 없다. */}
        {phase === "listening" ? (
          <button
            type="button"
            onClick={stopListening}
            className="dv-btn rounded-[var(--radius-pill)] px-8 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            style={
              {
                minHeight: "var(--hit-min)",
                background: "var(--paper)",
                color: "var(--foreground)",
                border: 0,
                "--lift": "var(--lift-button-paper)",
                fontWeight: "var(--weight-bold)",
              } as React.CSSProperties
            }
          >
            그만
          </button>
        ) : error && !prompt && !micBlocked ? null : (
          <button
            type="button"
            // 마이크가 막혔으면(micBlocked) 다시 읽어도 또 막힌다. 안내가
            // "허용으로 바꾸고 새로고침" 이라 주 버튼도 같은 말을 한다.
            onClick={micBlocked ? () => window.location.reload() : listen}
            disabled={!micBlocked && (busy || !prompt)}
            // 이 화면의 유일한 코랄. 주된 동작이 하나여야 무엇을 눌러야
            // 할지 한눈에 보인다.
            className="dv-btn rounded-[var(--radius-pill)] px-8 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60"
            style={
              {
                minHeight: "var(--hit-min)",
                background: "var(--coral)",
                color: "var(--text-on-color)",
                border: 0,
                "--lift": "var(--lift-button)",
                fontWeight: "var(--weight-black)",
                letterSpacing: "var(--tracking-tight)",
              } as React.CSSProperties
            }
          >
            {micBlocked ? "새로고침" : phase === "done" ? "다시 읽기" : "읽기"}
          </button>
        )}

        {/* 다음 것을 받는 버튼. 자리에 따라 이름만 바뀐다.
            - 읽기 전: "건너뛰기". 없으면 한 번 읽고 실패해야만 넘어갈 수
              있어서, 모르는 문장이 나오면 억지로 틀려야 했다
            - 결과 뒤: "다음"
            - 못 받았으면(prompt 없음): "다시 불러오기". 읽기는 읽을 것이
              없어 잠겨 있으니, 이게 없으면 누를 것이 하나도 없다 */}
        {(phase === "done" || (phase === "ready" && prompt) || (error && !prompt)) && (
          <button
            type="button"
            // disabled 가 아니라 aria-disabled 다. disabled 로 바뀌는 순간
            // 브라우저가 포커스를 빼서, 키보드로 누른 사람이 제자리를 잃는다.
            onClick={() => {
              if (!busy) void loadPrompt();
            }}
            aria-disabled={busy}
            className="dv-btn rounded-[var(--radius-pill)] px-8 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus aria-disabled:opacity-60"
            style={
              {
                minHeight: "var(--hit-min)",
                background: "var(--paper)",
                color: "var(--foreground)",
                border: 0,
                "--lift": "var(--lift-button-paper)",
                fontWeight: "var(--weight-bold)",
              } as React.CSSProperties
            }
          >
            {!prompt ? "다시 불러오기" : phase === "ready" ? "건너뛰기" : "다음"}
          </button>
        )}
      </div>
    </div>
  );
}
