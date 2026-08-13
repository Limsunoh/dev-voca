"""계정 입출력 규칙.

비밀번호는 어느 응답에도 담기지 않는다(write_only). 그리고 저장 경로가
set_password 를 거치도록 강제한다 - ModelSerializer 의 기본 create 는
평문을 그대로 필드에 넣어 저장하므로, 이 클래스를 거치지 않으면 비밀번호가
해시 없이 DB 에 들어간다.
"""

from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import serializers

from .models import DISPLAY_NAME_MAX, name_taken, normalize_display_name

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
            "is_staff",
        ]
        # 이메일은 로그인 키라 API 로 바꾸지 않는다. 바꾸려면 본인 확인이
        # 먼저 필요한데 그 절차가 아직 없다.
        #
        # google_picture 는 읽기만 연다. 화면이 "구글 사진" 선택지를
        # 그리려면 주소가 필요한데, 쓰기까지 열면 아무 주소나 넣어 우리
        # 화면을 여는 것만으로 그 서버에 요청이 나가는 통로가 된다.
        #
        # avatar_display 로 대신할 수 없다. 그건 "지금 무엇을 그릴지" 라서
        # 아바타를 한 번 고르면 사진이 남아 있어도 preset 으로 나온다.
        # 그것만 보면 구글 사진으로 되돌아갈 방법이 화면에서 사라진다.
        read_only_fields = ["id", "email", "is_staff", "google_picture"]

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
