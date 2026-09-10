"""계정 입출력 규칙.

비밀번호는 어느 응답에도 담기지 않는다(write_only). 그리고 저장 경로가
set_password 를 거치도록 강제한다 - ModelSerializer 의 기본 create 는
평문을 그대로 필드에 넣어 저장하므로, 이 클래스를 거치지 않으면 비밀번호가
해시 없이 DB 에 들어간다.
"""

from __future__ import annotations

import uuid

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.utils import timezone
from rest_framework import serializers

from .models import (
    AVATAR_PHOTO,
    AVATAR_PHOTO_MAX_BYTES,
    DISPLAY_NAME_MAX,
    AvatarPhotoError,
    name_taken,
    normalize_display_name,
    shrink_avatar_photo,
)

User = get_user_model()


def validate_display_name(value: str, *, instance=None) -> str:
    """이름을 다듬고, 이미 쓰는 이름인지 본다.

    가입과 프로필 수정이 같은 함수를 쓴다. 한쪽에만 두면 그쪽만 안내를
    받고 다른 쪽은 DB 제약에 걸려 엉뚱한 문구가 나간다 - 실제로 가입에서
    이름이 겹치면 "이미 가입된 이메일입니다" 가 떴다. 이메일은 멀쩡한데
    사용자는 이메일을 바꿔가며 계속 실패한다.

    모델의 save() 도 같은 규칙으로 다듬는다. 여기서 또 하는 이유는 다듬은
    뒤의 값으로 중복과 길이를 봐야 하기 때문이다 - 다듬기 전 값으로 보면
    "임선오 " 가 "임선오" 와 다르다고 판정돼 통과하고, "  임선오  " 는
    실제보다 길게 세어져 억울하게 막힌다.
    """
    name = normalize_display_name(value)

    if not name:
        raise serializers.ValidationError("이름을 입력해주세요.")

    # 길이를 모델의 max_length 에 맡기면 저장할 때 걸려 500 이 된다.
    if len(name) > DISPLAY_NAME_MAX:
        raise serializers.ValidationError(
            f"이름은 {DISPLAY_NAME_MAX}자까지 쓸 수 있습니다."
        )

    if name_taken(name, exclude_pk=instance.pk if instance else None):
        raise serializers.ValidationError("이미 쓰고 있는 이름입니다.")

    return name


def _conflict_message(exc: IntegrityError) -> dict:
    """DB 가 막은 것이 이름인지 이메일인지 가려낸다.

    제약 이름으로 판정한다. 엔진마다 문구가 다르지만 제약 이름은 우리가
    지은 것이라 양쪽에 다 들어간다.

    못 가려내면 이메일 쪽으로 둔다. 이 경로에서 유일성이 걸린 칸이 둘뿐이고,
    이름은 위에서 한 번 걸러지므로 남는 쪽이 이메일일 가능성이 높다.
    """
    if "display_name" in str(exc):
        return {"display_name": ["이미 쓰고 있는 이름입니다."]}
    return {"email": ["이미 가입된 이메일입니다."]}


