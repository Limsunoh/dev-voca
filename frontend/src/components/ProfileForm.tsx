"use client";

import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import type { ProfileState } from "@/app/profile/actions";
import {
  AVATAR_KEYS,
  Avatar,
  AvatarMark,
  avatarLabel,
} from "@/components/Avatar";
import type { AvatarDisplay } from "@/lib/api/accounts";

/**
 * 사진과 이름을 바꾸는 폼.
 *
 * 클라이언트 컴포넌트인 이유: 고른 아바타가 즉시 크게 보여야 한다.
 * 저장한 뒤에야 바뀌면 무엇을 고른 건지 모른 채 저장하게 된다.
 *
 * 실제 저장은 Server Action 이 받는다. 토큰은 브라우저를 거치지 않는다.
 */

type Props = {
  action: (prev: ProfileState, formData: FormData) => Promise<ProfileState>;
  initialName: string;
  /** 저장된 선택. 비어 있으면 서버가 알아서 정한 상태다. */
  initialAvatar: string;
  /** 지금 화면에 뜨는 것. 아무것도 안 고른 상태에서 무엇을 보여줄지. */
  shown: AvatarDisplay;
  /**
   * 구글 계정 사진 주소. 없으면 빈 문자열.
   *
   * shown 에서 뽑으면 안 된다. 아바타를 한 번 고르면 shown 이 preset 이
   * 되어 사진이 남아 있어도 "구글 사진" 선택지가 사라지고, 되돌릴 방법이
   * 화면에서 없어진다.
   */
  googlePicture: string;
};

export function ProfileForm({
  action,
  initialName,
  initialAvatar,
  shown,
  googlePicture,
}: Props) {
  const [state, formAction] = useActionState<ProfileState, FormData>(action, {});

  // 입력칸을 상태로 들고 있는 이유: 저장에 실패하면 폼이 다시 그려지는데,
  // defaultValue 로 두면 그때 원래 이름으로 되돌아간다. 사용자는 방금 친
  // 이름을 잃고 처음부터 다시 쳐야 한다. "이미 쓰는 이름" 이 자주 나는
  // 자리라 더 그렇다.
  const [name, setName] = useState(initialName);

  // 서버가 앞뒤 공백 따위를 다듬어 저장한다. 그 결과로 맞춰주지 않으면
  // 화면에는 다듬기 전 값이 남아, 저장된 것과 보이는 것이 어긋난다.
  const [syncedWith, setSyncedWith] = useState<string | undefined>(undefined);
  if (state.savedName !== undefined && state.savedName !== syncedWith) {
    setSyncedWith(state.savedName);
    setName(state.savedName);
  }

  const googlePhoto = googlePicture || null;

  // 저장된 값이 비어 있으면 서버가 정한 것을 고른 상태로 보여준다.
  // 아무것도 선택되지 않은 것처럼 보이면 지금 뭐가 적용 중인지 알 수 없다.
  const [avatar, setAvatar] = useState(
    initialAvatar || (googlePhoto ? "google" : shown.type === "preset" ? shown.key : "a1"),
  );

  // 고른 것이 구글 사진인데 사진이 없어진 경우는 서버가 정한 것을 그대로
  // 쓴다. 여기서 임의로 정하면 이 화면과 머리말이 다른 그림을 보여준다.
  const preview: AvatarDisplay =
    avatar === "google"
      ? googlePhoto
        ? { type: "photo", url: googlePhoto }
        : shown
      : { type: "preset", key: avatar };

  return (
    <form action={formAction} className="grid gap-6">
      <div className="flex items-center gap-4">
        <Avatar shown={preview} size={72} />
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
            프로필 사진
          </p>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            {googlePhoto
              ? "구글 사진을 쓰거나 아래에서 고를 수 있습니다."
              : "아래에서 고를 수 있습니다."}
          </p>
        </div>
      </div>

      <fieldset>
        <legend className="text-sm font-medium text-slate-700 dark:text-slate-300">
          사진 고르기
        </legend>
        {/* 라디오를 쓴다. 하나만 고르는 선택이라 키보드와 스크린 리더가
            그대로 동작한다. 버튼으로 만들면 그것을 직접 흉내 내야 한다. */}
        {/* 폰에서는 한 줄에 다 안 들어간다. 그냥 흘리면 5개 + 1개로
            갈려서 마지막 하나가 혼자 남는다. 네 칸씩 끊어 4+3(구글 사진이
            있을 때) 또는 4+2 로 떨어지게 한다. */}
        <div className="mt-2 grid grid-cols-4 justify-items-center gap-2 sm:flex sm:flex-wrap sm:justify-items-start">
          {googlePhoto && (
            <AvatarOption
              value="google"
              checked={avatar === "google"}
              onSelect={setAvatar}
              label="구글 계정 사진"
            >
              <Avatar shown={{ type: "photo", url: googlePhoto }} size={44} />
            </AvatarOption>
          )}

          {AVATAR_KEYS.map((key) => (
            <AvatarOption
              key={key}
              value={key}
              checked={avatar === key}
              onSelect={setAvatar}
              label={avatarLabel(key)}
            >
              <AvatarMark keyName={key} size={44} />
            </AvatarOption>
          ))}
        </div>
      </fieldset>

      <div>
        <label
          htmlFor="display_name"
          className="block text-sm font-medium text-slate-700 dark:text-slate-300"
        >
          보여지는 이름
        </label>
        <input
          id="display_name"
          name="display_name"
          type="text"
          required
          // 백엔드 DISPLAY_NAME_MAX 와 같아야 한다. 여기가 더 크면 서버가
          // 거절하고, 더 작으면 쓸 수 있는 이름을 못 쓰게 막는다.
          maxLength={12}
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-describedby="display_name-hint"
          // SearchInput 과 같은 값이다. 앱의 입력칸은 이 셋뿐이라 한 곳만
          // 고치면 로그인·프로필 칸만 대비가 낮고 높이가 낮은 채로 남는다.
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2.5 text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus dark:border-white/40 dark:bg-slate-900/55 dark:text-slate-100"
        />
        <p
          id="display_name-hint"
          className="mt-1 text-xs text-slate-500 dark:text-slate-400"
        >
          순위표에 이 이름이 뜹니다. 다른 사람이 쓰는 이름은 쓸 수 없습니다.
        </p>
      </div>

      {state.error && (
        <p
          role="alert"
          className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          {state.error}
        </p>
      )}

      {state.saved && !state.error && (
        <p
          role="status"
          className="rounded-md border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
        >
          저장했습니다.
        </p>
      )}

      <SaveButton />
    </form>
  );
}

