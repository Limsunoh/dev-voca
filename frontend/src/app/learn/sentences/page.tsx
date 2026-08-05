import { notFound } from "next/navigation";
import { Suspense } from "react";

import { CategoryFilter } from "@/components/CategoryFilter";
import { ChoiceFilter } from "@/components/ChoiceFilter";
import { LearnHeader } from "@/components/LearnHeader";
import { LearningCard } from "@/components/LearningCard";
import { Pagination } from "@/components/Pagination";
import { SearchInput } from "@/components/SearchInput";
import { ApiError } from "@/lib/api/client";
import {
  getSentenceCategories,
  getSentenceKinds,
  getSentences,
} from "@/lib/api/sentences";
import { routes } from "@/lib/routes";

export const metadata = {
  title: "문장 | devvoca",
  description: "리뷰 코멘트와 에러 메시지에서 실제로 만나는 영어 문장.",
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

export default async function SentencesPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const search = first(params.search);
  const category = first(params.category);
  const kind = first(params.kind);
  const difficulty = first(params.difficulty);

  // page 는 여기서 한 번만 정규화한다. 검증 없이 넘기면 "abc"·"2.7"·"-1" 이
  // 그대로 백엔드로 가 404 가 되고, 화면에는 "2.7 페이지" 같은 표시와
  // ?page=3.7 링크까지 생긴다.
  const currentPage = toPageNumber(first(params.page));
  const page = currentPage > 1 ? String(currentPage) : undefined;

  // 세 요청을 동시에 띄운다. 순서대로 기다리면 세 번의 왕복이 그대로
  // 대기 시간이 된다.
  //
  // 선택지 목록은 실패해도 빈 배열이라 절대 throw 하지 않으므로 그냥 await
  // 한다. 목록만 try 로 감싸면 catch 안에서도 선택지를 그대로 쓸 수 있다
  // (백엔드가 죽어서 들어온 자리에서 백엔드를 다시 부르지 않는다).
  const listPromise = getSentences({ search, category, kind, difficulty, page });
  const categories = await getSentenceCategories();
  const kinds = await getSentenceKinds();

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
          content="sentences"
          title="문장"
          description="리뷰 코멘트와 에러 메시지에서 실제로 만나는 문장을 모았습니다."
        />

        {/* 에러 화면에도 필터를 남긴다. 없으면 잘못된 조건으로 들어온
            사용자가 조건을 바꿀 수단이 없어 막다른 화면이 된다. */}
        <CategoryFilter options={categories} basePath={routes.sentences} />

        <p className="mt-6 rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          {badRequest
            ? "검색 조건이 올바르지 않습니다. 위에서 분류를 다시 골라보세요."
            : `문장을 불러오지 못했습니다. ${error.message}`}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <LearnHeader
        mode="learn"
        content="sentences"
        title="문장"
        description="리뷰 코멘트와 에러 메시지에서 실제로 만나는 문장을 모았습니다."
      />

      <div className="mt-6">
        {/* useSearchParams 를 쓰는 컴포넌트는 Suspense 로 감싼다.
            없으면 프로덕션 빌드가 실패한다. */}
        <Suspense fallback={<div className="h-[42px]" />}>
          {/* key 가 바뀌면 입력창이 새로 만들어진다 - 뒤로가기로 검색어가
              달라졌을 때 입력창이 URL 을 따라가게 하는 방법. */}
          <SearchInput
            key={search ?? ""}
            basePath={routes.sentences}
            label="문장 검색"
            placeholder="문장, 해석, 에러 원문으로 검색"
          />
        </Suspense>
      </div>

      <ChoiceFilter
        label="종류"
        paramName="kind"
        options={kinds}
        basePath={routes.sentences}
        selected={kind}
        keep={{ search, category, difficulty }}
      />

      <CategoryFilter
        options={categories}
        basePath={routes.sentences}
        selected={category}
        search={search}
        difficulty={difficulty}
        extra={{ kind }}
      />

      <p className="mt-6 text-sm text-slate-500 dark:text-slate-400">
        {search ? `"${search}" 검색 결과 ` : "전체 "}
        {data.count}개
      </p>

      {data.results.length === 0 ? (
        <p className="mt-8 rounded-md border border-slate-200 p-6 text-center text-slate-500 dark:border-slate-800 dark:text-slate-400">
          {/* 조건을 걸어 비었을 때 "등록된 문장이 없다"고 하면 서비스 전체가
              비어 있다는 뜻으로 읽힌다. 조건을 좁힌 결과임을 알려준다. */}
          {search || category || kind
            ? "조건에 맞는 문장이 없습니다. 검색어나 분류를 바꿔보세요."
            : "아직 등록된 문장이 없습니다."}
        </p>
      ) : (
        <ul className="mt-4 grid gap-3">
          {data.results.map((sentence) => (
            <li key={sentence.id}>
              <LearningCard
                href={routes.sentenceDetail(sentence.id)}
                title={sentence.text}
                subtitle={sentence.translation}
                badge={sentence.kind_label}
                tag={sentence.context || sentence.category_label || undefined}
                // 에러 메시지는 코드에 가까워 고정폭이 읽기 좋지만,
                // 사람이 쓴 문장은 고정폭으로 길어지면 오히려 읽기 어렵다.
                monoTitle={sentence.kind === "error"}
              />
            </li>
          ))}
        </ul>
      )}

      <Pagination
        basePath={routes.sentences}
        filters={{ search, category, kind, difficulty }}
        currentPage={currentPage}
        hasPrevious={Boolean(data.previous)}
        hasNext={Boolean(data.next)}
      />
    </main>
  );
}