class UserSerializer(serializers.ModelSerializer):
    """로그인한 사용자 정보. 화면 상단과 내 프로필이 쓴다."""

    name = serializers.CharField(source="name_for_display", read_only=True)

    # 화면이 그릴 것을 서버가 정해서 내려준다.
    # {"type": "photo", "url": ...} 이거나 {"type": "preset", "key": "a3"}.
    # 프론트가 "구글 사진이 있으면 그것, 없으면 아바타" 규칙을 따로 들고
    # 있으면 두 곳이 어긋난다.
    avatar_display = serializers.DictField(read_only=True)

    # 비밀번호를 쓸 수 있는 계정인지. 구글로만 가입하면 없다.
    #
    # 화면이 직접 판정할 수 없어서 서버가 내려준다. google_picture 가 있는지
    # 로는 못 가른다 - 이메일로 가입한 뒤 구글로도 로그인한 사람은 사진이
    # 있으면서 비밀번호도 있다. 그걸로 가르면 그 사람에게 비밀번호 변경
    # 화면이 안 뜬다.
    has_password = serializers.BooleanField(
        source="has_usable_password", read_only=True
    )
    # 내가 올린 사진의 주소. 없으면 빈 문자열.
    #
    # google_picture 와 같은 이유로 따로 내려준다. avatar_display 로
    # 대신할 수 없다 - 그건 "지금 무엇을 그릴지" 라서 아바타를 한 번
    # 고르면 사진이 남아 있어도 preset 으로 나오고, 그것만 보면 올린
    # 사진으로 되돌아갈 방법이 화면에서 사라진다.
    #
    # 바이트가 아니라 주소다. 사진 자체는 별도 엔드포인트가 내려준다
    # (이유는 models.py 의 avatar_photo_url 에 적어뒀다).
    uploaded_photo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "display_name",
            "name",
            "avatar",
            "avatar_display",
            "google_picture",
            "has_password",
            "uploaded_photo",
            "is_staff",
        ]
        # 이메일은 여기서 바꾸지 않는다. 로그인 키라 본인 확인이 먼저인데,
        # 그 절차는 EmailChangeRequestView 가 따로 갖고 있다(새 주소로 간
        # 확인 링크를 눌러야 바뀐다). 이 시리얼라이저는 화면이 이름·아바타를
        # 저장할 때 쓰는 것이라, 여기를 열면 확인 절차를 건너뛰는 뒷문이 된다.
        #
        # google_picture 는 읽기만 연다. 화면이 "구글 사진" 선택지를
        # 그리려면 주소가 필요한데, 쓰기까지 열면 아무 주소나 넣어 우리
        # 화면을 여는 것만으로 그 서버에 요청이 나가는 통로가 된다.
        #
        # avatar_display 로 대신할 수 없다. 그건 "지금 무엇을 그릴지" 라서
        # 아바타를 한 번 고르면 사진이 남아 있어도 preset 으로 나온다.
        # 그것만 보면 구글 사진으로 되돌아갈 방법이 화면에서 사라진다.
        read_only_fields = [
            "id",
            "email",
            "is_staff",
            "google_picture",
            "has_password",
        ]

    def get_uploaded_photo(self, user: User) -> str:
        return user.avatar_photo_url if user.has_avatar_photo else ""

    def validate_avatar(self, value: str) -> str:
        """올린 사진이 없는데 "올린 사진" 을 고르는 것을 막는다.

        막지 않아도 화면이 깨지지는 않는다 - avatar_display 가 아바타로
        떨어진다. 다만 그러면 프로필 화면의 선택 링이 있지도 않은 칸을
        가리키는 상태가 되고, 사용자는 무엇이 골라진 것인지 알 수 없다.

        사진은 이 경로가 아니라 POST /photo/ 로 올린다. 그쪽이 avatar 도
        함께 바꿔주므로, 정상적인 화면 흐름은 여기 걸릴 일이 없다.
        """
        if value == AVATAR_PHOTO and not (
            self.instance and self.instance.has_avatar_photo
        ):
            raise serializers.ValidationError("올린 사진이 없습니다.")
        return value

    def validate_display_name(self, value: str) -> str:
        return validate_display_name(value, instance=self.instance)

    def update(self, instance: User, validated_data: dict) -> User:
        try:
            return super().update(instance, validated_data)
        except IntegrityError as exc:
            # 위에서 확인했지만 그 사이 다른 요청이 같은 이름을 먼저
            # 가져갈 수 있다. DB 가 막아준 것을 500 대신 안내로 바꾼다.
            raise serializers.ValidationError(
                {"display_name": ["이미 쓰고 있는 이름입니다."]}
            ) from exc


