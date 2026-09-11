"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Burst } from "@/components/Burst";
import { Reaction } from "@/components/Reaction";
import { ExitGuard } from "@/components/ExitGuard";
import { QuestionCard } from "@/components/QuestionCard";
import type {
  RoundAnswered,
  RoundQuestion,
  RoundResult,
  RoundStarted,
  RoundSummary,
} from "@/lib/api/rounds";
import { routes } from "@/lib/routes";

/**
 * 90초 한 판.
 *
 * 낱개 문제를 계속 내던 옛 화면과 다르다. 판이 서버에 있고, 점수와
 * 남은 시간도 서버가 정한다 - 클라이언트가 잰 시간을 보내면 0 을 보내
 * 항상 만점이 된다.
 *
 * 화면이 타이머를 그리긴 하지만 그건 **표시용**이다. 실제 마감은 서버가
 * 판 토큰 안의 시작 시각으로 판정한다. 그래서 화면 시계가 느려도 빨라도
 * 점수는 안 흔들린다.
 *
 * 백엔드를 직접 부르지 않고 같은 출처의 중계(/api/rounds)를 부른다.
 */

type Phase = "idle" | "playing" | "done";

/** 중계에 보낼 것. action 으로 세 동작이 갈린다. */
async function call<T>(body: Record<string, unknown>): Promise<T> {
  const res = await fetch("/api/rounds", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail ?? "요청이 실패했습니다.");
  }
  return res.json() as Promise<T>;
}

