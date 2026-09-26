import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Pagination } from "@/components/Pagination";
import { getMistakes } from "@/lib/api/history";
import { ApiError } from "@/lib/api/client";
import { routes } from "@/lib/routes";
import { getToken } from "@/lib/session";

export const metadata: Metadata = {
  title: "오답 노트 · devvoca",
  description: "마지막으로 풀었을 때 틀린 단어와 문장을 모아 봅니다.",
};

/**
 * 오답 노트.
 *
 * **여기서 풀지 않는다.** 푸는 자리는 복습(`/test/review`)이고 여기는
 * 모아 보는 자리다. 둘 다 풀 수 있게 하면 같은 일을 하는 화면이 둘이 되고,
 * 어느 쪽으로 푼 것이 기록에 남는지도 헷갈린다.
 *
 * 항목을 누르면 그 단어·문장의 상세로 간다. "이게 무슨 뜻이었지" 를
 * 확인하는 자리라 푸는 것과 성격이 안 겹친다.
 */

type PageProps = {
  // Next 16 에서 searchParams 는 Promise 다. 동기 접근은 런타임 에러.
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/**
 * 정수가 아니거나 1 미만이면 1 페이지로 본다(단어 목록과 같은 규칙).
 *
 * 다듬지 않고 넘기면 DRF 가 "last" 를 마지막 페이지로 받아 주는데 화면은
 * 그걸 1 로 셈해서, 3페이지 내용을 "1 페이지" 라 적고 "이전" 이 엉뚱한
 * 곳을 가리켰다. 다듬은 값을 표시에도 요청에도 똑같이 쓴다.
 */
function toPageNumber(value: string | undefined): number {
  const n = Number(value);
  return Number.isInteger(n) && n > 1 ? n : 1;
}

export default async function MistakesPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const currentPage = toPageNumber(first(params.page));
  // 1 페이지는 번호를 안 붙인다. 아래 404 처리가 "번호가 있을 때만" 첫
  // 페이지로 보내므로, 이 값이 있으면 곧 2 이상이라는 뜻이다.
  const page = currentPage > 1 ? String(currentPage) : undefined;

  // 틀린 것은 계정에 쌓이는 기록이라 로그인해야 본다. 돌아올 곳을 넘겨
  // 로그인 뒤 이 화면으로 오게 한다.
  const token = await getToken();
  if (!token) redirect(`${routes.login}?next=${routes.mistakes}`);

  // redirect() 는 예외를 던져서 동작한다. try 안에서 부르면 나중에 누가
  // catch 를 넓혔을 때 그 예외를 "목록 실패" 로 삼킨다. 그래서 실패 종류만
  // 적어 두고 redirect 는 try 밖에서 한다.
  let data;
  let failure: "login" | "no-page" | "error" | null = null;
  try {
    data = await getMistakes(token, page);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      failure = "login";
    } else if (error instanceof ApiError && error.status === 404 && page) {
      // 없는 페이지. 주소를 손으로 고쳤거나, 다시 맞혀 줄이 빠지면서 마지막
      // 페이지가 사라진 뒤 새로고침한 경우다. 실패가 아니라 첫 페이지로
      // 보낸다 - "불러오지 못했습니다" 를 띄우면 서버 장애로 읽힌다.
      //
      // **페이지 번호가 있을 때만이다.** 번호 없이 404 가 오면 목록이 비어서가
      // 아니라(빈 목록도 첫 페이지는 200 이다) 주소 자체가 없는 것이다 -
      // 프론트가 백엔드보다 먼저 배포된 경우 같은. 그때 첫 페이지로 보내면
      // 같은 주소로 끝없이 돌아간다.
      failure = "no-page";
    } else {
      failure = "error";
    }
  }

  if (failure === "login") redirect(`${routes.login}?next=${routes.mistakes}`);
  if (failure === "no-page") redirect(routes.mistakes);
  if (failure === "error" || !data) {
    // 여기서 throw 하면 오류 화면이 뜨는데, 목록 하나 못 불러온 것치고는
    // 과하다.
    //
    // role="alert" 는 쓰지 않는다. 첫 렌더부터 있는 요소라 라이브 리전으로
    // 알릴 "새로 나타난 것" 이 아니다(홈의 DailyWordUnavailable 과 같은
    // 이유). 문구를 보이는 제목에 넣어 리더가 자연히 읽게 한다.
    return (
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-8">
        <h1
          style={{
            fontSize: "var(--text-xl)",
            fontWeight: "var(--weight-black)",
            letterSpacing: "var(--tracking-tight)",
            color: "var(--foreground)",
          }}
        >
          오답 노트를 불러오지 못했습니다.
        </h1>
        <p className="mt-2" style={{ color: "var(--text-muted)" }}>
          잠시 뒤에 다시 열어보세요.
        </p>
      </main>
    );
  }


  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-8">
      <h1
        className="text-[length:var(--text-2xl)] tracking-[var(--tracking-tight)]"
        style={{
          color: "var(--foreground)",
          fontWeight: "var(--weight-black)",
        }}
      >
        오답 노트
      </h1>

      {/* **복습과 개수가 다르다는 것을 여기서 알린다.** 복습은 틀린 것에
          더해 오래된 것까지 내므로 늘 여기보다 많거나 같다. 안 적으면
          오답 노트에 8개인데 복습에 12개가 떠서 사용자가 버그로 읽는다.

          **"한 번 맞히면" 이 사실이다.** 복습의 졸업 조건(연속 두 번)과
          다르다 - 복습이든 문제풀기든 일일공부든 마지막 답이 맞으면 그
          자리에서 빠진다. 한때 "복습에서 연속으로" 라고 적었는데, 그 말을
          믿고 돌아오면 항목이 이미 없어 버그로 읽힌다. */}
      <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>
        마지막으로 풀었을 때 틀린 것만 모았습니다. 어디서든 다시 한 번
        맞히면 목록에서 빠집니다. 복습에는 한동안 안 본 것도 함께 나와서
        개수가 더 많을 수 있습니다.
      </p>

      {data.count === 0 ? (
        <div
          className="mt-6 grid gap-3 p-6 text-center"
          style={{
            background: "var(--paper)",
            borderRadius: "var(--radius-2xl)",
            boxShadow: "var(--lift-card)",
          }}
        >
          <p style={{ color: "var(--text-body)" }}>아직 틀린 것이 없습니다.</p>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            문제를 풀다 틀리면 여기에 모입니다.
          </p>
        </div>
      ) : (
        <>
          <p
            className="mt-6 font-mono text-sm tabular-nums"
            style={{ color: "var(--text-muted)" }}
          >
            {data.count}개
          </p>

          <ul className="mt-3 grid gap-2.5">
            {data.results.map((row) => (
              <li key={row.id}>
                {/* 줄 전체가 링크다. 눌러야 할 곳을 따로 찾지 않아도 되고,
                    터치 대상도 넓어진다. */}
                <Link
                  href={
                    row.target_type === "word"
                      ? routes.wordDetail(row.target_id)
                      : routes.sentenceDetail(row.target_id)
                  }
                  className="dv-card dv-press-card block p-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                  style={
                    {
                      borderRadius: "var(--radius-2xl)",
                      "--lift": "var(--lift-card)",
                    } as React.CSSProperties
                  }
                >
                  {/* 단어는 고정폭, 문장은 가변폭. 이 저장소가 단어에만
                      고정폭을 쓰는 규칙을 따른다(LearningCard 의 monoTitle). */}
                  <p
                    className={
                      row.target_type === "word"
                        ? "font-mono break-words"
                        : "break-words"
                    }
                    lang="en-US"
                    style={{
                      color: "var(--foreground)",
                      fontWeight: "var(--weight-bold)",
                    }}
                  >
                    {row.text}
                  </p>
                  <p
                    className="mt-1 text-sm break-words"
                    style={{ color: "var(--text-body)" }}
                  >
                    {row.meaning}
                  </p>

                  {/* 틀린 날짜는 안 보여준다. 서버가 그 값을 못 준다 -
                      이유는 views_history 주석에 있다(쓰는 경로 셋 중
                      둘이 시각을 안 남긴다). 틀린 날짜를 보여주느니 안
                      보여주는 것이 낫다. */}
                </Link>
              </li>
            ))}
          </ul>

          <Pagination
            basePath={routes.mistakes}
            filters={{}}
            currentPage={currentPage}
            hasPrevious={Boolean(data.previous)}
            hasNext={Boolean(data.next)}
          />

          {/* 이 화면의 유일한 코랄. 여기서 풀지 않으므로 나가는 길이
              하나뿐이고, 그것이 주된 동작이다. */}
          <div className="mt-8">
            <Link
              href={routes.testReview}
              className="dv-btn flex w-full items-center justify-center px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus sm:w-auto sm:px-8"
              style={
                {
                  minHeight: "var(--hit-min)",
                  background: "var(--coral)",
                  color: "var(--text-on-color)",
                  border: 0,
                  borderRadius: "var(--radius-pill)",
                  "--lift": "var(--lift-button)",
                  fontWeight: "var(--weight-black)",
                  letterSpacing: "var(--tracking-tight)",
                } as React.CSSProperties
              }
            >
              복습하러 가기
            </Link>
          </div>
        </>
      )}
    </main>
  );
}