/**
 * 아바타 하나를 고르는 칸.
 *
 * 라디오 자체는 숨기고 그림을 라벨로 쓴다. 숨기되 sr-only 로 두는 이유:
 * display:none 이면 키보드 포커스가 안 가고 스크린 리더도 못 읽는다.
 */
function AvatarOption({
  value,
  checked,
  onSelect,
  label,
  children,
}: {
  value: string;
  checked: boolean;
  onSelect: (value: string) => void;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label
      // 누름 축소를 0.97 이 아니라 0.94 로 둔다. 56px 짜리 작은 사각형이라
      // 0.97 이면 실제 이동이 1px 도 안 돼 손가락 밑에서 안 보인다. 큰
      // 버튼과 같은 값을 쓰는 것보다 같은 세기로 느껴지는 쪽이 맞다.
      className={`flex h-14 w-14 cursor-pointer items-center justify-center rounded-lg border-2 transition-[scale,border-color,background-color] duration-[120ms] ease-press active:scale-[0.94] ${
        checked
          ? "border-slate-900 bg-slate-100 dark:border-slate-100 dark:bg-slate-800"
          : "border-transparent hover:border-slate-300 dark:hover:border-slate-700"
      } has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus`}
    >
      <input
        type="radio"
        name="avatar"
        value={value}
        checked={checked}
        onChange={() => onSelect(value)}
        className="sr-only"
      />
      <span className="sr-only">{label}</span>
      {children}
    </label>
  );
}

/**
 * 저장 버튼.
 *
 * 별도 컴포넌트인 이유: useFormStatus 는 form 안쪽에서만 상태를 읽는다.
 * 폼과 같은 컴포넌트에 두면 pending 이 항상 false 다.
 */
function SaveButton() {
  const { pending } = useFormStatus();

  return (
    <button
      type="submit"
      disabled={pending}
      className="w-full rounded-md bg-slate-900 px-4 py-2.5 font-medium text-white transition-[scale,background-color] duration-[120ms] ease-press hover:bg-slate-700 active:scale-[0.97] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60 sm:w-auto sm:justify-self-start sm:px-6 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
    >
      {pending ? "저장하는 중" : "저장"}
    </button>
  );
}
