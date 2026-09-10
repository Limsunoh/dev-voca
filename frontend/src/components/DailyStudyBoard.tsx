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
      {/* 작은 라벨이라 --text-dim 을 써도 되는 자리다. 본문·설명에는
          --text-muted 를 쓴다(--text-dim 은 라벨용). */}
      <p
        className="text-sm"
        style={{
          fontWeight: "var(--weight-bold)",
          letterSpacing: "var(--tracking-wide)",
          color: "var(--text-muted)",
        }}
      >
        하루 한 번
      </p>
      <h1
        className="mt-2"
        style={{
          fontSize: "var(--text-2xl)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
          color: "var(--foreground)",
        }}
      >
        오늘 얼마나 해볼까요
      </h1>
      <p
        className="mt-2 text-sm"
        style={{
          lineHeight: "var(--leading-relaxed)",
          color: "var(--text-muted)",
        }}
      >
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
        // 옅은 호박 띠. 막혔다는 것을 알리는 자리라 배지 문법을 쓴다
        // (옅은 채움 + 진한 글자). 테두리로 두르지 않는다 - 크림은 경계를
        // 테두리가 아니라 채움과 두께로 만든다.
        <p
          className="mt-5 px-4 py-3 text-sm"
          style={{
            background: "var(--amber-soft)",
            borderRadius: "var(--radius-md)",
            lineHeight: "var(--leading-relaxed)",
            color: "var(--amber-deep)",
          }}
        >
          오늘 {resuming.answered}/{resuming.total}문제까지 풀었습니다. 지금은
          이어서 풀 문제를 낼 수 없습니다. 잠시 뒤 다시 시도해주세요.
        </p>
      )}

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

      <div className="mt-6 flex flex-col gap-2.5">
        {lengths.map((one) => (
          <button
            key={one.value}
            type="button"
            onClick={() => onStart(one.value)}
            // 하다 만 판이 있으면 길이를 다시 고를 수 없다. 눌러봐야
            // 서버가 "이미 시작했다" 로 막는다.
            disabled={busy || (resuming !== null && !resuming.done)}
            // 흰 카드 셋을 나란히 둔다. 코랄로 채우지 않는 이유: 셋 다
            // 같은 자격의 선택지라, 하나만 코랄로 두면 그것을 권하는
            // 것이 되고 셋 다 코랄이면 코랄이 하나라는 규칙이 깨진다.
            // 고르는 자리에서는 카드가 맞다.
            className="dv-card dv-card-press flex items-center justify-between px-5 py-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60"
            style={
              {
                minHeight: 56,
                background: "var(--paper)",
                border: 0,
                borderRadius: "var(--radius-2xl)",
                "--lift": "var(--lift-card)",
              } as React.CSSProperties
            }
          >
            <span
              style={{
                fontSize: "var(--text-md)",
                fontWeight: "var(--weight-black)",
                letterSpacing: "var(--tracking-tight)",
                color: "var(--foreground)",
              }}
            >
              {one.label}
            </span>
            <span
              className="text-right text-sm"
              style={{ color: "var(--text-muted)" }}
            >
              {/* 몇 개를 배우는지 먼저 보여준다. 문제 수만 있으면 길이
                  선택이 "얼마나 오래 걸리나" 로만 읽히는데, 이 기능의
                  값은 그날 몇 단어를 익히느냐에 있다. */}
              {one.words > 0 && (
                <span
                  style={{
                    color: "var(--text-body)",
                    fontWeight: "var(--weight-bold)",
                  }}
                >
                  {one.words}단어 ·{" "}
                </span>
              )}
              {one.questions}문제
              {/* 보너스는 얻는 것이라 초록이다. 코랄은 "지금 눌러야 할 것"
                  이고 여기 셋은 다 같은 자격의 선택지다. */}
              <span
                className="ml-2"
                style={{
                  color: "var(--green-deep)",
                  fontWeight: "var(--weight-black)",
                }}
              >
                +{one.bonus}
              </span>
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
        <span
          className="font-mono text-sm tabular-nums"
          style={{
            color: "var(--text-muted)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          {answered} / {total}
        </span>
        {/* 점수는 잉크로 둔다. 코랄은 이 화면에서 "이어서 익히기" 버튼이
            갖고, 읽기만 하는 값에 강조색을 쓰면 그 뜻이 흐려진다. */}
        <span
          className="font-mono text-sm tabular-nums"
          style={{
            color: "var(--foreground)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          {study?.score ?? 0}점
        </span>
      </div>

      {/* 남은 시간이 아니라 진행률이다. 제한 시간이 없는 공부라 급할
          이유가 없고, 얼마나 남았는지만 알면 된다. */}
      <div
        className="h-1.5 overflow-hidden"
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
            지나온 것이라, 복습 화면·진행 점과 같게 둔다. */}
        <div
          className="h-full transition-[width] duration-300"
          style={{
            width: `${total ? (answered / total) * 100 : 0}%`,
            background: "var(--green)",
            borderRadius: "var(--radius-pill)",
          }}
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
          // 정답은 초록, 오답은 진한 코랄. 오답에 --coral 을 그대로 쓰지
          // 않는 이유는 --wrong-deep 이 그 자리를 위해 있어서다 - 크림
          // 위에서 --coral 은 본문 대비에 못 미친다.
          <span
            style={{
              color: result.correct ? "var(--correct)" : "var(--wrong-deep)",
              fontWeight: "var(--weight-black)",
            }}
          >
            {result.correct ? "정답" : `오답 · ${result.answer_text}`}
          </span>
        )}
      </p>

      {/* 다음 묶음이 기다릴 때만. 이 버튼이 없으면 아래 보기를 눌러
          답하게 되는데, 그 문제는 아직 안 배운 단어로 나온다. */}
      {onLearn && (
        // 이 화면의 코랄 하나. 이 버튼이 떠 있는 동안 보기는 잠겨 있어서
        // (위 QuestionCard 의 busy) 지금 누를 수 있는 것은 이것뿐이다.
        <button
          type="button"
          onClick={onLearn}
          className="dv-btn flex w-full items-center justify-center px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
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
          이어서 익히기
        </button>
      )}

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

function DoneCard({ study }: { study: StudyProgress | null }) {
  // **done 으로는 못 가른다.** 여기 오는 두 경로(초기 phase 판정, 답한 뒤
  // finished)가 둘 다 판을 닫고 온다 - 서버가 _finish 를 부른 뒤 그 인스턴스를
  // 그대로 내려주므로 done 은 항상 참이다. 다 풀었는지는 개수로 본다.
  // 모르면 "여기까지" 쪽으로 둔다. 다 풀지 않았는데 "완료" 라고 하는
  // 것이 그 반대보다 나쁘다.
  const short = study === null || study.answered < study.total;

  return (
    <div className="rise flex flex-1 flex-col justify-center text-center">
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        {short ? "오늘은 여기까지" : "오늘 몫 완료"}
      </p>
      {/* 화면에서 가장 큰 숫자. 잉크로 둔다 - 결과는 읽는 것이고, 이
          화면의 코랄은 아래 "순위표에서 확인" 버튼이 갖는다. 복습 결과
          화면이 같은 자리를 같은 방식으로 그린다. */}
      <p
        className="pop mt-2 font-mono text-5xl tabular-nums"
        style={{
          fontWeight: "var(--weight-bold)",
          letterSpacing: "var(--tracking-tighter)",
          color: "var(--foreground)",
        }}
      >
        {study?.score ?? 0}
      </p>
      {study && (
        <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
          {study.total}문제 중 {study.correct}개 정답
          {/* 보너스는 얻은 것이라 초록. 길이 고르기의 "+5" 와 같은 색이라
              고를 때 본 약속과 받은 결과가 이어진다. */}
          {!short && study.bonus > 0 && (
            <span
              className="ml-1"
              style={{
                color: "var(--green-deep)",
                fontWeight: "var(--weight-black)",
              }}
            >
              +{study.bonus} 보너스
            </span>
          )}
        </p>
      )}

      {short && (
        <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
          낼 수 있는 문제가 떨어져 먼저 마쳤습니다.
        </p>
      )}

      <p className="mt-6 text-sm" style={{ color: "var(--text-muted)" }}>
        일일공부는 하루 한 번입니다. 내일 또 만나요.
      </p>

      <div className="mt-6 flex flex-col gap-2.5">
        {/* 순위표가 주된 동작이라 코랄. 홈으로는 흰 알약으로 물러난다 -
            둘 다 코랄이면 여기서 뭘 해야 할지가 사라진다. */}
        <Link
          href={routes.board()}
          className="dv-btn flex items-center justify-center px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--coral)",
              color: "var(--text-on-color)",
              borderRadius: "var(--radius-pill)",
              fontWeight: "var(--weight-black)",
              letterSpacing: "var(--tracking-tight)",
              "--lift": "var(--lift-button)",
            } as React.CSSProperties
          }
        >
          순위표에서 확인
        </Link>
        <Link
          href={routes.home}
          className="dv-btn flex items-center justify-center px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--paper)",
              color: "var(--foreground)",
              borderRadius: "var(--radius-pill)",
              fontWeight: "var(--weight-black)",
              "--lift": "var(--lift-button-paper)",
            } as React.CSSProperties
          }
        >
          홈으로
        </Link>
      </div>
    </div>
  );
}
