import Link from "next/link";
import { redirect } from "next/navigation";

import { Avatar } from "@/components/Avatar";
import { HomeTasks } from "@/components/HomeTasks";
import { RecordSheet } from "@/components/RecordSheet";
import { SurfaceLayer } from "@/components/SurfaceLayer";
import type { User } from "@/lib/api/accounts";
import { fetchDailyStatus, type StudyProgress } from "@/lib/api/daily";
import { type Board, fetchBoard } from "@/lib/api/leaderboards";
import { fetchDue, type ReviewDue } from "@/lib/api/review";
import { getDailyWord, type WordListItem } from "@/lib/api/vocab";
import { routes } from "@/lib/routes";
import { getCurrentUser, getToken, isGuestChosen } from "@/lib/session";

/**
 * 홈.
 *
 * 사이트 랜딩이 아니라 앱을 열었을 때 처음 보는 화면이다. 그래서 서비스를
 * 설명하지 않고 오늘 볼 것을 바로 보여준다. 이동은 아래 탭바가 맡으므로
 * 여기에 목록으로 가는 버튼을 늘어놓지 않는다.
 *
 * 무엇을 더 놓을지(학습 기록·점수·스트릭)는 아직 정해지지 않아서 지금
 * 있는 것만으로 채웠다. 없는 숫자를 0 으로 채워두지 않는다 - 0 은 "내가
 * 아직 안 한 것" 으로 읽혀서 기능이 없는 것인지 구분되지 않는다.
 */
