"use client";

import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import type { PhotoState, ProfileState } from "@/app/profile/actions";
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
  /** 사진 올리기. 이름 저장과 폼이 다르다(actions.ts 에 이유). */
  uploadPhoto: (prev: PhotoState, formData: FormData) => Promise<PhotoState>;
  /** 올린 사진 지우기. 올리기와 같은 상태를 돌려준다(actions.ts). */
  deletePhoto: (prev: PhotoState, formData: FormData) => Promise<PhotoState>;
  /**
   * 내가 올린 사진의 주소. 없으면 빈 문자열.
   *
   * googlePicture 와 같은 이유로 따로 받는다 - shown 에서 뽑으면 아바타를
   * 고른 순간 "올린 사진" 선택지가 사라져 되돌릴 길이 없어진다.
   */
  uploadedPhoto: string;
};

export function ProfileForm({
  action,
  initialName,
  initialAvatar,
  shown,
  googlePicture,
  uploadPhoto,
  deletePhoto,
  uploadedPhoto,
}: Props) {
  const [state, formAction] = useActionState<ProfileState, FormData>(
    action,
    {},
  );

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

  // 사진 올리기·지우기는 별도 상태다. 이름 저장과 한 상태를 나눠 쓰면
  // 사진을 올린 직후 "저장했습니다" 가 이름 쪽에도 뜬다.
  const [photoState, photoAction] = useActionState<PhotoState, FormData>(
    uploadPhoto,
    {},
  );

  // 지우기도 같은 모양의 상태를 쓴다. void 를 돌려주면 화면이 지워진 것을
  // 모른 채 옛 주소를 계속 들고 있어, 서버에서는 지워졌는데 미리보기와
  // "사진 지우기" 버튼이 그대로 남는다.
  const [deleteState, deleteAction] = useActionState<PhotoState, FormData>(
    deletePhoto,
    {},
  );

  // 방금 올리거나 지운 결과가 있으면 그것을, 없으면 서버가 준 것을 쓴다.
  // 서버 응답을 기다렸다가 반영하는 이유: 서버가 줄여서 저장하므로,
  // 브라우저가 고른 원본을 그대로 미리 보여주면 실제 저장된 것과 다르다.
  //
  // **둘 중 나중 것을 골라야 한다.** 한때 `지우기 ?? 올리기 ?? 서버` 로
  // 뒀는데, 지우기가 남기는 값이 빈 문자열이라 ?? 가 통과시키지 않는다
  // (?? 는 null·undefined 에서만 넘어간다). 그래서 한 번 지우고 나면
  // 그 뒤에 올린 사진이 영영 화면에 안 나왔다.
  //
  // 시각으로 순서를 정한다. 두 액션이 각자 상태를 들고 있어서 "누가
  // 마지막이었나" 를 물을 곳이 여기밖에 없다.
  const lastPhotoChange =
    (deleteState.at ?? 0) > (photoState.at ?? 0) ? deleteState : photoState;
  const myPhoto = lastPhotoChange.photoUrl ?? uploadedPhoto;
  const hasMyPhoto = Boolean(myPhoto);

  // 저장된 값이 비어 있으면 서버가 정한 것을 고른 상태로 보여준다.
  // 아무것도 선택되지 않은 것처럼 보이면 지금 뭐가 적용 중인지 알 수 없다.
  const [avatar, setAvatar] = useState(
    initialAvatar ||
      (hasMyPhoto
        ? "photo"
        : googlePhoto
          ? "google"
          : shown.type === "preset"
            ? shown.key
            : "a1"),
  );

  // 사진을 새로 올리면 서버가 avatar 를 photo 로 바꿔서 내려준다. 화면의
  // 선택도 그리로 옮겨야 방금 올린 것이 골라진 상태로 보인다. 안 맞추면
  // 사진은 올라갔는데 아바타에 링이 남아 무엇이 적용된 것인지 알 수 없다.
  // 사진이 바뀔 때마다 선택을 그리로 옮긴다.
  //
  // 올렸으면 "올린 사진" 으로. 안 옮기면 사진은 올라갔는데 링은 아바타에
  // 남아, 무엇이 적용된 것인지 알 수 없다.
  //
  // 지웠으면 서버가 정한 것으로. 서버도 같은 판단으로 avatar 를 비운다
  // (views.py 의 delete). 안 옮기면 링이 사라진 칸을 가리킨다.
  //
  // 시각으로 한 번만 반응한다. 값으로 비교하면 지웠다가 같은 사진을 다시
  // 올렸을 때 주소가 같아 못 알아챈다.
  const [syncedAt, setSyncedAt] = useState<number | undefined>(undefined);
  if (lastPhotoChange.at && lastPhotoChange.at !== syncedAt) {
    setSyncedAt(lastPhotoChange.at);
    setAvatar(
      lastPhotoChange.photoUrl
        ? "photo"
        : shown.type === "preset"
          ? shown.key
          : "a1",
    );
  }

  // 고른 것이 구글 사진이나 올린 사진인데 그것이 없어진 경우는 서버가 정한
  // 것을 그대로 쓴다. 여기서 임의로 정하면 이 화면과 머리말이 다른 그림을
  // 보여준다.
  const preview: AvatarDisplay =
    avatar === "google"
      ? googlePhoto
        ? { type: "photo", url: googlePhoto }
        : shown
      : avatar === "photo"
        ? hasMyPhoto
          ? { type: "photo", url: myPhoto }
          : shown
        : { type: "preset", key: avatar };

  return (
    <div className="grid gap-4">
      {/* 사진 고르기를 카드 한 장으로 묶는다. 크림 바탕에 그냥 얹으면
          미리보기·설명·선택지 셋이 각각 떠다니는 것으로 보인다.

          카드는 form 이 아니라 div 다. 이 안에 폼이 **둘** 들어가기
          때문이다 - 올리기와 지우기는 서로 다른 동작이고, HTML 은 form
          안에 form 을 못 넣는다. 아바타 라디오는 아래 이름 폼에 속한다
          (저장 버튼을 눌러야 반영되는 값이라). */}
      <div
        className="grid gap-5 p-5"
        style={{
          background: "var(--paper)",
          borderRadius: "var(--radius-2xl)",
          boxShadow: "var(--lift-card)",
        }}
      >
        <div className="flex items-center gap-4">
          <Avatar shown={preview} size={72} />
          <div className="min-w-0">
            <p
              className="text-sm"
              style={{
                color: "var(--text-body)",
                fontWeight: "var(--weight-bold)",
              }}
            >
              프로필 사진
            </p>
            <p className="mt-1 text-xs" style={{ color: "var(--text-dim)" }}>
              {googlePhoto
                ? "사진을 올리거나 구글 사진 · 아래 아바타를 쓸 수 있습니다."
                : "사진을 올리거나 아래에서 고를 수 있습니다."}
            </p>
          </div>
        </div>

        {/* 올리기와 지우기는 각각 자기 폼을 가진다. 나란히 두고 보기에는
            한 줄로 붙인다. */}
        <div className="flex flex-wrap items-center gap-2">
          <form action={photoAction}>
            <PhotoPicker hasPhoto={hasMyPhoto} />
          </form>

          {hasMyPhoto && (
            <form action={deleteAction}>
              <DeletePhotoButton />
            </form>
          )}
        </div>

        {(photoState.error || deleteState.error) && (
          <p
            role="alert"
            className="rounded-[var(--radius-xl)] p-3 text-sm"
            style={{
              background: "var(--wrong-soft)",
              color: "var(--coral-deep)",
            }}
          >
            {photoState.error || deleteState.error}
          </p>
        )}

      </div>

      {/* 이름과 아바타는 저장 버튼을 눌러야 반영된다. 사진과 달리 되돌리기
          쉽고, 치는 도중에 매번 보내면 "이미 쓰는 이름" 이 글자마다 뜬다. */}
      <form action={formAction} className="grid gap-4">
      <section
        className="grid gap-5 p-5"
        style={{
          background: "var(--paper)",
          borderRadius: "var(--radius-2xl)",
          boxShadow: "var(--lift-card)",
        }}
      >
        <fieldset>
          <legend
            className="text-xs tracking-[var(--tracking-wide)]"
            style={{
              color: "var(--text-dim)",
              fontWeight: "var(--weight-black)",
            }}
          >
            사진 고르기
          </legend>
          {/* 라디오를 쓴다. 하나만 고르는 선택이라 키보드와 스크린 리더가
              그대로 동작한다. 버튼으로 만들면 그것을 직접 흉내 내야 한다. */}
          {/* 폰에서는 한 줄에 다 안 들어간다. 그냥 흘리면 5개 + 1개로
              갈려서 마지막 하나가 혼자 남는다. 네 칸씩 끊어 4+3(구글 사진이
              있을 때) 또는 4+2 로 떨어지게 한다. */}
          <div className="mt-3 grid grid-cols-4 justify-items-center gap-3 sm:flex sm:flex-wrap sm:justify-items-start">
            {/* 올린 사진을 맨 앞에 둔다. 직접 올린 것이 가장 나중에 한
                행동이라 여기 있을 것을 먼저 찾는다. */}
            {hasMyPhoto && (
              <AvatarOption
                value="photo"
                checked={avatar === "photo"}
                onSelect={setAvatar}
                label="내가 올린 사진"
              >
                <Avatar shown={{ type: "photo", url: myPhoto }} size={48} />
              </AvatarOption>
            )}

            {googlePhoto && (
              <AvatarOption
                value="google"
                checked={avatar === "google"}
                onSelect={setAvatar}
                label="구글 계정 사진"
              >
                <Avatar shown={{ type: "photo", url: googlePhoto }} size={48} />
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
                <AvatarMark keyName={key} size={48} />
              </AvatarOption>
            ))}
          </div>
        </fieldset>
      </section>

      <section
        className="p-5"
        style={{
          background: "var(--paper)",
          borderRadius: "var(--radius-2xl)",
          boxShadow: "var(--lift-card)",
        }}
      >
        <label
          htmlFor="display_name"
          className="block text-sm"
          style={{
            color: "var(--text-body)",
            fontWeight: "var(--weight-bold)",
          }}
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
          // AuthForm 과 같은 값이다. 카드(흰색) 안이라 --surface-field 가
          // 흰 바탕에서도 한 톤 낮아 칸이 드러난다.
          className="mt-2 w-full rounded-[var(--radius-xl)] px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={{
            minHeight: "var(--hit-floor)",
            background: "var(--surface-field)",
            color: "var(--foreground)",
            border: 0,
            boxShadow: "var(--lift-card)",
          }}
        />
        <p
          id="display_name-hint"
          className="mt-2 text-xs"
          style={{ color: "var(--text-dim)" }}
        >
          순위표에 이 이름이 뜹니다. 다른 사람이 쓰는 이름은 쓸 수 없습니다.
        </p>
      </section>

      {/* 알림은 테두리가 아니라 옅은 채움으로 구분한다. AuthForm 과 같다. */}
      {state.error && (
        <p
          role="alert"
          className="rounded-[var(--radius-xl)] p-3 text-sm"
          style={{
            background: "var(--wrong-soft)",
            color: "var(--coral-deep)",
          }}
        >
          {state.error}
        </p>
      )}

      {state.saved && !state.error && (
        <p
          role="status"
          className="rounded-[var(--radius-xl)] p-3 text-sm"
          style={{
            background: "var(--correct-soft)",
            color: "var(--correct-deep)",
          }}
        >
          저장했습니다.
        </p>
      )}

      <SaveButton />
      </form>
    </div>
  );
}

