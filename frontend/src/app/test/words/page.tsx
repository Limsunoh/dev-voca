import type { Metadata } from "next";

import { CategoryPicker } from "@/components/CategoryPicker";
import { ContentTabs } from "@/components/ContentTabs";
import { ExitGuard } from "@/components/ExitGuard";
import { LeaveLink } from "@/components/LeaveLink";
import { QuizBoard } from "@/components/QuizBoard";
import { getCategories } from "@/lib/api/vocab";
import { contentPath, routes } from "@/lib/routes";

export const metadata: Metadata = {
  title: "단어 문제풀기 · devvoca",
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
  // 상세의 "문제 풀기" 가 붙여 온다. 첫 문제만 이것으로 낸다.
  const item = first(params.item);

  // 분류 목록은 실패해도 빈 배열이라 화면을 막지 않는다.
  const categories = await getCategories();

  return (
    <main className="mx-auto w-full max-w-3xl px-4 pt-4 pb-10">
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

      {/* 이 화면에는 탭바가 없다(TabBar 의 return null 참고). 나가는 길이
          여기뿐이라 빠지면 막다른 화면이 된다.

          나가면 홈이 아니라 문제풀기 허브(/test)로 간다. 이 화면에 들어오는
          길은 허브와 상세의 "이 단어로 문제 풀기" 뿐이고 홈에서 곧장 오는
          길은 없다. 홈으로 보내면 허브로 돌아가는 데 탭을 한 번 더 누른다.

          푼 것이 있을 때만 묻는다. 낱개 연습은 점수가 서버에 안 남아서
          판을 떠나면 그대로 사라진다. 한 문제도 안 풀었으면 잃을 것이
          없으니 묻지 않는다 - 매번 물으면 성가시다. 옆의 "한 판 풀기" 도
          이 판을 끝내는 출구라 같은 규칙을 쓴다. */}
      <div className="mb-3 flex items-center justify-between gap-3">
        <ExitGuard
          to={routes.test}
          label="문제풀기"
          ariaLabel="문제풀기로 나가기"
          confirmWhenSolved
        />
        <LeaveLink
          href={routes.testRound}
          confirmLabel="한 판 풀기"
          className="flex items-center px-2.5 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={{
            minHeight: "var(--hit-floor)",
            borderRadius: "var(--radius-md)",
            color: "var(--text-muted)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          한 판 풀기
        </LeaveLink>
      </div>

      <ContentTabs mode="test" current="words" warnOnLeave />

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
          방금 푼 목록이 함께 초기화된다.

          항목은 key 에 넣지 않는다. 넣으면 ?item= 으로 들어온 판에서 분류
          "전체" 를 누를 때 판이 새로 만들어져 푼 것이 확인 없이 사라진다 -
          이미 고른 칩이라 확인 창을 건너뛰기 때문이다. 항목은 첫 문제에만
          쓰이므로 판이 알아서 한 번 쓰고 버린다. */}
      <QuizBoard key={category ?? "all"} category={category} item={item} />
    </main>
  );
}
