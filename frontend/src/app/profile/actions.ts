"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  changePassword,
  deleteMyPhoto,
  requestEmailChange,
  updateMe,
  uploadMyPhoto,
} from "@/lib/api/accounts";
import { ApiError } from "@/lib/api/client";
import { getToken, setToken } from "@/lib/session";

/**
 * 프로필 수정.
 *
 * Server Action 인 이유는 로그인·가입과 같다 - 토큰이 httpOnly 쿠키에만
 * 있어서 브라우저 자바스크립트가 볼 수 없고, 그것을 헤더에 붙이는 일은
 * 서버에서만 일어난다.
 */

export type ProfileState = {
  error?: string;
  saved?: boolean;
  /** 서버가 다듬어 저장한 이름. 화면의 입력칸을 이 값에 맞춘다. */
  savedName?: string;
};

export async function updateProfileAction(
  _prev: ProfileState,
  formData: FormData,
): Promise<ProfileState> {
  const token = await getToken();
  if (!token) {
    // 폼을 열어둔 채 로그인이 풀린 경우. 저장에 실패했다고만 하면
    // 몇 번을 더 누르게 된다.
    redirect("/login?next=/profile");
  }

  const displayName = String(formData.get("display_name") ?? "").trim();
  const avatar = String(formData.get("avatar") ?? "");

  if (!displayName) {
    return { error: "이름을 입력해주세요." };
  }

  let saved;
  try {
    saved = await updateMe(token, { display_name: displayName, avatar });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "잠시 후 다시 시도해주세요." };
  }

  // 머리말이 이름과 사진을 함께 그린다. 이 페이지만 다시 그리면 위쪽이
  // 옛 이름인 채로 남는다.
  revalidatePath("/", "layout");

  return { saved: true, savedName: saved.display_name };
}

export type EmailChangeState = {
  error?: string;
  /** 확인 메일을 보낸 주소. 화면이 "여기로 보냈습니다" 를 그린다. */
  sentTo?: string;
};

/**
 * 이메일 변경 신청.
 *
 * 성공해도 주소는 아직 안 바뀐다. 새 주소로 간 링크를 눌러야 끝난다.
 * 화면이 이 차이를 분명히 말해야 한다 - "저장했습니다" 로 읽히면 사용자는
 * 메일을 열지 않고 떠나고, 다음 로그인에서 옛 주소로 들어가려다 막힌다.
 */
export async function requestEmailChangeAction(
  _prev: EmailChangeState,
  formData: FormData,
): Promise<EmailChangeState> {
  const token = await getToken();
  if (!token) {
    redirect("/login?next=/profile");
  }

  // 필요한 키만 꺼내 쓴다. 폼에는 비밀번호 관리자용 username 칸도 실려
  // 오는데(EmailCard 참고) 서버는 그 키를 모른다. 나중에 폼을 통째로
  // 넘기는 코드로 바꾸면 서버가 모르는 키가 함께 가므로, 그때는 꺼낼 것을
  // 여기서 다시 추린다.
  const newEmail = String(formData.get("new_email") ?? "").trim();
  const currentPassword = String(formData.get("current_password") ?? "");

  if (!newEmail) return { error: "바꿀 이메일을 입력해주세요." };
  if (!currentPassword) return { error: "현재 비밀번호를 입력해주세요." };

  try {
    const sent = await requestEmailChange(token, {
      new_email: newEmail,
      current_password: currentPassword,
    });
    return { sentTo: sent.sent_to };
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "잠시 후 다시 시도해주세요." };
  }
}

export type PasswordState = {
  error?: string;
  /** 저장에 성공했나. 화면이 안내를 띄우고 입력칸을 비운다. */
  saved?: boolean;
  /** 처음 설정한 것인가. 안내 문구가 갈린다. */
  created?: boolean;
};

/**
 * 비밀번호 변경. 구글로만 가입한 사람의 최초 설정도 여기서 받는다.
 *
 * **응답의 새 토큰으로 쿠키를 덮어쓴다.** 서버가 이 계정의 토큰을 전부
 * 지우고 새로 발급하기 때문이다 - 다른 기기를 끊는 것이 목적이고, 그
 * 과정에서 지금 기기가 들고 있던 토큰도 무효가 된다. 쿠키를 갱신하지
 * 않으면 바꾸기는 성공했는데 다음 클릭에서 로그인 화면으로 튕긴다.
 *
 * hasPassword 를 화면에서 받는 이유: 서버가 이미 알고 있는 값이지만,
 * 안 받으면 비밀번호가 없는 계정에도 현재 비밀번호 칸을 그려야 할지
 * 화면이 판단할 수 없다. 값은 서버 컴포넌트가 내려준다.
 */
