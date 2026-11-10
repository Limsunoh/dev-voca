import type { Metadata } from "next";
import Link from "next/link";

import { ContactEmail, LegalDoc, type LegalSection } from "@/components/LegalDoc";

export const metadata: Metadata = {
  title: "계정 삭제 안내 · devvoca",
  description: "devvoca 계정과 학습 기록을 지우는 방법과, 지워지는 것과 남는 것을 안내합니다.",
};

/*
 * Google Play 는 앱 안의 삭제와 별도로, 로그인 없이 열리는 이 주소를 요구한다.
 * 앱 이름, 지우는 순서, 지워지는 것과 남는 것(기간 포함)이 이 한 화면에 있어야
 * 한다. 4절의 기간은 처리방침 3·4절을 옮긴 것이라 그쪽을 고치면 여기도 고친다.
 * 숫자가 어긋나면 delete-account-page.test.mts 가 빨개진다.
 */
const SECTIONS: LegalSection[] = [
  {
    id: "steps",
    title: "1. 직접 삭제하기",
    body: (
      <ol>
        <li>
          <Link href="/login?next=/profile">로그인</Link>합니다. 구글로 가입했다면
          구글로 로그인합니다.
        </li>
        <li>아래 탭바에서 내정보로 갑니다.</li>
        <li>화면 아래쪽의 계정 삭제 버튼을 누릅니다.</li>
        <li>
          현재 비밀번호를 입력합니다. 구글로만 가입해 비밀번호가 없으면 가입한
          이메일을 입력합니다.
        </li>
        <li>
          삭제를 누르면 바로 지워지고 시작 화면으로 돌아갑니다. 되돌릴 수
          없습니다.
        </li>
      </ol>
    ),
  },
  {
    id: "request",
    title: "2. 로그인할 수 없을 때",
    body: (
      <p>
        비밀번호를 잊었거나 이용이 정지되어 로그인할 수 없으면, 가입한 이메일
        주소에서 <ContactEmail />로 삭제를 요청해 주세요. 받은 날부터 10일 안에
        처리하고 결과를 메일로 알립니다.
      </p>
    ),
  },
  {
    id: "deleted",
    title: "3. 지워지는 것",
    body: (
      <ul>
        <li>
          계정 정보: 이메일 주소, 비밀번호, 보여지는 이름, 아바타와 올린 프로필
          사진, 구글 프로필 사진 주소, 약관 동의 기록, 로그인 상태를 기억하는 값
        </li>
        <li>
          학습 기록: 문제풀기 점수와 답, 하루 점수, 일일공부, 복습, 오답 노트.
          순위표에서도 빠집니다.
        </li>
      </ul>
    ),
  },
  {
    id: "kept",
    title: "4. 바로 지워지지 않는 것",
    body: (
      <>
        <p>
          아래 기록은 계정과 함께 바로 지워지지 않습니다. 기간이 적힌 것은 그
          기간 안에 지웁니다. 호스팅 업체가 보관하는 것은 업체 정책을 따릅니다.
          자세한 내용은{" "}
          <Link href="/privacy#retention">개인정보 처리방침 3·4절</Link>에
          있습니다.
        </p>
        <ul>
          <li>
            요청을 너무 자주 보내지 못하게 세는 기록(로그인·가입 시도는 이메일을
            알아볼 수 없게 바꾼 값, 로그인한 뒤에는 회원 번호와 시각): 하루
            안(매일 정리할 때 지웁니다)
          </li>
          <li>이미 순위표에서 내 사진을 본 사람의 브라우저에 남은 사진: 최대 7일</li>
          <li>운영자가 보낸 안내 메일(운영자 Gmail 보낸편지함): 보낸 날부터 30일 안</li>
          <li>
            호스팅 업체(서버를 맡긴 업체)의 접속 로그와 메일 발송 실패 기록:
            운영자가 볼 수 있는 기간은 Vercel 1시간, Railway 7일입니다. 업체가
            자체 목적으로 더 오래 보관하는 기간은 각 업체의 정책을 따릅니다.
          </li>
          <li>Railway 의 데이터베이스 백업: Railway 의 정책에 따른 기간</li>
          <li>
            관리자 작업 기록: 운영자가 관리자 화면에서 내 계정을 지우거나 고친
            적이 있으면 회원 번호와 바꾼 항목의 이름이, 문제풀기 기록을 지운 적이
            있으면 회원 번호·날짜·점수가 남습니다. 기간을 정해 지우지 않습니다.
          </li>
        </ul>
        <p>
          구글로 가입했다면 devvoca 계정을 지워도 구글 계정과의 연결은 남습니다.
          구글 계정 설정의 &quot;타사 앱 및 서비스&quot; 에서 해제할 수 있습니다.
        </p>
      </>
    ),
  },
];

export default function DeleteAccountPage() {
  return (
    <LegalDoc
      title="devvoca 계정 삭제 안내"
      intro={
        <p>
          devvoca 계정과 학습 기록을 지우는 방법입니다. 로그인하지 않아도 이
          페이지를 볼 수 있습니다.
        </p>
      }
      sections={SECTIONS}
      other={{ href: "/privacy", label: "개인정보 처리방침" }}
      showVersion={false}
    />
  );
}
