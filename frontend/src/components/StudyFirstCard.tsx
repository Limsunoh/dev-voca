import Link from "next/link";

import type { Today } from "@/components/TodayCards";
import type { User } from "@/lib/api/accounts";
import type { StudyLength, StudyProgress } from "@/lib/api/daily";
import { routes } from "@/lib/routes";

/** 홈이 일일공부를 앞세울 때 그릴 것. 시작 전이면 고른 길이, 하다 만 판이면 그 진행. */
export type StudyFirst =
  | { kind: "start"; plan: StudyLength }
  | { kind: "resume"; daily: StudyProgress };

/**
 * 오늘 일일공부를 안 끝낸 회원이면 무엇을 앞세울지, 아니면 null(지금 홈).
 *
 * null 인 경우:
 * - 게스트. 일일공부는 로그인해야 한다.
 * - 일일공부 상태를 못 받았다(lengths 가 null). 끝냈는지 모르는데 일일공부만
 *   남기면, 백엔드가 잠깐 안 받는 동안 홈이 막힌 카드 한 장이 된다. 단어라도
 *   보이는 지금 홈이 낫다.
 * - 오늘 몫을 끝냈다.
 * - 시작 전인데 하루 공부량이 길이 목록에 없다. 홈 맨 위에서 고르는 화면으로
 *   보내므로 보통은 오지 않는다.
 *
 * 몇 번째로 들어왔는지는 세지 않는다. 중간에 나갔다 다시 와도 일일공부가 먼저
 * 보여야 하고, 끝냈으면 그날 처음 열어도 지금 홈이 맞다.
 */
export function studyFirst(user: User | null, today: Today): StudyFirst | null {
  if (!user || !today.lengths) return null;
  if (today.daily) {
    return today.daily.done ? null : { kind: "resume", daily: today.daily };
  }
  const plan = today.lengths.find((one) => one.value === user.daily_length);
  return plan ? { kind: "start", plan } : null;
}

/**
 * 묶음 막대 한 칸. kind 는 묶음(익히고 푸는 칸)인지 전체(단어와 문장 전체에서
 * 나오는 마지막 칸)인지, size 는 그 칸의 문제 수, filled 는 그중 푼 수.
 */
type Segment = {
  kind: "chunk" | "rest";
  label: string;
  size: number;
  filled: number;
};

/**
 * 일일공부를 묶음 막대로 나눈다. 묶음마다 단어를 익히고 그 단어로 문제를 풀고,
 * 남은 문제(total - 묶음 크기 x 개수)는 단어와 문장 전체에서 나온다
 * (backend STUDY_PLANS). 칸 폭은 문제 수에 비례한다 - 30분은 마지막 칸이
 * 10문제라 묶음 칸의 두 배다.
 *
 * 라벨은 "묶음 1" 이 아니라 숫자만 쓴다. 30분은 일곱 칸이라 360 폭 폰에서
 * 한 칸이 31px 남짓이고, "묶음 1" 이 그 폭을 넘는다.
 */
function segments(
  total: number,
  chunkSize: number,
  chunkCount: number,
  answered: number,
): Segment[] {
  const parts: Omit<Segment, "filled">[] = Array.from(
    { length: chunkCount },
    (_, index) => ({ kind: "chunk", label: String(index + 1), size: chunkSize }),
  );
  const rest = total - chunkSize * chunkCount;
  if (rest > 0) parts.push({ kind: "rest", label: "전체", size: rest });

  let start = 0;
  return parts.map((part) => {
    const filled = Math.min(Math.max(answered - start, 0), part.size);
    start += part.size;
    return { ...part, filled };
  });
}

/**
 * 오늘의 일일공부 카드. 오늘 몫을 끝내기 전까지 홈의 주인공이다.
 *
 * 오늘의 단어 카드(DailyWord)와 같은 틀이다 - 흰 카드, 위에 라벨과 큰 글자,
 * 아래 띠에 버튼. 홈의 주인공 자리를 둘이 번갈아 맡으므로 모양이 같아야
 * 일일공부를 끝낸 뒤 화면이 바뀌어도 낯설지 않다.
 */