export async function changePasswordAction(
  _prev: PasswordState,
  formData: FormData,
): Promise<PasswordState> {
  const token = await getToken();
  if (!token) {
    redirect("/login?next=/profile");
  }

  // trim 하지 않는다. 비밀번호는 앞뒤 공백도 값이다 - 다듬어서 보내면
  // 사용자가 정한 것과 다른 값이 저장되고, 다음 로그인에서 안 맞는다.
  const newPassword = String(formData.get("new_password") ?? "");
  const confirm = String(formData.get("new_password_confirm") ?? "");
  const currentRaw = formData.get("current_password");

  if (!newPassword) {
    return { error: "새 비밀번호를 입력해주세요." };
  }

  // 확인 칸은 화면에서만 본다. 서버에 보낼 값이 아니라 오타 방지용이고,
  // 여기서 걸러야 잘못 적은 비밀번호로 다른 기기가 끊기는 일이 없다.
  if (newPassword !== confirm) {
    return { error: "새 비밀번호가 서로 다릅니다." };
  }

  let result;
  try {
    result = await changePassword(token, {
      // 칸이 아예 없었으면(비밀번호 없는 계정) 키를 빼고 보낸다. 빈
      // 문자열을 보내면 서버가 "확인할 수 없습니다" 로 막는다.
      ...(currentRaw === null ? {} : { current_password: String(currentRaw) }),
      new_password: newPassword,
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "잠시 후 다시 시도해주세요." };
  }

  // 새 토큰으로 쿠키를 갱신한다. 이것을 빠뜨리면 다음 요청이 401 이다.
  await setToken(result.token);

  // **has_password 가 바뀌었으므로 화면을 다시 그린다.**
  //
  // 이 값은 서버 컴포넌트가 내려주고 같은 화면의 카드 둘이 함께 본다 -
  // 비밀번호 카드는 "설정" 인지 "변경" 인지를, 이메일 카드는 폼을 그릴지
  // "비밀번호를 먼저 설정하세요" 를 그릴지를 여기서 가른다.
  //
  // 안 부르면 구글로 가입한 사람이 비밀번호를 만든 직후에도 화면은 없던
  // 때 그대로다. 이메일 변경 폼이 계속 안 나오고, 비밀번호 카드는 현재
  // 비밀번호 칸을 안 그린 채로 남아 한 번 더 누르면 "현재 비밀번호를
  // 입력해주세요" 가 뜬다 - 화면에 없는 칸을 채우라는 말이 된다.
  revalidatePath("/", "layout");

  return { saved: true, created: result.created };
}

/**
 * 프로필 사진 올리기·지우기.
 *
 * 이름 저장(updateProfileAction)과 폼을 나눈 이유: 사진은 고르는 즉시
 * 반영돼야 한다. 저장 버튼까지 기다리게 하면 미리보기가 실제로 저장된
 * 것인지 알 수 없고, 이름 저장이 실패하면 사진도 같이 날아간다.
 *
 * 별도 상태를 쓰는 것도 같은 이유다. 한 상태를 나눠 쓰면 사진을 올린
 * 직후에 "저장했습니다" 가 이름 쪽에도 뜬다.
 */

export type PhotoState = {
  error?: string;
  /**
   * 이 결과가 나온 시각(Date.now()).
   *
   * 올리기와 지우기가 각자 상태를 들고 있어서, 화면이 "누가 마지막이었나"
   * 를 물을 곳이 이 값밖에 없다. 없으면 지운 뒤에 올린 사진이 지우기
   * 상태에 가려 안 보인다(ProfileForm 의 lastPhotoChange 주석).
   *
   * 값 비교로 대신할 수 없다. 지웠다가 **같은 사진**을 다시 올리면
   * 주소가 같아서 바뀐 것을 못 알아챈다.
   */
  at?: number;
  /** 지금 화면에 그릴 사진 주소. 지웠으면 빈 문자열. */
  photoUrl?: string;
};

export async function uploadPhotoAction(
  _prev: PhotoState,
  formData: FormData,
): Promise<PhotoState> {
  const token = await getToken();
  if (!token) redirect("/login?next=/profile");

  const file = formData.get("photo");

  // File 인지 본다. 브라우저가 빈 file input 을 보내면 크기 0 짜리
  // File 이 오는데, 그대로 넘기면 백엔드가 "사진 파일이 비어 있습니다" 로
  // 거절한다. 그건 맞는 말이지만 사용자는 고른 적이 없어서 왜 그런지 모른다.
  if (!(file instanceof File) || file.size === 0) {
    return { error: "사진을 골라주세요." };
  }

  let saved;
  try {
    saved = await uploadMyPhoto(token, file);
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "잠시 후 다시 시도해주세요." };
  }

  // 머리말이 사진을 함께 그린다. 이 페이지만 다시 그리면 위쪽은 옛 그림이다.
  revalidatePath("/", "layout");

  return {
    at: Date.now(),
    photoUrl:
      saved.avatar_display.type === "photo" ? saved.avatar_display.url : "",
  };
}

/**
 * 사진 지우기.
 *
 * 올리기와 **같은 상태**를 돌려준다. 처음에는 void 로 뒀는데, 그러면
 * 화면이 지워진 것을 모른다 - 올릴 때 받은 주소가 클라이언트 상태에
 * 남아 있어서, 서버에서 지워도 미리보기와 "사진 지우기" 버튼이 그대로
 * 남는다. 실제로 그렇게 만들어놓고 QA 에서 잡았다.
 *
 * revalidatePath 만으로는 안 된다. 그건 서버가 내려주는 값을 새로
 * 그리게 할 뿐이고, useActionState 가 들고 있는 값은 안 건드린다.
 *
 * 인자를 안 받는다. useActionState 는 (이전 상태, 폼 데이터)로 부르지만
 * 지우기는 둘 다 볼 것이 없다 - 무엇을 지울지는 토큰이 정한다.
 */
export async function deletePhotoAction(): Promise<PhotoState> {
  const token = await getToken();
  if (!token) redirect("/login?next=/profile");

  try {
    await deleteMyPhoto(token);
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "잠시 후 다시 시도해주세요." };
  }

  revalidatePath("/", "layout");

  // 빈 문자열이라야 화면이 "사진 없음" 으로 읽는다. undefined 로 두면
  // 화면의 ?? 가 서버에서 온 옛 주소로 떨어져 지운 사진이 다시 뜬다.
  return { at: Date.now(), photoUrl: "" };
}
