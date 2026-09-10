"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import type {
  ReviewAnswered,
  ReviewDue,
  ReviewQuestion,
  ReviewResult,
  ReviewStarted,
} from "@/lib/api/review";
import { routes } from "@/lib/routes";

import { QuestionCard } from "./QuestionCard";

/**
 * 틀린 것 다시 풀기. 화면 셋을 phase 로 오간다.
 *
 *   idle     남은 개수와 시작 버튼
 *   playing  문제와 보기
 *   done     이번 판 결과
 *
 * 무엇이 나오고 점수를 왜 안 주는지 같은 정책은 lib/api/review.ts
 * 첫머리에 있다. 여기 다시 적으면 정책이 바뀔 때 한 곳만 고쳐진다.
 *
 * **진행은 서버가 센다.** 문제 본문에 실려 오는 것을 그대로 쓴다 -
 * 화면이 답한 횟수로 세면 서버가 건너뛴 만큼 어긋난다. 0 부터 세는
 * 값이라 첫 문제가 0 / 20 이다(ReviewQuestion.answered 주석).
 *
 * **DailyStudyBoard 와 골격이 닮았지만 합치지 않았다.** 엔드포인트,
 * 시작 인자 유무, 진행 출처, 초기 phase, 이어 풀기 토큰까지 다섯 축이
 * 달라서 공통 훅이 받을 인자가 남는 코드보다 길어진다. 세 번째 화면이
 * 생기면 그때 다시 본다.
 */

type Phase = "idle" | "playing" | "done";

