import Link from "next/link";

import { Avatar } from "@/components/Avatar";
import { SurfaceLayer } from "@/components/SurfaceLayer";
import type { User } from "@/lib/api/accounts";
import { getDailyWord, type WordListItem } from "@/lib/api/vocab";
import { routes } from "@/lib/routes";
import { getCurrentUser } from "@/lib/session";

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

  const [user, word]: [User | null, WordListItem | null] = await Promise.all([
    userPromise,
    wordPromise,
  ]);

  return (
    <>
      {/* 홈이 보여주는 것이 단어라 단어·문장과 같은 배경을 쓴다.
          문제풀이와 내정보는 각자 다른 배경을 받을 예정이다. */}
      <SurfaceLayer variant="surface-learn" />

      <main className="mx-auto flex w-full max-w-md flex-1 flex-col px-5 pt-6">
        <Greeting user={user} />
        {word ? <DailyWord word={word} /> : <DailyWordUnavailable />}
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
function Greeting({ user }: { user: User | null }) {
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
          className="shrink-0 rounded-full border border-white/20 px-3.5 py-2 text-sm font-medium text-slate-100 transition hover:border-white/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
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
    </header>
  );
}

/** 오늘의 단어. 포스터처럼 크게 두고 아래로 뜻과 진입을 붙인다. */
function DailyWord({ word }: { word: WordListItem }) {
  return (
    <section
      aria-labelledby="daily-word"
      className="mt-8 flex flex-1 flex-col justify-center pb-10"
    >
      <p className="text-sm font-medium text-focus">오늘의 단어</p>

      <h1
        id="daily-word"
        className="mt-3 font-mono text-[2.75rem] leading-none font-bold tracking-tighter text-slate-50"
      >
        {word.term}
      </h1>

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

      <div className="mt-7 h-px bg-gradient-to-r from-focus/50 via-white/10 to-transparent" />

      <div className="mt-7 flex gap-2.5">
        <Link
          href={routes.wordDetail(word.id)}
          className="flex min-h-12 flex-1 items-center justify-center rounded-full bg-focus px-5 font-semibold text-focus-on transition active:translate-y-px focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          더 보기
        </Link>
        <Link
          href={routes.words}
          className="flex min-h-12 flex-1 items-center justify-center rounded-full border border-white/15 px-5 font-semibold text-slate-100 transition active:translate-y-px focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
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
