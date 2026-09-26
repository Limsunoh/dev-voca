import type { RoundQuestion } from "@/lib/api/rounds";
import {
  choicesAreTerms,
  promptIsEnglish,
  promptIsMono,
  promptIsSentence,
} from "@/lib/quiz-text";

/**
 * 문제 하나와 보기들.
 *
 * 일일공부와 복습이 같이 쓴다. 두 화면은 머리말이 다르고(점수·진행률 대
 * 연속 횟수) 그 아래는 같다 - 같은 문제 모양을 서버가 내려주기 때문이다.
 * 복사해두면 보기 버튼의 터치 높이나 발음기호 서체를 한쪽만 고치게 된다.
 *
 * 결과 문구는 여기 두지 않는다. "정답/오답" 다음에 무엇을 덧붙이느냐가
 * 화면마다 다르다 - 일일공부는 점수, 복습은 "한 번 더 맞히면 끝" 이다.
 *
 * 보기 버튼의 생김새는 QuizBoard 가 아니라 여기에도 한 벌 있다. 두 곳의
 * 상태가 다르기 때문이다 - 여기는 고르기 전(idle)만 그리고 채점 결과는
 * 호출부가 자기 방식으로 알린다. 치수(56px · --radius-xl)와 두께만 같이
 * 간다.
 */
export function QuestionCard({
  question,
  busy,
  onPick,
}: {
  question: RoundQuestion;
  busy: boolean;
  onPick: (id: number) => void;
}) {
  const mono = promptIsMono(question.kind, question.sentence_kind);
  const sentence = promptIsSentence(question.kind);

  return (
    <>
      <div
        className="px-5 py-6"
        style={{
          background: "var(--paper)",
          borderRadius: "var(--radius-2xl)",
          // 누르는 것이 아니라 읽는 카드다. :active 가 없으니 인라인
          // boxShadow 로 둔다 - --lift 로 넘길 이유가 없다.
          boxShadow: "var(--lift-card)",
        }}
      >
        <div className="flex items-baseline justify-between gap-3">
          <p
            style={{
              fontSize: "var(--text-xs)",
              fontWeight: "var(--weight-bold)",
              letterSpacing: "var(--tracking-wide)",
              // --text-dim 은 흰 종이 위에서도 3.85:1 이라 본문 대비 4.5:1 에
              // 못 미친다. 라벨이라 작을수록 더 필요하다.
              color: "var(--text-muted)",
            }}
          >
            {question.kind_label}
          </p>
          {/* **제한 시간을 문제 옆에 적는다.**
              한 판은 문제마다 제한 시간이 다르다 - 지문이 단어면 3초,
              문장이면 7초다(backend quiz.TIME_LIMITS_MS). 그 안에 맞혀야
              +1 이고 지나서 맞히면 0 인데, 화면에 없으니 끝나고 점수를
              보고서야 안다. 위의 판 타이머는 90초 전체라 이것과 다르다.

              값이 없으면 안 그린다. 시간을 안 재는 화면(일일학습·복습)이
              같은 카드를 쓴다. */}
          {question.time_limit_ms != null && (
            <p
              className="tabular-nums"
              style={{
                fontSize: "var(--text-xs)",
                fontWeight: "var(--weight-bold)",
                color: "var(--text-muted)",
              }}
            >
              {Math.round(question.time_limit_ms / 1000)}초 안에
            </p>
          )}
        </div>
        <p
          className="mt-1"
          style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)" }}
        >
          {question.question}
        </p>
        {/* 용어와 에러 메시지 문장만 고정폭, 나머지는 본문체(lib/quiz-text).
            문장은 문제풀기(QuizBoard)와 같은 굵기·줄간격으로 한 단계 푼다 -
            여러 줄로 감기는 문장을 가장 굵게 그리면 글자가 뭉친다.
            전에는 "문장이 아니면 고정폭" 이라 한글 뜻·설명까지 고정폭으로
            나왔다. 고정폭 글꼴에는 한글이 없어 OS 글꼴로 굵고 뭉툭하게
            떨어졌다.

            설명 문제는 여러 줄 한글이라 문제풀기(QuizBoard)와 같게 본문
            크기·보통 굵기로 둔다. 제목 굵기로 두면 다섯 줄이 검은 덩어리가
            된다. */}
        {question.kind === "description" ? (
          <p
            className="mt-3 whitespace-pre-line"
            style={{
              fontSize: "var(--text-md)",
              fontWeight: "var(--weight-medium)",
              lineHeight: "var(--leading-relaxed)",
              color: "var(--text-body)",
            }}
          >
            {question.prompt}
          </p>
        ) : (
          <p
            lang={promptIsEnglish(question.kind) ? "en" : undefined}
            className={`mt-3 ${mono ? "font-mono" : ""}`}
            style={{
              fontSize: "var(--text-xl)",
              fontWeight: sentence
                ? "var(--weight-bold)"
                : "var(--weight-black)",
              lineHeight: sentence
                ? "var(--leading-snug)"
                : "var(--leading-tight)",
              // 고정폭 제목은 한 단계 더 좁힌다(가이드 type-mono).
              letterSpacing: mono
                ? "var(--tracking-tighter)"
                : "var(--tracking-tight)",
              color: "var(--foreground)",
            }}
          >
            {question.prompt}
          </p>
        )}
      </div>

      <ul className="flex flex-col gap-2.5">
        {question.choices.map((choice) => (
          <li key={choice.id}>
            <button
              type="button"
              onClick={() => onPick(choice.id)}
              disabled={busy}
              // 보기가 용어면 고정폭. 문제풀기(QuizBoard)의 보기와 같은 규칙이다.
              lang={choicesAreTerms(question.kind) ? "en" : undefined}
              // dv-card dv-card-press: 누르면 두께가 0 이 되고 그만큼
              // 내려앉는다. :active 는 인라인 style 로 못 써서 공통 클래스가 맡는다.
              className={`dv-card dv-card-press w-full px-4 py-3 text-left ${choicesAreTerms(question.kind) ? "font-mono" : ""} focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-default`}
              style={
                {
                  // 보기는 56px(가이드 shape-hit). 터치로 연달아 누르는
                  // 자리라 --hit-min(52px)보다 한 급 크다.
                  minHeight: 56,
                  background: "var(--paper)",
                  color: "var(--foreground)",
                  borderRadius: "var(--radius-xl)",
                  fontWeight: "var(--weight-bold)",
                  "--lift": "var(--lift-card)",
                } as React.CSSProperties
              }
            >
              {choice.text}
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