export default async function Home() {
  // **아직 아무것도 안 고른 사람은 첫 화면으로.** 앱은 열자마자 "누구로
  // 시작할지" 를 묻는다. 로그인했거나 게스트를 고른 적이 있으면 건너뛴다.
  //
  // 홈에서만 보는 이유: 앱의 진입점이 홈이다. 다른 경로로 바로 들어온
  // 사람(공유 링크 등)까지 막으면 그 링크가 안 열린다.
  if (!(await getCurrentUser()) && !(await isGuestChosen())) {
    redirect("/start");
  }

  // 두 요청을 동시에 띄운다. 순서대로 기다리면 두 번의 왕복이 그대로
  // 대기 시간이 되고, 그게 앱을 열자마자 보이는 시간이다.
  const userPromise = getCurrentUser();

  // 백엔드가 죽어도 홈은 떠야 한다. 앱을 열었는데 첫 화면이 에러면
  // 다른 데로 갈 방법도 같이 사라진다(탭바가 이 화면 아래에 있다).
  //
  // 조용히 삼키지는 않는다. 로그가 없으면 백엔드가 죽은 것과 이 코드의
  // 버그를 구분할 수 없고, 화면에는 둘 다 "불러오지 못했습니다" 로만 뜬다.
  const wordPromise = getDailyWord().catch((error: unknown) => {
    console.error("오늘의 단어를 불러오지 못했습니다.", error);
    return null;
  });

  // **토큰은 catch 밖에서 읽는다.** 안에 넣으면 쿠키 접근이 일으키는
  // DynamicServerError 까지 잡혀서, 정상 동작인데 빌드 로그에 에러가
  // 쌓인다. 그러면 진짜 오류가 그 사이에 묻힌다.
  const token = await getToken();

  // 순위 카드는 곁들이는 것이라 실패해도 홈을 막지 않는다. 오늘의 단어와
  // 같은 이유로 조용히 삼키지 않고 로그는 남긴다.
  const boardPromise = fetchBoard("weekly", token ?? undefined).catch(
    (error: unknown) => {
      console.error("순위표를 불러오지 못했습니다.", error);
      return null;
    },
  );

  // 공부한 날 수. 칩에만 쓴다.
  //
  // **연속 일수가 아니다.** 백엔드의 꾸준함 순위표 entries 는
  // Sum(_DAY_COUNTS) - 점수를 얻은 날을 모두 더한 값이라, 띄엄띄엄
  // 해도 쌓인다(leaderboards.py:323). 그래서 화면에도 "연속" 이라고
  // 쓰지 않는다. 진짜 연속 일수는 백엔드에 계산이 없다.
  //
  // 주간 순위표의 entries 로는 못 구한다 - 저건 이번 주 판 수다.
  // 로그인 안 했으면 내 줄이 없으므로 아예 안 부른다.
  const streakPromise = token
    ? fetchBoard("streak", token).catch((error: unknown) => {
        console.error("연속 학습을 불러오지 못했습니다.", error);
        return null;
      })
    : Promise.resolve(null);

  // 일일공부는 로그인해야 쓸 수 있다. 게스트에게는 아예 안 물어본다 -
  // 못 누르는 카드를 띄워두면 눌러보고 로그인으로 튕기는 경험이 된다.
  const dailyPromise = token
    ? fetchDailyStatus(token)
        .then((s) => s.today)
        .catch((error: unknown) => {
          console.error("일일공부 상태를 불러오지 못했습니다.", error);
          return null;
        })
    : Promise.resolve(null);

  // 복습도 로그인해야 쓴다. 실패해도 홈을 막지 않는다 - 카드 하나가
  // 안 뜰 뿐이고, 없으면 어차피 안 그리는 카드다.
  const duePromise = token
    ? fetchDue(token).catch((error: unknown) => {
        console.error("복습 개수를 불러오지 못했습니다.", error);
        return null;
      })
    : Promise.resolve(null);

  const [user, word, board, daily, due, streakBoard]: [
    User | null,
    WordListItem | null,
    Board | null,
    StudyProgress | null,
    ReviewDue | null,
    Board | null,
  ] = await Promise.all([
    userPromise,
    wordPromise,
    boardPromise,
    dailyPromise,
    duePromise,
    streakPromise,
  ]);

  // 내 줄이 상위권이면 rows 안에, 밖이면 me 에 있다.
  const studiedDays =
    streakBoard?.me?.entries ??
    streakBoard?.rows.find((row) => row.is_me)?.entries ??
    0;

  return (
    <>
      {/* 홈이 보여주는 것이 단어라 단어·문장과 같은 배경을 쓴다.
          문제풀이와 내정보는 각자 다른 배경을 받을 예정이다. */}
      <SurfaceLayer variant="surface-learn" />

      <main className="mx-auto flex w-full max-w-md flex-1 flex-col px-5 pt-6">
        <Greeting
          user={user}
          studiedDays={studiedDays}
          board={board}
          daily={daily}
          due={due}
        />
        {word ? <DailyWord word={word} /> : <DailyWordUnavailable />}

        {/* 오늘 할 일. 카드가 아니라 줄이다 - 위의 오늘의 단어와 같은
            무게로 보이면 화면이 무엇을 먼저 보라고 말하지 않는다.

            순위표를 여기 펼치지 않는다. 상위 셋을 늘어놓으면 홈이 순위표
            화면이 되고, 그러면 순위표 화면이 있을 이유가 없어진다. 내
            순위 한 줄만 두고 나머지는 그 화면에 맡긴다. */}
        <HomeTasks
          daily={daily}
          due={due}
          board={board}
          signedIn={user !== null}
        />
      </main>
    </>
  );
}

/**
 * 인사 줄.
 *
 * 사이트 머리말을 대신하는 자리지만 이동 수단은 아니다. 로고와 로그인
 * 버튼을 나란히 둔 줄이 "웹 사이트를 폰에서 연 것" 처럼 보이게 만들던
 * 부분이라, 이름을 부르는 한 줄로 바꿨다. 계정은 "나" 탭이 맡는다.
 */
