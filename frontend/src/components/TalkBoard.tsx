"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { MicGate } from "@/components/MicGate";
import { TalkFeedback } from "@/components/TalkFeedback";
import { TalkPromptCard } from "@/components/TalkPrompt";
import type { TalkKind, TalkPrompt, TalkResult } from "@/lib/api/talk";
import { listenOnce, readMicState, type ListenOutcome, type MicState } from "@/lib/speech";

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

// 최근에 낸 것을 몇 개까지 기억할까. 표현이 60개라 12면 다섯 판에 한 번쯤
// 겹치는 정도이고, 이보다 크게 잡으면 풀이 좁아져 404 가 빨라진다.
const RECENT_KEEP = 12;


export function TalkBoard({ kind }: { kind: TalkKind }) {
  const [mic, setMic] = useState<MicState | null>(null);
  const [phase, setPhase] = useState<Phase>("gate");
  const [prompt, setPrompt] = useState<TalkPrompt | null>(null);
  const [result, setResult] = useState<TalkResult | null>(null);
  const [outcome, setOutcome] = useState<ListenOutcome | null>(null);
  const [heardRaw, setHeardRaw] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // 듣기를 끊는 함수. 화면을 떠나거나 "그만" 을 누를 때 부른다.
  // 안 끊으면 인식기가 살아남아 다음 판에 옛 결과가 끼어든다.
  // 방금 낸 것들. 서버에 빼달라고 넘긴다.
  const recentRef = useRef<number[]>([]);
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
    setError(null);
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
          // 방금 낸 것들을 빼달라고 한다. 안 보내면 무작위로 다시 뽑아서
          // 같은 것이 연달아 나온다 - 표현이 60개뿐이라 열 번 누르면
          // 절반쯤은 겹친다. 문제풀기가 같은 방식을 쓴다(QuizBoard).
          exclude: recentRef.current,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        // 404 는 "낼 것이 없다" 는 뜻이다(다 봤거나 아직 데이터가 없다).
        // 실패로 다루면 사용자가 다시 눌러보게 되는데 결과가 같다.
        setError(
          res.status === 404
            ? "지금 낼 것이 없습니다. 다른 갈래를 보거나 나중에 다시 와주세요."
            : (data?.detail ?? "불러오지 못했습니다."),
        );
        return;
      }
      const next = data as TalkPrompt;
      // 방금 낸 것을 기억한다. 최근 것만 들고 있는다 - 다 모으면 뺄 것이
      // 풀 전체가 되어 "낼 것이 없습니다" 가 뜬다.
      recentRef.current = [next.id, ...recentRef.current].slice(0, RECENT_KEEP);
      setPrompt(next);
      setPhase("ready");
    } catch {
      setError("서버에 연결할 수 없습니다.");
    } finally {
      setBusy(false);
    }
  }, [kind]);

  // 갈래가 바뀌어도 여기서 다시 받지 않는다. 페이지가 key={kind} 로 이
  // 컴포넌트를 통째로 새로 만들기 때문이다(app/talk/page.tsx) - 상태가
  // 처음부터 다시 시작하므로 옛 단어가 남을 자리가 없다.

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
      setMic("granted");
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
    setPhase("listening");
    setResult(null);
    setOutcome(null);
    setHeardRaw([]);

    stopRef.current = listenOnce(async (heardOutcome) => {
      stopRef.current = null;
      setOutcome(heardOutcome);

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
    });
  }

  function stopListening() {
    stopRef.current?.();
    stopRef.current = null;
  }

  // 마이크 상태를 아직 못 읽었다. 잠깐이라 자리만 잡아둔다 - 여기서 뭔가를
  // 그리면 곧바로 다른 것으로 바뀌어 깜빡인다.
  if (mic === null) return <div className="min-h-40" />;

  if (phase === "gate") {
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
        {phase === "listening" && (
          <p
            className="text-sm"
            style={{ color: "var(--coral-deep)", fontWeight: "var(--weight-black)" }}
          >
            듣고 있어요
          </p>
        )}
      </div>

      {phase === "done" && outcome && (
        <TalkFeedback outcome={outcome} result={result} heardRaw={heardRaw} />
      )}

      {error && (
        <p
          role="alert"
          className="rounded-[var(--radius-xl)] p-3 text-sm"
          style={{ background: "var(--wrong-soft)", color: "var(--coral-deep)" }}
        >
          {error}
        </p>
      )}

      <div className="grid gap-2 sm:flex sm:justify-center">
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
        ) : (
          <button
            type="button"
            onClick={listen}
            disabled={busy || !prompt}
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
            {phase === "done" ? "다시 읽기" : "읽기"}
          </button>
        )}

        {phase === "done" && (
          <button
            type="button"
            onClick={() => void loadPrompt()}
            disabled={busy}
            className="dv-btn rounded-[var(--radius-pill)] px-8 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60"
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
            다음
          </button>
        )}
      </div>
    </div>
  );
}
