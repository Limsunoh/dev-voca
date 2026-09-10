"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Burst } from "@/components/Burst";
import { Reaction } from "@/components/Reaction";
import type { GradeResult, QuizContent, Question } from "@/lib/api/quiz";
import { Reading } from "./Reading";

/**
 * 백엔드를 직접 부르지 않고 같은 출처의 중계(/api/quiz)를 부른다.
 * 백엔드 주소는 서버 전용 환경변수라 브라우저에서 읽을 수 없고,
 * 직접 부르면 CORS 설정도 따로 열어야 한다.
 */
async function fetchQuestion(params: {
  category?: string;
  exclude?: string;
  content: QuizContent;
}): Promise<Question> {
  const query = new URLSearchParams();
  if (params.category) query.set("category", params.category);
  if (params.exclude) query.set("exclude", params.exclude);
  if (params.content !== "words") query.set("content", params.content);

  const res = await fetch(`/api/quiz?${query}`, { cache: "no-store" });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

async function submitAnswer(
  token: string,
  picked: number,
  content: QuizContent,
): Promise<GradeResult> {
  // 채점도 같은 콘텐츠로 보낸다. 문장 문제를 단어 쪽에 채점시키면
  // 토큰은 유효한데 정답을 엉뚱한 표에서 찾는다.
  const query = content === "words" ? "" : `?content=${content}`;
  const res = await fetch(`/api/quiz${query}`, {
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
 * **지금은 항상 0 이다.** 이 컴포넌트를 쓰는 /test/words 가 탭바를 숨기는
 * 화면이기 때문이다(routes 의 immersiveRoutes 참고). 탭바 높이를 재고 있는
 * 것으로 읽고 값을 믿지 마라 - 재는 대상이 화면에 없다.
 *
 * 그래도 남겨두는 이유: 이 컴포넌트가 탭바 있는 화면에서 쓰일 여지가 있다.
 * 문장 문제가 열리면 그 화면이 판이 아니라 연습이라 탭바를 둘 수 있고,
 * 그때 이 계산이 없으면 채점 뒤 "다음 문제" 버튼이 탭바 뒤로 들어간다.
 * 판단을 호출부에 흩지 않고 여기가 한다.
 *
 * 상수로 두지 않고 실측하는 이유: 탭바는 `pb-[env(safe-area-inset-bottom)]`
 * 로 기기마다 두꺼워진다(layout.tsx 가 viewportFit: "cover" 를 켜서 아이폰
 * 에서 이 값이 0 이 아니다). 5rem 만 박아두면 그 차이만큼 버튼이 물린다.
 */
function tabBarHeight(): number {
  // aria-label 이 아니라 data 속성으로 찾는다. 라벨 문구는 접근성을 다듬다
  // 바뀌기 쉬운데, 그때 조용히 못 찾게 되고 스크롤만 탭바 높이만큼 어긋난다.
  const bar = document.querySelector("[data-tabbar]");
  // 못 찾으면 0. 예전에는 5rem 으로 물러섰는데, 탭바를 없앤 뒤로는 그것이
  // 없는 탭바만큼 더 스크롤해서 문제를 화면 위로 밀어 올렸다.
  return bar ? bar.getBoundingClientRect().height : 0;
}

type Props = {
  /** 분류를 좁힐 때. 없으면 전체에서 낸다. */
  category?: string;
  /** 무엇으로 문제를 낼지. 기본은 단어. */
  content?: QuizContent;
};

export function QuizBoard({ category, content = "words" }: Props) {
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
  /** 방금 판정. 정답일 때 조각이 터진다. */
  const [burst, setBurst] = useState(0);
  /**
   * 걸어오는 사람. 맞히든 틀리든 오므로 burst·shake 를 못 쓴다.
   *
   * 횟수와 판정을 같이 들고 있는 이유: 판정만 두면 연속으로 같은 결과가
   * 나왔을 때 값이 안 바뀌어 다시 안 뛴다. 횟수만 두면 따봉인지 뒤통수인지
   * 모른다.
   *
   * 한 덩이로 묶은 것은 **둘이 한 사건이기 때문**이다. 따로 두면 나중에
   * 누군가 한쪽만 갱신할 여지가 생긴다 - key 로 쓰는 fire 와 색을 정하는
   * correct 가 어긋나면 지난 연출이 새 색으로 뜬다.
   */
  const [reaction, setReaction] = useState({ fire: 0, correct: false });
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
          content,
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
    [category, content],
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

    // 맞혔으면 축포가 먼저다.
    //
    // 둘을 같은 순간에 하면 서로를 지운다. 폭죽은 화면 한가운데에서 터지는데
    // 그 순간 화면이 300px 튀어서, 눈이 새 위치를 찾는 사이에 조각이 다
    // 사라진다(실측: scrollY 0 -> 301, 조각은 화면 밖으로). 요청받아 만든
    // 연출이 스스로 만든 스크롤에 묻히는 셈이었다.
    //
    // 그래서 순서를 준다 - 터지는 것을 보고, 그 다음 화면이 움직인다.
    // 480ms 는 폭죽(900ms)의 절반쯤이다. 다 끝날 때까지 기다리면 다음
    // 문제로 넘어가려는 손이 먼저 움직여 답답하다.
    //
    // 틀렸을 때는 미루지 않는다. 그쪽 연출(흔들림)은 보기 버튼 위에서
    // 일어나므로 화면이 움직이면 오히려 같이 보인다.
    const delay = result?.correct ? 480 : 0;

    const move = () => {
      // 목표를 그때 다시 잰다. 위에서 구한 값은 480ms 전 것이라, 그 사이
      // 글꼴이 늦게 붙거나 사용자가 손으로 스크롤하면 어긋난다.
      const now = nextButtonRef.current;
      if (!now) return;
      const fresh =
        window.scrollY +
        now.getBoundingClientRect().bottom -
        window.innerHeight +
        tabBarHeight() +
        gap;

      // 이미 보이면 화면은 그대로 둔다. 답을 고를 때마다 흔들리면 방금 고른
      // 보기를 눈으로 다시 찾아야 한다. 데스크톱처럼 화면이 길면 대개 여기다.
      if (fresh > window.scrollY) {
        // behavior 를 "auto" 로 둔다. smooth 를 쓰면 이 화면에서는 아무 일도
        // 일어나지 않는다 - 채점 직후의 리렌더와 겹치면 브라우저가 진행 중인
        // 부드러운 이동을 버린다(실측: scrollTo({top:156}) 가 불렸는데
        // scrollY 가 0 이었고, 같은 시점에 수동 scrollTo 는 정상이었다).
        //
        // 움직임을 줄이겠다고 한 설정을 따로 보지 않는 이유: auto 는 애초에
        // 애니메이션이 없어서 그 설정과 무관하게 같은 결과다.
        window.scrollTo({ top: fresh, behavior: "auto" });
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
      now.focus({ preventScroll: true });
    };

    // 틀렸을 때는 지체 없이 옮긴다. delay 가 0 이면 타이머를 거치지 않고
    // 바로 부른다 - setTimeout(0) 도 한 틱 뒤라서, 그 사이 사용자가 이미
    // 손으로 스크롤했을 수 있다.
    if (delay === 0) {
      move();
      return;
    }

    const id = setTimeout(move, delay);
    // 그 사이 다음 문제로 넘어가면 취소한다. 안 그러면 새 문제가 뜬 화면을
    // 옛 계산으로 끌어내린다.
    return () => clearTimeout(id);
  }, [picked, result, error]);

  async function pick(choiceId: number) {
    if (!question || picked !== null) return;

    setPicked(choiceId);
    try {
      const graded = await submitAnswer(question.token, choiceId, content);
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
      // 맞혔을 때는 화면 가운데에서 조각이 터진다. 흔들림과 같은 이유로
      // 카운터다.
      if (graded.correct) setBurst((n) => n + 1);
      // 사람은 맞히든 틀리든 온다. 따봉이냐 뒤통수냐만 갈린다.
      setReaction((r) => ({ fire: r.fire + 1, correct: graded.correct }));
      // 채점 뒤 화면을 옮기는 일은 아래 useEffect 가 맡는다. 여기서 하면
      // 해설 카드가 아직 DOM 에 없어 버튼 좌표를 잘못 읽는다.
      //
      // 맞힌 것만 제외 목록에 넣는다. 틀린 단어야말로 다시 봐야 하는데
      // 여기에 넣으면 그 세션에서 가장 확실하게 안 나오는 단어가 된다.
      //
      // **무엇의 id 를 넣느냐가 유형마다 다르다.** 백엔드의 exclude 는
      // 그 콘텐츠의 id 를 기대하는데, 정답의 종류가 늘 그것과 같지는 않다.
      //
      //   단어 문제      answer_id 가 단어 id      -> 그대로
      //   상황 고르기    answer_id 가 문장 id      -> 그대로
      //   빈칸 채우기    answer_id 가 단어 id인데   -> 낸 문장을 따로 쓴다
      //                  걸러야 할 것은 문장이다
      //
      // 마지막 줄이 핵심이다. 그대로 넣으면 문장이 안 걸러져 같은 문장이
      // 다시 나오고, 어쩌다 그 번호의 다른 문장이 조용히 빠진다.
      if (graded.correct) {
        const excludeId =
          question.answer_type === "word" && question.source_sentence_id
            ? question.source_sentence_id
            : graded.answer_id;
        recentRef.current = [excludeId, ...recentRef.current].slice(
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
      <p className="mt-10 text-center" style={{ color: "var(--text-muted)" }}>
        문제를 가져오는 중입니다.
      </p>
    );
  }

  if (error && !question) {
    return (
      <div className="mt-10">
        {/* 안내는 앰버 채움에 진한 앰버 글자. 채움을 진하게 하면 이 카드가
            화면에서 가장 강한 것이 되어, 정작 눌러야 할 아래 버튼보다
            먼저 읽힌다(가이드 color-difficulty 와 같은 원칙). */}
        <p
          className="p-4"
          style={{
            background: "var(--amber-soft)",
            color: "var(--amber-deep)",
            borderRadius: "var(--radius-xl)",
            fontWeight: "var(--weight-medium)",
          }}
        >
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
            // 축포 카운터도 되돌린다. 안 그러면 판이 바뀌어도 이전 값이
            // 남아, 여기서 초기화하는 다른 것들과 규율이 어긋난다.
            setBurst(0);
            setReaction({ fire: 0, correct: false });
            void load();
          }}
          // 이 화면의 유일한 동작이라 코랄을 준다.
          className="dv-btn mt-4 px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
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
          처음부터 다시
        </button>
      </div>
    );
  }

  if (!question) return null;

  return (
    <div className="mt-6">
      {/* 맞혔을 때 화면 가운데에서 터진다. fixed 라 이 자리에 두어도
          문제 위치와 무관하게 화면 중앙에서 난다. */}
      <Burst fire={burst} />

      {/* 화면 아래쪽에서 걸어와 반응하고 간다. Burst 와 같은 이유로
          이 자리에 둔다 - fixed 라 문제 위치와 무관하다.

          **한 판 모드(RoundBoard)에는 안 넣었다.** 90초 타이머가 돌아
          문제가 빠르게 넘어가는데, 이 연출은 정답·오답 양쪽에 다 와서
          여기보다 두 배로 자주 뜬다. 0.6초가 매번 잘리면 연출이 아니라
          잔상이 된다. (넘긴 문제 처리는 걸림돌이 아니다 - 거기 축포가
          이미 !skipped 로 막고 있어서 같은 조건 하나면 된다.) */}
      <Reaction fire={reaction.fire} correct={reaction.correct} />

      <div className="flex flex-wrap items-center justify-between gap-2">
        {/* 분류 칩(MetaBadge 의 CategoryChip)의 비링크 모양과 같은 문법.
            같은 화면에 분류 고르개가 이미 서 있어서, 여기까지 다른 회색을
            쓰면 같은 알약이 세 종류가 된다. */}
        <span
          className="inline-flex items-center rounded-full px-3 py-1.5 text-xs whitespace-nowrap"
          style={{
            background: "var(--sand)",
            color: "var(--text-muted)",
            fontWeight: "var(--weight-bold)",
          }}
        >
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
                // 연속은 초록이다. 코랄로 두면 "지금 여기"·오답과 같은 색이
                // 되어, 잘 가고 있다는 신호가 경고처럼 보인다(가이드
                // color-accent).
                className="pop inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs"
                style={{
                  background: "var(--green-soft)",
                  color: "var(--green-deep)",
                  fontWeight: "var(--weight-black)",
                }}
              >
                <span aria-hidden>연속</span>
                {combo}
              </span>
            )}
            {/* 숫자가 바뀔 때 자리가 밀리지 않게 고정폭 숫자를 쓴다.
                9 에서 10 이 되면 글자가 옆으로 밀려 눈에 거슬린다. */}
            <span
              className="text-sm tabular-nums"
              // 맨 바탕 위라 라벨용이 아니라 --text-muted.
              style={{ color: "var(--text-muted)" }}
            >
              {score.solved}문제 중 {score.correct}개
            </span>
          </div>
        )}
      </div>

      {/* 무엇을 고르라는 것인지. 지문보다 확실히 작고 흐리다 - 여기서
          눈이 멈추면 안 되고, 바로 아래 지문으로 넘어가야 한다. */}
      <h2
        className="mt-5"
        style={{
          fontSize: "var(--text-xs)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-wide)",
          // 본문이라 --text-muted. --text-dim 은 작은 라벨용이다.
          //
          // 한때 "카드 안이면 --text-dim 도 4.2:1 이라 괜찮다" 고 적혀
          // 있었는데 그 숫자가 실측이 아니었다. 대비 값은 여기 적지 않고
          // globals.css 의 토큰 주석 한 곳에만 둔다 - 값이 움직일 때
          // 호출부마다 거짓말이 되기 때문이다.
          color: "var(--text-muted)",
        }}
      >
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
        // 데스크톱에서 두 칸으로 나눈다. 한 줄에 하나씩 두면 보기 하나가
        // 768px 막대가 되어, 게임 선택지가 아니라 설문 문항처럼 읽힌다.
        // 두 칸이면 시선 이동도 짧다. 폰에서는 한 칸이 맞다 - 두 칸으로
        // 쪼개면 긴 뜻풀이가 줄바꿈되어 높이가 들쭉날쭉해진다.
        // 간격을 두께만큼 넓힌다. 카드가 아래로 3px 를 내밀어서, gap-2(8px)
        // 로 두면 위 보기의 두께가 아래 보기 윗선에 거의 붙는다.
        className={`mt-5 grid gap-2.5 sm:grid-cols-2 ${
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
          className="mt-4 p-3 text-sm"
          style={{
            background: "var(--amber-soft)",
            color: "var(--amber-deep)",
            borderRadius: "var(--radius-md)",
            fontWeight: "var(--weight-medium)",
          }}
        >
          {error}
        </p>
      )}

      {/* aria-live 를 바깥에 두고 항상 렌더한다. 리전 자체가 내용과 함께
          새로 생기면 화면 낭독기가 대부분 그 등장을 알리지 않는다 - 리전은
          미리 있어야 이후 변화를 감시한다. 안쪽만 조건부로 바꾼다. */}
      <div aria-live="polite">{result && <Explanation result={result} />}</div>

      {picked !== null && (
        <button
          ref={nextButtonRef}
          type="button"
          onClick={() => void load()}
          // 채점이 끝난 뒤 이 화면의 유일한 다음 동작이라 코랄이다.
          // 한 화면에 코랄 버튼은 하나만 둔다 - 보기 넷은 종이라 겹치지 않는다.
          className="dv-btn mt-6 w-full px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--coral)",
              color: "var(--text-on-color)",
              borderRadius: "var(--radius-pill)",
              // fontSize 를 여기 적지 않는다. globals.css 가 코랄 버튼
              // 글자를 19px 로 올리는데(대비 때문), 인라인으로 크기를
              // 걸면 그 규칙이 덮여서 16px 로 남는다.
              fontWeight: "var(--weight-black)",
              "--lift": "var(--lift-button)",
            } as React.CSSProperties
          }
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

/**
 * 문제 지문.
 *
 * 크림에서 지문이 **카드 안으로 들어왔다.** 다크였을 때는 배경 그라디언트가
 * 영역을 갈랐지만 그것을 걷어냈고(globals.css 의 "영역별 배경" 절), 이제
 * 층을 만드는 것은 카드의 두께 하나다. 지문이 맨 바탕에 놓이면 아래 보기
 * 넷만 종이로 떠 있어서, 화면에서 가장 중요한 것이 유일하게 평평해진다.
 *
 * 가운데 정렬도 카드를 쓰기 때문이다. 왼쪽 정렬이면 카드 오른쪽이 늘
 * 비어 지문이 짧은 문제에서 카드가 반만 찬 것처럼 보인다.
 */
function Prompt({ kind, text }: { kind: string; text: string }) {
  // 유형마다 서체·크기가 다르다. 카드는 하나로 두고 안쪽 글자만 가른다 -
  // 카드까지 유형별로 두면 유형이 늘 때마다 같은 두께를 다시 적게 된다.
  //
  // 설명 문제: 여러 줄 한글이라 본문체로 읽기 좋게. 크기를 키우면 폰에서
  // 다섯 줄이 되어 보기가 첫 화면에서 밀린다.
  //
  // 문장(빈칸·상황): 에러 메시지와 실무 표현이라 코드에 가깝다. 아래
  // 해설이 같은 문자열을 이미 고정폭으로 그려서, 지문만 본문체면 한
  // 화면에서 같은 문장이 두 서체로 나온다. 크기를 --text-3xl 로 두지
  // 않는 이유는 지문이 한 줄짜리 문장이라 단어 하나보다 훨씬 길어서다 -
  // "IndexError: list ____ out of range" 가 390px 에서 세 줄로 감기고,
  // 그러면 보기 넷이 첫 화면에서 밀린다.
  //
  // 그 밖(뜻 고르기·단어 고르기): 이 화면에서 가장 먼저 읽어야 할 것이라
  // --text-3xl(28px). 고정폭 제목은 tracking 을 한 단계 더 좁힌다
  // (가이드 type-mono).
  //
  // lang 은 한글 폰트가 라틴·기호를 잘못 렌더하는 것을 막는다.
  const body: {
    lang?: string;
    className: string;
    style: React.CSSProperties;
  } =
    kind === "description"
      ? {
          className: "whitespace-pre-line",
          style: {
            fontSize: "var(--text-md)",
            fontWeight: "var(--weight-medium)",
            lineHeight: "var(--leading-relaxed)",
            color: "var(--text-body)",
          },
        }
      : kind === "blank" || kind === "situation"
        ? {
            lang: "en",
            className: "font-mono",
            style: {
              fontSize: "var(--text-xl)",
              fontWeight: "var(--weight-bold)",
              lineHeight: "var(--leading-snug)",
              letterSpacing: "var(--tracking-tighter)",
              color: "var(--foreground)",
            },
          }
        : {
            // 줄간격을 --leading-none 으로 바짝 붙이지 않는다. term 문제의
            // 지문은 한글 뜻이라 폰에서 두 줄로 감기고("네트워크에서 위치를
            // 나타내는 주소 체계" 가 390px 에서 두 줄), 그때 줄 높이가 글자
            // 크기와 같으면 받침과 다음 줄 윗선이 맞닿는다. 영어 용어도
            // 안전하지 않다 - "eventual consistency" 가 390px 에서 한 줄에
            // 겨우 들어간다.
            className: kind === "meaning" ? "font-mono" : "",
            style: {
              fontSize: "var(--text-3xl)",
              fontWeight: "var(--weight-black)",
              lineHeight: "var(--leading-tight)",
              letterSpacing:
                kind === "meaning"
                  ? "var(--tracking-tighter)"
                  : "var(--tracking-tight)",
              color: "var(--foreground)",
            },
          };

  return (
    <div
      className="mt-3 px-5 py-6 text-center"
      style={{
        background: "var(--paper)",
        borderRadius: "var(--radius-2xl)",
        // 읽는 카드라 눌리지 않는다. :active 가 없으니 인라인 boxShadow 로
        // 둬도 --lift 규칙과 충돌하지 않는다.
        boxShadow: "var(--lift-card)",
      }}
    >
      <p lang={body.lang} className={body.className} style={body.style}>
        {text}
      </p>
    </div>
  );
}

/**
 * 오답 보기의 두께. inset 테두리와 아래 3px 를 한 값으로 묶는다.
 *
 * 쉬는 두께와 hover 두께가 **같아야 해서** 상수로 뺐다. globals.css 의
 * .dv-card-press:hover 는 disabled 와 무관하게 걸려서, --lift-hover 를
 * 안 주면 채점이 끝난 뒤 마우스를 올리는 순간 코랄 테두리가 기본 회색
 * 두께로 덮인다. 두 자리에 같은 문자열을 적어두면 한쪽만 고쳐진다.
 */
const WRONG_LIFT =
  "0 0 0 2px var(--wrong) inset, 0 3px 0 rgb(193 62 34 / 0.25)";

/**
 * 보기 하나.
 *
 * 상태 넷의 생김새가 이 화면에서 가장 중요한 정보다.
 *
 *   idle     흰 종이 + 두께
 *   picked   같은 종이에 잉크 테두리(안쪽 2px). 채점을 기다리는 짧은 구간
 *   correct  초록 채움 + 초록 두께
 *   wrong    **채움이 아니라 코랄 테두리**
 *
 * 마지막 줄이 이 시스템의 규칙이다(가이드 color-accent). 코랄이 "지금
 * 여기"(주요 버튼)와 "틀림" 을 겸하기 때문에, 오답까지 코랄로 채우면
 * 같은 화면의 코랄 버튼과 구분이 안 된다. 정답만 채우고 오답은 테두리로
 * 둔다.
 *
 * 색만으로 가르지도 않는다 - "정답"·"오답" 글자가 항상 같이 간다.
 */
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

  // 아직 결과를 모르는 상태(picked·idle)는 중립으로 둔다. 삼항이 아니라
  // 맵인 이유: 삼항이면 correct 가 아닌 모든 상태가 오답 색이 되어, 나중에
  // picked 에 "채점 중" 같은 문구를 넣는 순간 결과를 모르는 상태가 빨개진다.
  const markTone = {
    correct: "var(--text-on-color)",
    wrong: "var(--wrong-deep)",
    picked: "var(--text-dim)",
    idle: "var(--text-dim)",
  }[state];

  // 표면·글자·두께를 한 자리에서 정한다.
  //
  // **boxShadow 를 인라인으로 적지 않는다.** 인라인 선언은 클래스를 항상
  // 이겨서 globals.css 의 :active(두께 0)가 무시되고, 그러면 transform 만
  // 걸려 버튼이 두께를 단 채 내려가 바닥을 뚫은 모양이 된다. 두께는 --lift
  // 변수로 넘긴다.
  //
  // picked·wrong 의 테두리는 inset 그림자다. border 로 두면 그 1~2px 만큼
  // 안쪽 폭이 줄어 상태가 바뀔 때 글자가 밀린다. inset 은 자리를 안 먹는다.
  //
  // --lift-hover 를 판정 상태에도 같이 준다. 이유는 WRONG_LIFT 주석 참고.
  const tone: Record<ChoiceState, React.CSSProperties> = {
    idle: {
      background: "var(--paper)",
      color: "var(--foreground)",
      "--lift": "var(--lift-card)",
    } as React.CSSProperties,
    // 고른 직후. 채점을 기다리는 짧은 순간이라 "이걸 골랐다" 만 말하고
    // 맞았는지는 아직 말하지 않는다. 그래서 판정색(초록·코랄)이 아니라
    // 잉크다 - 여기서 코랄을 쓰면 응답이 오기 전에 틀린 것처럼 보인다.
    //
    // 두께를 0 으로 둬서 눌린 채로 머문다. 서버 왕복을 기다리는 그 구간이
    // 이 화면에서 피드백이 가장 필요한 자리인데, 손을 뗀 순간 두께가
    // 돌아오면 "눌렀다" 는 신호가 꺼진다.
    picked: {
      background: "var(--paper)",
      color: "var(--foreground)",
      "--lift": "0 0 0 2px var(--foreground) inset",
      "--lift-hover": "0 0 0 2px var(--foreground) inset",
      transform: "translateY(var(--press-y-card))",
    } as React.CSSProperties,
    // 채움을 --correct 가 아니라 --correct-deep 으로 둔다. --correct
    // (#17916b) 위의 흰 글자는 3.96:1 이라, 16px 굵은 글씨(WCAG 의 대형
    // 글자 기준 18.66px 에 못 미친다)에 필요한 4.5:1 을 못 넘긴다.
    // --correct-deep 은 6.32:1 이고, 두께가 이미 --lift-button-green
    // (--green-deep)이라 채움과 두께가 같은 계열로 붙는다.
    correct: {
      background: "var(--correct-deep)",
      color: "var(--text-on-color)",
      "--lift": "var(--lift-button-green)",
      "--lift-hover": "var(--lift-button-green)",
    } as React.CSSProperties,
    // 채움이 아니라 테두리. 위 주석 참고.
    wrong: {
      background: "var(--paper)",
      color: "var(--wrong-deep)",
      // 두께를 --wrong-deep 의 옅은 알파로 둔다. --wrong-soft(옅은 장미)는
      // 크림 바탕과 거의 같은 밝기라 3px 가 안 보이고, --wrong-deep 을
      // 그대로 쓰면 정답(초록 채움)보다 오답이 더 진해진다.
      "--lift": WRONG_LIFT,
      "--lift-hover": WRONG_LIFT,
    } as React.CSSProperties,
  };

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      // dv-card dv-card-press: 누르면 두께가 0 이 되고 그만큼(3px) 내려앉는다.
      // 크림에서 누름이 축소에서 내려앉음으로 바뀌었다(globals.css 의
      // "누름 피드백" 절). :active 는 인라인 style 로 못 써서 클래스가 맡고,
      // 채점 뒤에는 disabled 라 브라우저가 :active 를 주지 않는다.
      className="dv-card dv-card-press flex w-full items-center gap-3 px-4 py-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-default"
      style={{
        // 보기는 56px(가이드 shape-hit). 주요 버튼(52px)보다 한 급 크다 -
        // 연달아 네 개를 겨냥하는 자리라 실수가 제일 잦다.
        minHeight: 56,
        borderRadius: "var(--radius-xl)",
        fontSize: "var(--text-base)",
        fontWeight:
          state === "correct" ? "var(--weight-black)" : "var(--weight-bold)",
        ...tone[state],
      }}
    >
      {/* min-w-0 이 있어야 flex 항목이 내용보다 작아진다. 글자를 끊는 쪽은
          globals.css 의 base 규칙(body 상속)이 맡는다. 둘 중 하나만 있으면
          보기 문구가 길 때 버튼이 화면 밖으로 밀린다. */}
      <span className={`min-w-0 flex-1 ${mono ? "font-mono" : ""}`}>
        {text}
      </span>
      {mark && (
        // 정답·오답 글자도 테두리·채움과 같은 톤으로 둔다. 회색으로 두면
        // 방금 무슨 일이 일어났는지 눈이 먼저 읽는 신호가 하나뿐이다.
        //
        // 색 전환을 여기 두는 이유: 지금은 이 span 이 채점된 뒤에야 처음
        // 생겨 전환할 이전 값이 없지만, picked 에 문구가 붙으면 계속 살아
        // 있게 되어 색만 툭 바뀐다. 버튼 쪽에 걸어봐야 자식 글자색에는
        // 닿지 않는다.
        <span
          className="shrink-0 text-xs transition-[color] duration-[120ms] ease-press"
          style={{ color: markTone, fontWeight: "var(--weight-black)" }}
        >
          {mark}
        </span>
      )}
    </button>
  );
}

function Explanation({ result }: { result: GradeResult }) {
  const { word, sentence } = result;

  // 정답이 무엇이냐에 따라 보여줄 것이 다르다. 빈칸 채우기는 문장 문제인데
  // 정답은 단어라, 유형이 아니라 정답의 종류로 갈라야 한다.
  //
  // 둘 다 없으면 아무것도 그리지 않는다. 백엔드가 항상 하나는 주지만,
  // 없는 채로 그리면 "정답은 이것입니다" 아래가 비어 더 혼란스럽다.
  if (!word && !sentence) return null;

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
      className="rise mt-6 p-5"
      style={{
        background: "var(--paper)",
        borderRadius: "var(--radius-2xl)",
        // 읽는 카드라 눌리지 않는다. 인라인 boxShadow 여도 :active 와
        // 충돌하지 않는다.
        boxShadow: "var(--lift-card)",
      }}
    >
      {/* 맞았는지 틀렸는지가 이 카드에서 가장 먼저 읽혀야 한다. 회색으로
          두면 보기 버튼의 테두리 색이 유일한 신호가 된다. */}
      {/* 판정은 옅은 채움 + 진한 글자의 알약으로 둔다. 글자만 색을 입히면
          흰 종이 위에서 이 줄이 본문과 같은 무게로 읽힌다.

          오답 쪽을 코랄로 채우지 않는 것은 보기 버튼과 같은 이유다 -
          코랄 채움은 "누르는 것" 의 색이다(가이드 color-accent). */}
      <p
        className="inline-flex items-center rounded-full px-3 py-1.5 text-xs"
        style={{
          background: result.correct
            ? "var(--correct-soft)"
            : "var(--wrong-soft)",
          color: result.correct ? "var(--correct-deep)" : "var(--wrong-deep)",
          fontWeight: "var(--weight-black)",
        }}
      >
        {result.correct ? "맞았습니다" : "정답은 이것입니다"}
      </p>

      {word ? <WordAnswer word={word} /> : null}
      {sentence ? <SentenceAnswer sentence={sentence} /> : null}
    </section>
  );
}

/** 정답이 단어일 때. 뜻 고르기·단어 고르기·설명 문제와 빈칸 채우기가 쓴다. */
function WordAnswer({ word }: { word: NonNullable<GradeResult["word"]> }) {
  return (
    <>
      <div className="mt-2 flex flex-wrap items-baseline gap-2">
        <h3
          className="font-mono"
          style={{
            fontSize: "var(--text-xl)",
            fontWeight: "var(--weight-black)",
            letterSpacing: "var(--tracking-tighter)",
            color: "var(--foreground)",
          }}
        >
          {word.term}
        </h3>
        {word.pronunciation && (
          // 발음기호는 고정폭으로 두지 않는다. IPA 기호가 고정폭 글꼴에서
          // 깨지거나 폭이 어긋나는 경우가 있다. lang 은 한글 폰트가 IPA 를
          // 잘못 렌더하는 것을 막는다.
          <span lang="en-US" style={{ color: "var(--text-muted)" }}>
            {word.pronunciation}
          </span>
        )}
        {word.reading && (
          <Reading text={word.reading} style={{ color: "var(--text-muted)" }} />
        )}
      </div>

      <p
        className="mt-1"
        style={{
          fontSize: "var(--text-md)",
          fontWeight: "var(--weight-medium)",
          color: "var(--text-body)",
        }}
      >
        {word.meaning}
      </p>

      {word.description && (
        <p
          className="mt-3 whitespace-pre-line text-sm"
          style={{
            lineHeight: "var(--leading-relaxed)",
            color: "var(--text-muted)",
          }}
        >
          {word.description}
        </p>
      )}

      {word.example && (
        /* 예문은 반전 카드다(--surface-card-dark). 흰 종이 위 흰 종이로
           두면 층이 안 생기고, 왼쪽 세로선 하나로 가르는 것은 테두리를
           안 쓰는 이 시스템의 문법이 아니다(가이드 shape-lift). */
        <div
          className="mt-4 px-4 py-3"
          style={{
            background: "var(--surface-card-dark)",
            borderRadius: "var(--radius-xl)",
          }}
        >
          <p
            lang="en"
            className="font-mono text-sm"
            style={{ color: "var(--paper)" }}
          >
            {word.example}
          </p>
          {word.example_translation && (
            // 반전 카드 위 보조 글자는 --text-on-dark 다. 상세 화면의
            // 예문 번역과 같은 자리라 같은 토큰을 쓴다 - 흰색 알파로
            // 각자 내리면 반전 카드 색을 바꿀 때 한쪽만 따라온다.
            <p
              className="mt-1.5 text-sm"
              style={{ color: "var(--text-on-dark)" }}
            >
              {word.example_translation}
            </p>
          )}
        </div>
      )}
    </>
  );
}

/**
 * 정답이 문장일 때. 상황 고르기가 쓴다.
 *
 * 단어와 순서가 다르다. 상황 고르기는 **상황이 정답 보기**라 그걸 먼저
 * 크게 보여주고, 그 아래에 무슨 문장이었는지를 둔다. 문장을 위에 두면
 * 방금 지문에서 읽은 것을 한 번 더 읽게 된다.
 */
function SentenceAnswer({
  sentence,
}: {
  sentence: NonNullable<GradeResult["sentence"]>;
}) {
  return (
    <>
      <h3
        className="mt-3"
        style={{
          fontSize: "var(--text-xl)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
          color: "var(--foreground)",
        }}
      >
        {sentence.context}
      </h3>

      {/* 문장 본문은 고정폭이다. 에러 메시지와 실무 표현이라 코드에 가깝다.
          단어 목록·상세가 쓰는 것과 같은 구분이다. */}
      <p
        lang="en"
        className="mt-3 font-mono text-sm"
        style={{ color: "var(--text-body)" }}
      >
        {sentence.text}
      </p>
      {sentence.reading && (
        <Reading
          text={sentence.reading}
          className="mt-1 block"
          style={{ color: "var(--text-muted)" }}
        />
      )}
      {sentence.translation && (
        <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
          {sentence.translation}
        </p>
      )}

      {sentence.description && (
        <p
          className="mt-3 whitespace-pre-line text-sm"
          style={{
            lineHeight: "var(--leading-relaxed)",
            color: "var(--text-muted)",
          }}
        >
          {sentence.description}
        </p>
      )}
    </>
  );
}