/**
 * 아바타 하나를 고르는 칸.
 *
 * 라디오 자체는 숨기고 그림을 라벨로 쓴다. 숨기되 sr-only 로 두는 이유:
 * display:none 이면 키보드 포커스가 안 가고 스크린 리더도 못 읽는다.
 *
 * 고른 것은 코랄 링으로 표시한다(디자이너 프로토타입과 같은 방식).
 * 테두리가 아니라 box-shadow 인 이유: 테두리는 안쪽 칸 크기를 바꿔서
 * 고를 때마다 그림이 2px 씩 움찔한다. 링은 바깥으로만 자란다.
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
      className="dv-card dv-press-card flex h-14 w-14 cursor-pointer items-center justify-center has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-4 has-[:focus-visible]:outline-focus"
      style={
        {
          borderRadius: "var(--radius-lg)",
          /* 여기 그림자는 두께가 아니라 "지금 고른 것" 을 알리는 링이다.
           그래서 누를 때 사라지지 않는다(.dv-press-card 가 transform 만
           건드리는 이유).

           링을 두 겹으로 두른다. 안쪽 크림 한 겹이 없으면 a3 처럼 아바타
           바탕이 코랄 계열(#C13E22 = --coral-deep)인 것에서 링이 그림과
           붙어 보여, 골랐는지 아닌지가 그 하나만 안 보인다. 아바타 색은
           디자인이 정한 것이라 링 쪽에서 해결한다. */
          "--lift": checked
            ? "0 0 0 2px var(--background), 0 0 0 5px var(--coral)"
            : "none",
        } as React.CSSProperties
      }
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
 * 갤러리에서 사진 고르기.
 *
 * accept="image/*" 하나로 iOS·안드로이드 둘 다 갤러리가 열린다. 별도
 * 라이브러리를 넣지 않는다 - 이 프로젝트의 런타임 의존성은 next·react·
 * react-dom 셋뿐이고, 사진 한 장 고르자고 늘릴 이유가 없다.
 *
 * input 자체는 숨기고 라벨을 버튼처럼 쓴다. 기본 파일 입력은 브라우저마다
 * 생김새가 달라서 이 화면의 다른 버튼과 따로 논다. 숨기되 sr-only 로 두는
 * 이유는 아바타 라디오와 같다 - display:none 이면 키보드로 못 간다.
 *
 * 지우기 버튼은 여기 없다. 그것은 다른 폼(지우기 액션)에 속하고, 폼은
 * 겹칠 수 없어서 형제로 나란히 둔다.
 */
