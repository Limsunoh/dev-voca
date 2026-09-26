import { notFound } from "next/navigation";

import {
  DetailAction,
  DetailBack,
  DetailCard,
  DetailHero,
  DetailShell,
} from "@/components/DetailLayout";
import { CategoryChip, DifficultyBadge } from "@/components/MetaBadge";
import { getSentence } from "@/lib/api/sentences";
import { routes, safeListUrl } from "@/lib/routes";

// Next 16 에서 params 는 Promise 다.
type PageProps = {
  params: Promise<{ id: string }>;
  /**
   * 목록이 실어 보낸 자기 주소. 되돌아가기 버튼이 쓴다. 주소창으로 아무
   * 값이나 올 수 있어 `safeListUrl` 로 걸러 쓴다.
   * 자세한 것은 learn/words/[id]/page.tsx 참고.
   */
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  const sentence = await getSentence(id);
  if (!sentence) return { title: "문장을 찾을 수 없습니다 · devvoca" };

  // 문장은 길어서 제목에 통째로 넣으면 탭 이름이 잘린다.
  const head =
    sentence.text.length <= 40
      ? sentence.text
      : `${sentence.text.slice(0, 40)}...`;

  return {
    title: `${head} · devvoca`,
    description: sentence.translation,
  };
}

export default async function SentenceDetailPage({
  params,
  searchParams,
}: PageProps) {
  const { id } = await params;
  const sentence = await getSentence(id);

  // 검수 안 된 문장도 백엔드가 404 를 주므로 여기로 온다.
  if (!sentence) notFound();

  // 에러 메시지는 코드에 가까워 고정폭이 읽기 좋다. 실무 표현은 사람이
  // 쓴 문장이라 가변폭으로 둔다.
  const isError = sentence.kind === "error";

  const backToList = safeListUrl((await searchParams).from, routes.sentences);

  return (
    <DetailShell>
      <DetailBack href={backToList} label="문장" />

      <DetailHero
        title={sentence.text}
        reading={sentence.reading || undefined}
        meaning={sentence.translation}
        mono={isError}
        meta={
          <>
            <CategoryChip label={sentence.kind_label} />
            {sentence.category_label && (
              <CategoryChip
                label={sentence.category_label}
                href={`${routes.sentences}?category=${encodeURIComponent(sentence.category)}`}
              />
            )}
            <DifficultyBadge
              level={sentence.difficulty}
              label={sentence.difficulty_label}
            />
          </>
        }
      />

      {sentence.context && (
        <DetailCard label="어디서 나오나" delay="[animation-delay:280ms]">
          <p className="text-pretty">{sentence.context}</p>
        </DetailCard>
      )}

      {/* 설명은 흰 카드다. 어두운 카드는 "예문처럼 실제로 보러 온 것" 에만
          준다(DetailCard 의 tone 주석) - 단어 상세에서는 예문이 그 자리다.
          문장 화면에서 보러 온 것은 문장 자체이고 그건 위 히어로가 맡는다.
          설명을 어둡게 두면 두 상세에서 어두운 카드의 뜻이 갈린다. */}
      {sentence.description && (
        <DetailCard label="설명" delay="[animation-delay:360ms]">
          <p className="whitespace-pre-line text-pretty">
            {sentence.description}
          </p>
        </DetailCard>
      )}

      {/* 문장 문제로 보내고, 첫 문제를 이 문장으로 낸다. testWords 로
          보내면 문장을 보다 단어 문제가 나와 흐름을 잃는다. */}
      <DetailAction href={`${routes.testSentences}?item=${sentence.id}`}>
        이 문장으로 문제 풀기
      </DetailAction>
    </DetailShell>
  );
}
