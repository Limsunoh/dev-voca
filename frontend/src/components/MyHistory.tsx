import type { History, HistoryDay } from "@/lib/api/history";

/**
 * 내 학습 기록. 최근 14일 칸과 최근 판 목록.
 *
 * 내정보의 "학습 기록" 에서 순위 아래에 놓인다. 순위는 "남과 견줘 어디인가"
 * 이고 이것은 "내가 언제 무엇을 했나" 라, 두 카드로 나눈다.
 *
 * 누를 것이 없다. 보는 자리라 dv-card-press 를 걸지 않는다.
 */
export function MyHistory({ history }: { history: History | null }) {
  return (
    <div
      className="px-4 py-4 dv-card sm:px-5"
      style={
        {
          background: "var(--paper)",
          borderRadius: "var(--radius-2xl)",
          "--lift": "var(--lift-card)",
        } as React.CSSProperties
      }
    >
      {history ? <Body history={history} /> : <Unavailable />}
    </div>
  );
}

function Body({ history }: { history: History }) {
  const scored = history.days.filter((d) => d.total > 0).length;

  return (
    <>
      <h3
        className="text-xs tracking-[var(--tracking-wide)]"
        style={{ color: "var(--text-dim)", fontWeight: "var(--weight-black)" }}
      >
        최근 {history.days.length}일
      </h3>
      <p className="mt-1 text-sm" style={{ color: "var(--text-body)" }}>
        {scored > 0
          ? `${history.days.length}일 중 ${scored}일 점수를 얻었습니다.`
          : "최근에 점수를 얻은 날이 없습니다."}
      </p>

      <DayStrip days={history.days} />

      {/* "한 판" 이라고만 쓰지 않는다. 이 저장소에서 "한 판" 은 90초 모드의
          이름이라, 그 아래 판이 열 개 나오면 "가장 최근 한 번" 으로 읽힌다. */}
      <h3
        className="mt-5 text-xs tracking-[var(--tracking-wide)]"
        style={{ color: "var(--text-dim)", fontWeight: "var(--weight-black)" }}
      >
        최근 푼 판
      </h3>
      {history.rounds.length === 0 ? (
        <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
          아직 끝낸 판이 없습니다.
        </p>
      ) : (
        <ol className="mt-2 grid gap-1.5">
          {history.rounds.map((round, index) => (
            // key 를 index 로 둔다. 서버가 판의 pk 를 보내지 않는다 - 화면이
            // 쓸 곳이 아직 없다(token_id 는 판 토큰의 일부라 보내면 안 된다).
            // 서버에서 그린 뒤 바뀌지 않는 목록이라 index 로 충분하다.
            <li
              key={index}
              className="flex items-baseline justify-between gap-3 px-3 py-2 text-sm"
              style={{
                background: "var(--background-deep)",
                borderRadius: "var(--radius-lg)",
              }}
            >
              <span style={{ color: "var(--text-muted)" }}>
                {dayText(round.day)}
              </span>
              <span
                className="tabular-nums"
                style={{ color: "var(--text-body)" }}
              >
                {round.answered}문제 중 {round.correct}개 정답
              </span>
              <span
                className="ml-auto font-mono tabular-nums"
                style={{
                  color: "var(--foreground)",
                  fontWeight: "var(--weight-bold)",
                }}
              >
                {round.score}점
              </span>
            </li>
          ))}
        </ol>
      )}
    </>
  );
}

/**
 * 14일 칸. 점수를 얻은 날만 칠한다.
 *
 * 점수 크기로 진하기를 나누지 않는다. 이 칸이 답하는 질문은 "며칠 했나" 라
 * 꾸준함 순위표와 같은 자로 잰다. 점수는 칸을 누르지 않아도 읽히도록
 * 화면 읽기 프로그램용 글에 적는다.
 *
 * **칠하는 색은 초록이다(코랄이 아니다).** 코랄은 이 앱에서 "주된 동작" 과
 * "오답" 을 맡는다. 해낸 날을 코랄로 칠하면 한 일이 틀린 것처럼 보이고,
 * 화면의 하나뿐인 코랄 버튼("저장")과도 다툰다.
 *
 * 칸 수는 서버가 보낸 대로 따른다. 여기에 14 를 적으면 "며칠을 보여주나" 가
 * 서버와 화면 두 곳에 생긴다.
 */
