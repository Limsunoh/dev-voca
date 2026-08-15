"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { GradeResult, Question } from "@/lib/api/quiz";

/**
 * 백엔드를 직접 부르지 않고 같은 출처의 중계(/api/quiz)를 부른다.
 * 백엔드 주소는 서버 전용 환경변수라 브라우저에서 읽을 수 없고,
 * 직접 부르면 CORS 설정도 따로 열어야 한다.
 */
async function fetchQuestion(params: {
  category?: string;
  exclude?: string;
}): Promise<Question> {
  const query = new URLSearchParams();
  if (params.category) query.set("category", params.category);
  if (params.exclude) query.set("exclude", params.exclude);

  const res = await fetch(`/api/quiz?${query}`, { cache: "no-store" });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

async function submitAnswer(
  token: string,
  picked: number,
): Promise<GradeResult> {
  const res = await fetch("/api/quiz", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, picked }),
  });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

/**
 * 문제풀기 판.
 *
 * 서버 컴포넌트로 못 만든다. 보기를 고르고 채점하고 다음 문제로 넘어가는
 * 흐름이 전부 클라이언트 상태다.
 *
 * 방금 낸 문제를 다시 내지 않으려고 푼 단어 id 를 모아 보낸다. 다만
 * 무한정 쌓으면 URL 이 길어져서 최근 것만 남긴다.
 */

/**
 * exclude 로 보낼 최근 문제 수.
 *
 * 백엔드가 받는 상한(MAX_EXCLUDE_IDS)과 같은 값이다. 더 보내도 잘린다.
 *
 * 30 으로 두면 한 분류를 다 풀어도 목록이 잘려나가 계속 새 문제가
 * 나온다 - 가장 작은 분류가 58개다. 100 이면 가장 큰 분류(96개)도
 * 끝까지 풀 수 있어 "다 풀었습니다" 안내에 실제로 도달한다.
 */
const RECENT_LIMIT = 100;

type Props = {
  /** 분류를 좁힐 때. 없으면 전체에서 낸다. */
  category?: string;
};

