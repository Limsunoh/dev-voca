import { redirect } from "next/navigation";

import { AuthForm } from "@/components/AuthForm";
import { getCurrentUser } from "@/lib/session";
import { signUpAction } from "../actions";

export const metadata = {
  title: "가입하기 · dev-voca",
  description: "dev-voca 계정을 만듭니다.",
};

type PageProps = {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export default async function SignUpPage({ searchParams }: PageProps) {
  if (await getCurrentUser()) redirect("/");

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
