import { redirect } from "next/navigation";

import { AuthForm } from "@/components/AuthForm";
import { getLoginState } from "@/lib/session";
import { signUpAction } from "../actions";

export const metadata = {
  title: "가입하기 · DeVoca",
  description: "DeVoca 계정을 만듭니다.",
};

type PageProps = {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export default async function SignUpPage({ searchParams }: PageProps) {
  // 백엔드가 답하지 않아 로그인을 확인하지 못한 사람(unreachable)도 홈으로 보낸다. 여기
  // 남기면 "로그인 없이 둘러보기" 를 눌러 멀쩡한 로그인을 지울 수 있다.
  const { user, unreachable } = await getLoginState();
  if (user || unreachable) redirect("/");

  const params = await searchParams;
  const next = typeof params.next === "string" ? params.next : undefined;
  // 구글로 왔는데 새 계정이고 동의 값이 없어 되돌아온 경우.
  const consentRequired = params.error === "consent";

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-16">
      <AuthForm
        mode="signup"
        action={signUpAction}
        next={next}
        consentRequired={consentRequired}
      />
    </main>
  );
}