class SignUpSerializer(serializers.ModelSerializer):
    """이메일 가입."""

    # max_length 를 직접 준다. 필드를 선언하면 모델의 max_length 를 물려받지
    # 않는데, 이메일 검사기는 320자까지 통과시킨다. 그 사이 길이가 들어오면
    # 검증은 지나가고 DB 가 거절해 500 이 난다.
    # (SQLite 는 길이를 안 지켜서 로컬 테스트로는 안 드러난다.)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["email", "password", "display_name"]

    def validate_display_name(self, value: str) -> str:
        return validate_display_name(value)

    def validate_email(self, value: str) -> str:
        """이미 있는 이메일인지 본다.

        unique=True 가 DB 에서 막아주지만, 그 에러는 영어 문구로 나오고
        500 이 되기도 한다. 여기서 걸러 한국어로 알려준다.
        """
        # 대소문자만 다른 중복을 막는다. 도메인은 대소문자를 구분하지 않아
        # Gmail.com 과 gmail.com 이 같은 주소다.
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("이미 가입된 이메일입니다.")
        return value

    def validate(self, attrs: dict) -> dict:
        """Django 의 비밀번호 검사기를 태운다.

        너무 짧거나, 흔하거나, 숫자로만 된 비밀번호를 막는다. 설정의
        AUTH_PASSWORD_VALIDATORS 를 그대로 쓰므로 규칙이 한 곳에 모인다.

        필드 단위(validate_password)가 아니라 여기서 하는 이유: 검사기 중
        하나가 "이메일과 비슷한 비밀번호" 를 막는데, 그 검사는 사용자 정보를
        받아야 동작한다. 안 넘기면 그 검사만 조용히 건너뛰어, 이메일을
        그대로 비밀번호로 쓴 가입이 통과한다.

        저장하지 않은 인스턴스를 넘긴다. 아직 계정이 없는 시점이고,
        검사기는 필드 값만 읽는다.
        """
        candidate = User(
            email=attrs.get("email", ""),
            display_name=attrs.get("display_name", ""),
        )
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            # Django 예외를 DRF 예외로 바꿔야 400 응답이 된다.
            # 그냥 두면 500 이다. 키를 password 로 지정해 화면이
            # 어느 칸의 문제인지 알 수 있게 한다.
            raise serializers.ValidationError(
                {"password": list(exc.messages)}
            ) from exc
        return attrs

    def create(self, validated_data: dict) -> User:
        # create_user 를 거쳐야 비밀번호가 해시된다.
        try:
            return User.objects.create_user(**validated_data)
        except IntegrityError as exc:
            # 위에서 중복을 확인했지만 그 사이 다른 요청이 먼저 들어올 수
            # 있다. DB 가 막아준 것을 500 대신 안내로 바꾼다.
            #
            # 어느 칸이 걸렸는지 가려낸다. 전부 이메일 탓으로 돌리면,
            # 이름이 겹쳤을 때 "이미 가입된 이메일입니다" 가 떠서 사용자가
            # 멀쩡한 이메일을 바꿔가며 계속 실패한다.
            raise serializers.ValidationError(_conflict_message(exc)) from exc

    def update(self, instance: User, validated_data: dict) -> User:
        """이 시리얼라이저로는 수정하지 않는다.

        막아두는 이유: ModelSerializer 의 기본 update 는 평문 비밀번호를
        필드에 그대로 넣고 저장한다. 지금은 부르는 곳이 없지만, 나중에
        누군가 재사용하면 해시 없이 DB 에 들어간다. 그때는 에러도 안 나서
        한참 뒤에야 드러난다.
        """
        raise NotImplementedError(
            "가입 전용 시리얼라이저입니다. 수정은 UserSerializer 를 쓰세요."
        )