export function ReviewBoard({ due }: { due: ReviewDue }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [question, setQuestion] = useState<ReviewQuestion | null>(null);
  const [result, setResult] = useState<ReviewResult | null>(null);
  const [total, setTotal] = useState(0);
  const [answered, setAnswered] = useState(0);
  const [correct, setCorrect] = useState(0);
  const [graduated, setGraduated] = useState(0);
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

  const start = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");

    try {
      const started = await call<ReviewStarted>({ action: "start" });
      if (!aliveRef.current) return;

      tokenRef.current = started.token;
      setQuestion(started.question);
      setTotal(started.question.total);
      setAnswered(started.question.answered);
      setCorrect(0);
      setGraduated(0);
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
      const got = await call<ReviewAnswered>({
        action: "answer",
        token: tokenRef.current,
        choice_id: choiceId,
      });
      if (!aliveRef.current) return;

      tokenRef.current = got.token ?? "";
      setResult(got.result);
      // 다음 문제가 있으면 서버가 센 순번을 쓴다. 마지막이면 그것이
      // 없으므로 하나 올린다 - 끝난 판이라 더 어긋날 자리도 없다.
      setAnswered((n) => got.question?.answered ?? n + 1);
      if (got.result.correct) setCorrect((n) => n + 1);
      if (got.result.graduated) setGraduated((n) => n + 1);

      if (got.finished || !got.question) {
        // busyRef 를 쥔 채 화면을 넘긴다. finally 에서 풀리지만 그때는
        // 이미 phase 가 done 이라 보기 버튼이 없다. 마지막 답 직후의
        // 짧은 창에 한 번 더 눌리는 것을 막는다.
        setPhase("done");
        return;
      }
      setQuestion(got.question);
    } catch (err) {
      if (!aliveRef.current) return;
      setError(err instanceof Error ? err.message : "채점하지 못했습니다.");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  if (phase === "done") {
    return (
      <DoneCard
        answered={answered}
        correct={correct}
        graduated={graduated}
        onAgain={start}
        busy={busy}
        error={error}
      />
    );
  }

  if (phase === "playing" && question) {
    return (
      <PlayCard
        question={question}
        result={result}
        graduateStreak={due.graduate_streak}
        answered={answered}
        total={total}
        busy={busy}
        error={error}
        onPick={send}
      />
    );
  }

  return <IdleCard due={due} busy={busy} error={error} onStart={start} />;
}

/**
 * 서버가 준 값을 문장에 넣어도 되는 수인가.
 *
 * 타입이 number 라고 해서 런타임 값이 수인 것은 아니다 - 응답은 JSON
 * 이고 request 는 캐스팅만 한다. 필드가 빠지거나(undefined) 문자열·
 * null 이 오면 문장에 그대로 박혀 "연속 abc번" 이 된다. 0 과 음수도
 * 막는다 - "연속 0번 맞히면 빠집니다" 는 틀린 말이다.
 */
function counted(value: number): boolean {
  // 상한을 둔다. 1e21 은 정수 판정을 통과하지만 화면에는 지수 표기로
  // 찍혀("연속 1e+21번") 읽을 수 없다. 사람이 풀 수 있는 수가 아니다.
  return Number.isInteger(value) && value > 0 && value <= 1000;
}

/* ---- 시작 전 ---- */

function IdleCard({
  due,
  busy,
  error,
  onStart,
}: {
  due: ReviewDue;
  busy: boolean;
  error: string;
  onStart: () => void;
}) {
  // 복습할 것이 없으면 시작 버튼을 그리지 않는다. 눌러봐야 "없다" 로
  // 막히고, 그건 화면이 이미 아는 사실이다.
  if (due.due === 0) {
    return (
      <div className="rise flex flex-1 flex-col justify-center text-center">
        <p
          className="text-lg"
          style={{
            color: "var(--foreground)",
            fontWeight: "var(--weight-black)",
            letterSpacing: "var(--tracking-tight)",
          }}
        >
          다시 볼 것이 없습니다
        </p>
        <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>
          문제를 풀다 틀리면 여기 모입니다. 맞힌 것도 일주일이 지나면 다시
          나옵니다.
        </p>
        {/* 여기서 연속으로 맞혀야 빠진다는 것을 적는다. 문제풀이에서
            맞힌 것은 정답을 안 보고 맞힌 것이라 세지 않는데, 그걸 모르면
            "분명히 맞혔는데 왜 그대로지" 가 된다. */}
        <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
          다시 보기에서 연속으로 맞혀야 빠집니다.
        </p>
        {/* 볼 것이 없는 화면이라 여기서 할 일은 문제를 푸는 것 하나다.
            이 화면의 유일한 코랄 버튼. */}
        <Link
          href={routes.testRound}
          className="dv-btn mx-auto mt-6 inline-flex items-center rounded-[var(--radius-pill)] px-6 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--coral)",
              color: "var(--text-on-color)",
              fontWeight: "var(--weight-black)",
              "--lift": "var(--lift-button)",
            } as React.CSSProperties
          }
        >
          문제 풀러 가기
        </Link>
      </div>
    );
  }

  // **서버가 준 수를 그대로 문장에 넣지 않는다.** 타입은 number 라고
  // 적혀 있지만 실제 값은 JSON 이라 컴파일러가 못 막는다. 필드가 빠지면
  // "연속 번 맞히면" 처럼 구멍이 뚫리고, 0 이나 음수가 오면 "연속 -1번"
  // 을 사용자에게 읽힌다. 셀 수 없으면 숫자를 뺀 문장으로 물러난다.
  const capped =
    counted(due.round_size) && due.due > due.round_size ? due.round_size : null;
  const streak = counted(due.graduate_streak) ? due.graduate_streak : null;

  return (
    <div className="rise flex flex-1 flex-col justify-center gap-6 text-center">
      <div>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          다시 볼 것
        </p>
        {/* 화면에서 가장 큰 숫자. tabular-nums 를 두는 이유는 pop 으로
            튀어오를 때 자릿수에 따라 가운데가 흔들리지 않게 하기 위해서다. */}
        <p
          className="pop mt-1 text-5xl tabular-nums"
          style={{
            fontFamily: "var(--font-mono)",
            fontWeight: "var(--weight-bold)",
            letterSpacing: "var(--tracking-tighter)",
            color: "var(--foreground)",
          }}
        >
          {due.due}
        </p>
      </div>

      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        {capped
          ? `이번 판에서 ${capped}개를 봅니다. 점수는 붙지 않고 시간도 재지 않습니다.`
          : "점수는 붙지 않고 시간도 재지 않습니다."}
      </p>

      <div>
        {/* 이 화면의 주된 동작이라 코랄. 한 화면에 코랄 버튼은 하나다. */}
        <button
          type="button"
          onClick={onStart}
          disabled={busy}
          className="dv-btn w-full rounded-[var(--radius-pill)] px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-50 sm:w-auto sm:px-10"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--coral)",
              color: "var(--text-on-color)",
              border: 0,
              fontWeight: "var(--weight-black)",
              "--lift": "var(--lift-button)",
            } as React.CSSProperties
          }
        >
          {busy ? "여는 중" : "시작"}
        </button>
        {/* "여기서" 는 위 빈 화면 문구와 같은 이유로 붙인다.
            라벨이 아니라 설명 문장이라 --text-muted 를 쓴다. 12px 이라
            라벨용 토큰을 쓰면 이 화면에서 제일 알아야 할
            규칙이 제일 흐리게 나온다. */}
        <p className="mt-3 text-xs" style={{ color: "var(--text-muted)" }}>
          {streak
            ? `여기서 연속 ${streak}번 맞히면 목록에서 빠집니다.`
            : "여기서 연속으로 맞히면 목록에서 빠집니다."}
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

