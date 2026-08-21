"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import type {
  DailyAnswered,
  DailyStarted,
  DailyStatus,
  StudyLength,
  StudyProgress,
} from "@/lib/api/daily";
import type { RoundQuestion, RoundResult } from "@/lib/api/rounds";
import { routes } from "@/lib/routes";

/**
 * 하루 한 번 일일공부.
 *
 * 90초 한 판과 다른 점 셋:
 *
 *   제한 시간이 없다   문제 수로만 끝난다. 길이를 고르는 것이 그래서다
 *   감점이 없다       맞히면 +1, 틀리면 0. 시간을 안 재는 공부라 벌을
 *                    주면 찍기를 피하려고 화면만 오래 붙들게 된다
 *   진행이 서버에 남는다 답할 때마다 저장돼 중간에 나가도 푼 만큼 남는다
 *
 * 판 상태를 ref 로 드는 이유는 RoundBoard 와 같다 - 비동기 응답이 오는
 * 사이에 다른 클릭이 들어오면 state 는 한 틱 낡은 값을 본다.
 */

type Phase = "choosing" | "playing" | "done";

async function call<T>(body: Record<string, unknown>): Promise<T> {
  const res = await fetch("/api/daily", {
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

export function DailyStudyBoard({ status }: { status: DailyStatus }) {
  // 오늘 이미 다 한 사람은 결과부터, 하다 만 사람은 이어서 푸는 화면부터
  // 본다. 길이는 시작할 때 정해져 바꿀 수 없으므로 고르기로 돌아가지
  // 않는다 - 돌아가봐야 어느 길이를 눌러도 "이미 시작했다" 로 막힌다.
  const initial: Phase = status.today?.done
    ? "done"
    : status.token && status.question
      ? "playing"
      : "choosing";

  const [phase, setPhase] = useState<Phase>(initial);
  const [question, setQuestion] = useState<RoundQuestion | null>(
    status.question,
  );
  const [result, setResult] = useState<RoundResult | null>(null);
  const [study, setStudy] = useState<StudyProgress | null>(status.today);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const tokenRef = useRef("");
  const busyRef = useRef(false);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  // 서버가 준 이어 풀 토큰. ref 라 렌더 중에 넣어도 되지만, 한 번만
  // 넣는다는 것을 분명히 하려고 effect 에 둔다.
  useEffect(() => {
    if (status.token) tokenRef.current = status.token;
  }, [status.token]);

  const start = async (length: string) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");

    try {
      const started = await call<DailyStarted>({ action: "start", length });
      if (!aliveRef.current) return;

      tokenRef.current = started.token;
      setQuestion(started.question);
      setStudy(started.study);
      setResult(null);
      setPhase("playing");
    } catch (err) {
      if (!aliveRef.current) return;
      setError(err instanceof Error ? err.message : "시작하지 못했습니다.");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const send = async (choiceId: number) => {
    if (busyRef.current || !tokenRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");

    try {
      const answered = await call<DailyAnswered>({
        action: "answer",
        token: tokenRef.current,
        choice_id: choiceId,
      });
      if (!aliveRef.current) return;

      tokenRef.current = answered.token ?? "";
      setResult(answered.result);
      setStudy(answered.study);

      if (answered.finished || !answered.question) {
        // busyRef 를 쥔 채 화면을 넘긴다. finally 에서 풀리지만 그때는
        // 이미 phase 가 done 이라 보기 버튼이 없다. 마지막 답 직후의
        // 짧은 창에 한 번 더 눌리는 것을 막는다.
        setPhase("done");
        return;
      }
      setQuestion(answered.question);
    } catch (err) {
      if (!aliveRef.current) return;
      setError(err instanceof Error ? err.message : "채점하지 못했습니다.");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  if (phase === "done") {
    return <DoneCard study={study} />;
  }

  if (phase === "playing" && question) {
    return (
      <PlayCard
        question={question}
        result={result}
        study={study}
        busy={busy}
        error={error}
        onPick={send}
      />
    );
  }

  return (
    <ChooseCard
      lengths={status.lengths}
      resuming={status.today}
      busy={busy}
      error={error}
      onStart={start}
    />
  );
}

/* ---- 길이 고르기 ---- */

function ChooseCard({
  lengths,
  resuming,
  busy,
  error,
  onStart,
}: {
  lengths: StudyLength[];
  /** 하다 만 판. 있으면 길이를 다시 고를 수 없다. */
  resuming: StudyProgress | null;
  busy: boolean;
  error: string;
  onStart: (length: string) => void;
}) {
  return (
    <div className="rise flex flex-1 flex-col justify-center">
      <p className="text-sm font-medium text-focus">하루 한 번</p>
      <h1 className="mt-2 text-2xl font-bold text-slate-100">
        오늘 얼마나 해볼까요
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-slate-400">
        제한 시간은 없습니다. 맞히면 1점, 틀려도 깎이지 않습니다.
        <br />
        다 풀면 길이에 따라 보너스가 붙습니다.
      </p>

      {/* 여기까지 왔다는 것은 이어 풀 토큰을 못 받았다는 뜻이다(낼 수 있는
          문제가 없는 등). 길이를 다시 고를 수는 없으므로 - 어느 것을 눌러도
          "이미 시작했다" 로 막힌다 - 상황을 사실대로 알린다. */}
      {resuming && !resuming.done && (
        <p className="mt-5 rounded-xl border border-white/25 px-4 py-3 text-sm text-slate-300">
          오늘 {resuming.answered}/{resuming.total}문제까지 풀었습니다. 지금은
          이어서 풀 문제를 낼 수 없습니다. 잠시 뒤 다시 시도해주세요.
        </p>
      )}

      {error && (
        <p role="alert" className="mt-4 text-sm text-rose-300">
          {error}
        </p>
      )}

      <div className="mt-6 flex flex-col gap-2.5">
        {lengths.map((one) => (
          <button
            key={one.value}
            type="button"
            onClick={() => onStart(one.value)}
            // 하다 만 판이 있으면 길이를 다시 고를 수 없다. 눌러봐야
            // 서버가 "이미 시작했다" 로 막는다.
            disabled={busy || (resuming !== null && !resuming.done)}
            className="flex min-h-14 items-center justify-between rounded-2xl border border-white/25 px-5 text-left transition-[scale,border-color] duration-[120ms] ease-press hover:border-white/45 active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60"
          >
            <span className="font-semibold text-slate-100">{one.label}</span>
            <span className="text-right text-sm text-slate-400">
              {one.questions}문제
              <span className="ml-2 text-focus">+{one.bonus}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ---- 푸는 중 ---- */

function PlayCard({
  question,
  result,
  study,
  busy,
  error,
  onPick,
}: {
  question: RoundQuestion;
  result: RoundResult | null;
  study: StudyProgress | null;
  busy: boolean;
  error: string;
  onPick: (id: number) => void;
}) {
  const answered = study?.answered ?? 0;
  const total = study?.total ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-sm tabular-nums text-slate-400">
          {answered} / {total}
        </span>
        <span className="font-mono text-sm tabular-nums text-focus">
          {study?.score ?? 0}점
        </span>
      </div>

      {/* 남은 시간이 아니라 진행률이다. 제한 시간이 없는 공부라 급할
          이유가 없고, 얼마나 남았는지만 알면 된다. */}
      <div
        className="h-1 overflow-hidden rounded-full bg-white/10"
        role="progressbar"
        aria-label="진행"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={answered}
      >
        <div
          className="h-full rounded-full bg-focus/70 transition-[width] duration-300"
          style={{ width: `${total ? (answered / total) * 100 : 0}%` }}
        />
      </div>

      <div className="rounded-2xl border border-white/12 bg-slate-950/40 px-5 py-6">
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
              className="min-h-12 w-full rounded-xl border border-white/40 px-4 py-3 text-left text-slate-100 transition-[scale,border-color] duration-[120ms] ease-press hover:border-white/60 active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60"
            >
              {choice.text}
            </button>
          </li>
        ))}
      </ul>

      {/* 새로 나타나는 영역이라 읽어준다. */}
      <p aria-live="polite" className="min-h-6 text-sm">
        {result && (
          <span className={result.correct ? "text-focus" : "text-rose-300"}>
            {result.correct ? "정답" : `오답 · ${result.answer_text}`}
          </span>
        )}
      </p>

      {error && (
        <p role="alert" className="text-sm text-rose-300">
          {error}
        </p>
      )}
    </div>
  );
}

/* ---- 끝난 뒤 ---- */

function DoneCard({ study }: { study: StudyProgress | null }) {
  return (
    <div className="rise flex flex-1 flex-col justify-center text-center">
      <p className="text-sm text-slate-400">오늘 몫 완료</p>
      <p className="pop mt-2 font-mono text-5xl font-bold tabular-nums text-focus">
        {study?.score ?? 0}
      </p>
      {study && (
        <p className="mt-3 text-sm text-slate-400">
          {study.total}문제 중 {study.correct}개 정답
          {study.done && study.bonus > 0 && (
            <span className="ml-1 text-focus">+{study.bonus} 보너스</span>
          )}
        </p>
      )}

      <p className="mt-6 text-sm text-slate-500">
        일일공부는 하루 한 번입니다. 내일 또 만나요.
      </p>

      <div className="mt-6 flex flex-col gap-2.5">
        <Link
          href={routes.board()}
          className="flex min-h-12 items-center justify-center rounded-full bg-focus px-5 font-semibold text-focus-on transition-[scale] duration-[120ms] ease-press active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          순위표에서 확인
        </Link>
        <Link
          href={routes.home}
          className="flex min-h-12 items-center justify-center rounded-full border border-white/40 px-5 font-medium text-slate-100 transition-[scale,border-color] duration-[120ms] ease-press hover:border-white/60 active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          홈으로
        </Link>
      </div>
    </div>
  );
}
