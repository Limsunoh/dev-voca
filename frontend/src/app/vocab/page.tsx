import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { LearningCard } from "@/components/LearningCard";
import { SearchInput } from "@/components/SearchInput";
import { ApiError, getWords } from "@/lib/api/vocab";

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

  let data;
  try {
    data = await getWords({ search, category, difficulty, page });
  } catch (error) {
    // 예상 못 한 에러는 error.tsx 로 올려보낸다.
    if (!(error instanceof ApiError)) throw error;

    // 없는 페이지 번호(?page=999)는 DRF 가 404 를 준다. 이걸 서버 장애처럼
    // 안내하면 사용자가 원인을 오해하므로 "그런 페이지 없음"으로 구분한다.
    if (error.status === 404) notFound();

    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Header />
        <p className="mt-8 rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          단어를 불러오지 못했습니다. {error.message}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <Header />

      <div className="mt-6">
        {/* useSearchParams 를 쓰는 컴포넌트는 Suspense 로 감싼다.
            없으면 프로덕션 빌드가 실패한다. */}
        <Suspense fallback={<div className="h-[42px]" />}>
          {/* key 가 바뀌면 입력창이 새로 만들어진다 - 뒤로가기로 검색어가
              달라졌을 때 입력창이 URL 을 따라가게 하는 방법. */}
          <SearchInput key={search ?? ""} basePath="/vocab" />
        </Suspense>
      </div>

      <p className="mt-6 text-sm text-slate-500 dark:text-slate-400">
        {search ? `"${search}" 검색 결과 ` : "전체 "}
        {data.count}개
      </p>

      {data.results.length === 0 ? (
        <p className="mt-8 rounded-md border border-slate-200 p-6 text-center text-slate-500 dark:border-slate-800 dark:text-slate-400">
          {search
            ? "검색 결과가 없습니다. 다른 단어로 찾아보세요."
            : "아직 등록된 단어가 없습니다."}
        </p>
      ) : (
        <ul className="mt-4 grid gap-3">
          {data.results.map((word) => (
            <li key={word.id}>
              <LearningCard
                href={`/vocab/${word.id}`}
                title={word.term}
                subtitle={word.meaning}
                badge={word.difficulty_label}
                tag={word.category || undefined}
              />
            </li>
          ))}
        </ul>
      )}

      <Pagination
        filters={{ search, category, difficulty }}
        currentPage={currentPage}
        hasPrevious={Boolean(data.previous)}
        hasNext={Boolean(data.next)}
      />
    </main>
  );
}

/**
 * 이전/다음 링크.
 *
 * 백엔드가 준 next/previous 절대 URL 을 그대로 쓰지 않는다 - 그러면 API 주소가
 * 화면에 노출된다. 우리가 아는 필터만 유지한 채 page 만 바꿔 붙인다.
 * (searchParams 를 통째로 넘기면 URL 에 낀 임의의 키까지 링크마다 따라다닌다.)
 */
function Pagination({
  filters,
  currentPage,
  hasPrevious,
  hasNext,
}: {
  filters: Record<string, string | undefined>;
  currentPage: number;
  hasPrevious: boolean;
  hasNext: boolean;
}) {
  if (!hasPrevious && !hasNext) return null;

  function hrefFor(page: number): string {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value) query.set(key, value);
    }
    if (page > 1) query.set("page", String(page));

    const qs = query.toString();
    return qs ? `/vocab?${qs}` : "/vocab";
  }

  const linkClass =
    "rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:border-slate-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-500";

  return (
    <nav
      aria-label="페이지 이동"
      className="mt-8 flex items-center justify-between"
    >
      {hasPrevious ? (
        <Link href={hrefFor(currentPage - 1)} className={linkClass}>
          이전
        </Link>
      ) : (
        <span />
      )}

      <span className="text-sm text-slate-500 dark:text-slate-400">
        {currentPage} 페이지
      </span>

      {hasNext ? (
        <Link href={hrefFor(currentPage + 1)} className={linkClass}>
          다음
        </Link>
      ) : (
        <span />
      )}
    </nav>
  );
}

function Header() {
  return (
    <header>
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
        단어장
      </h1>
      <p className="mt-1 text-slate-600 dark:text-slate-400">
        개발할 때 마주치는 영어 단어를 모았습니다.
      </p>
    </header>
  );
}