function DayStrip({ days }: { days: HistoryDay[] }) {
  // 서버는 늘 칸을 채워 보내지만, 응답 모양이 틀려 비어 오면 아래
  // days[0] 에서 터져 내정보 전체가 오류 화면이 된다. 곁들이는 정보가
  // 화면을 깨뜨리지 않게 막는다.
  if (days.length === 0) return null;

  return (
    // 폭을 묶는다. 카드 폭을 다 쓰면 데스크톱에서 칸이 39px 로 커져 칠한
    // 칸이 덩어리로 보이고 화면을 누른다. 폰에서는 카드가 이보다 좁아
    // 영향이 없다.
    <div className="mt-3 max-w-sm">
      <ol
        className="grid gap-1"
        style={{
          gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))`,
        }}
      >
        {days.map((day) => {
          const done = day.total > 0;
          return (
            // 색칠한 칸과 읽기용 글을 떼어 둔다. 색 상자 안에 글을 넣으면
            // (보이지 않는 글이어도) 상자가 글을 담는 틀이 되어 여백 규칙에
            // 걸리고, 칸은 그림일 뿐이라 화면 읽기에는 글만 있으면 된다.
            <li key={day.day}>
              <div
                aria-hidden
                className="aspect-square"
                style={{
                  background: done ? "var(--green)" : "var(--background-deep)",
                  borderRadius: "var(--radius-lg)",
                }}
              />
              <span className="sr-only">
                {dayText(day.day)} {dayLabel(day)}
              </span>
            </li>
          );
        })}
      </ol>
      <div
        className="mt-1 flex justify-between text-xs"
        style={{ color: "var(--text-muted)" }}
        aria-hidden
      >
        <span>{dayText(days[0].day)}</span>
        <span>오늘</span>
      </div>
    </div>
  );
}

/**
 * 칸 하나를 읽어 줄 말.
 *
 * **"0점" 과 "안 함" 을 가른다.** 마이너스 판만 한 날은 하루 점수가 0 으로
 * 잘려 칸이 안 칠해지지만, 그날 공부한 것이다. 그 사람에게 "안 함" 이라고
 * 하면 같은 카드의 판 목록("-3점")과 어긋나고, 망친 날을 아예 없던 날로
 * 만든다(순위표가 "기록이 없습니다" 대신 0점 줄을 보여주는 것과 같은 이유).
 */
function dayLabel(day: HistoryDay): string {
  if (day.total > 0) return `${day.total}점`;
  // 서버가 준 recorded 로 가른다. best_round·daily_study 로 짐작하면 일일공부를
  // 다 틀린 날(감점이 없어 0점)이 "안 함" 으로 읽힌다.
  return day.recorded ? "0점" : "안 함";
}

/**
 * 못 불러왔을 때. 내정보 전체를 오류로 만들지 않는다.
 *
 * role="alert" 를 쓰지 않는다 - 첫 렌더부터 있는 글이라 라이브 리전이
 * 알릴 "새로 나타난 것" 이 아니다(홈의 DailyWordUnavailable 과 같은 이유).
 */
function Unavailable() {
  return (
    <p className="text-sm" style={{ color: "var(--text-muted)" }}>
      학습 기록을 불러오지 못했습니다. 잠시 뒤에 다시 열어보세요.
    </p>
  );
}

/**
 * "9월 23일". 서버가 한국 날짜 문자열("2026-09-23")로 보내므로 Date 로
 * 바꾸지 않고 잘라 쓴다 - Date 로 바꾸면 기기 시간대에 따라 하루 밀린다.
 */
function dayText(day: string): string {
  const [, month, date] = day.split("-");
  return `${Number(month)}월 ${Number(date)}일`;
}
