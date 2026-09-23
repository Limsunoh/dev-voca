import { ProgressDots, StatCard } from "@/components/StatCard";
import { fetchDailyStatus, type StudyProgress } from "@/lib/api/daily";
import { fetchDue, type ReviewDue } from "@/lib/api/review";
import { routes } from "@/lib/routes";

/** 카드 두 장이 그릴 값. loadToday 가 채운다. */
export type Today = {
  daily: StudyProgress | null;
  due: ReviewDue | null;
};

/**
 * 로그인했으면 둘을 동시에 받는다. 게스트에게는 아예 안 묻는다 - 둘 다
 * 로그인해야 쓰는 기능이라 못 누르는 카드를 띄우면 눌러보고 로그인으로
 * 튕기는 경험이 된다.
 *
 * 실패해도 화면을 막지 않는다. 카드 하나가 안 뜰 뿐이다. 조용히 삼키지는
 * 않는다 - 로그가 없으면 백엔드가 죽은 것과 이 코드의 버그를 가를 수 없다.
 */
export async function loadToday(token: string | null): Promise<Today> {
  if (!token) return { daily: null, due: null };
  const [daily, due] = await Promise.all([
    fetchDailyStatus(token)
      .then((s) => s.today)
      .catch((error: unknown) => {
        console.error("일일공부 상태를 불러오지 못했습니다.", error);
        return null;
      }),
    fetchDue(token).catch((error: unknown) => {
      console.error("복습 개수를 불러오지 못했습니다.", error);
      return null;
    }),
  ]);
  return { daily, due };
}

/**
 * 오늘 할 일 카드 두 장 - 일일공부와 다시 보기.
 *
 * 홈과 문제풀기 허브가 같은 카드를 쓴다. 두 벌로 그리면 "시작 전은
 * 하이픈", "볼 것이 없으면 비운다" 같은 판단이 한쪽에서만 바뀐다.
 *
 * 불러오기(loadToday)와 그리기를 나눈 이유: 홈은 이 둘을 오늘의 단어와
 * **동시에** 받는다. 카드가 스스로 불러오면 홈이 단어를 다 받은 뒤에야
 * 요청이 떠서 왕복이 하나 늘어난다.
 */
export function TodayCards({ daily, due }: Today) {
  return (
    <div className="flex gap-2.5">
      {/* 세 상태를 구분한다 - 안 시작 / 푸는 중 / 오늘 몫 완료.
          done 을 안 읽으면 다 끝낸 사람의 카드가 10/10 인 채로
          여전히 "할 일" 처럼 보인다.

          시작 전에는 0 이 아니라 하이픈이다. MyStandings 가 같은 자리에서
          같은 것을 쓴다 - 0 은 "0점을 냈다" 로 읽혀서 아직 안 한 것과
          구분되지 않는다. */}
      <StatCard
        href={routes.testDaily}
        label="일일공부"
        value={daily ? daily.answered : "-"}
        unit={daily ? `/${daily.total}` : undefined}
        footer={
          daily?.done ? (
            <StatNote>오늘 몫 완료</StatNote>
          ) : daily ? (
            <ProgressDots total={daily.total} done={daily.answered} />
          ) : (
            <StatNote>아직 시작 전</StatNote>
          )
        }
      />

      {/* 볼 것이 없으면 이 자리를 비운다. 0 을 띄우면 "할 일이 있는
          카드" 모양으로 보여서, 눌러 들어갔다 빈 화면을 만난다. */}
      {due && due.due > 0 && (
        <StatCard
          href={routes.testReview}
          label="다시 보기"
          value={due.due}
          unit="개"
          tone="coral"
          footer={<StatNote>틀린 것부터</StatNote>}
        />
      )}
    </div>
  );
}

/** 통계 카드 아래 한 줄. 진행 점이 없는 자리를 이 문구가 대신한다. */
function StatNote({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="text-[length:var(--text-11)]"
      style={{
        fontWeight: "var(--weight-bold)",
        color: "var(--text-dim)",
      }}
    >
      {children}
    </span>
  );
}
