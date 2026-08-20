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

/**
 * 아래 탭바가 덮는 높이(px).
 *
 * 상수로 두지 않고 실측하는 이유: 탭바는 `pb-[env(safe-area-inset-bottom)]`
 * 로 기기마다 두꺼워진다(layout.tsx 가 viewportFit: "cover" 를 켜서 아이폰
 * 에서 이 값이 0 이 아니다). 5rem 만 박아두면 그 차이만큼 버튼이 탭바에
 * 물린다.
 *
 * 탭바는 fixed 라 스크롤 계산에 잡히지 않으므로, 채점 뒤 버튼 위치를 구할
 * 때 이 높이를 직접 빼줘야 한다.
 */
function tabBarHeight(): number {
  // aria-label 이 아니라 data 속성으로 찾는다. 라벨 문구는 접근성을 다듬다
  // 바뀌기 쉬운데, 그때 조용히 못 찾게 되고 스크롤만 탭바 높이만큼 어긋난다.
  const bar = document.querySelector("[data-tabbar]");
  // 로그인·가입 화면에는 탭바가 없다. 거기엔 이 화면도 없지만, 못 찾았을
  // 때 0 을 쓰면 버튼이 가려지므로 5rem 으로 물러선다.
  return bar ? bar.getBoundingClientRect().height : 80;
}

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
  /**
   * 연속 정답 수.
   *
   * 맞은 개수와 따로 센다. "12문제 중 8개" 는 지난 성적이고, 연속은 지금
   * 얼마나 잘 가고 있는지다 - 틀리는 순간 0 으로 떨어져야 의미가 있다.
   */
  const [combo, setCombo] = useState(0);
  /** 방금 판정. 오답일 때 화면을 짧게 흔든다. */
  const [shake, setShake] = useState(0);
  // 방금 푼 단어들. state 로 두면 load 가 렌더 시점의 값을 클로저로
  // 잡아서, 채점 직후 바로 "다음 문제" 를 누르면 방금 푼 단어가
  // 제외 목록에 안 들어간다.
  const recentRef = useRef<number[]>([]);
  // state 가 아니라 ref 인 이유: 연타는 다시 그리기 전에 들어온다.
  // setLoading 은 다음 렌더에야 반영돼서 가드로 쓸 수 없다.
  const loadingRef = useRef(false);
  // "다음 문제" 버튼. 답을 고른 뒤 이 버튼이 보이는 자리까지 스크롤한다.
  //
  // 해설 카드가 아니라 버튼을 기준으로 삼는다. 해설은 설명·예문·번역이 다
  // 있으면 화면 높이를 넘어서, 카드를 맞추면 위쪽만 보이고 버튼은 접힌
  // 아래에 남는다. 버튼을 맞추면 그 위의 해설은 자연히 화면에 들어온다.
  const nextButtonRef = useRef<HTMLButtonElement>(null);

  /**
   * 다음 문제를 받아온다.
   *
   * resetScroll: 화면을 위로 되돌릴지. 기본은 되돌린다 - 채점 때 아래로
   * 내려온 상태라 그대로 두면 새 문제의 지문이 화면 위로 잘려 나간다.
   *
   * 첫 진입과 분류 변경에서는 끈다. 그때는 사용자가 방금 스스로 만든
   * 위치이기 때문이다. 폰에서 분류 칩은 여러 줄이라 아래쪽 칩을 누르려면
   * 스크롤해야 하는데, 누를 때마다 맨 위로 튕기면 분류를 바꿔가며
   * 비교하는 동안 계속 칩 줄까지 다시 내려와야 한다.
   */
  const load = useCallback(
    async (resetScroll = true) => {
      // "다음 문제" 를 연타하면 요청이 겹쳐서 나중에 온 응답이 앞선 것을
      // 덮어쓴다. 화면에 보이는 문제와 토큰이 어긋날 수 있다.
      if (loadingRef.current) return;
      loadingRef.current = true;

      // 상태를 바꾸기 전에 화면부터 올린다. 뒤에 두면 이미 리렌더가 걸려
      // 문서가 짧아지는 중이라 최종 위치가 흔들린다.
      //
      // behavior 를 "auto" 로 명시하는 이유: 채점 때 시작한 smooth 스크롤이
      // 아직 진행 중일 수 있다. 생략하면 일부 브라우저가 진행 중인 이동을
      // 끊지 않아서, 위로 올라가는 대신 원래 가던 아래쪽으로 계속 간다.
      if (resetScroll) window.scrollTo({ top: 0, behavior: "auto" });

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
    },
    [category],
  );

  // 첫 문제. 화면은 그대로 둔다 - 분류 칩을 누르고 온 자리일 수 있다.
  useEffect(() => {
    void load(false);
  }, [load]);

  /**
   * 채점이 끝나면 "다음 문제" 버튼이 보이는 자리까지 화면을 옮긴다.
   *
   * 이게 없으면 해설과 버튼이 화면 밖 아래에 생기는데 보이는 부분은
   * 그대로라, 답을 골랐는데도 아무 일도 안 일어난 것처럼 보인다.
   *
   * result 가 아니라 picked 를 조건으로 삼는 이유: 채점이 실패하면
   * result 는 null 로 남지만 에러 배너와 "다음 문제" 버튼은 그대로
   * 생긴다. result 만 보면 그 경우에 화면이 안 움직여서, 보기가 전부
   * 잠긴 채 안내도 넘어갈 버튼도 안 보이는 상태가 된다 - 서버가
   * 채점만 못 하는 상황에서 화면이 얼어붙은 것처럼 보인다.
   *
   * pick() 안이 아니라 여기인 이유: 그 시점에는 setResult 가 큐에만
   * 들어가 해설 카드가 아직 DOM 에 없다. 버튼 ref 는 이전 렌더부터
   * 붙어 있어서 좌표를 읽을 수는 있는데, 그 값이 카드 높이만큼 어긋난다.
   * effect 는 커밋 뒤에 돌아 레이아웃이 확정돼 있다.
   *
   * 해설이 아니라 버튼을 기준으로 삼는 이유: 해설은 설명·예문·번역이
   * 다 있으면 화면 높이를 넘어서, 카드를 맞추면 위쪽만 보이고 버튼은
   * 접힌 아래에 남는다. 버튼을 맞추면 그 위 해설은 자연히 들어온다.
   */
  useEffect(() => {
    // 아직 고르지 않았으면 옮길 것이 없다.
    if (picked === null) return;
    // 채점도 실패도 아직이면(응답 대기 중) 화면이 그대로다.
    if (!result && !error) return;

    const button = nextButtonRef.current;
    if (!button) return;

    // 버튼 아래 모서리가 탭바 위에 오도록 목표를 직접 계산한다.
    // scrollIntoView 를 쓰지 않는 이유: 대상이 화면보다 크면 block 설정과
    // 무관하게 시작 모서리를 맞춰서, 고치려던 상황이 그대로 돌아온다.
    // 탭바와 버튼 사이 숨 쉴 틈. tabBarHeight() 가 safe-area 를 포함한
    // 실측값이라 이건 순수한 여백이고, 기기가 달라져도 줄어들지 않는다.
    const gap = 16;
    const target =
      window.scrollY +
      button.getBoundingClientRect().bottom -
      window.innerHeight +
      tabBarHeight() +
      gap;

    // 이미 보이면 화면은 그대로 둔다. 답을 고를 때마다 흔들리면 방금 고른
    // 보기를 눈으로 다시 찾아야 한다. 데스크톱처럼 화면이 길면 대개 여기다.
    if (target > window.scrollY) {
      // behavior 를 "auto" 로 둔다. smooth 를 쓰면 이 화면에서는 아무 일도
      // 일어나지 않는다 - 채점 직후의 리렌더와 겹치면 브라우저가 진행 중인
      // 부드러운 이동을 버린다(실측: scrollTo({top:156}) 가 불렸는데
      // scrollY 가 0 이었고, 같은 시점에 수동 scrollTo 는 정상이었다).
      //
      // 부드럽게 만들려고 rAF 뒤에 smooth 를 한 번 더 부르는 방법도 써봤는데,
      // 그 사이(약 16ms)에 사용자가 손으로 스크롤하면 두 번째 호출이 그것을
      // 도로 끌어내린다. auto 로 이미 목표에 도착해 있으므로 두 번째가
      // 다듬을 거리도 없다 - 얻는 것 없이 위험만 남는다.
      //
      // 움직임을 줄이겠다고 한 설정을 따로 보지 않는 이유: auto 는 애초에
      // 애니메이션이 없어서 그 설정과 무관하게 같은 결과다.
      window.scrollTo({ top: target, behavior: "auto" });
    }

    // 포커스도 옮긴다. 화면만 움직이면 포커스는 방금 고른 보기에 남는데,
    // 그 보기는 해설 카드 높이만큼 화면 위로 밀려나 있다. 키보드로 풀던
    // 사람은 보이지 않는 곳에 서 있게 되고, 화면 낭독기의 읽는 위치와
    // 눈에 보이는 위치도 어긋난다.
    //
    // 스크롤 여부와 무관하게 옮긴다. 화면이 안 움직인 경우에도 방금 고른
    // 보기는 disabled 가 되어 포커스를 잃는다.
    //
    // preventScroll 이 있어야 방금 계산한 자리를 브라우저가 다시 건드리지
    // 않는다. 마우스로 고른 사람에게 포커스 링이 뜨지는 않는다 - 버튼이
    // focus-visible 만 쓴다.
    button.focus({ preventScroll: true });
  }, [picked, result, error]);

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

      // 연속은 맞으면 오르고 틀리면 0 이다. 틀렸을 때 유지하면 "연속" 이
      // 아니라 그냥 누적이 된다.
      setCombo((c) => (graded.correct ? c + 1 : 0));

      // 틀렸을 때만 화면을 짧게 흔든다. 값을 올려 애니메이션을 다시
      // 재생시킨다 - boolean 이면 연속으로 틀렸을 때 두 번째부터 안 뛴다.
      if (!graded.correct) setShake((n) => n + 1);
      // 채점 뒤 화면을 옮기는 일은 아래 useEffect 가 맡는다. 여기서 하면
      // 해설 카드가 아직 DOM 에 없어 버튼 좌표를 잘못 읽는다.
      //
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
      <p className="mt-10 text-center text-slate-400">
        문제를 가져오는 중입니다.
      </p>
    );
  }

  if (error && !question) {
    return (
      <div className="mt-10">
        <p className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-4 text-amber-100">
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
            setCombo(0);
            void load();
          }}
          className="mt-4 min-h-12 rounded-full bg-focus px-5 font-semibold text-focus-on transition-[scale] duration-[120ms] ease-press active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
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
        {/* 분류 칩(CategoryChip)의 비링크 모양과 같은 문법. 같은 화면에
            필터 칩이 이미 여러 줄 서 있어서, 여기까지 다른 회색을 쓰면
            같은 알약이 세 종류가 된다. */}
        <span className="rounded-full bg-white/8 px-3 py-1 text-sm text-slate-300">
          {question.kind_label}
        </span>
        {score.solved > 0 && (
          <div className="flex items-center gap-2.5">
            {/* 연속 정답. 두 개부터 보여준다 - 하나는 그냥 맞힌 것이지
                연속이 아니다. 끊기면 사라져서 "지금 몇 개째" 가 한눈에
                보인다.

                key 로 숫자를 넘겨 오를 때마다 다시 마운트시킨다. 그래야
                등장 애니메이션이 매번 재생된다. */}
            {combo >= 2 && (
              <span
                key={combo}
                className="pop inline-flex items-center gap-1 rounded-full bg-focus/15 px-2.5 py-1 text-sm font-semibold text-focus"
              >
                <span aria-hidden>연속</span>
                {combo}
              </span>
            )}
            {/* 숫자가 바뀔 때 자리가 밀리지 않게 고정폭 숫자를 쓴다.
                9 에서 10 이 되면 글자가 옆으로 밀려 눈에 거슬린다. */}
            <span className="text-sm text-slate-400 tabular-nums">
              {score.solved}문제 중 {score.correct}개
            </span>
          </div>
        )}
      </div>

      <h2 className="mt-4 text-sm font-medium text-focus">
        {question.question}
      </h2>

      <Prompt kind={question.kind} text={question.prompt} />

      {/* 틀리면 보기 묶음이 짧게 흔들린다.
          key 로 횟수를 넘겨 매번 다시 마운트시킨다 - 클래스만 토글하면
          연속으로 틀렸을 때 두 번째부터 애니메이션이 안 뛴다.

          조건이 `shake > 0` 이 아니라 `result 가 오답` 인 이유: 누적값은
          한 번 틀리면 계속 참이라, 그 뒤로는 맞혀도 새 문제로 넘어가도
          클래스가 붙은 채 남는다(실측으로 14번 중 14번 붙어 있었다).
          지금 문제의 판정을 봐야 이번에 틀렸을 때만 흔들린다.

          움직임을 줄인 사용자에게는 globals.css 의 reduced-motion 블록이
          시간을 0 으로 만들어 흔들리지 않는다. */}
      {/* 흔들림에 key 를 쓰지 않는다. 요소를 다시 마운트시키면 그 사이에
          스크롤 effect 가 버튼 좌표를 읽어 목표가 어긋난다(실측: 버튼이
          993px 인데 목표가 214px 로 계산돼 화면이 제자리였다).

          대신 animationName 을 짝수/홀수로 번갈아 준다. 같은 이름이면
          두 번째 오답부터 애니메이션이 안 뛰는데, 이름이 바뀌면 브라우저가
          새 애니메이션으로 보고 매번 재생한다. DOM 은 그대로라 레이아웃이
          흔들리지 않는다. */}
      <ul
        className={`mt-6 grid gap-2 ${
          result && !result.correct
            ? shake % 2 === 0
              ? "shake"
              : "shake-alt"
            : ""
        }`}
      >
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
          className="mt-4 rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-100"
        >
          {error}
        </p>
      )}

      {/* aria-live 를 바깥에 두고 항상 렌더한다. 리전 자체가 내용과 함께
          새로 생기면 화면 낭독기가 대부분 그 등장을 알리지 않는다 - 리전은
          미리 있어야 이후 변화를 감시한다. 안쪽만 조건부로 바꾼다. */}
      <div aria-live="polite">
        {result && <Explanation result={result} />}
      </div>

      {picked !== null && (
        <button
          ref={nextButtonRef}
          type="button"
          onClick={() => void load()}
          className="mt-6 min-h-12 w-full rounded-full bg-focus px-4 font-semibold text-focus-on transition-[scale] duration-[120ms] ease-press active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
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
      <p className="mt-3 whitespace-pre-line text-lg leading-relaxed text-slate-200">
        {text}
      </p>
    );
  }

  // 홈의 "오늘의 단어" 와 같은 급으로 둔다. 이 화면에서 가장 먼저 읽어야
  // 할 것이 문제이므로, 필터 칩 줄보다 확실히 커야 눈이 여기서 멈춘다.
  //
  // 줄간격을 kind 로 가른다. meaning 문제의 지문은 영어 단어 하나라 감기지
  // 않아서 홈처럼 leading-none 으로 바짝 붙여도 되지만, term 문제의 지문은
  // 한글 뜻이라 폰에서 두 줄로 감긴다("네트워크에서 위치를 나타내는 주소
  // 체계" 가 390px 에서 두 줄). 거기에 leading-none 을 주면 줄 높이가 글자
  // 크기와 같아져 받침과 다음 줄 윗선이 맞닿는다.
  //
  // tracking 도 한 자리에서 정한다. 기본값에 tracking-tight 를 두고 삼항에서
  // tracking-tighter 를 덧붙이면 같은 속성이 두 번 올라가고, 어느 쪽이 이기는지
  // 클래스 순서가 아니라 Tailwind 의 생성 순서가 정한다.
  // 줄간격은 양쪽 다 leading-tight 다. 영어 용어도 안전하지 않다 -
  // "eventual consistency" 가 390px 에서 330px 를 먹어 한 줄에 겨우 들어가고,
  // 이보다 조금만 길면 감긴다. 한 줄일 때는 leading-none 과 보이는 차이가
  // 없으니 감길 때만 벌어지는 쪽으로 통일한다.
  const shape =
    kind === "meaning"
      ? "font-mono leading-tight tracking-tighter"
      : "leading-tight tracking-tight";

  return (
    <p className={`mt-3 text-3xl font-bold text-slate-50 ${shape}`}>{text}</p>
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

  // 아직 결과를 모르는 상태(picked·idle)는 중립으로 둔다.
  const markTone = {
    correct: "text-emerald-200",
    wrong: "text-rose-200",
    picked: "text-slate-300",
    idle: "text-slate-300",
  }[state];

  // 표면은 learn 의 카드와 같은 문법으로 둔다(반투명 + white/N 테두리).
  // 색을 리터럴로 채우면 뒤에 깔린 surface-quiz 배경이 통째로 가려져서,
  // 문제풀이 화면만 다른 앱처럼 보인다.
  //
  // 고르기 전 테두리가 유일한 "여기가 버튼" 신호다. slate-700 은 어두운
  // 배경에서 1.8:1 이라 버튼 넷이 그냥 텍스트 넉 줄로 보인다.
  // WCAG 1.4.11 은 컨트롤 경계에 3:1 을 요구한다 - SearchInput 이 같은
  // 이유로 이미 white/40 을 쓰고 있다.
  const style = {
    // 누르면 배경이 밝아진다. 축소만으로는 이 버튼에서 거의 안 보인다 -
    // 높이가 50px 뿐이라 0.96 이어도 위아래로 1px 밖에 안 움직인다(카드는
    // 133px 이라 같은 값에서 2.7px 움직여 눈에 띈다). 납작한 요소는 크기
    // 대신 색이 신호를 맡아야 한다.
    // hover·active 를 enabled: 로 감싼다. 채점이 끝나면 고르지 않은 보기도
    // idle 로 돌아오는데, 그때는 disabled 라 누를 수 없다. 그런데 hover 는
    // disabled 와 무관하게 걸려서, 마우스를 올리면 테두리가 밝아져 아직
    // 누를 수 있는 것처럼 보인다(실측: 알파 0.4 -> 0.6).
    idle: "border-white/40 bg-slate-950/45 enabled:hover:border-white/60 enabled:active:border-white/70 enabled:active:bg-slate-800/70",
    // 고른 직후. 채점을 기다리는 짧은 순간이라 강조색으로 "이걸 골랐다" 만
    // 말하고, 맞았는지는 아직 말하지 않는다.
    //
    // 배경을 누름 상태와 같은 밝기로 유지한다. 기본 배경으로 돌려놓으면
    // 손을 뗀 순간 밝기가 원래대로 내려가서, 서버 응답을 기다리는 바로 그
    // 구간에 "눌렀다" 는 신호가 꺼진다. 그 구간이 이 화면에서 피드백이
    // 가장 필요한 자리다(느린 응답을 흉내내 재현했다).
    picked: "border-focus bg-slate-800/70",
    // 정답·오답은 채도를 낮춘 톤으로 둔다. emerald-950 같은 원색을 깔면
    // 청록 팔레트와 따로 놀고, 배경 그라디언트도 덮어버린다.
    // MetaBadge 의 난이도 배지가 쓰는 -400/N 문법과 같은 계열이다.
    //
    // 알파가 /75 인 이유: 채움(-400/10)은 배경 대비 1.1:1 이라 사실상 안
    // 보이므로, 상태를 전하는 그래픽 신호가 테두리 하나뿐이다. /60 으로
    // 두면 rose 가 .surface-quiz 위쪽 밝은 구간에서 2.9:1 이라 WCAG
    // 1.4.11 의 3:1 에 못 미친다. 둘을 같이 올려야 정답이 오답보다
    // 흐려 보이지 않는다.
    correct: "border-emerald-400/75 bg-emerald-400/10",
    wrong: "border-rose-400/75 bg-rose-400/10",
  }[state];

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      // 누르면 살짝 들어간다. 채점은 서버 왕복이라 이게 없으면 손가락을 뗀
      // 뒤 응답이 올 때까지 아무 반응이 없다 - 눌리긴 한 건지 알 수 없다.
      //
      // 0.96 은 globals.css 의 "누름 피드백" 절이 정한 값이다. 보기 넷이
      // 붙어 있어 흔들려 보일까 봐 0.98 로 뒀었는데, 그 정도로는 눌러도
      // 보이지 않아 있으나 마나였다.
      //
      // 채점 뒤에는 disabled 라 브라우저가 :active 를 주지 않는다. 따로 끌
      // 필요가 없다.
      //
      // 목록에 transform 이 아니라 scale 을 적는다. Tailwind v4 의
      // active:scale-* 는 transform 이 아니라 별개의 scale 속성을 쓴다.
      // transform 만 적어두면 전환 대상에 안 잡혀서 크기가 툭 바뀐다.
      className={`flex min-h-12 w-full items-center justify-between gap-3 rounded-lg border px-4 py-3 text-left transition-[scale,border-color,background-color] duration-[120ms] ease-press active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-default ${style}`}
    >
      {/* min-w-0 이 있어야 flex 항목이 내용보다 작아진다. 글자를 끊는 쪽은
          globals.css 의 base 규칙(body 상속)이 맡는다. 둘 중 하나만 있으면
          보기 문구가 길 때 버튼이 화면 밖으로 밀린다. */}
      <span className={`min-w-0 text-slate-200 ${mono ? "font-mono" : ""}`}>
        {text}
      </span>
      {mark && (
        // 정답·오답 글자도 테두리와 같은 톤으로 둔다. 회색으로 두면 방금
        // 무슨 일이 일어났는지 눈이 먼저 읽는 신호가 테두리 하나뿐이다.
        //
        // 삼항이 아니라 맵인 이유: 삼항으로 두면 correct 가 아닌 모든 상태가
        // 오답 색이 된다. 지금은 mark 가 빈 문자열이라 이 span 이 안 그려져
        // 드러나지 않지만, 나중에 picked 에 "채점 중" 같은 문구를 넣는 순간
        // 아직 결과를 모르는 상태가 빨갛게 뜬다.
        //
        // 색 전환을 여기 두는 이유도 같은 미래 때문이다. 지금은 이 span 이
        // 채점된 뒤에야 처음 생겨서 전환할 이전 값이 없지만, picked 에 문구가
        // 붙으면 계속 살아 있게 되어 색만 툭 바뀐다. 버튼 쪽에 걸어봐야
        // 자식 글자색에는 닿지 않는다.
        <span
          className={`shrink-0 text-xs font-semibold transition-[color] duration-[120ms] ease-press ${markTone}`}
        >
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
    // 읽어주는 것은 이 카드를 감싼 바깥 div 의 aria-live 가 맡는다 - 여기에
    // 또 걸면 리전 안에 리전이 생겨 낭독이 겹친다.
    <section
      // 보기 버튼과 같은 표면. 해설만 불투명하게 두면 이 카드만 떠 보인다.
      //
      // 올라오며 나타난다. 이게 없으면 답을 고른 순간 화면 아래가 갑자기
      // 길어지고 곧바로 스크롤이 따라붙어서, 무엇이 생겼는지 모른 채 화면만
      // 움직인 것처럼 보인다.
      //
      // 높이는 애니메이트하지 않는다. 해설이 붙은 뒤 버튼 위치를 재서
      // 스크롤할 자리를 정하는데(위 useEffect), 그때 높이가 아직 변하는
      // 중이면 목표가 어긋난다. 자리는 즉시 잡고 그 안에서 떠오르기만 한다.
      className="rise mt-6 rounded-lg border border-white/12 bg-slate-950/45 p-4"
    >
      {/* 맞았는지 틀렸는지가 이 카드에서 가장 먼저 읽혀야 한다. 회색으로
          두면 보기 버튼의 테두리 색이 유일한 신호가 된다. */}
      <p
        className={`text-sm font-semibold ${
          result.correct ? "text-emerald-200" : "text-rose-200"
        }`}
      >
        {result.correct ? "맞았습니다" : "정답은 이것입니다"}
      </p>

      <div className="mt-2 flex flex-wrap items-baseline gap-2">
        <h3 className="font-mono text-xl font-bold text-slate-50">
          {word.term}
        </h3>
        {word.pronunciation && (
          // 발음기호는 고정폭으로 두지 않는다. IPA 기호가 고정폭 글꼴에서
          // 깨지거나 폭이 어긋나는 경우가 있다. lang 은 한글 폰트가 IPA 를
          // 잘못 렌더하는 것을 막는다.
          <span lang="en-US" className="text-slate-300">
            {word.pronunciation}
          </span>
        )}
      </div>

      <p className="mt-1 text-slate-100">{word.meaning}</p>

      {word.description && (
        <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-slate-300">
          {word.description}
        </p>
      )}

      {word.example && (
        <div className="mt-3 border-l-2 border-white/15 pl-3">
          <p className="font-mono text-sm text-slate-200">{word.example}</p>
          {word.example_translation && (
            <p className="mt-1 text-sm text-slate-400">
              {word.example_translation}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