export function RoundBoard({ isGuest }: { isGuest: boolean }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [question, setQuestion] = useState<RoundQuestion | null>(null);
  const [result, setResult] = useState<RoundResult | null>(null);
  const [summary, setSummary] = useState<RoundSummary | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [left, setLeft] = useState(0);
  const [skipsLeft, setSkipsLeft] = useState(0);
  // 서버가 정한 한 판 길이. 막대 분모와 aria 값에 함께 쓴다.
  const [seconds, setSeconds] = useState(90);
  const [tally, setTally] = useState({
    answered: 0,
    correct: 0,
    score: 0,
    late: 0,
  });
  /** 방금 판정. 정답일 때 조각이 터진다. 카운터인 이유는 Burst 주석 참고. */
  const [burst, setBurst] = useState(0);
  /**
   * 걸어오는 사람. 맞히든 틀리든 오므로 burst 를 못 쓴다.
   *
   * 횟수와 판정을 같이 들고 있는 이유는 QuizBoard 와 같다 - 판정만 두면
   * 연속으로 같은 결과가 나왔을 때 두 번째부터 다시 안 뛴다.
   */
  const [reaction, setReaction] = useState({ fire: 0, correct: false });

  // 마감 시각(ms). 남은 시간을 매 초 다시 계산하는 근거다. setInterval 로
  // 1씩 빼면 탭이 백그라운드로 갔을 때 타이머가 멈춰 시간이 남아 보인다.
  const deadlineRef = useRef(0);
  /**
   * 채점 뒤 멈추는 시간(ms). 서버가 판을 열 때 내려준다.
   *
   * 여기에 숫자를 적어두지 않는 이유: 서버가 마감을 미루는 양과 달라지면
   * 그 차이가 문제마다 쌓인다. 스무 문제면 눈에 띄게 어긋난다.
   */
  const pauseRef = useRef(0);
  // 판이 끝났는데 타이머가 한 번 더 도는 것을 막는다.
  const closingRef = useRef(false);

  /**
   * 아래 셋이 **state 가 아니라 ref 인 이유.**
   *
   * 타이머 콜백과 클릭 핸들러는 자기가 만들어진 렌더의 값을 붙들고 있다.
   * 답을 보내는 중에 90초가 지나면, 타이머는 아직 옛 토큰을 들고 있어
   * 그것으로 판을 닫으려 한다 - 서버는 이미 지나간 순번이라 거절하고,
   * 90초를 다 푼 사람이 점수를 통째로 잃는다. 마감 직전에 답하는 것은
   * 예외가 아니라 이 판의 가장 흔한 끝맺음이다.
   *
   * 같은 이유로 이중 클릭도 state 로는 못 막는다. 두 클릭이 한 틱 안에
   * 들어오면 둘 다 busy=false 를 보고 둘 다 나간다.
   */
  const tokenRef = useRef("");
  const busyRef = useRef(false);
  const aliveRef = useRef(true);

  // 화면을 떠난 뒤 도착한 응답으로 상태를 건드리지 않는다. 떠난 화면의
  // send 가 이어서 finish 를 부르면 요청이 한 번 더 나간다.
  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  const finish = useCallback(async (roundToken: string) => {
    if (closingRef.current) return;
    closingRef.current = true;

    try {
      const done = await call<RoundSummary>({
        action: "finish",
        token: roundToken,
      });
      if (!aliveRef.current) return;
      setSummary(done);
      setPhase("done");
    } catch (err) {
      if (!aliveRef.current) return;
      // **다시 시도할 수 있게 열어둔다.** 서버의 끝내기는 여러 번 와도
      // 같은 결과라(session.finish 주석) 재시도가 안전하다. 닫아버리면
      // 한 번 실패한 판은 점수를 영영 못 남긴다.
      closingRef.current = false;
      setError(err instanceof Error ? err.message : "판을 닫지 못했습니다.");
      setPhase("done");
    }
  }, []);

  // 남은 시간. 마감 시각과의 차이로 구하므로 탭이 멈췄다 돌아와도 맞는다.
  useEffect(() => {
    if (phase !== "playing") return;

    const tick = () => {
      // **답이 오가는 동안은 숫자를 건드리지 않는다.** 채점이 끝나면
      // 연출 시간만큼 마감이 뒤로 밀리는데, 그 사이 다시 그리면 남은
      // 시간이 61 에서 62 로 **올라간다**. 90초 판에 "91" 이 뜨기도 한다.
      if (busyRef.current) return;

      const remain = Math.max(0, deadlineRef.current - Date.now());
      setLeft(remain);
      // **답이 오가는 중이면 미룬다.** 지금 닫으면 서버가 방금 태운
      // 순번 때문에 옛 토큰을 거절한다. send 가 끝나며 마감을 다시 본다.
      if (remain === 0 && !busyRef.current) finish(tokenRef.current);
    };

    tick();
    const id = setInterval(tick, 250);
    return () => clearInterval(id);
  }, [phase, finish]);

  const start = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    try {
      const started = await call<RoundStarted>({ action: "start" });
      if (!aliveRef.current) return;

      // 응답에 문제가 없으면 여기서 멈춘다.
      //
      // 그냥 진행하면 phase 만 playing 이 되고 PlayCard 는 question 이
      // null 이라 아무것도 안 그린다 - 문제도 보기도 타이머도 에러 문구도
      // 없이 나가기 버튼 하나만 뜬다. throw 를 안 했으니 error.tsx 도
      // 안 뜬다. 사용자는 왜 비었는지 모른 채 나갈 수밖에 없다.
      //
      // catch 는 네트워크 실패만 잡지 응답 모양은 안 본다. 서버가 배포
      // 중이거나 중계가 빈 응답을 흘리면 실제로 이 모양이 온다.
      if (!started.question || !started.token) {
        setError("판을 여는 응답이 올바르지 않습니다. 다시 시도해주세요.");
        return;
      }

      closingRef.current = false;
      deadlineRef.current = Date.now() + started.round_seconds * 1000;
      // 서버가 정한 값을 그대로 쓴다. 없으면 0 이라 예전처럼 안 멈춘다 -
      // 서버가 옛 버전이어도 판이 깨지지 않는다.
      pauseRef.current = started.reaction_pause_ms ?? 0;
      setSeconds(started.round_seconds);
      tokenRef.current = started.token;
      setQuestion(started.question);
      setSkipsLeft(started.max_skips);
      setTally({ answered: 0, correct: 0, score: 0, late: 0 });
      // 축포 카운터도 되돌린다. 판마다 0 에서 시작해야 다른 리셋들과
      // 규율이 맞는다.
      setBurst(0);
      // 걸어오는 사람도 같이 되돌린다. 안 되돌리면 "한 판 더" 를 눌렀을 때
      // fire 가 지난 판의 숫자로 남아, 첫 문제를 풀기도 전에 사람이 걸어와
      // 지난 판의 마지막 판정을 한 번 더 보여준다.
      setReaction({ fire: 0, correct: false });
      setResult(null);
      setSummary(null);
      setPhase("playing");
    } catch (err) {
      if (!aliveRef.current) return;
      setError(err instanceof Error ? err.message : "판을 열지 못했습니다.");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const send = async (choiceId: number | null, skip = false) => {
    // ref 로 막는다. state 로 보면 한 틱 안에 들어온 두 클릭이 둘 다
    // busy=false 를 읽고 둘 다 나가, 뒤엣것이 이미 태운 순번으로 거절된다.
    if (busyRef.current || !tokenRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");

    try {
      const answered = await call<RoundAnswered>({
        action: "answer",
        token: tokenRef.current,
        choice_id: choiceId,
        skip,
      });
      if (!aliveRef.current) return;

      tokenRef.current = answered.token;
      setResult(answered.result);
      setTally((prev) => ({
        // **넘긴 것도 센다.** 서버가 그렇게 집계하므로(session.finish),
        // 여기서 빼면 진행 중 "3/3" 이던 것이 결과에서 "5문제 중 3개"
        // 로 뛴다. 같은 판인데 분모가 달라 보인다.
        answered: prev.answered + 1,
        correct: prev.correct + (answered.result.correct ? 1 : 0),
        score: prev.score + answered.result.score,
        // 맞혔는데 시간이 지나 0 점이 된 것. 결과에서 "2개 맞혔는데 왜
        // 0점?" 을 설명하는 데 쓴다. 서버 요약(finish)에는 이 수가 없어서
        // 여기서 센다 - 채점 응답마다 in_time 이 오므로 셀 수 있다.
        late:
          prev.late +
          (answered.result.correct && !answered.result.in_time ? 1 : 0),
      }));
      if (answered.result.skipped) setSkipsLeft((n) => Math.max(0, n - 1));

      // 맞혔을 때 조각이 터진다. 넘긴 것은 제외한다 - 서버가 skipped 를
      // correct: false 로 주지만, 혹시 바뀌더라도 넘긴 문제에 축포가
      // 터지지 않게 여기서 한 번 더 막는다.
      if (answered.result.correct && !answered.result.skipped) {
        setBurst((n) => n + 1);
      }

      // 걸어오는 사람은 맞든 틀리든 온다. 넘긴 것만 뺀다 - 넘기기는 판정이
      // 아니라 "모르겠다" 라서 칭찬할 것도 나무랄 것도 없고, 넘길 때까지
      // 기다리게 하면 넘기는 의미가 없다.
      //
      // **서버도 넘긴 것은 보상하지 않는다**(session._deadline_ms). 여기서만
      // 빼면 화면은 안 멈추는데 마감은 밀려 판이 길어진다.
      const pausing = !answered.result.skipped;
      if (pausing) {
        setReaction((r) => ({ fire: r.fire + 1, correct: answered.result.correct }));
        // 서버가 미룬 만큼 이쪽 시계도 미룬다. 서버 시각을 그대로 받지
        // 않는 이유는 판을 열 때와 같다 - 두 기계의 시계가 어긋나면
        // 남은 시간이 튄다. 양쪽이 같은 값을 더하면 어긋날 일이 없다.
        deadlineRef.current += pauseRef.current;
      }

      if (answered.finished || !answered.question) {
        await finish(answered.token);
        return;
      }

      // 답하는 사이 마감이 지났으면 여기서 닫는다. 타이머는 진행 중이라
      // 넘겼고, 그 사이 토큰이 새로 왔으므로 이제 거절되지 않는다.
      if (Date.now() >= deadlineRef.current) {
        await finish(answered.token);
        return;
      }

      // 연출이 끝난 뒤에 다음 문제를 낸다. 바로 내면 걸어오는 사람 위로
      // 새 문제가 덮여서, 맞았는지 틀렸는지 볼 틈이 없다.
      //
      // 이 사이 busyRef 를 쥐고 있어(finally 에서만 푼다) 보기 버튼이
      // 안 먹는다. 연출 중에 답이 나가면 그 답의 시계가 이미 흐른 뒤다.
      if (pausing && pauseRef.current > 0) {
        await new Promise((r) => setTimeout(r, pauseRef.current));
        // 기다리는 사이 판을 나갔을 수 있다.
        if (!aliveRef.current) return;

        // **마감을 다시 본다.** 기다리기 전에 봤어도 그 사이 지났을 수
        // 있다. 안 보면 타이머가 0 인 채로 다음 문제가 떠서, 누르면
        // 닫으려는 요청과 답이 같은 토큰으로 겹쳐 나가 판이 통째로
        // 기록되지 않는다.
        if (Date.now() >= deadlineRef.current) {
          await finish(answered.token);
          return;
        }
      }

      setQuestion(answered.question);
    } catch (err) {
      if (!aliveRef.current) return;
      setError(err instanceof Error ? err.message : "채점하지 못했습니다.");

      // **여기서도 마감을 본다.** 답이 실패한 사이 90초가 끝났으면,
      // 그냥 두면 타이머가 갱신 안 된 옛 토큰으로 판을 닫으려 하고
      // 서버가 거절한다 - 다 푼 판이 통째로 기록되지 않는다.
      // 토큰은 실패했으므로 아직 안 태워졌고, 그래서 이걸로 닫을 수 있다.
      // busyRef 를 여기서 풀지 않는다. finish 를 기다리는 동안 풀어두면
      // 그 사이 보기 버튼이 다시 눌려 같은 토큰으로 답이 한 번 더 나간다.
      // 성공 경로도 busyRef 를 쥔 채 finish 를 부르고 finally 에서만 푼다.
      if (Date.now() >= deadlineRef.current) {
        await finish(tokenRef.current);
        return;
      }
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  if (phase === "idle") {
    return (
      // 세로 가운데. 시작 카드 하나뿐이라 위에 붙이면 아래가 통째로 빈다.
      // 판이 시작되면(아래 playing) 위에 붙는다 - 그때는 타이머가 화면
      // 맨 위에 있어야 한다.
      <div className="flex flex-1 flex-col justify-center">
        {/* 아직 판이 안 열렸다. 점수로 잃을 게 없으니 묻지 않고 나간다.
            대신 갈 곳을 여럿 둔다 - 여기는 고르는 자리다. */}
        <div className="mb-5 flex items-center justify-between gap-3">
          <ExitGuard to={routes.home} label="홈" />
          {/* 맨몸 글자 링크로 둔다. 옆의 나가기가 흰 알약이라, 여기까지
              알약이면 같은 무게의 버튼 둘이 나란히 서서 어느 것이 나가는
              길인지 안 보인다. */}
          <Link
            href={routes.board()}
            className="inline-flex min-h-11 items-center rounded-full px-2.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            style={{
              color: "var(--text-muted)",
              fontWeight: "var(--weight-bold)",
            }}
          >
            순위표
          </Link>
        </div>
        <StartCard onStart={start} busy={busy} error={error} />
      </div>
    );
  }

  if (phase === "done") {
    return (
      // 결과 카드도 하나뿐이라 가운데가 맞다.
      <div className="flex flex-1 flex-col justify-center">
        {/* 판이 끝났다. 점수는 이미 서버에 올라갔으니 경고할 것이 없다. */}
        <div className="mb-5 flex items-center gap-3">
          <ExitGuard to={routes.profile} label="내 기록" />
        </div>
        <RoundResultCard
          summary={summary}
          error={error}
          isGuest={isGuest}
          onAgain={start}
          busy={busy}
          late={tally.late}
        />
      </div>
    );
  }

  return (
    <>
      {/* 푸는 동안에만 둔다. 시작 카드와 결과 카드에는 판정이 없다. */}
      <Burst fire={burst} />

      {/* 화면 아래쪽에서 걸어와 반응하고 간다. Burst 와 같은 이유로 여기
          둔다 - 문제 위치와 무관하게 화면 기준으로 서야 한다.

          판 모드에서는 이 연출 동안 다음 문제를 안 낸다. 그 시간은 서버가
          마감에서 빼주므로(session.REACTION_PAUSE_MS) 90초를 손해 보지
          않는다. 대신 한 판의 실제 길이가 그만큼 늘어난다. */}
      <Reaction fire={reaction.fire} correct={reaction.correct} />

      {/* 판이 도는 중이다. 나가는 길은 이것 하나뿐이고, 여기서만 묻는다.
          지금 나가면 서버가 판을 안 닫아서 점수가 안 남는다. */}
      <div className="mb-4 flex items-center gap-3">
        {/* 라벨이 "그만두기" 인 이유: 확인창 안의 확정 버튼이 "나가기" 라
            같은 이름이 한 화면에 둘이면 낭독기가 같은 말을 두 번 읽고,
            무엇을 눌러야 진짜 나가는지 헷갈린다. 여는 쪽과 확정하는 쪽의
            이름을 다르게 둔다. */}
        <ExitGuard
          to={routes.home}
          label="그만두기"
          confirm
          score={tally.score}
          countdown
        />
      </div>

      <PlayCard
        question={question}
        result={result}
        left={left}
        total={seconds}
        skipsLeft={skipsLeft}
        tally={tally}
        busy={busy}
        error={error}
        onPick={(id) => send(id)}
        onSkip={() => send(null, true)}
      />
    </>
  );
}

/* ---- 시작 전 ---- */

function StartCard({
  onStart,
  busy,
  error,
}: {
  onStart: () => void;
  busy: boolean;
  error: string;
}) {
  return (
    // 흰 카드에 두께. 크림에는 영역별 배경이 없어서 맨몸으로 두면 시작
    // 카드가 바탕에 녹는다. dv-card-press 는 안 붙인다 - 카드가 아니라
    // 안의 "시작" 버튼이 눌리는 자리다.
    <div
      className="rise dv-card px-6 py-10 text-center"
      style={
        {
          background: "var(--paper)",
          borderRadius: "var(--radius-2xl)",
          "--lift": "var(--lift-card)",
        } as React.CSSProperties
      }
    >
      {/* 90 을 크게 둔다. 이 화면에서 가장 먼저 읽어야 할 것이 "얼마나
          걸리나" 이고, 제목은 그 다음이다. 크기 차이를 벌려야 훑는 눈이
          순서대로 걸린다.

          잉크로 둔다. 다크에서는 호박이었는데 크림 위의 --amber 는 2.2:1
          이라 큰 글자여도 흐리게 뜬다. 코랄로 바꾸지도 않는다 - 이 카드의
          코랄 하나는 아래 "시작" 버튼이 갖고, 읽는 숫자와 누르는 버튼이
          같은 색이면 어느 쪽이 동작인지 사라진다. */}
      <p
        className="font-mono text-4xl tabular-nums sm:text-5xl"
        style={{
          fontWeight: "var(--weight-bold)",
          letterSpacing: "var(--tracking-tighter)",
          color: "var(--foreground)",
        }}
      >
        90
        <span
          className="ml-0.5 text-lg sm:text-xl"
          style={{
            fontWeight: "var(--weight-medium)",
            color: "var(--text-muted)",
          }}
        >
          초
        </span>
      </p>
      <h1
        className="mt-3 text-xl sm:text-2xl"
        style={{
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
          color: "var(--foreground)",
        }}
      >
        한 판 풀어봅니다
      </h1>
      <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>
        맞히면 +1, 틀리면 -1. 모르겠으면 세 번까지 넘길 수 있습니다.
      </p>

      {error && (
        <p
          role="alert"
          className="mt-4 text-sm"
          style={{
            color: "var(--coral-deep)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          {error}
        </p>
      )}

      {/* 이 화면의 코랄 하나. 여기서 할 일은 판을 여는 것뿐이다. */}
      <button
        type="button"
        onClick={onStart}
        disabled={busy}
        className="dv-btn mt-6 inline-flex items-center px-8 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-50"
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
        {busy ? "여는 중..." : "시작"}
      </button>
    </div>
  );
}

/* ---- 푸는 중 ---- */

function PlayCard({
  question,
  result,
  left,
  total,
  skipsLeft,
  tally,
  busy,
  error,
  onPick,
  onSkip,
}: {
  question: RoundQuestion | null;
  result: RoundResult | null;
  left: number;
  /** 서버가 정한 한 판 길이(초). 막대 분모다. */
  total: number;
  skipsLeft: number;
  tally: { answered: number; correct: number; score: number };
  busy: boolean;
  error: string;
  onPick: (id: number) => void;
  onSkip: () => void;
}) {
  const seconds = Math.ceil(left / 1000);
  // 10초 아래로 내려가면 색이 바뀐다. 숫자만으로는 급한 줄 모른다.
  const urgent = seconds <= 10;

  if (!question) return null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        {/* 쉬는 동안은 잉크, 10초 아래로는 코랄.
            평소를 코랄로 두면 경고할 색이 남지 않는다 - 이 화면에서 코랄은
            "지금 급하다" 하나를 뜻한다. 색만으로 알리지도 않는다: 숫자가
            줄고 아래 막대가 짧아지는 것이 먼저 있고 색은 그 위에 얹힌다. */}
        <span
          className="font-mono text-2xl tabular-nums transition-colors sm:text-3xl"
          style={{
            fontWeight: "var(--weight-black)",
            letterSpacing: "var(--tracking-tighter)",
            color: urgent ? "var(--coral)" : "var(--foreground)",
          }}
          // 매 초 바뀌는 값이라 읽어주면 방해가 된다. 남은 시간은 아래
          // 진행 막대와 색으로도 드러난다.
          aria-hidden
        >
          {seconds}
        </span>
        <span
          className="font-mono text-sm tabular-nums"
          style={{
            color: "var(--text-muted)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          {tally.score >= 0 ? `+${tally.score}` : tally.score}점 ·{" "}
          {tally.correct}/{tally.answered}
        </span>
      </div>

      {/* 남은 시간 막대. 90초를 100% 로 잡는다. */}
      <div
        className="h-1.5 overflow-hidden"
        role="progressbar"
        aria-label="남은 시간"
        aria-valuemin={0}
        aria-valuemax={total}
        // **경과분을 넣는다.** 남은 초를 그대로 주면 90 에서 0 으로
        // 줄어들어, 스크린리더가 진행이 되돌아간다고 읽는다.
        aria-valuenow={total - seconds}
        style={{
          background: "var(--sand-deep)",
          borderRadius: "var(--radius-pill)",
        }}
      >
        {/* 여기는 복습·일일공부의 진행 막대와 **뜻이 반대다.** 그쪽은
            채운 만큼이 지나온 것(초록)이고, 여기 채움은 **남은 시간**이라
            줄어든다. 그래서 초록을 안 쓴다 - 같은 초록이 한쪽에서는
            "해낸 것", 다른 쪽에서는 "남은 것" 이 되면 훑을 때 헷갈린다.
            평소는 잉크, 10초 아래로는 위 숫자와 함께 코랄로 넘어간다. */}
        <div
          className="h-full transition-[width] duration-300 ease-linear"
          style={{
            width: `${Math.min(100, (left / (total * 1000)) * 100)}%`,
            background: urgent ? "var(--coral)" : "var(--foreground)",
            borderRadius: "var(--radius-pill)",
          }}
        />
      </div>

      {/* 문제와 보기는 QuestionCard 가 그린다.
          여기 한 벌을 따로 들고 있었는데(복습·일일공부는 이미 공용을 쓴다),
          같은 것을 두 벌 두면 보기의 터치 높이나 발음기호 서체를 한쪽만
          고치게 된다 - QuestionCard 주석이 경고하던 바로 그 자리다. 크림에서
          두 벌의 보기 버튼이 실제로 갈라졌다(공용은 56px·--radius-xl 인데
          여기는 48px·rounded-xl 이었다). 화면 셋이 같은 문제를 내므로 같은
          모양이어야 한다. */}
      <QuestionCard question={question} busy={busy} onPick={onPick} />

      <div className="flex items-center justify-between gap-3">
        {/* 흰 알약으로 물러난다. 코랄은 보기를 고르는 쪽에 있어야 하고,
            넘기기는 세 번뿐인 도피구다 - 눈에 띄게 두면 그걸 먼저 쓴다.
            횟수를 다 쓰면 흐려지지만 사라지지는 않는다. 사라지면 버튼 줄이
            통째로 움직여 옆의 채점 결과가 다른 자리로 뛴다. */}
        <button
          type="button"
          onClick={onSkip}
          disabled={busy || skipsLeft === 0}
          className="dv-btn inline-flex min-h-11 items-center px-4 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-40"
          style={
            {
              background: "var(--paper)",
              color: "var(--text-body)",
              border: 0,
              borderRadius: "var(--radius-pill)",
              fontWeight: "var(--weight-bold)",
              "--lift": "var(--lift-card)",
            } as React.CSSProperties
          }
        >
          넘기기 {skipsLeft > 0 && `(${skipsLeft})`}
        </button>

        {/* 직전 채점 결과. 새로 나타나는 영역이라 읽어준다. */}
        <p aria-live="polite" className="text-sm">
          {result && !result.skipped && (
            // 맞았지만 시간이 지난 것(0점)은 초록으로 두지 않는다. 점수가
            // 안 붙은 것을 정답과 같은 색으로 칠하면 문구만 예외가 되고
            // 색은 거짓말을 한다. 잉크로 물러난다.
            <span
              style={{
                color: !result.correct
                  ? "var(--wrong-deep)"
                  : result.in_time
                    ? "var(--correct)"
                    : "var(--text-muted)",
                fontWeight: "var(--weight-black)",
              }}
            >
              {/* **시간 초과로 맞힌 것은 0점이다.** 그냥 "정답" 으로 두면
                  맞혔는데 점수가 안 오르는 이유를 알 방법이 없다. */}
              {result.correct
                ? result.in_time
                  ? "정답"
                  : "정답 · 시간 초과"
                : `오답 · ${result.answer_text}`}
            </span>
          )}
        </p>
      </div>

      {error && (
        <p
          role="alert"
          className="text-sm"
          style={{
            color: "var(--coral-deep)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          {error}
        </p>
      )}
    </div>
  );
}

/* ---- 끝난 뒤 ---- */

function RoundResultCard({
  summary,
  error,
  isGuest,
  onAgain,
  busy,
  late,
}: {
  summary: RoundSummary | null;
  error: string;
  isGuest: boolean;
  onAgain: () => void;
  busy: boolean;
  /**
   * 맞혔지만 시간이 지나 0 점이 된 개수.
   *
   * 서버 요약에는 없어서 클라이언트가 센다. 이게 없으면 "3문제 중 2개
   * 정답 / 0점" 이 설명 없이 나와 버그로 읽힌다.
   */
  late: number;
}) {
  return (
    <div
      className="rise dv-card px-6 py-8 text-center"
      style={
        {
          background: "var(--paper)",
          borderRadius: "var(--radius-2xl)",
          "--lift": "var(--lift-card)",
        } as React.CSSProperties
      }
    >
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        한 판 끝
      </p>

      {summary ? (
        <>
          {/* 이 화면에서 가장 큰 숫자. 잉크로 둔다 - 일일공부·복습 결과가
              같은 자리를 같은 방식으로 그리고, 코랄은 아래 "순위표에서
              확인" 이 갖는다. */}
          <p
            className="pop mt-2 font-mono text-5xl tabular-nums"
            style={{
              fontWeight: "var(--weight-bold)",
              letterSpacing: "var(--tracking-tighter)",
              color: "var(--foreground)",
            }}
          >
            {summary.score}
          </p>
          <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>
            {summary.answered}문제 중 {summary.correct}개 정답
            {summary.skipped > 0 && ` · ${summary.skipped}개 넘김`}
            {/* 시간 지나 맞힌 것은 0 점이다. 이 줄이 없으면 "2개 맞혔는데
                왜 0점?" 이 되어 버그로 읽힌다(실측: 3문제 중 2개 정답인데
                0점이었다). 푸는 중에는 "정답 · 시간 초과" 로 알려주면서
                결과에서만 빠뜨리면 앞뒤가 안 맞는다. */}
            {late > 0 && ` · ${late}개는 시간이 지나 0점`}
          </p>

          {/* 기록됐을 때만 순위 얘기를 한다. 게스트에게 "17위" 를 보여주면
              다음에 왔을 때 그 등수가 사라져 있다. */}
          {summary.recorded ? (
            // 기록이 남은 사람에게는 순위표가 다음에 할 일이라 코랄.
            // 아래 "한 판 더" 는 흰 알약으로 물러난다.
            <Link
              href={routes.board()}
              className="dv-btn mt-6 inline-flex items-center px-6 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
              style={
                {
                  minHeight: "var(--hit-min)",
                  background: "var(--coral)",
                  color: "var(--text-on-color)",
                  borderRadius: "var(--radius-pill)",
                  fontWeight: "var(--weight-black)",
                  "--lift": "var(--lift-button)",
                } as React.CSSProperties
              }
            >
              순위표에서 확인
            </Link>
          ) : (
            isGuest && (
              // 게스트 안내는 옅은 띠에 앉힌다. 이 카드 안의 또 다른
              // 카드로 두지 않는다 - 흰 종이 위에 흰 종이면 두께만 겹치고
              // 층이 안 생긴다.
              <p
                className="mt-5 px-4 py-3 text-sm"
                style={{
                  background: "var(--background-deep)",
                  borderRadius: "var(--radius-md)",
                  lineHeight: "var(--leading-relaxed)",
                  color: "var(--text-muted)",
                }}
              >
                로그인하면 다음 판부터 순위표에 올라갑니다.{" "}
                {/* 게스트에게는 로그인이 이 화면의 코랄 하나다 - 위
                    "순위표에서 확인" 이 안 그려지는 갈래라 겹치지 않는다.
                    밑줄을 남긴다: 문장 안의 링크는 색만으로 알리지 않는다. */}
                <Link
                  href={`/login?next=${routes.testRound}`}
                  className="underline underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                  style={{
                    color: "var(--coral-deep)",
                    fontWeight: "var(--weight-black)",
                  }}
                >
                  로그인
                </Link>
              </p>
            )
          )}
        </>
      ) : (
        <p className="mt-3" style={{ color: "var(--text-body)" }}>
          {error || "결과를 불러오지 못했습니다."}
        </p>
      )}

      <div className="mt-6">
        {/* 흰 알약. 위의 "순위표에서 확인" 이 코랄이라 여기는 물러난다.
            결과를 못 불러온 갈래에서는 이것이 화면의 유일한 버튼이 되지만
            그대로 둔다 - 그때는 방금 실패한 판을 다시 여는 것이라, 코랄로
            권할 동작이 아니다. */}
        <button
          type="button"
          onClick={onAgain}
          disabled={busy}
          className="dv-btn inline-flex min-h-11 items-center px-5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-50"
          style={
            {
              background: "var(--paper)",
              color: "var(--foreground)",
              border: 0,
              borderRadius: "var(--radius-pill)",
              fontWeight: "var(--weight-black)",
              "--lift": "var(--lift-button-paper)",
            } as React.CSSProperties
          }
        >
          {busy ? "여는 중..." : "한 판 더"}
        </button>
      </div>
    </div>
  );
}
