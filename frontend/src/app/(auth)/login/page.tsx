import { redirect } from "next/navigation";

import { AuthForm } from "@/components/AuthForm";
import { getCurrentUser } from "@/lib/session";
import { loginAction } from "../actions";

export const metadata = {
  title: "로그인 | devvoca",
  description: "devvoca 에 로그인합니다.",
};

type PageProps = {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export default async function LoginPage({ searchParams }: PageProps) {
  // 이미 로그인한 사람에게 로그인 화면을 보여줄 이유가 없다.
  if (await getCurrentUser()) redirect("/");

  const params = await searchParams;
  const next = typeof params.next === "string" ? params.next : undefined;
  // 구글에서 실패해 돌아온 경우. 이유는 서버 로그에만 남긴다.
  const googleFailed = params.error === "google";

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-16">
      <AuthForm mode="login" action={loginAction}
        next={next}
        googleFailed={googleFailed}
      />
    </main>
  );
}
