import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { Suspense } from "react";

import { CategoryFilter } from "@/components/CategoryFilter";
import { ChoiceFilter } from "@/components/ChoiceFilter";
import { ExamScopeFilter } from "@/components/ExamScopeFilter";
import { FilterPanel } from "@/components/FilterPanel";
import { LearnHeader } from "@/components/LearnHeader";
import {
  CategoryChip,
  DifficultyBadge,
  ExamBadge,
} from "@/components/MetaBadge";
import { LearningCard } from "@/components/LearningCard";
import { Pagination } from "@/components/Pagination";
import { SearchInput } from "@/components/SearchInput";
import { newShuffleSeed } from "@/lib/api/client";
import {
  ApiError,
  getCategories,
  getDifficulties,
  getExamSubjects,
  getWords,
  WORD_SORTS,
} from "@/lib/api/vocab";
import { detailWithBack, listUrl, routes } from "@/lib/routes";

export const metadata = {
  title: "단어장 | devvoca",
  description: "개발할 때 마주치는 영어 단어를 모아 봅니다.",
  // 주소에 섞은 순서가 붙으면서 같은 내용이 매번 다른 주소가 된다. 검색엔진에
  // 정본이 어느 것인지 알려주지 않으면 같은 목록을 수백 개 주소로 색인한다.
  //
  // generateMetadata 로 바꾸지 않는다 - 값이 고정 문자열이라 요청 정보가
  // 필요 없고, searchParams 를 읽는 순간 metadata 가 막히는 경로가 생긴다.
  alternates: { canonical: routes.words },
};

