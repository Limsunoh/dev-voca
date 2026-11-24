import { redirect } from "next/navigation";

import { AuthForm } from "@/components/AuthForm";
import { getLoginState } from "@/lib/session";
import { loginAction } from "../actions";

export const metadata = {
  title: "로그인 · DeVoca",
  description: "DeVoca 에 로그인합니다.",
};

type PageProps = {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export default async function LoginPage({ searchParams }: PageProps) {
  // 이미 로그인한 사람에게 로그인 화면을 보여줄 이유가 없다.
  // 백엔드가 답하지 않아 로그인을 확인하지 못한 사람(unreachable)도 홈으로 보낸다. 여기
  // 남기면 "로그인 없이 둘러보기" 를 눌러 멀쩡한 로그인을 지울 수 있다.
  const { user, unreachable } = await getLoginState();
  if (user || unreachable) redirect("/");

  const params = await searchParams;
  const next = typeof params.next === "string" ? params.next : undefined;
  // 구글에서 실패해 돌아온 경우. 이유는 서버 로그에만 남긴다.
  const googleFailed = params.error === "google";

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-16">
      <AuthForm
        mode="login"
        action={loginAction}
        next={next}
        googleFailed={googleFailed}
      />
    </main>
  );
}
