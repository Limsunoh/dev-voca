"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import type {
  ReviewAnswered,
  ReviewDue,
  ReviewQuestion,
  ReviewResult,
  ReviewStarted,
} from "@/lib/api/review";
import type { RoundChoice } from "@/lib/api/rounds";
import { routes } from "@/lib/routes";

import { Burst } from "./Burst";
import { QuestionCard } from "./QuestionCard";
import { WrongAnswer } from "./WrongAnswer";
import { Reaction } from "./Reaction";

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

/**
 * 풀던 판. **새로고침해도 이어 풀도록 탭에 적어 둔다.**
 *
 * 판은 서버에 안 남는다(backend review.py 머리말). 다음 답에 쓸 토큰과
 * 지금 문제를 화면만 들고 있어서, 새로고침하면 처음부터 다시 시작했다.
 * 일일공부처럼 DB 에 두지 않은 것은 시작에 제약이 없어서다 - 일일공부는
 * 하루 한 번이라 못 이으면 그날 판을 잃지만, 복습은 언제든 새로 연다.
 * 잃는 것이 이번 판의 자리와 맞힌 수뿐이라 탭에 두면 된다. 다른 탭이나
 * 다른 기기에서는 이어지지 않는다.
 *
 * **계정마다 키를 나눈다.** 같은 탭에서 로그아웃하고 다른 계정으로
 * 들어오면 앞 사람이 틀린 단어가 문제로 뜬다. 답은 서버가 막지만(남의
 * 토큰) 보이는 것부터 안 된다.
 */
type SavedRound = {
  token: string;
  question: ReviewQuestion;
  correct: number;
  graduated: number;
};

/**
 * 적어 둔 판을 이만큼만 믿는다. 토큰 수명(backend review.TOKEN_MAX_AGE,
 * 6시간)에서 10분을 뺐다 - 토큰은 서버가 응답을 만들 때 서명하고 우리는
 * 받은 뒤에 적으므로, 적은 시각이 서명보다 조금 늦다.
 *
 * 이게 없으면 탭을 켜 둔 채 다음 날 들어와도 "이어서 풀기" 가 뜬다. 누르면
 * 문제가 나오고, 답을 고른 뒤에야 "만료됐습니다" 를 받는다 - 답 하나를
 * 버리고 나서야 새로 시작할 수 있었다.
 */
const KEEP_MS = (6 * 60 - 10) * 60 * 1000;

/**
 * 탭 저장소 접근은 전부 try 로 감싼다. 사생활 보호 창이나 사이트 데이터를
 * 막은 브라우저에서는 접근 자체가 예외를 던진다(StudyCards 의 같은 자리).
 * 못 적으면 새로고침할 때 처음부터일 뿐이다.
 */
function readRound(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function remember(key: string, round: SavedRound): void {
  try {
    // 적은 시각을 붙인다. 읽을 때 KEEP_MS 와 견준다.
    window.sessionStorage.setItem(
      key,
      JSON.stringify({ ...round, savedAt: Date.now() }),
    );
  } catch {
    // 위 머리말.
  }
}

function forget(key: string): void {
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    // 위 머리말.
  }
}

/**
 * 적어 둔 글을 판으로 읽는다. 모양이 아니면 null.
 *
 * 우리가 적은 것이지만 믿지 않는다. 배포로 문제 모양이 바뀌면 옛 탭에는
 * 옛 모양이 남아 있고, 그대로 그리면 진행이 "5 / undefined" 가 되거나
 * 보기 하나가 null 이라 문제 화면이 통째로 죽는다. 보기는 하나하나 본다.
 */
function parseRound(raw: string | null): SavedRound | null {
  if (!raw) return null;
  try {
    const saved = JSON.parse(raw);
    const question = saved?.question;
    // 사람이 풀 수 있는 수만. 1e21 도 정수라 상한을 둔다(counted 와 같다).
    const whole = (n: unknown) =>
      Number.isInteger(n) && (n as number) >= 0 && (n as number) <= 1000;
    const choice = (c: unknown) =>
      Number.isInteger((c as RoundChoice | null)?.id) &&
      typeof (c as RoundChoice | null)?.text === "string";
    const age =
      typeof saved?.savedAt === "number" ? Date.now() - saved.savedAt : -1;
    if (
      typeof saved?.token === "string" &&
      saved.token &&
      age >= 0 &&
      age < KEEP_MS &&
      Array.isArray(question?.choices) &&
      question.choices.length > 0 &&
      question.choices.every(choice) &&
      whole(question.answered) &&
      whole(question.total) &&
      question.answered < question.total &&
      whole(saved.correct) &&
      whole(saved.graduated) &&
      saved.correct <= question.answered &&
      saved.graduated <= saved.correct
    ) {
      return {
        token: saved.token,
        question,
        correct: saved.correct,
        graduated: saved.graduated,
      };
    }
  } catch {
    // 깨진 글. 없는 것과 같다.
  }
  return null;
}

