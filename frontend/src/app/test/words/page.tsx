import { CategoryPicker } from "@/components/CategoryPicker";
import { ContentTabs } from "@/components/ContentTabs";
import { QuizBoard } from "@/components/QuizBoard";
import { getCategories } from "@/lib/api/vocab";
import { contentPath } from "@/lib/routes";

export const metadata = {
  title: "단어 문제풀기 | devvoca",
  description: "외운 단어를 문제로 확인합니다.",
};

type PageProps = {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function TestWordsPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const category = first(params.category);

  // 분류 목록은 실패해도 빈 배열이라 화면을 막지 않는다.
  const categories = await getCategories();

  return (
    <main className="mx-auto max-w-3xl px-4 pt-4 pb-10">
      {/* 머리말을 한 줄로 줄인다. 전에는 탭·제목·설명·칩 여덟 개가 화면
          위 절반을 먹어서, 정작 풀어야 할 문제가 반쯤 잘리고 보기는 둘만
          보였다. 여기는 읽는 화면이 아니라 푸는 화면이다.

          제목("단어 문제풀기")과 설명을 뺀 이유: 탭이 이미 "문제풀기 - 단어"
          를 말하고 있어서 같은 말이 세 번 나온다. */}
      {/* 화면에는 안 보이지만 남겨둔다. 머리말을 지우면서 h1 이 통째로
          사라졌는데, 그러면 스크린리더의 헤딩 목록에 레벨 1 이 없어
          이 화면이 무엇인지 알 방법이 없다. 탭은 이동 수단이지 제목이
          아니다. */}
      <h1 className="sr-only">단어 문제풀기</h1>

      <ContentTabs mode="test" current="words" />

      <div className="mt-4 flex items-center justify-between gap-3">
        {/* key 로 분류를 넘겨 주소가 바뀌면 새로 만든다. 뒤로가기로 돌아올
            때 메뉴가 열린 채 남아 보기 버튼을 덮는 것을 막는다. */}
        <CategoryPicker
          key={category ?? "all"}
          options={categories}
          basePath={contentPath("test", "words")}
          selected={category}
        />
      </div>

      {/* key 로 분류를 넘긴다. 분류가 바뀌면 판을 새로 만들어야 점수와
          방금 푼 목록이 함께 초기화된다. */}
      <QuizBoard key={category ?? "all"} category={category} />
    </main>
  );
}