export function QuizBoard({ category }: Props) {
  const [question, setQuestion] = useState<Question | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [result, setResult] = useState<GradeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [score, setScore] = useState({ solved: 0, correct: 0 });
  // 방금 푼 단어들. state 로 두면 load 가 렌더 시점의 값을 클로저로
  // 잡아서, 채점 직후 바로 "다음 문제" 를 누르면 방금 푼 단어가
  // 제외 목록에 안 들어간다.
  const recentRef = useRef<number[]>([]);
  // state 가 아니라 ref 인 이유: 연타는 다시 그리기 전에 들어온다.
  // setLoading 은 다음 렌더에야 반영돼서 가드로 쓸 수 없다.
  const loadingRef = useRef(false);

  const load = useCallback(async () => {
    // "다음 문제" 를 연타하면 요청이 겹쳐서 나중에 온 응답이 앞선 것을
    // 덮어쓴다. 화면에 보이는 문제와 토큰이 어긋날 수 있다.
    if (loadingRef.current) return;
    loadingRef.current = true;

    setLoading(true);
    setError(null);
    setPicked(null);
    setResult(null);

    try {
      const q = await fetchQuestion({
        category,
        exclude: recentRef.current.join(","),
      });
      setQuestion(q);
    } catch (e) {
      // 옛 문제를 지운다. 남겨두면 이미 답을 본 문제가 다시 뜨고,
      // picked 가 비어 있어 "다음 문제" 버튼도 "다시 시도" 버튼도
      // 안 나오는 막다른 화면이 된다.
      setQuestion(null);
      setError(
        e instanceof Error && e.message === "404"
          ? "낼 수 있는 문제를 다 풀었습니다. 분류를 넓히거나 처음부터 다시 시작해보세요."
          : "문제를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.",
      );
    } finally {
      setLoading(false);
      loadingRef.current = false;
    }
  }, [category]);

  // 첫 문제.
  useEffect(() => {
    void load();
  }, [load]);

  async function pick(choiceId: number) {
    if (!question || picked !== null) return;

    setPicked(choiceId);
    try {
      const graded = await submitAnswer(question.token, choiceId);
      setResult(graded);
      setScore((s) => ({
        solved: s.solved + 1,
        correct: s.correct + (graded.correct ? 1 : 0),
      }));
      // 맞힌 것만 제외 목록에 넣는다. 틀린 단어야말로 다시 봐야 하는데
      // 여기에 넣으면 그 세션에서 가장 확실하게 안 나오는 단어가 된다.
      if (graded.correct) {
        recentRef.current = [graded.answer_id, ...recentRef.current].slice(
          0,
          RECENT_LIMIT,
        );
      }
    } catch {
      // picked 를 되돌리지 않는다. 되돌리면 "다음 문제" 버튼이 사라져
      // 안내대로 넘어갈 방법이 없어지고, 같은 토큰으로 다시 채점된다.
      setError("채점하지 못했습니다. 다음 문제로 넘어가주세요.");
    }
  }

  if (loading) {
    return (
      <p className="mt-10 text-center text-slate-500 dark:text-slate-400">
        문제를 가져오는 중입니다.
      </p>
    );
  }

  if (error && !question) {
    return (
      <div className="mt-10">
        <p className="rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          {error}
        </p>
        <button
          type="button"
          onClick={() => {
            // 푼 목록을 비우고 다시 부른다. 다 풀어서 404 가 난
            // 경우에는 그냥 재시도하면 같은 404 가 반복된다.
            // 점수도 같이 비운다 - 처음부터 다시인데 이전 판 숫자가
            // 이어지면 몇 개를 맞혔는지 알 수 없다.
            recentRef.current = [];
            setScore({ solved: 0, correct: 0 });
            void load();
          }}
          className="mt-4 rounded-md bg-slate-900 px-4 py-2 font-medium text-white dark:bg-slate-100 dark:text-slate-900"
        >
          처음부터 다시
        </button>
      </div>
    );
  }

  if (!question) return null;

  return (
    <div className="mt-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {question.kind_label}
        </span>
        {score.solved > 0 && (
          <span className="text-sm text-slate-500 dark:text-slate-400">
            {score.solved}문제 중 {score.correct}개 정답
          </span>
        )}
      </div>

      <h2 className="mt-4 text-sm font-semibold text-slate-500 dark:text-slate-400">
        {question.question}
      </h2>

      <Prompt kind={question.kind} text={question.prompt} />

      <ul className="mt-6 grid gap-2">
        {question.choices.map((choice) => (
          <li key={choice.id}>
            <ChoiceButton
              text={choice.text}
              // 설명 문제는 보기가 단어라 고정폭이 읽기 좋다.
              mono={question.kind !== "meaning"}
              state={choiceState(choice.id, picked, result)}
              disabled={picked !== null}
              onClick={() => void pick(choice.id)}
            />
          </li>
        ))}
      </ul>

      {/* 문제가 떠 있는 상태의 에러(주로 채점 실패). 위쪽 가드는
          문제조차 못 받은 경우만 다뤄서 여기가 따로 필요하다. */}
      {error && question && (
        <p
          role="alert"
          className="mt-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          {error}
        </p>
      )}

      {result && <Explanation result={result} />}

      {picked !== null && (
        <button
          type="button"
          onClick={() => void load()}
          className="mt-6 w-full rounded-md bg-slate-900 px-4 py-3 font-medium text-white transition hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
        >
          다음 문제
        </button>
      )}
    </div>
  );
}

/** 보기의 상태. 채점 전에는 고른 것만 표시하고, 채점 후 정답·오답을 가른다. */
type ChoiceState = "idle" | "picked" | "correct" | "wrong";

function choiceState(
  id: number,
  picked: number | null,
  result: GradeResult | null,
): ChoiceState {
  if (result) {
    if (id === result.answer_id) return "correct";
    if (id === picked) return "wrong";
    return "idle";
  }
  return id === picked ? "picked" : "idle";
}

