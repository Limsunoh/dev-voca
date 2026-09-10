import type { Metadata } from "next";

import { EmailConfirmCard } from "@/components/EmailConfirmCard";

import { confirmEmailChangeAction } from "./actions";

export const metadata: Metadata = {
  title: "이메일 변경 확인 · devvoca",
};

/**
 * 메일의 확인 링크가 열리는 화면.
 *
 * **여기서 곧바로 주소를 바꾸지 않는다.** 화면을 여는 것만으로 바뀌게
 * 하면, 메일 서비스의 링크 검사기가 먼저 열어 사용자가 누르기도 전에
 * 끝난다. 그러면 본인이 눌렀다는 증거가 없어진다 - 확인 절차를 둔 이유
 * 자체가 사라진다.
 *
 * 그래서 버튼을 하나 두고, 그것을 눌러야 바뀐다. 검사기는 링크를 열 뿐
 * 버튼을 누르지 않는다.
 *
 * 로그인을 요구하지 않는다. 메일을 폰에서 열었는데 폰에는 우리 로그인이
 * 없을 수 있다. 링크에 실린 토큰이 증거다.
 */
export default async function EmailConfirmPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;

  return (
    <main className="mx-auto w-full max-w-md flex-1 px-4 py-8">
      <h1
        className="text-[length:var(--text-2xl)] tracking-[var(--tracking-tight)]"
        style={{
          color: "var(--foreground)",
          fontWeight: "var(--weight-black)",
        }}
      >
        이메일 변경 확인
      </h1>

      <div className="mt-6">
        <EmailConfirmCard action={confirmEmailChangeAction} token={token} />
      </div>
    </main>
  );
}
