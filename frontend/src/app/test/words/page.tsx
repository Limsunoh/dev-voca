import { CategoryFilter } from "@/components/CategoryFilter";
import { LearnHeader } from "@/components/LearnHeader";
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
    <main className="mx-auto max-w-3xl px-4 py-10">
      <LearnHeader
        mode="test"
        content="words"
        title="단어 문제풀기"
        description="뜻 고르기, 단어 고르기, 설명 보고 맞히기가 번갈아 나옵니다."
      />

      {/* toggle 을 끈다. 목록과 달리 여기는 진행 중인 판이라, 켜진 칩을
          잘못 한 번 누르면 아래 key 가 바뀌면서 점수와 방금 푼 목록이
          사라진다. 초기화는 "전체" 를 눌러 의도적으로 하게 둔다. */}
      <CategoryFilter
        options={categories}
        basePath={contentPath("test", "words")}
        selected={category}
        toggle={false}
      />

      {/* key 로 분류를 넘긴다. 분류가 바뀌면 판을 새로 만들어야 점수와
          방금 푼 목록이 함께 초기화된다. */}
      <QuizBoard key={category ?? "all"} category={category} />
    </main>
  );
}
