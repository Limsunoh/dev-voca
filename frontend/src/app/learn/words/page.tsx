import { notFound } from "next/navigation";
import { Suspense } from "react";

import { CategoryFilter } from "@/components/CategoryFilter";
import { ChoiceFilter } from "@/components/ChoiceFilter";
import { LearnHeader } from "@/components/LearnHeader";
import { CategoryChip, DifficultyBadge } from "@/components/MetaBadge";
import { LearningCard } from "@/components/LearningCard";
import { Pagination } from "@/components/Pagination";
import { SearchInput } from "@/components/SearchInput";
import { newShuffleSeed } from "@/lib/api/client";
import {
  ApiError,
  getCategories,
  getDifficulties,
  getWords,
} from "@/lib/api/vocab";
import { routes } from "@/lib/routes";

export const metadata = {
  title: "단어장 | devvoca",
  description: "개발할 때 마주치는 영어 단어를 모아 봅니다.",
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

  // page 는 여기서 한 번만 정규화한다. 검증 없이 넘기면 "abc"·"2.7"·"-1" 이
  // 그대로 백엔드로 가 404 가 되고(DRF Paginator 가 거부한다), 화면에는
  // "2.7 페이지" 같은 표시와 ?page=3.7 링크까지 생긴다.
  const currentPage = toPageNumber(first(params.page));
  const page = currentPage > 1 ? String(currentPage) : undefined;

  // 목록을 열 때마다 새로 섞는다. 정렬이 고정이면 앞쪽 단어만 계속 보이고
  // 뒤쪽은 다음 페이지를 눌러야 만난다.
  //
  // 시드가 URL 에 없으면 새로 만든다. 그래서 /learn/words 로 그냥 들어오면
  // (새로고침, 상세에서 뒤로가기, 필터 누르기) 매번 다른 순서가 나온다.
  // 반대로 페이지 넘기기 링크에는 시드를 실어 보내므로 1페이지와 2페이지는
  // 같은 순서를 공유한다 - 안 그러면 1페이지에서 본 단어가 2페이지에 또 나온다.
  //
  // 검색 중일 때는 섞지 않는다. 찾으러 온 사람에게 섞기는 방해다 -
  // "commit" 을 검색했는데 정확히 그 단어가 12번째에 나오면 안 된다.
  // (백엔드 검색은 관련도 순위가 없어서 기본 정렬이 사실상 그 역할을 한다.)
  //
  // URL 로 들어온 시드는 길이를 자른다. 안 자르면 페이지 넘기기 링크마다
  // 그 길이가 그대로 박힌다. 백엔드도 자르지만 그건 SQL 인자 쪽이다.
  const shuffle = search
    ? undefined
    : (first(params.shuffle)?.slice(0, 64) || newShuffleSeed());

  // 두 요청을 동시에 띄운다. 순서대로 기다리면 두 번의 왕복이 그대로
  // 대기 시간이 된다.
  //
  // 분류 목록은 실패해도 빈 배열이라 절대 throw 하지 않으므로 그냥 await
  // 한다. 목록만 try 로 감싸면 catch 안에서도 분류를 그대로 쓸 수 있다
  // (백엔드가 죽어서 들어온 자리에서 백엔드를 다시 부르지 않는다).
  const listPromise = getWords({ search, category, difficulty, page, shuffle });
  const [categories, difficulties] = await Promise.all([
    getCategories(),
    getDifficulties(),
  ]);

  let data;
  try {
    data = await listPromise;
  } catch (error) {
    // 예상 못 한 에러는 error.tsx 로 올려보낸다.
    if (!(error instanceof ApiError)) throw error;

    // 없는 페이지 번호(?page=999)는 DRF 가 404 를 준다. 이걸 서버 장애처럼
    // 안내하면 사용자가 원인을 오해하므로 "그런 페이지 없음"으로 구분한다.
    if (error.status === 404) notFound();

    // 400 은 대부분 URL 의 조건값이 잘못된 경우다(오타·오래된 북마크).
    // 서버 문제가 아니므로 그렇게 안내하고, 상태 코드는 보여주지 않는다.
    const badRequest = error.status === 400;

    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <LearnHeader
          mode="learn"
          content="words"
          title="단어장"
          description="개발할 때 마주치는 영어 단어를 모았습니다."
        />

        {/* 에러 화면에도 필터를 남긴다. 없으면 잘못된 조건으로 들어온
            사용자가 조건을 바꿀 수단이 없어 막다른 화면이 된다. */}
        <CategoryFilter options={categories} basePath={routes.words} />

        <p className="mt-6 rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          {badRequest
            ? "검색 조건이 올바르지 않습니다. 위에서 분류를 다시 골라보세요."
            : `단어를 불러오지 못했습니다. ${error.message}`}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
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
          그 조건 안에서 새로 섞인 목록이 나온다. */}
      <ChoiceFilter
        label="난이도"
        paramName="difficulty"
        options={difficulties}
        basePath={routes.words}
        selected={difficulty}
        keep={{ search, category }}
      />

      <CategoryFilter
        options={categories}
        basePath={routes.words}
        selected={category}
        search={search}
        difficulty={difficulty}
      />

      <p className="mt-6 text-sm text-slate-500 dark:text-slate-300">
        {search ? `"${search}" 검색 결과 ` : "전체 "}
        {data.count}개
      </p>

      {data.results.length === 0 ? (
        <p className="mt-8 rounded-md border border-slate-200 p-6 text-center text-slate-500 dark:border-slate-800 dark:text-slate-300">
          {/* 분류만 걸어 비었을 때 "등록된 단어가 없다"고 하면 서비스 전체가
              비어 있다는 뜻으로 읽힌다. 조건을 좁힌 결과임을 알려준다. */}
          {search || category || difficulty
            ? "조건에 맞는 단어가 없습니다. 위에서 조건을 바꿔보세요."
            : "아직 등록된 단어가 없습니다."}
        </p>
      ) : (
        <ul className="mt-4 grid gap-3">
          {data.results.map((word) => (
            <li key={word.id}>
              <LearningCard
                href={routes.wordDetail(word.id)}
                title={word.term}
                aside={word.pronunciation || undefined}
                subtitle={word.meaning}
                badge={
                  <DifficultyBadge
                    level={word.difficulty}
                    label={word.difficulty_label}
                  />
                }
                tag={
                  word.category_label ? (
                    // 카드 전체가 이미 링크라 여기는 링크로 만들지 않는다.
                    // 링크 안의 링크는 마크업이 깨지고 키보드 순서도 꼬인다.
                    <CategoryChip label={word.category_label} />
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
        filters={{ search, category, difficulty, shuffle }}
        currentPage={currentPage}
        hasPrevious={Boolean(data.previous)}
        hasNext={Boolean(data.next)}
      />
    </main>
  );
}
