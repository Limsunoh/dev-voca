import { notFound } from "next/navigation";

import {
  DetailBack,
  DetailCard,
  DetailHero,
  DetailMeaning,
  DetailShell,
} from "@/components/DetailLayout";
import { CategoryChip, DifficultyBadge } from "@/components/MetaBadge";
import { getWord } from "@/lib/api/vocab";
import { routes } from "@/lib/routes";

// Next 16 에서 params 는 Promise 다.
type PageProps = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  const word = await getWord(id);
  if (!word) return { title: "단어를 찾을 수 없습니다 | devvoca" };

  return {
    title: `${word.term} | devvoca`,
    description: word.meaning,
  };
}

export default async function WordDetailPage({ params }: PageProps) {
  const { id } = await params;
  const word = await getWord(id);

  // 검수 안 된 단어도 백엔드가 404 를 주므로 여기로 온다.
  if (!word) notFound();

  return (
    <DetailShell>
      <DetailBack href={routes.words} label="단어장으로" />

      <DetailHero
        title={word.term}
        aside={word.pronunciation || undefined}
        meta={
          <>
            <DifficultyBadge
              level={word.difficulty}
              label={word.difficulty_label}
            />
            {word.category_label && (
              <CategoryChip
                label={word.category_label}
                href={`${routes.words}?category=${encodeURIComponent(word.category)}`}
              />
            )}
          </>
        }
      />

      <DetailMeaning>{word.meaning}</DetailMeaning>

      {word.description && (
        <DetailCard label="설명" delay="[animation-delay:280ms]">
          <p className="whitespace-pre-line text-pretty">{word.description}</p>
        </DetailCard>
      )}

      {word.example && (
        <DetailCard label="예문" delay="[animation-delay:360ms]" raised>
          {/* 예문은 코드에 가까워 고정폭으로 둔다. 번역은 사람이 쓴
              문장이라 가변폭이 읽기 좋다. */}
          <p className="font-mono text-[1rem] leading-relaxed text-slate-100">
            {word.example}
          </p>
          {word.example_translation && (
            <p className="mt-3 border-t border-white/10 pt-3 text-slate-400">
              {word.example_translation}
            </p>
          )}
        </DetailCard>
      )}
    </DetailShell>
  );
}
