"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Burst } from "@/components/Burst";
import { ExitGuard } from "@/components/ExitGuard";
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

  // 마감 시각(ms). 남은 시간을 매 초 다시 계산하는 근거다. setInterval 로
  // 1씩 빼면 탭이 백그라운드로 갔을 때 타이머가 멈춰 시간이 남아 보인다.
  const deadlineRef = useRef(0);
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
      setSeconds(started.round_seconds);
      tokenRef.current = started.token;
      setQuestion(started.question);
      setSkipsLeft(started.max_skips);
      setTally({ answered: 0, correct: 0, score: 0, late: 0 });
      // 축포 카운터도 되돌린다. 판마다 0 에서 시작해야 다른 리셋들과
      // 규율이 맞는다.
      setBurst(0);
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
          <Link
            href={routes.board()}
            className="min-h-11 rounded-lg px-2.5 py-2 text-sm text-slate-400 transition hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
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
    <div className="rise rounded-2xl border border-white/10 bg-slate-950/40 px-6 py-10 text-center">
      {/* 90 을 크게 둔다. 이 화면에서 가장 먼저 읽어야 할 것이 "얼마나
          걸리나" 이고, 제목은 그 다음이다. 크기 차이를 벌려야 훑는 눈이
          순서대로 걸린다. */}
      <p className="font-mono text-4xl font-bold text-amber-300 sm:text-5xl">
        90
        <span className="ml-0.5 text-lg font-medium text-amber-300/70 sm:text-xl">
          초
        </span>
      </p>
      <h1 className="mt-3 text-xl font-bold text-slate-100 sm:text-2xl">
        한 판 풀어봅니다
      </h1>
      <p className="mt-2 text-sm text-slate-400">
        맞히면 +1, 틀리면 -1. 모르겠으면 세 번까지 넘길 수 있습니다.
      </p>

      {error && (
        <p role="alert" className="mt-4 text-sm text-rose-300">
          {error}
        </p>
      )}

      <button
        type="button"
        onClick={onStart}
        disabled={busy}
        className="mt-6 inline-flex min-h-12 items-center rounded-xl bg-amber-300/15 px-8 text-base font-semibold text-amber-100 ring-1 ring-amber-300/40 transition hover:bg-amber-300/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60"
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
        <span
          className={[
            "font-mono text-2xl font-bold tabular-nums transition-colors sm:text-3xl",
            urgent ? "text-rose-300" : "text-slate-100",
          ].join(" ")}
          // 매 초 바뀌는 값이라 읽어주면 방해가 된다. 남은 시간은 아래
          // 진행 막대와 색으로도 드러난다.
          aria-hidden
        >
          {seconds}
        </span>
        <span className="font-mono text-sm tabular-nums text-slate-400">
          {tally.score >= 0 ? `+${tally.score}` : tally.score}점 ·{" "}
          {tally.correct}/{tally.answered}
        </span>
      </div>

      {/* 남은 시간 막대. 90초를 100% 로 잡는다. */}
      <div
        className="h-1 overflow-hidden rounded-full bg-white/8"
        role="progressbar"
        aria-label="남은 시간"
        aria-valuemin={0}
        aria-valuemax={total}
        // **경과분을 넣는다.** 남은 초를 그대로 주면 90 에서 0 으로
        // 줄어들어, 스크린리더가 진행이 되돌아간다고 읽는다.
        aria-valuenow={total - seconds}
      >
        <div
          className={[
            "h-full rounded-full transition-[width] duration-300 ease-linear",
            urgent ? "bg-rose-400/80" : "bg-amber-300/70",
          ].join(" ")}
          style={{ width: `${Math.min(100, (left / (total * 1000)) * 100)}%` }}
        />
      </div>

      <div className="rounded-2xl border border-white/10 bg-slate-950/40 px-5 py-6">
        <p className="text-xs text-slate-500">{question.kind_label}</p>
        <p className="mt-1 text-sm text-slate-400">{question.question}</p>
        <p
          className={[
            "mt-3 text-xl font-semibold text-slate-100 sm:text-2xl",
            // 단어·에러 메시지는 고정폭, 사람이 쓴 문장은 가변폭.
            question.kind === "situation" || question.kind === "blank"
              ? ""
              : "font-mono",
          ].join(" ")}
        >
          {question.prompt}
        </p>
      </div>

      <ul className="flex flex-col gap-2">
        {question.choices.map((choice) => (
          <li key={choice.id}>
            <button
              type="button"
              onClick={() => onPick(choice.id)}
              disabled={busy}
              className="min-h-12 w-full rounded-xl border border-white/12 bg-slate-950/35 px-4 py-3 text-left text-slate-100 transition hover:border-amber-300/40 hover:bg-amber-300/8 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60"
            >
              {choice.text}
            </button>
          </li>
        ))}
      </ul>

      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={onSkip}
          disabled={busy || skipsLeft === 0}
          className="min-h-11 rounded-lg px-3 text-sm text-slate-400 transition hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-40"
        >
          넘기기 {skipsLeft > 0 && `(${skipsLeft})`}
        </button>

        {/* 직전 채점 결과. 새로 나타나는 영역이라 읽어준다. */}
        <p aria-live="polite" className="text-sm">
          {result && !result.skipped && (
            <span
              className={
                !result.correct
                  ? "text-rose-300"
                  : result.in_time
                    ? "text-teal-300"
                    : "text-slate-300"
              }
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
        <p role="alert" className="text-sm text-rose-300">
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
    <div className="rise rounded-2xl border border-white/10 bg-slate-950/40 px-6 py-8 text-center">
      <p className="text-sm text-slate-400">한 판 끝</p>

      {summary ? (
        <>
          <p className="pop mt-2 font-mono text-5xl font-bold tabular-nums text-amber-200">
            {summary.score}
          </p>
          <p className="mt-2 text-sm text-slate-400">
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
            <Link
              href={routes.board()}
              className="mt-6 inline-flex min-h-11 items-center rounded-lg bg-violet-300/15 px-5 text-sm font-medium text-violet-100 ring-1 ring-violet-300/35 transition hover:bg-violet-300/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            >
              순위표에서 확인
            </Link>
          ) : (
            isGuest && (
              <p className="mt-5 rounded-lg border border-white/10 bg-slate-950/40 px-4 py-3 text-sm text-slate-400">
                로그인하면 다음 판부터 순위표에 올라갑니다.{" "}
                <Link
                  href={`/login?next=${routes.testRound}`}
                  className="font-medium text-teal-300 underline underline-offset-2 hover:text-teal-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                >
                  로그인
                </Link>
              </p>
            )
          )}
        </>
      ) : (
        <p className="mt-3 text-slate-300">
          {error || "결과를 불러오지 못했습니다."}
        </p>
      )}

      <div className="mt-6">
        <button
          type="button"
          onClick={onAgain}
          disabled={busy}
          className="min-h-11 rounded-lg border border-white/12 px-5 text-sm font-medium text-slate-200 transition hover:border-white/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60"
        >
          {busy ? "여는 중..." : "한 판 더"}
        </button>
      </div>
    </div>
  );
}