function PhotoPicker({ hasPhoto }: { hasPhoto: boolean }) {
  const { pending } = useFormStatus();

  return (
    <label
      className="dv-btn cursor-pointer rounded-[var(--radius-pill)] px-5 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus"
      style={
        {
          minHeight: "var(--hit-min)",
          background: "var(--paper)",
          color: "var(--foreground)",
          border: 0,
          "--lift": "var(--lift-button-paper)",
          fontWeight: "var(--weight-bold)",
          opacity: pending ? 0.6 : 1,
        } as React.CSSProperties
      }
    >
      <input
        type="file"
        name="photo"
        accept="image/*"
        disabled={pending}
        // 고르는 즉시 보낸다. 파일을 고른 뒤 버튼을 또 눌러야 하면
        // 고른 것이 반영된 줄 알고 화면을 떠난다.
        //
        // 보내고 나서 값을 비운다. 안 비우면 같은 파일을 다시 골랐을 때
        // 값이 안 바뀌어 onChange 가 아예 안 난다 - 사진을 지웠다가
        // 같은 것을 다시 올리려는 흐름에서 아무 일도 안 일어난다.
        onChange={(event) => {
          const form = event.currentTarget.form;
          form?.requestSubmit();
          event.currentTarget.value = "";
        }}
        className="sr-only"
      />
      {pending ? "올리는 중" : hasPhoto ? "다른 사진" : "사진 올리기"}
    </label>
  );
}

