"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import type {
  DailyAnswered,
  DailyStarted,
  DailyStatus,
  StudyCard,
  StudyLength,
  StudyProgress,
} from "@/lib/api/daily";
import type { RoundQuestion, RoundResult } from "@/lib/api/rounds";
import { routes } from "@/lib/routes";

import { QuestionCard } from "./QuestionCard";
import { StudyCards } from "./StudyCards";

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

/**
 * 화면 단계.
 *
 * learning 은 문제 앞에 온다. 문제는 그때 이미 받아둔 상태라(서버가
 * 학습과 함께 내려준다) 카드를 다 넘기면 왕복 없이 playing 으로 간다.
 */
type Phase = "choosing" | "learning" | "playing" | "done";

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
    : status.learning.length > 0
      ? "learning"
      : status.token && status.question
        ? "playing"
        : "choosing";

  const [phase, setPhase] = useState<Phase>(initial);
  const [question, setQuestion] = useState<RoundQuestion | null>(
    status.question,
  );
  // 이번 묶음의 학습 카드. 다 넘기면 비우고 playing 으로 간다.
  const [cards, setCards] = useState<StudyCard[]>(status.learning);
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
      // 학습이 먼저다. 카드가 없는 판(콘텐츠가 적어 묶음을 못 만든 경우)은
      // 곧바로 문제로 간다.
      setCards(started.learning);
      setPhase(started.learning.length > 0 ? "learning" : "playing");
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

      // **다음 묶음이 시작되면 학습부터다.** 이 화면은 채점 결과를
      // 다음 문제 위에 인라인으로 띄우므로(별도 "다음" 버튼이 없다),
      // 학습으로 넘어가면 그 줄이 사라진다. 그래서 카드를 들고만 있고
      // 넘기는 것은 사용자가 결과를 본 뒤다 - 아래 PlayCard 의 onLearn 이 한다.
      setCards(answered.learning);
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

  if (phase === "learning" && cards.length > 0) {
    return (
      <StudyCards
        // 묶음이 바뀌면 카드 번호를 처음으로 되돌린다. 안 주면 다음
        // 묶음이 마지막 카드부터 시작한다.
        key={study?.chunk_index ?? 0}
        cards={cards}
        chunkIndex={study?.chunk_index ?? 0}
        chunkCount={study?.chunk_count ?? 0}
        onDone={() => {
          // 문제는 이미 받아둔 상태다. 카드를 비우고 넘어가기만 한다 -
          // 여기서 서버를 부르면 왕복이 늘고, 그 요청은 점수와 무관해
          // 되돌리기를 막을 이유도 없다.
          setCards([]);
          setResult(null);
          setPhase("playing");
        }}
      />
    );
  }

  // 학습할 카드가 없으면 문제로 간다. 후보가 모자라 묶음을 못 뽑으면
  // 서버가 빈 목록을 주는데, phase 만 보고 분기하면 그 판이 아래 길이
  // 고르기로 떨어진다 - 판이 도는 중에 "길이를 고르세요" 가 뜨면
  // 사용자는 진행이 날아간 줄 안다.
  if (phase !== "choosing" && question) {
    return (
      <PlayCard
        question={question}
        result={result}
        study={study}
        busy={busy}
        error={error}
        onPick={send}
        // 다음 묶음이 시작되면 결과 줄 아래에 "이어서 익히기" 가 뜬다.
        // 자동으로 넘기지 않는 이유: 이 화면은 채점 결과를 다음 문제
        // 위에 인라인으로 띄우는데, 곧바로 학습으로 가면 방금 맞았는지
        // 틀렸는지를 못 보고 화면이 튄다.
        onLearn={cards.length > 0 ? () => setPhase("learning") : undefined}
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
        {/* 무엇을 하는 시간인지 먼저 말한다. "문제를 푼다" 로만 안내하면
            학습 카드가 나왔을 때 잘못 들어온 화면으로 읽힌다. */}
        몇 개를 익히고 그것으로 문제를 풉니다.
        <br />
        제한 시간은 없고, 틀려도 점수가 깎이지 않습니다.
      </p>

      {/* 하다 만 판이 있으면 아래 버튼이 전부 비활성이다. 이유를 안 적으면
          흐릿한 버튼 세 개만 보이고 왜 못 누르는지 알 수 없다. 이 화면은
          한 번의 응답 사이클에만 뜨는데(다음 GET 에서는 판이 닫혀 결과로
          간다), 그 한 번이 "진행이 날아갔다" 고 읽는 순간이다. */}
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
              {/* 몇 개를 배우는지 먼저 보여준다. 문제 수만 있으면 길이
                  선택이 "얼마나 오래 걸리나" 로만 읽히는데, 이 기능의
                  값은 그날 몇 단어를 익히느냐에 있다. */}
              {one.words > 0 && (
                <span className="text-slate-300">{one.words}단어 · </span>
              )}
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
  onLearn,
}: {
  question: RoundQuestion;
  result: RoundResult | null;
  study: StudyProgress | null;
  busy: boolean;
  error: string;
  onPick: (id: number) => void;
  /** 다음 묶음의 학습이 기다릴 때만 온다. 없으면 버튼을 안 그린다. */
  onLearn?: () => void;
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

      {/* 학습이 기다리면 보기를 막는다. 안 막으면 아직 안 배운 단어로
          답하게 되고, "먼저 익히고 푼다" 는 이 기능의 전제가 깨진다. */}
      <QuestionCard
        question={question}
        busy={busy || onLearn !== undefined}
        onPick={onPick}
      />

      {/* 새로 나타나는 영역이라 읽어준다. */}
      <p aria-live="polite" className="min-h-6 text-sm">
        {result && (
          <span className={result.correct ? "text-focus" : "text-rose-300"}>
            {result.correct ? "정답" : `오답 · ${result.answer_text}`}
          </span>
        )}
      </p>

      {/* 다음 묶음이 기다릴 때만. 이 버튼이 없으면 아래 보기를 눌러
          답하게 되는데, 그 문제는 아직 안 배운 단어로 나온다. */}
      {onLearn && (
        <button
          type="button"
          onClick={onLearn}
          className="flex min-h-12 w-full items-center justify-center rounded-full bg-focus px-5 font-semibold text-focus-on transition-[scale] duration-[120ms] ease-press active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          이어서 익히기
        </button>
      )}

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
  // **done 으로는 못 가른다.** 여기 오는 두 경로(초기 phase 판정, 답한 뒤
  // finished)가 둘 다 판을 닫고 온다 - 서버가 _finish 를 부른 뒤 그 인스턴스를
  // 그대로 내려주므로 done 은 항상 참이다. 다 풀었는지는 개수로 본다.
  // 모르면 "여기까지" 쪽으로 둔다. 다 풀지 않았는데 "완료" 라고 하는
  // 것이 그 반대보다 나쁘다.
  const short = study === null || study.answered < study.total;

  return (
    <div className="rise flex flex-1 flex-col justify-center text-center">
      <p className="text-sm text-slate-400">
        {short ? "오늘은 여기까지" : "오늘 몫 완료"}
      </p>
      <p className="pop mt-2 font-mono text-5xl font-bold tabular-nums text-focus">
        {study?.score ?? 0}
      </p>
      {study && (
        <p className="mt-3 text-sm text-slate-400">
          {study.total}문제 중 {study.correct}개 정답
          {!short && study.bonus > 0 && (
            <span className="ml-1 text-focus">+{study.bonus} 보너스</span>
          )}
        </p>
      )}

      {short && (
        <p className="mt-3 text-sm text-slate-400">
          낼 수 있는 문제가 떨어져 먼저 마쳤습니다.
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
