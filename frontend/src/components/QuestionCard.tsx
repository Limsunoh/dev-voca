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
      <div className="rounded-2xl border border-white/12 bg-slate-950/40 px-5 py-6">
        <p className="text-xs text-slate-500">{question.kind_label}</p>
        <p className="mt-1 text-sm text-slate-400">{question.question}</p>
        <p
          className={[
            "mt-3 text-xl font-semibold text-slate-100 sm:text-2xl",
            // 단어·에러 메시지는 고정폭, 사람이 쓴 문장은 가변폭.
            question.kind === "situation" || question.kind === "blank"
              ? ""
              : "font-mono",
          ].join(" ")}
        >
          {question.prompt}
        </p>
      </div>

      <ul className="flex flex-col gap-2">
        {question.choices.map((choice) => (
          <li key={choice.id}>
            <button
              type="button"
              onClick={() => onPick(choice.id)}
              disabled={busy}
              className="min-h-12 w-full rounded-xl border border-white/40 px-4 py-3 text-left text-slate-100 transition-[scale,border-color] duration-[120ms] ease-press hover:border-white/60 active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60"
            >
              {choice.text}
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