/**
 * 지금 적혀 있는 판의 토큰. 나이와 모양은 안 본다 - "아직 이 판이 적혀
 * 있나" 만 가른다. 오래된 판이라도 같은 판이면 이어서 적어야 한다.
 */
function storedToken(key: string): string | null {
  try {
    const token = JSON.parse(readRound(key) ?? "null")?.token;
    return typeof token === "string" ? token : null;
  } catch {
    return null;
  }
}

/** 우리가 적고 우리가 읽는 값이라 바뀌었다고 알려줄 바깥 신호가 없다. */
function noSubscribe(): () => void {
  return () => {};
}

/** 중계가 거절한 요청. status 로 "다시 보내도 안 되는 것" 을 가른다. */
class CallError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function ReviewBoard({
  due,
  userId = null,
}: {
  due: ReviewDue;
  /** 풀던 판을 적어 둘 계정. 모르면 적지 않는다(새로고침하면 처음부터). */
  userId?: number | null;
}) {
  const memoryKey = userId === null ? null : `review-round-${userId}`;
  const [phase, setPhase] = useState<Phase>("idle");
  const [question, setQuestion] = useState<ReviewQuestion | null>(null);
  const [result, setResult] = useState<ReviewResult | null>(null);
  const [total, setTotal] = useState(0);
  const [answered, setAnswered] = useState(0);
  const [correct, setCorrect] = useState(0);
  const [graduated, setGraduated] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  /**
   * 맞혔을 때만 걸어오는 사람.
   *
   * **틀렸을 때는 안 부른다.** 다른 화면에서는 머리를 콩 때리고 가는데,
   * 여기는 이미 틀린 것만 모아 다시 보는 자리다. 그 자리에서 또 틀렸다고
   * 때리면 이 앱이 줄이려는 것(영어와 에러에 대한 공포)을 오히려 키우고,
   * 사용자는 복습 자체를 피하게 된다.
   *
   * 그래서 correct 는 항상 true 다. 값을 남겨두는 것은 Reaction 의 계약이
   * 그렇기 때문이고, 여기서 false 가 들어갈 일은 없다.
   */
  const [reaction, setReaction] = useState({ fire: 0, correct: true });
  /** 맞혔을 때 터지는 조각. */
  const [burst, setBurst] = useState(0);

  const tokenRef = useRef("");
  const busyRef = useRef(false);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  /** 판을 화면에 편다. 새로 연 판과 적어 둔 판이 같이 쓴다. */
  const open = (round: SavedRound) => {
    tokenRef.current = round.token;
    setQuestion(round.question);
    setTotal(round.question.total);
    setAnswered(round.question.answered);
    setCorrect(round.correct);
    setGraduated(round.graduated);
    setResult(null);
    setError("");
    // 지난 판의 연출을 끈다. 안 끄면 새 판 첫 화면에 지난 판 마지막
    // 연출이 그대로 떠 있다(fire 가 0 이 아니라서 그려진다).
    setReaction({ fire: 0, correct: true });
    setBurst(0);
    setPhase("playing");
  };

  const start = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");

    try {
      const started = await call<ReviewStarted>({ action: "start" });
      if (!aliveRef.current) return;

      const round = {
        token: started.token,
        question: started.question,
        correct: 0,
        graduated: 0,
      };
      if (memoryKey) remember(memoryKey, round);
      open(round);
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

    // 응답이 오면 이 판이 아직 탭에 적혀 있는지 이것으로 본다(아래).
    const sent = tokenRef.current;
    try {
      const got = await call<ReviewAnswered>({
        action: "answer",
        token: sent,
        choice_id: choiceId,
      });

      // 적어 둘 값과 화면의 값이 같아야 해서 한 번 세어 둘 다 쓴다.
      const nextCorrect = correct + (got.result.correct ? 1 : 0);
      const nextGraduated = graduated + (got.result.graduated ? 1 : 0);

      // **적는 것은 화면이 떠났는지 보기 전에 한다.** 답을 누르고 응답이
      // 오기 전에 탭바로 나가면 화면은 사라져도 서버는 이 답을 받았다.
      // 그때 안 적으면 탭에는 이미 답한 문제의 토큰이 남아, 돌아와서 이어
      // 풀면 같은 문제를 다시 내고 400 으로 끝난다. 탭 저장소는 화면보다
      // 오래 산다.
      //
      // **단, 이 판이 아직 적혀 있을 때만.** 떠났다 돌아와 "새로 시작" 을
      // 눌렀으면 탭에는 새 판이 있다. 늦게 온 옛 판의 응답이 그것을 덮으면
      // 안 된다.
      if (memoryKey && storedToken(memoryKey) === sent) {
        if (got.finished || !got.question) {
          forget(memoryKey);
        } else {
          remember(memoryKey, {
            token: got.token ?? "",
            question: got.question,
            correct: nextCorrect,
            graduated: nextGraduated,
          });
        }
      }
      if (!aliveRef.current) return;

      tokenRef.current = got.token ?? "";
      setResult(got.result);
      // 다음 문제가 있으면 서버가 센 순번을 쓴다. 마지막이면 그것이
      // 없으므로 하나 올린다 - 끝난 판이라 더 어긋날 자리도 없다.
      setAnswered((n) => got.question?.answered ?? n + 1);
      setCorrect(nextCorrect);
      setGraduated(nextGraduated);

      // 맞혔을 때만 연출한다. 틀렸을 때 아무것도 안 오는 것이 이 화면의
      // 판단이다(위 reaction 주석).
      //
      // **연출을 기다렸다가 다음 문제를 내지 않는다.** 판 모드가 멈추는
      // 이유는 거기서 화면을 어둡게 깔아(dim) 그동안 문제와 결과 줄이
      // 가려지기 때문이다(RoundBoard 의 그 자리 주석). 이 화면은 어둡게 안
      // 깔고, 결과 줄이 문제 카드와 별개 요소라 다음 문제가 떠도 "앞 문제"
      // 로 그대로 남는다.
      if (got.result.correct) {
        setReaction((r) => ({ fire: r.fire + 1, correct: true }));
        setBurst((n) => n + 1);
      }

      if (got.finished || !got.question) {
        // busyRef 를 쥔 채 화면을 넘긴다. finally 에서 풀리지만 그때는
        // 이미 phase 가 done 이라 보기 버튼이 없다. 마지막 답 직후의
        // 짧은 창에 한 번 더 눌리는 것을 막는다.
        setPhase("done");
        return;
      }
      setQuestion(got.question);
    } catch (err) {
      // **400 이면 이 판은 더 못 간다.** 토큰이 만료됐거나 이미 답한 문제의
      // 토큰이다 - 답을 보내고 응답이 오기 전에 새로고침하면 적어 둔 판이
      // 한 문제 뒤처진다. 같은 답을 다시 보내도 같은 400 이라 문제 화면에
      // 두면 막다른 길이 된다. 시작 화면으로 돌려 새로 열게 한다.
      const dead = err instanceof CallError && err.status === 400;
      // 화면이 떠났어도 지운다. 위에서 적는 것과 같은 이유이고, 같은
      // 조건이다 - 그 사이 탭에 적힌 다음 토큰이나 새 판은 멀쩡하다.
      if (dead && memoryKey && storedToken(memoryKey) === sent) {
        forget(memoryKey);
      }
      if (!aliveRef.current) return;

      if (dead) {
        tokenRef.current = "";
        setQuestion(null);
        setResult(null);
        setPhase("idle");
        // 서버 문구를 그대로 쓰지 않는다. 가장 흔한 경우의 문구가 "최신
        // 화면에서 다시 풀어주세요" 인데, 시작 버튼 앞에서는 뜻이 안 닿는다.
        //
        // 시작 화면의 남은 개수는 이 화면을 연 때의 값이다. 이 길은 거의
        // 새로고침 직후 이어 풀기에서 나서 그 값이 곧 지금 값이다.
        setError("이 판은 더 이어갈 수 없습니다. 새로 시작해주세요.");
        return;
      }
      setError(err instanceof Error ? err.message : "채점하지 못했습니다.");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  /* 채점 연출 둘. **어느 가지에도 넣지 않는다.** 이유는 DailyStudyBoard 의
     같은 자리 주석에 있다 - 마지막 한 문제가 잘리는 것과, 가지를 오갈 때
     지난 판정이 다시 재생되는 것 둘 다 막는다. */
  const overlays = (
    <>
      <Burst fire={burst} />
      <Reaction fire={reaction.fire} correct={reaction.correct} dim={false} />
    </>
  );

  const body = (() => {
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

    return (
      <IdleCard
        due={due}
        memoryKey={memoryKey}
        busy={busy}
        error={error}
        onStart={start}
        onResume={open}
      />
    );
  })();

  return (
    <>
      {overlays}
      {body}
    </>
  );
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
  memoryKey,
  busy,
  error,
  onStart,
  onResume,
}: {
  due: ReviewDue;
  memoryKey: string | null;
  busy: boolean;
  error: string;
  onStart: () => void;
  onResume: (round: SavedRound) => void;
}) {
  /**
   * 이 탭에서 풀던 판. **이어 풀지는 누를 때 정한다.**
   *
   * 첫 화면은 서버가 그리는데 서버에는 탭 저장소가 없다. 그래서 서버 몫은
   * null 이고, 화면에 붙은 뒤에 적어 둔 판으로 한 번 바뀐다(StudyCards 의
   * 같은 자리). 곧장 문제로 넘기지 않고 버튼을 "이어서 풀기" 로 바꾸는 이유:
   * 붙은 뒤 판을 펴려면 이펙트 안에서 상태를 바꿔야 하는데, 그건 첫 그림을
   * 한 번 더 그리게 하는 길이라 린트가 막는다. 누르는 한 번이 더 들지만
   * 무엇이 이어지는지 먼저 보인다.
   */
  const raw = useSyncExternalStore(
    noSubscribe,
    () => (memoryKey ? readRound(memoryKey) : null),
    () => null,
  );
  const saved = parseRound(raw);

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
        {saved
          ? `풀던 판이 있습니다. ${saved.question.total}개 중 ${saved.question.answered}개를 풀었습니다.`
          : capped
            ? `이번 판에서 ${capped}개를 봅니다. 점수는 붙지 않고 시간도 재지 않습니다.`
            : "점수는 붙지 않고 시간도 재지 않습니다."}
      </p>

      <div>
        {/* 이 화면의 주된 동작이라 코랄. 한 화면에 코랄 버튼은 하나다. */}
        <button
          type="button"
          onClick={() => {
            // **누를 때 다시 읽는다.** 이 화면은 그려질 때 한 번 읽는데, 그
            // 뒤 떠나기 전 화면의 늦은 응답이 다음 토큰을 적을 수 있다. 그린
            // 때의 판으로 열면 이미 쓴 토큰이라 답하자마자 400 이다.
            const now = memoryKey ? parseRound(readRound(memoryKey)) : null;
            if (now) onResume(now);
            else onStart();
          }}
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
          {busy ? "여는 중" : saved ? "이어서 풀기" : "시작"}
        </button>
        {/* 적어 둔 판을 버리고 새 판을 연다. 이게 없으면 그 사이 다른 곳에서
            새로 틀린 것이 생겨도 옛 판을 끝까지 풀어야 새 목록을 받았다.
            새 판이 적어 둔 것을 덮어쓰므로 따로 지울 것은 없다. 코랄은 위
            하나라 글자 버튼으로 둔다. block 으로 두는 이유: 데스크톱에서
            주 버튼이 제 폭(sm:w-auto)으로 줄면 인라인 버튼이 그 옆 같은 줄로
            붙어 높이가 어긋난다. 폰과 같이 늘 아래 줄에 둔다. */}
        {saved && (
          <button
            type="button"
            onClick={onStart}
            disabled={busy}
            className="mx-auto mt-2 block px-3 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-50"
            style={{
              minHeight: "var(--hit-floor)",
              background: "transparent",
              border: 0,
              borderRadius: "var(--radius-md)",
              color: "var(--text-muted)",
              fontWeight: "var(--weight-bold)",
            }}
          >
            새로 시작
          </button>
        )}
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

      {/* 방금 푼 문제의 결과. 새로 나타나는 영역이라 읽어준다.

          **문제 위에 두고 "앞 문제" 라고 붙인다.** 이유는 DailyStudyBoard 의
          같은 자리와 같다 - 답하면 곧바로 다음 문제가 뜨므로, 아래에 두면
          방금 답의 결과가 새 문제의 답처럼 읽혔다.

          높이를 두 줄로 잡아둔다. 단어를 틀리면 정답과 그 뜻으로 두 줄이
          되는데, 한 줄 높이로 두면 오답마다 아래 문제와 보기가 내려간다.
          문장을 틀려 해석이 길면 그보다 늘어나는 것, aria-atomic 을 거는
          이유는 DailyStudyBoard 의 같은 자리에 적었다. */}
      <p aria-live="polite" aria-atomic="true" className="min-h-10 text-sm">
        {result && (
          <>
            <span
              style={{
                color: "var(--text-muted)",
                fontWeight: "var(--weight-bold)",
              }}
            >
              앞 문제 ·{" "}
            </span>
            <ResultLine result={result} graduateStreak={graduateStreak} />
          </>
        )}
      </p>

      <QuestionCard question={question} busy={busy} onPick={onPick} />

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
        <WrongAnswer text={result.answer_text} extra={result.answer_extra} />
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
    throw new CallError(data?.detail ?? "요청이 실패했습니다.", res.status);
  }
  return res.json() as Promise<T>;
}