class LoginSerializer(serializers.Serializer):
    """이메일 로그인."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs: dict) -> dict:
        """계정을 확인한다.

        authenticate 를 쓰는 이유: 비활성 계정 차단과 비밀번호 대조를
        Django 가 한 곳에서 처리한다. 직접 get() 후 check_password 를 하면
        is_active 검사를 빠뜨리기 쉽다.

        실패 사유를 나누지 않는 이유: "없는 이메일" 과 "비밀번호 틀림" 을
        구분해 알려주면, 그 응답만으로 어떤 이메일이 가입돼 있는지 확인할
        수 있다.
        """
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["email"],
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError(
                "이메일 또는 비밀번호가 올바르지 않습니다."
            )

        attrs["user"] = user
        return attrs


class EmailChangeRequestSerializer(serializers.Serializer):
    """이메일 변경 신청. 확인 메일을 보내기 전까지의 검사.

    여기서 통과해도 주소는 아직 안 바뀐다. 새 주소로 간 링크를 눌러야 끝난다.
    """

    # max_length 를 직접 주는 이유는 SignUpSerializer 쪽에 적어뒀다 -
    # 이메일 검사기는 320자까지 통과시키는데 DB 는 254자라 그 사이 길이가
    # 들어오면 검증을 지나가고 저장에서 500 이 난다.
    new_email = serializers.EmailField(max_length=254)

    # 지금 화면 앞에 있는 사람이 계정 주인인지 확인한다. 링크만으로는
    # 새 주소의 주인임만 증명되고, 그 둘은 다른 사람일 수 있다.
    # 자세한 이유는 email_change.py 머리말에 있다.
    current_password = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    def validate_new_email(self, value: str) -> str:
        """이미 쓰는 주소인지, 지금 주소와 같은지 본다."""
        user = self.context["user"]
        new_email = value.lower()

        if new_email == user.email.lower():
            raise serializers.ValidationError("지금 쓰고 있는 이메일입니다.")

        # 대소문자만 다른 중복도 막는다. 저장할 때 소문자로 내려가므로
        # 그대로 두면 확인 링크를 누르는 시점에 DB 가 거절해, 사용자는
        # 메일까지 받고 나서야 실패를 안다.
        if User.objects.filter(email__iexact=new_email).exists():
            raise serializers.ValidationError("이미 가입된 이메일입니다.")

        return new_email

    def validate_current_password(self, value: str) -> str:
        user = self.context["user"]

        # 구글로만 가입한 계정은 비밀번호가 없다(make_password(None) 로
        # 만들어져 check_password 가 무엇을 넣어도 False 다). 그대로 두면
        # "비밀번호가 올바르지 않습니다" 만 반복해서 뜨고, 사용자는 자기가
        # 비밀번호를 만든 적이 없다는 것을 화면 어디서도 알 수 없다.
        if not user.has_usable_password():
            raise serializers.ValidationError(
                "구글로 가입한 계정입니다. 비밀번호를 먼저 설정해주세요."
            )

        if not user.check_password(value):
            raise serializers.ValidationError("비밀번호가 올바르지 않습니다.")

        return value


class PasswordChangeSerializer(serializers.Serializer):
    """비밀번호 변경. 처음 설정하는 경우도 같이 받는다.

    두 흐름을 한 클래스로 두는 이유: 화면도 하나이고 저장도 같은
    set_password 다. 나누면 뷰가 어느 쪽인지 먼저 판정해 시리얼라이저를
    골라야 하는데, 그 판정이 뷰와 시리얼라이저 두 곳에 생긴다.

    **구글로만 가입한 사람은 비밀번호가 없다.** 계정을 만들 때
    make_password(None) 로 못 쓰는 값이 들어가서 has_usable_password() 가
    False 다. 그 사람에게 현재 비밀번호를 물으면 댈 수 있는 값이 없어
    영영 비밀번호를 만들지 못한다. 그래서 현재 비밀번호는 이미 가진
    사람에게만 요구한다.

    반대로 비밀번호가 있는 사람에게 현재 비밀번호를 안 물으면, 로그인된
    화면을 잠깐 빌린 사람이 그대로 갈아치우고 주인을 밀어낼 수 있다.
    """

    # required=False 로 두고 아래 validate 에서 직접 본다. 필드 단위로
    # required 를 켜면 구글 전용 계정에도 "이 필드는 필수입니다" 가 나간다.
    current_password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        style={"input_type": "password"},
    )
    new_password = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    def validate(self, attrs: dict) -> dict:
        user = self.context["user"]
        # 비밀번호를 이미 가진 사람인가. 이 값으로 두 흐름이 갈린다.
        has_password = user.has_usable_password()

        if has_password:
            current = attrs.get("current_password") or ""
            if not current:
                raise serializers.ValidationError(
                    {"current_password": ["현재 비밀번호를 입력해주세요."]}
                )
            # check_password 를 쓴다. authenticate 를 쓰면 이메일까지
            # 넘겨야 하고, 비활성 계정이면 None 이 와서 "비밀번호가 틀렸다"
            # 로 보인다 - 이 경로는 이미 인증을 통과해 들어온 자리다.
            if not user.check_password(current):
                raise serializers.ValidationError(
                    {"current_password": ["현재 비밀번호가 올바르지 않습니다."]}
                )
        elif attrs.get("current_password"):
            # 비밀번호가 없는 계정인데 현재 비밀번호가 왔다. 대조할 값이
            # 없으므로 통과시키면 안 되고, 조용히 무시하면 화면이 잘못된
            # 칸을 계속 보여준다.
            raise serializers.ValidationError(
                {
                    "current_password": [
                        "이 계정은 비밀번호가 없어 현재 비밀번호를 확인할 수 없습니다."
                    ]
                }
            )

        new_password = attrs["new_password"]

        # 같은 값으로 바꾸는 것을 막는다. 비밀번호를 바꾸는 이유가 보통
        # "누가 알아낸 것 같다" 이고, 그때 같은 값으로 저장되면 아래에서
        # 다른 기기 토큰만 끊고 비밀번호는 그대로다. 성공했다고 보이는데
        # 실제로는 아무것도 안 바뀐다.
        #
        # 비밀번호가 없던 계정은 건너뛴다. check_password 가 항상 False 라
        # 비교할 대상이 없다.
        if has_password and user.check_password(new_password):
            raise serializers.ValidationError(
                {"new_password": ["지금 쓰는 비밀번호와 다른 값으로 정해주세요."]}
            )

        # 가입과 같은 검사기를 태운다. 여기서 user 를 넘기는 이유는
        # SignUpSerializer 와 같다 - 사용자 정보를 안 넘기면 "이메일과
        # 비슷한 비밀번호" 검사가 조용히 건너뛰어진다. 가입 때는 저장 전
        # 인스턴스를 만들어 넘겼지만 여기는 이미 있는 계정을 그대로 쓴다.
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {"new_password": list(exc.messages)}
            ) from exc

        # 뷰가 다시 판정하지 않게 결과를 실어 보낸다. 뷰에서 또
        # has_usable_password() 를 부르면 이미 저장한 뒤라 항상 True 다.
        attrs["was_unusable"] = not has_password
        return attrs

    def save(self) -> None:
        """비밀번호만 저장한다. 토큰 처리는 뷰가 한다.

        여기서 토큰까지 손대지 않는 이유: 토큰을 새로 발급하면 그 값을
        응답에 실어야 하는데, 시리얼라이저가 그것까지 들면 "입력을
        검증한다" 는 역할을 넘어선다. 무엇보다 이 클래스만 보고는 지금
        기기가 로그아웃되는지 알 수 없게 된다.
        """
        user = self.context["user"]
        user.set_password(self.validated_data["new_password"])
        # update_fields 로 좁힌다. 통째로 저장하면 이 요청이 들고 있던
        # 옛 값이 다른 칸을 덮어쓴다 - 사진 담당이 같은 시각에 아바타를
        # 바꾸는 중이면 그 변경이 사라진다.
        user.save(update_fields=["password"])


class AvatarPhotoSerializer(serializers.Serializer):
    """프로필 사진 업로드.

    ModelSerializer 가 아닌 이유: 받는 것은 파일 하나인데 저장하는 것은
    줄여서 바꾼 바이트다. 들어온 값과 저장할 값이 다르므로 필드를 모델에
    묶어두면 오히려 헷갈린다.

    크기 상한을 여기서 한 번 더 본다. Django 의 DATA_UPLOAD_MAX_MEMORY_SIZE
    도 큰 본문을 막지만 그건 전역 설정이라 다른 API 와 함께 움직이고,
    걸렸을 때 나가는 것은 우리가 지은 안내가 아니다.
    """

    photo = serializers.ImageField(write_only=True)

    def validate_photo(self, uploaded):
        # ImageField 는 Pillow 로 열어보긴 하지만 머리말만 본다. 그리고
        # 여기서 걸러야 큰 파일을 바이트로 읽어 들이기 전에 막힌다.
        if uploaded.size > AVATAR_PHOTO_MAX_BYTES:
            mb = AVATAR_PHOTO_MAX_BYTES // (1024 * 1024)
            raise serializers.ValidationError(f"사진은 {mb}MB 까지 올릴 수 있습니다.")
        return uploaded

    def save(self, **kwargs) -> User:
        """줄여서 저장하고, 보여줄 것을 사진으로 돌린다.

        avatar 를 함께 바꾸는 이유: 사진만 넣고 avatar 를 안 건드리면,
        아바타를 골라둔 사람은 사진을 올려도 화면이 그대로다. 무엇이
        잘못됐는지 알 수 없다.
        """
        user: User = self.context["user"]
        uploaded = self.validated_data["photo"]

        try:
            user.avatar_photo = shrink_avatar_photo(uploaded.read())
        except AvatarPhotoError as exc:
            raise serializers.ValidationError({"photo": [str(exc)]}) from exc

        # 주소 값을 새로 만든다. 그대로 두면 옛 주소를 아는 사람이 바뀐
        # 사진도 계속 본다. 브라우저 캐시가 깨지는 것도 이 값 덕이다.
        user.avatar_photo_key = uuid.uuid4()
        user.avatar_photo_at = timezone.now()
        user.avatar = AVATAR_PHOTO
        user.save(
            update_fields=[
                "avatar_photo",
                "avatar_photo_key",
                "avatar_photo_at",
                "avatar",
            ]
        )
        return user