function Greeting({
  user,
  studiedDays,
  board,
  daily,
  due,
}: {
  user: User | null;
  studiedDays: number;
  board: Board | null;
  daily: StudyProgress | null;
  due: ReviewDue | null;
}) {
  if (!user) {
    return (
      // 로그인 입구를 여기 둔다. 웹 머리말을 없애면서 "가입하기" 버튼이
      // 같이 사라졌는데, "나" 탭을 눌러야 로그인이 나온다는 건 알아채기
      // 어렵다. 로그인 안 한 사람에게 "나" 는 자기 것이 없는 탭으로 읽힌다.
      <header className="flex items-center justify-between gap-3">
        <p className="text-lg font-semibold tracking-tight text-slate-100">
          오늘의 개발 영어
        </p>
        <Link
          href={routes.login}
          className="shrink-0 rounded-full border border-white/40 px-3.5 py-2 text-sm font-medium text-slate-100 transition-[scale,border-color] duration-[120ms] ease-press hover:border-white/60 active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          로그인
        </Link>
      </header>
    );
  }

  return (
    <header className="flex items-center gap-3">
      <Avatar shown={user.avatar_display} size={40} />
      <p className="min-w-0 truncate text-lg font-semibold tracking-tight">
        <span className="text-slate-100">{user.name}</span>
        <span className="font-normal text-slate-300">님</span>
      </p>

      {/* 공부한 날이 0 이면 칩을 안 그린다. "0일" 은 격려가 아니라
          아직 아무것도 안 했다는 통보라 첫 화면에 둘 것이 못 된다.
          그 대신 아래 일일공부 줄이 무엇을 할지 말해준다. */}
      {studiedDays > 0 && (
        <RecordSheet studiedDays={studiedDays}>
          <TodayRecord
            daily={daily}
            due={due}
            board={board}
            studiedDays={studiedDays}
          />
        </RecordSheet>
      )}
    </header>
  );
}

/**
 * 기록 시트 안에 들어가는 내용.
 *
 * 홈 화면에 이미 있는 것(오늘 할 일 줄)을 그대로 되풀이하지 않는다.
 * 여기 두는 것은 "쌓여온 것" 이다 - 연속 며칠인지, 이번 주에 몇 점인지.
 * 화면에 늘 띄우기엔 오늘 할 일보다 급하지 않고, 그렇다고 없으면
 * 매일 여는 이유가 약해지는 값들이다.
 */
