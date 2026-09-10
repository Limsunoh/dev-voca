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
      <DetailBack href={routes.sentences} label="문장" />

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

      {/* 설명이 이 화면의 강조점이다. 단어 상세는 예문이 그 자리를 갖지만
          문장에는 예문이 없다 - 문장 자체가 이미 예문이라 히어로가 그것을
          맡고, 여기서 더 알려주는 것은 설명뿐이다. */}
      {sentence.description && (
        <DetailCard label="설명" delay="[animation-delay:360ms]" tone="dark">
          <p className="whitespace-pre-line text-pretty">
            {sentence.description}
          </p>
        </DetailCard>
      )}

      {/* 문장 낱개 문제로 보낸다. testWords 로 보내면 문장을 보다 단어
          문제가 나와 흐름을 잃는다(routes.ts 의 tabHref 와 같은 판단). */}
      <DetailAction href={routes.testSentences}>
        이 문장으로 문제 풀기
      </DetailAction>
    </DetailShell>
  );
}
