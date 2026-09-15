"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * 마이크에 소리가 들어오는지 눈으로 보는 자리.
 *
 * ## 왜 필요한가
 *
 * 인식기가 "소리가 안 들어왔다" 고 말해도 **어디가 문제인지는 여전히 모른다.**
 * 크롬이 엉뚱한 장치를 잡고 있는 것과, 장치는 맞는데 윈도우 입력이 0인 것과,
 * 인식기만 소리를 못 받는 것이 전부 같은 결과로 보인다.
 *
 * 여기는 인식기를 안 쓴다. 마이크를 직접 열어 파형의 크기를 그대로 그린다.
 * 그래서 답이 셋으로 갈린다.
 *
 *     막대가 크게 움직인다 + 인식 실패  인식기 쪽 문제다
 *     막대가 조금만 움직인다            소리는 들어오는데 작다. 가까이서 말하면 된다
 *     막대가 안 움직인다                장치나 윈도우 설정 문제다
 *     여는 것부터 실패                  권한이나 장치가 없다
 *
 * 둘째 줄이 있어야 하는 이유: 인식기는 크롬에서 "작게 말함" 과 "소리 없음"
 * 을 같은 신호로 준다. 이 막대가 그 둘을 가르는 유일한 자리다.
 *
 * **장치 이름을 같이 보여주는 것이 핵심이다.** 크롬은 사이트마다 입력 장치를
 * 따로 기억해서, 새 마이크를 꽂아도 예전 장치를 계속 잡고 있는 경우가 흔하다.
 * 이름이 보이면 그 자리에서 알 수 있다.
 *
 * ## 인식기가 도는 동안에는 안 쓴다
 *
 * 같은 마이크를 둘이 동시에 열면 기기·드라이버에 따라 한쪽이 소리를 못 받는
 * 경우가 있다. 진단하려다 진단 대상을 망가뜨리는 셈이라, 이건 듣기와 따로
 * 눌러서 확인하는 버튼으로 둔다.
 */

type Phase = "idle" | "asking" | "running" | "failed";

/** 화면에 그릴 막대 칸 수. 촘촘할수록 작은 소리도 보인다. */
const BARS = 20;