/* ---- 푸는 중 ---- */

function PlayCard({
  question,
  result,
  graduateStreak,
  answered,
  total,
  busy,
  error,
  onPick,
}: {
  question: ReviewQuestion;
  result: ReviewResult | null;
  graduateStreak: number;
  answered: number;
  total: number;
  busy: boolean;
  error: string;
  onPick: (id: number) => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        {/* tabular-nums: 9/20 에서 10/20 으로 갈 때 폭이 바뀌면 왼쪽 끝이
            고정인 채로 글자만 밀려 한 번 더 읽게 된다. */}
        <span
          className="text-sm tabular-nums"
          style={{
            fontFamily: "var(--font-mono)",
            fontWeight: "var(--weight-bold)",
            color: "var(--text-muted)",
            letterSpacing: "var(--tracking-tighter)",
          }}
        >
          {answered} / {total}
        </span>
        <span className="text-sm" style={{ color: "var(--text-muted)" }}>
          점수 없음
        </span>
      </div>

      {/* 남은 시간이 아니라 진행률이다. 제한 시간이 없는 공부라 급할
          이유가 없고, 얼마나 남았는지만 알면 된다.

          막대는 7px 로 키웠다. 크림 바탕에서 1px 짜리 선은 두께 있는 카드
          옆에서 그어놓은 줄로 보인다 - 홈의 진행 점(ProgressDots)이 같은
          높이라 두 화면의 진행 표시가 같은 굵기로 선다. */}
      <div
        className="h-[7px] overflow-hidden"
        role="progressbar"
        aria-label="진행"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={answered}
        style={{
          background: "var(--sand-deep)",
          borderRadius: "var(--radius-pill)",
        }}
      >
        {/* 채워진 부분은 초록. 코랄은 "지금 눌러야 할 것" 이고 이건 이미
            지나온 것이라, 진행 점에서 done 을 초록으로 둔 것과 같다. */}
        <div
          className="h-full transition-[width] duration-300"
          style={{
            width: `${total ? (answered / total) * 100 : 0}%`,
            background: "var(--green)",
            borderRadius: "var(--radius-pill)",
          }}
        />
      </div>

      <QuestionCard question={question} busy={busy} onPick={onPick} />

      {/* 새로 나타나는 영역이라 읽어준다. */}
      <p aria-live="polite" className="min-h-6 text-sm">
        {result && (
          <ResultLine result={result} graduateStreak={graduateStreak} />
        )}
      </p>

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

/**
 * 채점 한 줄.
 *
 * 맞혔을 때 **몇 번 더 맞혀야 하는지** 알려주는 것이 이 화면의 핵심이다.
 * 그게 보여야 두 번째 정답에 의미가 생긴다. 없으면 왜 같은 문제가 또
 * 나오는지 모른 채 푼다.
 *
 * 남은 횟수를 서버가 준 두 값(streak, graduate_streak)으로 센다.
 * "한 번 더" 를 박아두면 졸업 기준이 3 이 된 날 화면만 거짓이 되고,
 * 실제로는 두 번 더 맞혀야 하는데 아무 신호도 안 뜬다.
 */
function ResultLine({
  result,
  graduateStreak,
}: {
  result: ReviewResult;
  graduateStreak: number;
}) {
  if (!result.correct) {
    return (
      <span
        style={{
          color: "var(--wrong-deep)",
          fontWeight: "var(--weight-bold)",
        }}
      >
        오답 · {result.answer_text}
      </span>
    );
  }

  // IdleCard 와 같은 판정을 쓴다. 뺄셈 결과를 그대로 믿으면 서버가
  // 1.5 를 줬을 때 "0.5번 더 맞히면 끝" 이 나온다.
  const left = graduateStreak - result.streak;
  const known = counted(left);

  return (
    // 정답은 초록. 오답 코랄과 색으로 갈린다 - 여기는 글자 한 줄이라
    // 형태로 가를 자리가 없고, 문구("정답"/"오답")가 색과 같이 간다.
    <span
      style={{
        color: "var(--correct-deep)",
        fontWeight: "var(--weight-black)",
      }}
    >
      정답
      <span
        className="ml-2"
        style={{
          color: "var(--text-muted)",
          fontWeight: "var(--weight-regular)",
        }}
      >
        {result.graduated
          ? "다 외웠습니다"
          : !known
            ? "연속으로 더 맞히면 끝"
            : left === 1
              ? "한 번 더 맞히면 끝"
              : `${left}번 더 맞히면 끝`}
      </span>
    </span>
  );
}

/* ---- 끝난 뒤 ---- */

function DoneCard({
  answered,
  correct,
  graduated,
  busy,
  error,
  onAgain,
}: {
  answered: number;
  correct: number;
  graduated: number;
  busy: boolean;
  error: string;
  onAgain: () => void;
}) {
  return (
    <div className="rise flex flex-1 flex-col justify-center gap-6 text-center">
      <div>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          이번 판
        </p>
        <p
          className="pop mt-1 text-5xl tabular-nums"
          style={{
            fontFamily: "var(--font-mono)",
            fontWeight: "var(--weight-bold)",
            letterSpacing: "var(--tracking-tighter)",
            color: "var(--foreground)",
          }}
        >
          {correct} / {answered}
        </p>
      </div>

      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        {graduated > 0
          ? `${graduated}개를 다 외워 목록에서 뺐습니다.`
          : "연속으로 맞히면 목록에서 빠집니다."}
      </p>

      <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
        {/* "이어서 더" 가 주된 동작이라 코랄. 홈으로는 흰 알약으로 물러난다 -
            둘 다 코랄이면 여기서 뭘 해야 할지가 사라진다. */}
        <button
          type="button"
          onClick={onAgain}
          disabled={busy}
          className="dv-btn rounded-[var(--radius-pill)] px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-50 sm:px-10"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--coral)",
              color: "var(--text-on-color)",
              border: 0,
              fontWeight: "var(--weight-black)",
              "--lift": "var(--lift-button)",
            } as React.CSSProperties
          }
        >
          {busy ? "여는 중" : "이어서 더"}
        </button>
        <Link
          href={routes.home}
          className="dv-btn inline-flex items-center justify-center rounded-[var(--radius-pill)] px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus sm:px-10"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--paper)",
              color: "var(--foreground)",
              fontWeight: "var(--weight-black)",
              "--lift": "var(--lift-button-paper)",
            } as React.CSSProperties
          }
        >
          홈으로
        </Link>
      </div>

      {/* "이어서 더" 가 실패하는 흔한 경로가 있다 - 이번 판에서 남은
          것을 전부 졸업시키면 서버가 "복습할 것이 없습니다" 로 막는다.
          그게 이 기능의 정상적인 끝이라 자주 만난다. 여기 안 그리면
          버튼만 깜빡이고 아무 일도 안 일어난 것처럼 보인다. */}
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

async function call<T>(body: Record<string, unknown>): Promise<T> {
  const res = await fetch("/api/review", {
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