// Next 16 에서 searchParams 는 Promise 다. 동기 접근은 런타임 에러.
// 이걸 쓰는 것만으로 이 페이지는 요청마다 렌더링된다(항상 최신).
type PageProps = {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

/** searchParams 값은 string | string[] | undefined 라 첫 값만 꺼내 쓴다. */
function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/** 정수가 아니거나 1 미만이면 1 페이지로 본다. */
function toPageNumber(value: string | undefined): number {
  const n = Number(value);
  return Number.isInteger(n) && n > 1 ? n : 1;
}

export default async function VocabPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const search = first(params.search);
  const category = first(params.category);
  const difficulty = first(params.difficulty);
  // 정처기 범위만 보기. 값은 "true" 하나뿐이라 그것만 통과시킨다 -
  // 아무 문자열이나 그대로 백엔드로 보내면 400 이 나고, 화면에는
  // "불러오지 못했습니다" 만 뜬다.
  const examOnly = first(params.is_exam) === "true" ? "true" : undefined;
  const examSubject = first(params.exam_subject);

  // page 는 여기서 한 번만 정규화한다. 검증 없이 넘기면 "abc"·"2.7"·"-1" 이
  // 그대로 백엔드로 가 404 가 되고(DRF Paginator 가 거부한다), 화면에는
  // "2.7 페이지" 같은 표시와 ?page=3.7 링크까지 생긴다.
  const currentPage = toPageNumber(first(params.page));
  const page = currentPage > 1 ? String(currentPage) : undefined;

  // 정렬. 아는 이름만 받는다 - 모르는 값을 그대로 두면 주소에 남아
  // 페이지 넘기기마다 따라다니고, 칩은 아무것도 안 켜진 채로 보인다.
  const sort = WORD_SORTS.find(
    (option) => option.value === first(params.sort),
  );

  // 목록을 열 때마다 새로 섞는다. 정렬이 고정이면 앞쪽 단어만 계속 보이고
  // 뒤쪽은 다음 페이지를 눌러야 만난다.
  //
  // **섞은 순서는 URL 에 적는다.** 시드가 없으면 새로 만들어 주소에 붙인
  // 다음 그 주소로 보낸다(아래 redirect). 그래야 같은 주소가 언제 다시
  // 열려도 같은 순서를 낸다 - 새로고침, 브라우저 뒤로가기, 상세에서
  // 돌아오기가 모두 그 경우다. 탭바나 필터로 새로 들어오면 주소에 시드가
  // 없으니 그때는 새 순서가 나온다.
  //
  // 페이지 넘기기 링크에도 시드를 실어 보낸다 - 안 그러면 1페이지에서 본
  // 단어가 2페이지에 또 나온다.
  //
  // 정렬을 골랐으면 섞지 않는다. 고른 순서를 보러 온 것이다(백엔드도
  // ordering 이 오면 시드를 무시한다 - views.py 의 _shuffle).
  //
  // 검색 중일 때는 섞지 않는다. 찾으러 온 사람에게 섞기는 방해다 -
  // "commit" 을 검색했는데 정확히 그 단어가 12번째에 나오면 안 된다.
  // (백엔드 검색은 관련도 순위가 없어서 기본 정렬이 사실상 그 역할을 한다.)
  //
  // URL 로 들어온 시드는 공백을 털고 길이를 자른다. 자르는 이유는 안 자르면
  // 페이지 넘기기 링크마다 그 길이가 그대로 박히는 것이고(백엔드도 자르지만
  // 그건 SQL 인자 쪽이다), **공백을 터는 이유는 백엔드가 그렇게 보기
  // 때문이다.** `?shuffle=%20` 은 여기서는 값이 있는 것처럼 보이는데
  // 백엔드(`apps/vocab/views.py` 의 `.strip()`)에는 빈 값이라 안 섞는다.
  // 기준이 어긋나면 그 주소는 "섞인 목록" 을 사칭하면서 정렬 고정 목록을
  // 보여주고, 주소가 순서를 기억하는 설계라 그 상태가 계속 따라다닌다.
  const shuffle =
    search || sort
      ? undefined
      : first(params.shuffle)?.trim().slice(0, 64) || undefined;

  // 지금 보고 있는 목록. 페이지 넘기기 링크와 카드의 되돌아올 주소가
  // 이것을 같이 쓴다 - 두 곳에서 따로 조립하면 한쪽만 고쳐지고
  // 되돌아가기가 다른 목록을 가리킨다.
  //
  // **읽어들인 값만 담는다.** params 를 그대로 펼치면 우리가 안 쓰는 키와
  // 정규화 전 값이 주소에 남는다 - `?page=abc` 로 들어온 사람의 주소창에
  // 그 글자가 계속 붙어 다닌다.
  const filters = {
    search,
    category,
    difficulty,
    sort: sort?.value,
    shuffle,
    is_exam: examOnly,
    exam_subject: examSubject,
  };

  if (!search && !shuffle && !sort) {
    // 목록을 부르기 전에 보낸다. 시드 없이 들어올 때마다 왕복이 한 번
    // 늘어난다 - 탭바로 들어올 때와 필터·분류를 누를 때가 그렇다(그쪽
    // 링크들은 시드를 안 싣는다). 그 뒤로는 이 주소가 순서를 기억한다.
    //
    // **기록을 밀지 않고 대체한다.** 서버 컴포넌트에서 부른 redirect 는
    // replace 로 동작하므로(액션에서 부를 때만 push 다) 뒤로가기 한 번에
    // 시드 없는 주소를 거치지 않고 이전 화면으로 간다. 밀렸다면 뒤로가기를
    // 두 번 눌러야 했을 것이다.
    //
    // 주소창에 직접 쳐서 들어오면 307 로 오고, 화면 안에서 눌러 이동하면
    // 서버 응답 안에 같은 신호가 실려 온다. 화면 미리 가져오기는 화면
    // 내용을 만들지 않고 경로 모양만 받아 가므로 이 자리를 지나지 않는다.
    redirect(
      listUrl(
        routes.words,
        { ...filters, shuffle: newShuffleSeed() },
        currentPage,
      ),
    );
  }

  const currentListUrl = listUrl(routes.words, filters, currentPage);

  // 두 요청을 동시에 띄운다. 순서대로 기다리면 두 번의 왕복이 그대로
  // 대기 시간이 된다.
  //
  // 분류 목록은 실패해도 빈 배열이라 절대 throw 하지 않으므로 그냥 await
  // 한다. 목록만 try 로 감싸면 catch 안에서도 분류를 그대로 쓸 수 있다
  // (백엔드가 죽어서 들어온 자리에서 백엔드를 다시 부르지 않는다).
  const listPromise = getWords({
    search,
    category,
    difficulty,
    page,
    shuffle,
    ordering: sort?.ordering,
    is_exam: examOnly,
    exam_subject: examSubject,
  });
  const [categories, difficulties, examSubjects] = await Promise.all([
    getCategories(),
    getDifficulties(),
    getExamSubjects(),
  ]);

  let data;
  try {
    data = await listPromise;
  } catch (error) {
    // 예상 못 한 에러는 error.tsx 로 올려보낸다.
    if (!(error instanceof ApiError)) throw error;

    // 없는 페이지 번호(?page=999)는 DRF 가 404 를 준다. 404 화면을 띄우면
    // "주소가 잘못됐거나 공개되지 않은 단어" 로 읽히므로, 조건은 둔 채 첫
    // 페이지로 보낸다(오답 노트와 같은 동작). 목록이 줄어 옛 링크의 뒤쪽
    // 페이지가 사라진 경우도 여기로 온다.
    //
    // 번호가 있을 때만이다. 번호 없는 404 는 주소 자체가 없는 것이라, 첫
    // 페이지로 보내면 같은 주소로 끝없이 돌아간다.
    if (error.status === 404) {
      if (page) redirect(listUrl(routes.words, filters));
      notFound();
    }

    // 400 은 대부분 URL 의 조건값이 잘못된 경우다(오타·오래된 북마크).
    // 서버 문제가 아니므로 그렇게 안내하고, 상태 코드는 보여주지 않는다.
    const badRequest = error.status === 400;

    return (
      <main className="mx-auto w-full max-w-3xl px-4 py-10">
        <LearnHeader
          mode="learn"
          content="words"
          title="단어장"
          description="개발할 때 마주치는 영어 단어를 모았습니다."
        />

        {/* 에러 화면에도 필터를 남긴다. 없으면 잘못된 조건으로 들어온
            사용자가 조건을 바꿀 수단이 없어 막다른 화면이 된다. */}
        <CategoryFilter options={categories} basePath={routes.words} />

        {/* 경고 카드. 테두리를 쓰지 않는다 - 크림에서 경계는 채움과 두께가
            맡는다(가이드 shape-lift). 옅은 앰버 채움이 흰 카드들 사이에서
            충분히 눈에 띈다. */}
        <p
          className="dv-card mt-6 p-4"
          style={
            {
              background: "var(--amber-soft)",
              color: "var(--amber-deep)",
              borderRadius: "var(--radius-2xl)",
              fontWeight: "var(--weight-bold)",
              "--lift": "var(--lift-card)",
            } as React.CSSProperties
          }
        >
          {badRequest
            ? "검색 조건이 올바르지 않습니다. 위에서 분류를 다시 골라보세요."
            : `단어를 불러오지 못했습니다. ${error.message}`}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10">
      <LearnHeader
        mode="learn"
        content="words"
        title="단어장"
        description="개발할 때 마주치는 영어 단어를 모았습니다."
      />

      <div className="mt-6">
        {/* useSearchParams 를 쓰는 컴포넌트는 Suspense 로 감싼다.
            없으면 프로덕션 빌드가 실패한다. */}
        <Suspense fallback={<div className="h-[46px]" />}>
          {/* key 가 바뀌면 입력창이 새로 만들어진다 - 뒤로가기로 검색어가
              달라졌을 때 입력창이 URL 을 따라가게 하는 방법. */}
          <SearchInput key={search ?? ""} basePath={routes.words} />
        </Suspense>
      </div>

      {/* 필터 링크에는 시드를 싣지 않는다. 그래서 난이도나 분류를 누르면
          그 조건 안에서 새로 섞인 목록이 나온다. 정렬은 싣는다 - 쉬운
          것부터 보다가 분류를 바꿨는데 순서가 풀리면 다시 골라야 한다.

          배지는 정렬도 센다. 필터가 접혀 있을 때 순서가 바뀌어 있다는
          것을 알려줄 곳이 배지뿐이다. */}
      <FilterPanel
        active={[difficulty, category, examOnly, examSubject, sort?.value]}
      >
        {/* 정처기 줄이 맨 위다. 다른 조건은 목록을 좁히지만 이건 무엇을
            공부하는지 자체를 바꾼다 - 정처기를 켠 사람에게 분류(Git·리뷰)는
            부차적이고 과목이 먼저다.

            ChoiceFilter 를 쓰지 않는 이유: 그건 여러 값 중 하나를 고르는
            줄이고, 이건 켜고 끄는 하나다. 값이 하나뿐인 목록을 만들면
            "전체 / 정처기" 처럼 읽혀 무엇이 기본인지 흐려진다. */}
        <ExamScopeFilter
          basePath={routes.words}
          active={Boolean(examOnly)}
          keep={{ search, category, difficulty, sort: sort?.value }}
        />

        {/* 과목은 정처기를 켰을 때만 뜬다. 안 켠 사람에게는 5과목이
            무슨 말인지 알 수 없는 줄이 하나 더 있는 셈이다. */}
        {examOnly && (
          <ChoiceFilter
            label="과목"
            paramName="exam_subject"
            options={examSubjects}
            basePath={routes.words}
            selected={examSubject}
            keep={{
              search,
              category,
              difficulty,
              is_exam: examOnly,
              sort: sort?.value,
            }}
          />
        )}

        <ChoiceFilter
          label="난이도"
          paramName="difficulty"
          options={difficulties}
          basePath={routes.words}
          selected={difficulty}
          keep={{
            search,
            category,
            is_exam: examOnly,
            exam_subject: examSubject,
            sort: sort?.value,
          }}
        />

        <CategoryFilter
          options={categories}
          basePath={routes.words}
          selected={category}
          search={search}
          difficulty={difficulty}
          extra={{
            is_exam: examOnly,
            exam_subject: examSubject,
            sort: sort?.value,
          }}
        />

        {/* 정렬은 맨 아래다. 위 줄들은 무엇을 볼지 좁히고, 이것은 그것을
            어떤 순서로 볼지만 정한다. 고르지 않으면 섞는다.

            검색 중에는 섞지 않으므로(위 shuffle) 맨 앞 칩을 "기본순" 이라
            부른다. "섞어서" 로 두면 켜진 칩이 실제 순서와 다른 말을 한다. */}
        <ChoiceFilter
          label="정렬"
          paramName="sort"
          options={WORD_SORTS}
          allLabel={search ? "기본순" : "섞어서"}
          basePath={routes.words}
          selected={sort?.value}
          keep={{
            search,
            category,
            difficulty,
            is_exam: examOnly,
            exam_subject: examSubject,
          }}
        />
      </FilterPanel>

      {/* 24px 이던 것을 줄였다. 필터 상자가 테두리를 갖고 있어 그대로 두면
          사이가 벌어져 보인다. 접혔을 때는 상자가 없지만 그때는 위가 알약
          하나뿐이라 역시 16px 이 맞다. */}
      <p
        className="mt-4"
        style={{
          fontSize: "var(--text-sm)",
          color: "var(--text-muted)",
          fontWeight: "var(--weight-bold)",
        }}
      >
        {search ? `"${search}" 검색 결과 ` : "전체 "}
        {data.count}개
      </p>

      {data.results.length === 0 ? (
        // 바깥이 div 인 이유: 조건을 걸어 비었을 때 안내 아래에 "조건
        // 지우기" 링크가 붙는데, 그 둘을 p 하나에 넣으면 브라우저가 문단을
        // 끊는다. 안내 문구는 안쪽에서 다시 p 로 감싼다 - 그래야 문단으로
        // 읽히고, 두 줄로 접혔을 때 text-center 가 둘째 줄에도 걸린다
        // (익명 flex 아이템에는 클래스가 안 붙는다).
        // 빈 자리는 옅은 띠로 둔다. 흰 카드로 두면 목록에 카드가 한 장
        // 있는 것처럼 보이는데, 내용이 없다는 것이 이 상자의 뜻이다.
        // 띠는 그림자 없이 면으로만 구분한다(FilterPanel 이 쓰는 문법).
        <div
          className="mt-8 flex flex-col items-center p-6 text-center"
          style={{
            background: "var(--background-deep)",
            borderRadius: "var(--radius-2xl)",
            color: "var(--text-muted)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          {/* 분류만 걸어 비었을 때 "등록된 단어가 없다"고 하면 서비스 전체가
              비어 있다는 뜻으로 읽힌다. 조건을 좁힌 결과임을 알려준다. */}
          {search || category || difficulty || examOnly || examSubject ? (
            <>
              <p>조건에 맞는 단어가 없습니다.</p>
              {/* 필터가 접혀 있으면 "위에서 조건을 바꿔보세요" 는 안 보이는
                  것을 가리키게 된다. 조건을 좁히다 0 이 되는 것은 흔한
                  경로라(분류 9 x 난이도 4) 여기서 바로 풀 수 있게 둔다.
                  링크라 서버 컴포넌트 그대로이고 접힘과 무관하게 보인다. */}
              <Link
                href={routes.words}
                className="dv-btn mt-4 inline-flex min-h-11 items-center rounded-full px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                style={
                  {
                    background: "var(--paper)",
                    color: "var(--foreground)",
                    fontSize: "var(--text-sm)",
                    fontWeight: "var(--weight-black)",
                    // 쉬는 두께는 --lift 로. 인라인 box-shadow 는 :active 를 이긴다.
                    "--lift": "var(--lift-button-paper)",
                  } as React.CSSProperties
                }
              >
                조건 지우기
              </Link>
            </>
          ) : (
            <p>아직 등록된 단어가 없습니다.</p>
          )}
        </div>
      ) : (
        <ul className="mt-4 grid gap-3">
          {data.results.map((word) => (
            <li key={word.id}>
              <LearningCard
                href={detailWithBack(
                  routes.wordDetail(word.id),
                  currentListUrl,
                )}
                title={word.term}
                aside={word.pronunciation || undefined}
                reading={word.reading || undefined}
                subtitle={word.meaning}
                badge={
                  <DifficultyBadge
                    level={word.difficulty}
                    label={word.difficulty_label}
                  />
                }
                tag={
                  // 카드 전체가 이미 링크라 여기는 링크로 만들지 않는다.
                  // 링크 안의 링크는 마크업이 깨지고 키보드 순서도 꼬인다.
                  //
                  // 정처기 배지가 앞이다. 분류는 566개 전부 갖고 있어 훑을 때
                  // 눈에 안 들어오지만, 정처기는 일부만 달려서 그 자체가 신호다.
                  word.is_exam || word.category_label ? (
                    <div className="flex flex-wrap items-center gap-2">
                      {word.is_exam && (
                        <ExamBadge subjectLabel={word.exam_subject_label} />
                      )}
                      <CategoryChip label={word.category_label} />
                    </div>
                  ) : undefined
                }
              />
            </li>
          ))}
        </ul>
      )}

      {/* 페이지 넘기기에는 시드를 실어 보낸다. 필터와 반대다 - 여기서
          시드가 빠지면 2페이지가 새 순서로 섞여서 1페이지에 본 단어를
          또 만나고 어떤 단어는 아예 못 만난다. */}
      <Pagination
        basePath={routes.words}
        filters={filters}
        currentPage={currentPage}
        hasPrevious={Boolean(data.previous)}
        hasNext={Boolean(data.next)}
      />
    </main>
  );
}
