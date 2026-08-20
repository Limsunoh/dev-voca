import { notFound } from "next/navigation";

import {
  DetailBack,
  DetailCard,
  DetailHero,
  DetailMeaning,
  DetailShell,
} from "@/components/DetailLayout";
import { CategoryChip, DifficultyBadge } from "@/components/MetaBadge";
import { getSentence } from "@/lib/api/sentences";
import { routes } from "@/lib/routes";

// Next 16 에서 params 는 Promise 다.
type PageProps = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  const sentence = await getSentence(id);
  if (!sentence) return { title: "문장을 찾을 수 없습니다 | devvoca" };

  // 문장은 길어서 제목에 통째로 넣으면 탭 이름이 잘린다.
  const head =
    sentence.text.length <= 40
      ? sentence.text
      : `${sentence.text.slice(0, 40)}...`;

  return {
    title: `${head} | devvoca`,
    description: sentence.translation,
  };
}

export default async function SentenceDetailPage({ params }: PageProps) {
  const { id } = await params;
  const sentence = await getSentence(id);

  // 검수 안 된 문장도 백엔드가 404 를 주므로 여기로 온다.
  if (!sentence) notFound();

  // 에러 메시지는 코드에 가까워 고정폭이 읽기 좋다. 실무 표현은 사람이
  // 쓴 문장이라 가변폭으로 둔다.
  const isError = sentence.kind === "error";

  return (
    <DetailShell>
      <DetailBack href={routes.sentences} label="문장으로" />

      <DetailHero
        title={sentence.text}
        mono={isError}
        meta={
          <>
            <CategoryChip label={sentence.kind_label} />
            <DifficultyBadge
              level={sentence.difficulty}
              label={sentence.difficulty_label}
            />
            {sentence.category_label && (
              <CategoryChip
                label={sentence.category_label}
                href={`${routes.sentences}?category=${encodeURIComponent(sentence.category)}`}
              />
            )}
          </>
        }
      />

      <DetailMeaning>{sentence.translation}</DetailMeaning>

      {sentence.context && (
        <DetailCard label="어디서 나오나" delay="[animation-delay:280ms]">
          <p className="text-pretty">{sentence.context}</p>
        </DetailCard>
      )}

      {sentence.description && (
        <DetailCard label="설명" delay="[animation-delay:360ms]" raised>
          <p className="whitespace-pre-line text-pretty">
            {sentence.description}
          </p>
        </DetailCard>
      )}
    </DetailShell>
  );
}
