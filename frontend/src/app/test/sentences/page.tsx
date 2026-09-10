import type { Metadata } from "next";
import Link from "next/link";

import { CategoryPicker } from "@/components/CategoryPicker";
import { ContentTabs } from "@/components/ContentTabs";
import { ExitGuard } from "@/components/ExitGuard";
import { QuizBoard } from "@/components/QuizBoard";
import { getSentenceCategories } from "@/lib/api/sentences";
import { contentPath, routes } from "@/lib/routes";

export const metadata: Metadata = {
  title: "문장 문제풀기 | devvoca",
  description: "에러 메시지와 실무 표현을 문제로 확인합니다.",
};

type PageProps = {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/**
 * 문장 문제풀기.
 *
 * 단어 쪽(test/words)과 같은 구조다. 다른 것은 QuizBoard 에 넘기는
 * content 하나뿐이고, 그걸로 백엔드의 문장 quiz/grade 를 부른다.
 *
 * 문제 유형은 둘이다 - 빈칸 채우기(문장에서 용어를 가림)와 상황 고르기
 * (문장을 보여주고 언제 나오는 말인지 고름). 어느 것을 낼지는 서버가
 * 정한다. 문장마다 낼 수 있는 유형이 달라서다 - 단어가 안 들어 있는
 * 문장은 빈칸을 못 만들고, 상황이 비어 있으면 상황 고르기를 못 낸다.
 */
export default async function TestSentencesPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const category = first(params.category);

  // 분류 목록은 실패해도 빈 배열이라 화면을 막지 않는다.
  const categories = await getSentenceCategories();

  return (
    <main className="mx-auto max-w-3xl px-4 pt-4 pb-10">
      {/* 화면에는 안 보이지만 남겨둔다. 이유는 test/words 쪽에 적어뒀다. */}
      <h1 className="sr-only">문장 문제풀기</h1>

      {/* 이 화면에는 탭바가 없다(TabBar 의 return null 참고). 나가는 길이
          여기뿐이라 빠지면 막다른 화면이 된다. */}
      <div className="mb-3 flex items-center justify-between gap-3">
        <ExitGuard to={routes.home} label="홈" />
        <Link
          href={routes.testRound}
          className="flex items-center px-2.5 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={{
            minHeight: "var(--hit-floor)",
            borderRadius: "var(--radius-md)",
            color: "var(--text-muted)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          한 판 풀기
        </Link>
      </div>

      <ContentTabs mode="test" current="sentences" />

      <div className="mt-4 flex items-center justify-between gap-3">
        {/* key 로 분류를 넘겨 주소가 바뀌면 새로 만든다. 뒤로가기로 돌아올
            때 메뉴가 열린 채 남아 보기 버튼을 덮는 것을 막는다. */}
        <CategoryPicker
          key={category ?? "all"}
          options={categories}
          basePath={contentPath("test", "sentences")}
          selected={category}
        />
      </div>

      {/* key 로 분류를 넘긴다. 분류가 바뀌면 판을 새로 만들어야 점수와
          방금 푼 목록이 함께 초기화된다. */}
      <QuizBoard
        key={category ?? "all"}
        category={category}
        content="sentences"
      />
    </main>
  );
}
