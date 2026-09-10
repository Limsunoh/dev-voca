import type { RoundQuestion } from "@/lib/api/rounds";

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
        <p
          className="mt-1"
          style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)" }}
        >
          {question.question}
        </p>
        <p
          className={[
            "mt-3",
            // 단어·에러 메시지는 고정폭, 사람이 쓴 문장은 가변폭.
            question.kind === "situation" || question.kind === "blank"
              ? ""
              : "font-mono",
          ].join(" ")}
          style={{
            fontSize: "var(--text-xl)",
            fontWeight: "var(--weight-black)",
            lineHeight: "var(--leading-tight)",
            // 고정폭 제목은 한 단계 더 좁힌다(가이드 type-mono).
            letterSpacing:
              question.kind === "situation" || question.kind === "blank"
                ? "var(--tracking-tight)"
                : "var(--tracking-tighter)",
            color: "var(--foreground)",
          }}
        >
          {question.prompt}
        </p>
      </div>

      <ul className="flex flex-col gap-2.5">
        {question.choices.map((choice) => (
          <li key={choice.id}>
            <button
              type="button"
              onClick={() => onPick(choice.id)}
              disabled={busy}
              // dv-card dv-card-press: 누르면 두께가 0 이 되고 그만큼
              // 내려앉는다. :active 는 인라인 style 로 못 써서 공통 클래스가 맡는다.
              className="dv-card dv-card-press w-full px-4 py-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-default"
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