export function MicCheck() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [level, setLevel] = useState(0);
  /** 지금까지 들어온 가장 큰 소리. 말하다 멈춰도 남아 있어야 판단이 된다. */
  const [peak, setPeak] = useState(0);
  const [device, setDevice] = useState("");
  const [error, setError] = useState("");

  /** 정리할 것들. 화면을 떠나거나 멈출 때 한 번에 닫는다. */
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const frameRef = useRef(0);
  /**
   * 여는 중에 끝났는지 가리는 표.
   *
   * **정리는 한 번만 도는데 여는 일은 그 뒤에도 끝난다.** 권한 창이 떠 있는
   * 동안 사용자가 "다시 읽기" 를 누르면 이 컴포넌트가 화면에서 빠지고,
   * 그때 streamRef 는 아직 비어 있어 정리가 아무것도 안 닫는다. 그러고 나서
   * getUserMedia 가 마이크를 건네주면 **그 마이크를 놓을 사람이 없다** -
   * 탭의 녹음 표시가 새로고침 전까지 남고, 그리기 반복도 영영 돈다.
   *
   * 더 나쁜 것은 그 상태가 바로 이 파일 머리말이 경계한 것이라는 점이다.
   * 마이크를 둘이 동시에 쥐면 인식기가 소리를 못 받는 기기가 있다 - 진단
   * 장치가 진단 대상을 망가뜨린다.
   *
   * await 를 지날 때마다 이 값을 다시 본다. 달라졌으면 방금 받은 것을
   * 그 자리에서 닫고 나간다.
   */
  const genRef = useRef(0);

  const stop = useCallback(() => {
    // 도는 중이거나 여는 중인 것을 전부 무효로 만든다.
    genRef.current += 1;
    cancelAnimationFrame(frameRef.current);
    frameRef.current = 0;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    // close() 는 약속을 돌려주는데 기다릴 것이 없다. 실패해도 할 일이 없다.
    contextRef.current?.close().catch(() => {});
    contextRef.current = null;
  }, []);

  // 화면을 떠날 때 마이크를 놓는다. 안 놓으면 탭에 녹음 표시가 계속 남는다.
  useEffect(() => stop, [stop]);

  async function start() {
    const gen = ++genRef.current;
    setPhase("asking");
    setError("");
    setPeak(0);
    setLevel(0);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (gen !== genRef.current) {
        // 여는 사이에 끝났다. 받은 것을 여기서 닫는다.
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;

      // 크롬이 실제로 고른 장치 이름. 권한을 받은 뒤에만 채워진다.
      setDevice(stream.getAudioTracks()[0]?.label ?? "");

      const context = new AudioContext();
      contextRef.current = context;
      // 사용자 제스처 없이 만들어지면 멈춘 채로 시작한다. 깨워야 값이 온다.
      if (context.state === "suspended") await context.resume();
      if (gen !== genRef.current) {
        // 깨우는 사이에 끝났다. 위 stop() 이 이 context 를 이미 닫았을
        // 수도 있고 아닐 수도 있어서(대입 순서), 여기서 한 번 더 닫는다.
        // 두 번 닫아도 안전하다.
        context.close().catch(() => {});
        stream.getTracks().forEach((track) => track.stop());
        return;
      }

      const analyser = context.createAnalyser();
      // 작게 잡는다. 크기만 볼 것이라 주파수 해상도가 필요 없고, 작을수록
      // 화면이 빨리 따라온다.
      analyser.fftSize = 512;
      context.createMediaStreamSource(stream).connect(analyser);

      const samples = new Uint8Array(analyser.fftSize);
      setPhase("running");

      const tick = () => {
        // 세대가 바뀌었으면 그린 뒤 멈추지 말고 여기서 끝낸다. stop() 이
        // cancelAnimationFrame 을 부르지만, 이미 예약된 한 프레임은 돈다.
        if (gen !== genRef.current) return;
        analyser.getByteTimeDomainData(samples);
        // 무음이 128이다. 거기서 얼마나 벗어났는지가 소리 크기다.
        let loudest = 0;
        for (const sample of samples) {
          loudest = Math.max(loudest, Math.abs(sample - 128));
        }
        const now = Math.min(1, loudest / 64);
        setLevel(now);
        setPeak((before) => Math.max(before, now));
        frameRef.current = requestAnimationFrame(tick);
      };
      frameRef.current = requestAnimationFrame(tick);
    } catch (err) {
      stop();
      setPhase("failed");
      setError(
        err instanceof Error && err.name === "NotAllowedError"
          ? "마이크가 막혀 있습니다. 주소창 왼쪽 아이콘에서 허용으로 바꿔주세요."
          : "마이크를 열지 못했습니다. 장치가 연결돼 있는지 봐주세요.",
      );
    }
  }

  function halt() {
    stop();
    setPhase("idle");
  }

  const lit = Math.round(level * BARS);
  /**
   * 들어온 적이 있는가. 0.08 은 조용한 방의 바닥 잡음보다 위다 - 더 낮게
   * 잡으면 아무 소리도 안 냈는데 "들어온다" 고 말한다.
   */
  const heard = peak > 0.08;

  return (
    <div
      className="rounded-[var(--radius-xl)] p-4"
      style={{ background: "var(--paper)" }}
    >
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        소리가 들어오는지 봅니다. 인식과는 따로 돕니다.
      </p>

      {phase === "running" && (
        <>
          {/* 막대. 소리 크기를 그대로 그린다. */}
          <div
            aria-hidden
            className="mt-3 flex gap-1"
            style={{ height: "1.5rem" }}
          >
            {Array.from({ length: BARS }, (_, i) => (
              <span
                key={i}
                className="flex-1 rounded-full"
                style={{
                  background:
                    i < lit ? "var(--correct-deep)" : "var(--border-hairline)",
                }}
              />
            ))}
          </div>

          {/* 막대는 눈으로만 읽힌다. 낭독기와 감소 모션을 위해 글자로도 말한다. */}
          <p aria-live="polite" className="mt-2 text-sm">
            {heard ? (
              <span style={{ color: "var(--correct-deep)" }}>
                소리가 들어오고 있습니다.
              </span>
            ) : (
              <span style={{ color: "var(--text-muted)" }}>
                마이크에 대고 말해보세요. 아직 소리가 없습니다.
              </span>
            )}
          </p>

          {device && (
            <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>
              지금 쓰는 장치: <strong>{device}</strong>
              {!heard && " — 이게 말하고 있는 마이크가 맞나요?"}
            </p>
          )}

          {/* **여기서 장치를 못 바꿔준다.** 음성 인식 API 에는 장치를
              지정하는 수단이 없다 - 브라우저 기본 장치를 그냥 따라간다.
              마이크를 직접 여는 이 확인 막대만 장치를 고를 수 있는데, 정작
              인식은 못 고르므로 여기서 고르게 하면 "확인은 되는데 읽기는
              안 되는" 더 나쁜 상태가 된다. 그래서 바꾸는 곳을 알려준다. */}
          {!heard && device && (
            <div className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
              <p style={{ color: "var(--foreground)", fontWeight: "var(--weight-black)" }}>
                다른 마이크로 바꾸려면
              </p>
              <ol className="mt-1 grid gap-1">
                <li>
                  1. 크롬 주소창에 <strong>chrome://settings/content/microphone</strong> 을
                  넣고, 맨 위 목록에서 쓰는 마이크를 고릅니다.
                </li>
                <li>
                  2. 거기에 안 보이면 윈도우 설정 · 시스템 · 소리 · 입력 에서
                  먼저 그 장치를 기본으로 바꿉니다.
                </li>
                <li>3. 이 화면을 새로고침하고 다시 해봅니다.</li>
              </ol>
              <p className="mt-2">
                앱에서는 못 바꿉니다. 음성 인식이 브라우저 기본 장치만 씁니다.
              </p>
            </div>
          )}
        </>
      )}

      {phase === "failed" && (
        <p role="alert" className="mt-2 text-sm" style={{ color: "var(--coral-deep)" }}>
          {error}
        </p>
      )}

      <button
        type="button"
        onClick={phase === "running" ? halt : start}
        disabled={phase === "asking"}
        className="dv-btn mt-3 rounded-[var(--radius-pill)] px-6 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        style={
          {
            minHeight: "var(--hit-min)",
            background: "var(--background)",
            color: "var(--foreground)",
            // dv-btn 은 두께를 이 변수로 받는다. 안 주면 쉬는 상태에서 납작하고
            // 누를 때만 4px 내려가 바닥 없이 뜬 버튼이 된다.
            "--lift": "var(--lift-button-paper)",
          } as React.CSSProperties
        }
      >
        {phase === "running" ? "그만 보기" : "마이크 소리 확인"}
      </button>
    </div>
  );
}
