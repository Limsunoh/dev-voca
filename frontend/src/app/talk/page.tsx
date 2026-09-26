import type { Metadata } from "next";

import { TalkBoard } from "@/components/TalkBoard";
import { TalkKindTabs } from "@/components/TalkKindTabs";
import { TalkLevelTabs } from "@/components/TalkLevelTabs";
import type { TalkKind, TalkLevel } from "@/lib/routes";

export const metadata: Metadata = {
  title: "일상영어 · devvoca",
  description: "소리내어 읽고 맞게 읽었는지 확인합니다.",
};

/**
 * 소리내어 읽기.
 *
 * 판이 없어서 탭바를 숨기지 않는다(immersiveRoutes 에 안 넣는다). 점수가
 * 안 남으니 나가다 잃을 것이 없고, 잃을 것이 없으면 출구를 하나로 좁힐
 * 이유도 없다.
 *
 * 갈래를 쿼리로 가른다. 전역 콘텐츠 축을 안 쓰는 이유는 TalkKindTabs 에
 * 적어뒀다.
 */

type PageProps = {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function TalkPage({ searchParams }: PageProps) {
  const params = await searchParams;
  // 아는 값이 아니면 기본으로 떨어뜨린다. 주소를 손으로 고쳐도 빈 화면이
  // 되지 않는다.
  const kind: TalkKind = first(params.kind) === "dev" ? "dev" : "daily";
  // 아는 난이도가 아니면 "전체" 로 떨어진다. 서버도 같은 판단을 한 번 더
  // 하지만, 여기서 정리해야 탭의 켜진 표시가 주소와 어긋나지 않는다.
  const level: TalkLevel = ((): TalkLevel => {
    const raw = Number(first(params.level));
    return raw === 1 || raw === 2 || raw === 3 ? raw : 0;
  })();

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-4 pt-4 pb-10">
      {/* 화면에는 안 보이지만 남긴다. 제목을 지우면 스크린리더의 헤딩
          목록에 레벨 1 이 없어 이 화면이 무엇인지 알 방법이 없다. 탭은
          이동 수단이지 제목이 아니다(/test/words 와 같은 판단). */}
      <h1 className="sr-only">일상영어</h1>

      {/* 두 축을 세로로 쌓는다. 폰에서 한 줄에 넣으면 "어려움" 이 잘린다.
          갈래가 위인 이유: 무엇을 읽을지가 먼저이고 난이도는 그 안에서
          좁히는 것이다. */}
      <div className="mb-4 grid justify-items-start gap-2">
        <TalkKindTabs current={kind} level={level} />
        <TalkLevelTabs kind={kind} current={level} />
      </div>

      {/* 갈래가 바뀌면 판을 처음부터 다시 시작한다. key 를 안 주면 리액트가
          같은 컴포넌트로 보고 상태를 유지해서, 개발 용어를 읽던 결과가
          일상 표현 화면에 남는다. */}
      {/* 난이도도 key 에 넣는다. 갈래와 같은 이유다 - 안 넣으면 난이도를
          바꿔도 읽던 것이 그대로 남고, 이미 낸 것을 빼는 목록(exclude)이
          옛 풀 기준으로 쌓인 채 따라온다. */}
      <TalkBoard key={`${kind}-${level}`} kind={kind} level={level} />
    </main>
  );
}