/**
 * 되돌릴 길. 한 번 올리면 못 돌아가면 안 된다.
 *
 * 별도 컴포넌트인 이유는 SaveButton 과 같다 - useFormStatus 는 폼 안쪽
 * 에서만 상태를 읽어서, 폼과 같은 컴포넌트에 두면 pending 이 늘 false 다.
 */
function DeletePhotoButton() {
  const { pending } = useFormStatus();

  return (
    <button
      type="submit"
      disabled={pending}
      className="dv-btn rounded-[var(--radius-pill)] px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60"
      style={
        {
          minHeight: "var(--hit-min)",
          background: "var(--paper)",
          color: "var(--text-muted)",
          border: 0,
          "--lift": "var(--lift-button-paper)",
          fontWeight: "var(--weight-bold)",
        } as React.CSSProperties
      }
    >
      {pending ? "지우는 중" : "사진 지우기"}
    </button>
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
      // 이 화면의 유일한 코랄. 로그아웃은 흰 버튼으로 둔다(profile/page.tsx).
      className="dv-btn w-full rounded-[var(--radius-pill)] px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60 sm:w-auto sm:justify-self-start sm:px-8"
      style={
        {
          minHeight: "var(--hit-min)",
          background: "var(--coral)",
          color: "var(--text-on-color)",
          border: 0,
          "--lift": "var(--lift-button)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
        } as React.CSSProperties
      }
    >
      {pending ? "저장하는 중" : "저장"}
    </button>
  );
}