function TodayRecord({
  daily,
  due,
  board,
  studiedDays,
}: {
  daily: StudyProgress | null;
  due: ReviewDue | null;
  board: Board | null;
  studiedDays: number;
}) {
  const mine = board?.me ?? board?.rows.find((row) => row.is_me);

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-2">
        <Stat label="공부한 날" value={`${studiedDays}일`} accent />
        <Stat
          label="오늘 일일공부"
          value={
            daily?.done
              ? "마침"
              : daily
                ? `${daily.answered}/${daily.total}`
                : "아직"
          }
        />
      </div>

      <dl className="flex flex-col">
        <Line label="다시 볼 것" value={due ? `${due.due}개` : "없음"} />
        <Line label="이번 주 순위" value={mine ? `${mine.rank}위` : "기록 없음"} />
        <Line label="이번 주 점수" value={mine ? `${mine.score}점` : "0점"} />
      </dl>
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-xl border border-white/12 bg-slate-950/50 px-3 py-2.5">
      <p className="font-mono text-[10px] tracking-wider text-slate-400">
        {label}
      </p>
      <p
        className={`mt-0.5 font-mono text-lg font-bold tracking-tight tabular-nums ${
          accent ? "text-focus" : "text-slate-50"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-t border-white/10 py-2.5 text-sm">
      <dt className="text-slate-400">{label}</dt>
      <dd className="font-mono text-xs font-semibold text-focus tabular-nums">
        {value}
      </dd>
    </div>
  );
}

/** 오늘의 단어. 포스터처럼 크게 두고 아래로 뜻과 진입을 붙인다. */
function DailyWord({ word }: { word: WordListItem }) {
  return (
    <section
      aria-labelledby="daily-word"
      className="mt-8 flex flex-1 flex-col justify-center pb-10"
    >
      {/* 네 덩이가 80ms 씩 차이를 두고 올라온다: 라벨(0) · 단어(80) ·
          발음과 뜻(160) · 구분선과 버튼(240). 마지막 덩이는 요소가 둘이지만
          같은 240ms 를 공유해 한 덩이로 움직인다.

          하루 한 번 여는 화면이고 여기가 이 앱의 첫인상이라, 모션 예산을
          여기에 쓴다.

          한 덩이로 묶지 않고 나눈 이유: 통째로 올라오면 그냥 화면이 밀려
          들어온 것으로 보인다. 순서가 있으면 무엇부터 읽어야 하는지가
          같이 전달된다 - 라벨, 단어, 뜻, 그다음에 갈 곳.

          마지막 덩이가 240ms 에 시작해 560ms 에 끝난다. 그전에 누를 수
          있는 것이 없으니 조작을 막지 않는다. */}
      <p className="rise text-sm font-medium text-focus">오늘의 단어</p>

      <h1
        id="daily-word"
        className="rise mt-3 font-mono text-[2.75rem] leading-none font-bold tracking-tighter text-slate-50 [animation-delay:80ms]"
      >
        {word.term}
      </h1>

      {/* flex 로 두는 이유: 그냥 div 면 첫 자식의 위 여백이 이 상자를 뚫고
          부모로 새어나간다(margin collapse). 그러면 상자만 올라오고 여백은
          제자리에 남아서, 발음기호가 없는 단어에서 뜻이 잘못된 위치에서
          출발한다. flex 컨테이너는 자식 여백을 안에 가둔다. */}
      <div className="rise flex flex-col [animation-delay:160ms]">
        {word.pronunciation && (
          // 발음기호는 고정폭으로 두지 않는다. IPA 기호가 고정폭 글꼴에서
          // 깨지거나 폭이 어긋나는 경우가 있다.
          <p lang="en-US" className="mt-4 text-base text-slate-300">
            {word.pronunciation}
          </p>
        )}

        <p className="mt-5 text-xl leading-snug font-semibold tracking-tight text-slate-100">
          {word.meaning}
        </p>
      </div>

      <div className="rise mt-7 h-px bg-gradient-to-r from-focus/50 via-white/10 to-transparent [animation-delay:240ms]" />

      {/* flex-wrap 을 준다. 글자를 200% 로 키우면 버튼 둘이 한 줄에 못
          들어가는데, 안 주면 줄바꿈 대신 화면 밖으로 밀린다. */}
      <div className="rise mt-7 flex flex-wrap gap-2.5 [animation-delay:240ms]">
        <Link
          href={routes.wordDetail(word.id)}
          className="flex min-h-12 flex-1 items-center justify-center rounded-full bg-focus px-5 font-semibold text-focus-on transition-[scale] duration-[120ms] ease-press active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          더 보기
        </Link>
        <Link
          href={routes.words}
          // 테두리가 유일한 "여기가 버튼" 신호다. white/15 는 1.5:1 이라
          // WCAG 1.4.11 이 컨트롤 경계에 요구하는 3:1 에 못 미치고,
          // 옆의 "더 보기"(bg-focus, 13:1)와 나란히 서면 이쪽만 눌리지
          // 않는 글자처럼 보인다. SearchInput 이 이미 white/40 을 쓴다.
          className="flex min-h-12 flex-1 items-center justify-center rounded-full border border-white/40 px-5 font-semibold text-slate-100 transition-[scale,border-color] duration-[120ms] ease-press hover:border-white/60 active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          단어장
        </Link>
      </div>
    </section>
  );
}

/**
 * 단어를 못 불러왔을 때.
 *
 * 빈 화면을 두지 않는다. 여기서 막히면 사용자는 앱이 고장 난 것으로 본다.
 */
function DailyWordUnavailable() {
  return (
    // role="alert" 는 쓰지 않는다. 그건 "지금 막 나타난 것" 을 알리는
    // 라이브 리전인데 이건 첫 렌더부터 있는 요소라 리더마다 동작이 갈린다.
    // h1 이라 어차피 읽힌다.
    <section className="mt-8 flex flex-1 flex-col justify-center pb-10">
      <h1 className="text-xl font-semibold tracking-tight text-slate-100">
        오늘의 단어를 불러오지 못했습니다.
      </h1>
      {/* "단어장은 볼 수 있다" 고 안내하지 않는다. 단어를 못 불러오는
          상황이면 단어장도 같이 못 뜨는데, 그 문구를 믿고 눌렀다가 또
          실패 화면을 보게 된다. */}
      <p className="mt-2 text-slate-300">잠시 뒤에 다시 열어보세요.</p>
    </section>
  );
}