function Prompt({ kind, text }: { kind: string; text: string }) {
  // 단어를 보여주는 문제는 크고 고정폭으로, 설명은 읽기 좋게 본문체로.
  if (kind === "description") {
    return (
      <p className="mt-3 whitespace-pre-line text-lg text-slate-800 dark:text-slate-200">
        {text}
      </p>
    );
  }

  return (
    <p
      className={`mt-3 text-3xl font-bold text-slate-900 dark:text-slate-100 ${
        kind === "meaning" ? "font-mono" : ""
      }`}
    >
      {text}
    </p>
  );
}

function ChoiceButton({
  text,
  mono,
  state,
  disabled,
  onClick,
}: {
  text: string;
  mono: boolean;
  state: ChoiceState;
  disabled: boolean;
  onClick: () => void;
}) {
  // 색만으로 정답·오답을 구분하지 않는다. 색각 이상이 있으면 안 보인다.
  const mark = { correct: "정답", wrong: "오답", picked: "", idle: "" }[state];

  const style = {
    // 고르기 전 테두리가 유일한 "여기가 버튼" 신호다. slate-700 은 어두운
    // 배경에서 1.8:1 이라 버튼 넷이 그냥 텍스트 넉 줄로 보인다.
    // WCAG 1.4.11 은 컨트롤 경계에 3:1 을 요구한다 - SearchInput 이 같은
    // 이유로 이미 white/40 을 쓰고 있다.
    idle: "border-slate-200 hover:border-slate-400 dark:border-white/40 dark:hover:border-white/60",
    picked: "border-slate-900 dark:border-slate-100",
    correct: "border-emerald-500 bg-emerald-50 dark:bg-emerald-950",
    wrong: "border-rose-400 bg-rose-50 dark:bg-rose-950",
  }[state];

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex w-full items-center justify-between gap-3 rounded-lg border px-4 py-3 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-default ${style}`}
    >
      {/* min-w-0 이 있어야 flex 항목이 내용보다 작아진다. 글자를 끊는 쪽은
          globals.css 의 base 규칙(body 상속)이 맡는다. 둘 중 하나만 있으면
          보기 문구가 길 때 버튼이 화면 밖으로 밀린다. */}
      <span
        className={`min-w-0 text-slate-800 dark:text-slate-200 ${mono ? "font-mono" : ""}`}
      >
        {text}
      </span>
      {mark && (
        <span className="shrink-0 text-xs font-semibold text-slate-600 dark:text-slate-300">
          {mark}
        </span>
      )}
    </button>
  );
}

function Explanation({ result }: { result: GradeResult }) {
  const { word } = result;

  return (
    // 채점 결과는 버튼 색으로만 알리면 화면을 못 보는 사람에게 안 닿는다.
    // 새로 나타나는 영역이라 aria-live 로 읽어준다.
    <section
      aria-live="polite"
      className="mt-6 rounded-lg border border-slate-200 p-4 dark:border-slate-800"
    >
      <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">
        {result.correct ? "맞았습니다" : "정답은 이것입니다"}
      </p>

      <div className="mt-2 flex flex-wrap items-baseline gap-2">
        <h3 className="font-mono text-xl font-bold text-slate-900 dark:text-slate-100">
          {word.term}
        </h3>
        {word.pronunciation && (
          <span lang="en-US" className="text-slate-500 dark:text-slate-400">
            {word.pronunciation}
          </span>
        )}
      </div>

      <p className="mt-1 text-slate-800 dark:text-slate-200">{word.meaning}</p>

      {word.description && (
        <p className="mt-3 whitespace-pre-line text-sm text-slate-600 dark:text-slate-400">
          {word.description}
        </p>
      )}

      {word.example && (
        <div className="mt-3">
          <p className="font-mono text-sm text-slate-700 dark:text-slate-300">
            {word.example}
          </p>
          {word.example_translation && (
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              {word.example_translation}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