export function StudyFirstCard({ first }: { first: StudyFirst }) {
  // 시작 전은 고른 길이의 계획대로, 하다 만 판은 서버가 연 판대로 그린다.
  // 콘텐츠가 적은 DB 에서는 서버가 묶음을 줄여 열 수 있어 둘이 다를 수 있다.
  //
  // 옛 백엔드(lengths 에 chunk_size·chunk_count 가 없음)면 시작 전 묶음을 모른다.
  // 0 으로 두어 막대 없이 숫자만 적는다 - 한 칸짜리 막대는 "학습 없이 문제만"
  // 으로 읽힌다.
  const { total, chunkSize, chunkCount, answered } =
    first.kind === "start"
      ? {
          total: first.plan.questions,
          chunkSize: first.plan.chunk_size ?? 0,
          chunkCount: first.plan.chunk_count ?? 0,
          answered: 0,
        }
      : {
          total: first.daily.total,
          chunkSize: first.daily.chunk_size,
          chunkCount: first.daily.chunk_count,
          answered: first.daily.answered,
        };
  const learns = chunkSize > 0 && chunkCount > 0;
  const rest = total - chunkSize * chunkCount;
  const track =
    first.kind === "resume" || learns
      ? segments(total, chunkSize, chunkCount, answered)
      : [];
  // 지금 하던 칸. 하다 만 판에서만 라벨을 강조색으로 둔다.
  const current =
    first.kind === "resume"
      ? track.findIndex((part) => part.filled < part.size)
      : -1;

  let summary: string;
  if (first.kind === "start") {
    summary = learns
      ? `단어 ${first.plan.words}개를 ${chunkSize}개씩 익히고 바로 문제로 확인합니다.` +
        (rest > 0 ? ` 마지막 ${rest}문제는 단어와 문장 전체에서 나옵니다.` : "")
      : `단어 ${first.plan.words}개를 익히고 문제 ${total}개를 풉니다.`;
  } else {
    // 학습 없이 연 판(콘텐츠가 모자라 서버가 묶음을 0 으로 내린 판)은 칸이
    // "전체" 하나라 어디쯤인지 말할 것이 없다.
    const part = learns ? track[current] : undefined;
    const where =
      part?.kind === "chunk"
        ? `${current + 1}번째 묶음을 하던 중입니다. `
        : part?.kind === "rest"
          ? "마지막 문제들을 풀던 중입니다. "
          : "";
    summary = `${where}들어가면 멈춘 곳부터 이어집니다.`;
  }

  return (
    <section
      aria-labelledby="daily-study"
      className="dv-card mt-5 overflow-hidden"
      style={
        {
          "--lift": "var(--lift-card)",
          background: "var(--paper)",
          borderRadius: "var(--radius-2xl)",
        } as React.CSSProperties
      }
    >
      {/* 오늘의 단어 카드처럼 라벨(0) · 큰 글자(80) · 설명과 막대(160) ·
          버튼 띠(240) 순으로 올라온다. 하루 한 번 여는 첫 화면이라 모션
          예산을 여기에 쓴다. */}
      <div className="px-5 pt-5 pb-[18px]">
        <p
          className="rise text-xs"
          style={{
            fontWeight: "var(--weight-black)",
            letterSpacing: "var(--tracking-wide)",
            color: "var(--brand)",
          }}
        >
          오늘의 일일공부
        </p>

        <h1
          id="daily-study"
          className="rise mt-2.5 tabular-nums [animation-delay:80ms]"
          style={{
            fontSize: "var(--text-4xl)",
            fontWeight: "var(--weight-black)",
            letterSpacing: "var(--tracking-tight)",
            lineHeight: "var(--leading-tight)",
            color: "var(--foreground)",
          }}
        >
          {first.kind === "start" ? (
            `하루 ${first.plan.label}`
          ) : (
            <>
              {answered}
              <span
                style={{ fontSize: "var(--text-md)", color: "var(--text-muted)" }}
              >
                /{total}문제
              </span>
            </>
          )}
        </h1>

        <div className="rise flex flex-col [animation-delay:160ms]">
          <p
            className="mt-3"
            style={{
              fontSize: 15,
              lineHeight: "var(--leading-normal)",
              color: "var(--text-body)",
            }}
          >
            {summary}
          </p>

          {/* 숫자와 문장이 이미 말하므로 막대는 읽지 않게 둔다. 칸마다 "3/5"
              를 읽어 주면 같은 내용을 일곱 번 듣는다. */}
          {track.length > 0 && (
            <div aria-hidden className="mt-5 flex gap-1.5">
              {track.map((part, index) => (
                <div
                  key={part.label}
                  className="flex min-w-0 flex-col items-center gap-1.5"
                  style={{ flex: `${part.size} 1 0` }}
                >
                  <div
                    className="h-2.5 w-full overflow-hidden"
                    style={{
                      borderRadius: "var(--radius-xs)",
                      // "전체" 칸은 묶음과 성격이 달라 한 단계 옅게 둔다.
                      background:
                        part.kind === "rest" ? "var(--sand)" : "var(--sand-deep)",
                    }}
                  >
                    <div
                      className="h-full"
                      style={{
                        width: `${(part.filled / part.size) * 100}%`,
                        background: "var(--brand)",
                      }}
                    />
                  </div>
                  <span
                    className="text-[length:var(--text-11)]"
                    style={{
                      fontWeight:
                        index === current
                          ? "var(--weight-black)"
                          : "var(--weight-bold)",
                      color:
                        index === current ? "var(--brand)" : "var(--text-muted)",
                    }}
                  >
                    {part.label}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div
        className="rise px-5 py-4 [animation-delay:240ms]"
        style={{ background: "var(--background-deep)" }}
      >
        <Link
          href={routes.testDaily}
          className="dv-btn flex items-center justify-center px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={
            {
              "--lift": "var(--lift-button)",
              minHeight: "var(--hit-min)",
              borderRadius: "var(--radius-pill)",
              background: "var(--brand)",
              color: "var(--text-on-color)",
              fontWeight: "var(--weight-black)",
              letterSpacing: "var(--tracking-tight)",
              textDecoration: "none",
            } as React.CSSProperties
          }
        >
          {first.kind === "start" ? "시작하기" : "이어서 하기"}
        </Link>
      </div>
    </section>
  );
}
