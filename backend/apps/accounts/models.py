"""사용자 계정.

로그인 키를 username 이 아니라 email 로 둔다. 구글 로그인이 주는 것이
이메일이라, username 을 키로 쓰면 "구글에서 온 사람의 username 을 무엇으로
만들 것인가" 라는 문제가 생긴다 - 이메일 앞부분을 잘라 쓰면 서로 다른
도메인의 같은 아이디가 부딪히고, 뒤에 숫자를 붙이면 그 숫자가 영영 남는다.

이메일 하나를 키로 두면 이메일 가입과 구글 로그인이 같은 계정으로 모인다.
같은 사람이 두 방법을 번갈아 써도 계정이 갈라지지 않는다.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """이메일로 계정을 만드는 매니저.

    기본 UserManager 는 username 을 필수로 받는다. 로그인 키를 바꿨으므로
    생성 경로도 함께 바꿔야 createsuperuser 와 테스트가 동작한다.
    """

    use_in_migrations = True

    def get_by_natural_key(self, email: str):
        """로그인할 때 계정을 찾는 경로.

        기본 구현은 정확히 일치하는 이메일만 찾는다. 저장할 때는 소문자로
        내리므로 보통은 맞아떨어지지만, 옛 데이터나 다른 경로로 대문자가
        섞여 들어간 행이 하나라도 있으면 그 계정은 영영 로그인할 수 없다.
        읽기와 쓰기가 같은 규칙을 보도록 여기서 맞춘다.
        """
        return self.get(**{f"{self.model.USERNAME_FIELD}__iexact": email})

    def _create_user(self, email: str, password: str | None, **extra) -> User:
        if not email:
            raise ValueError("이메일은 필수입니다.")

        # 통째로 소문자로 내린다. normalize_email 은 도메인만 낮추는데,
        # 그러면 Foo@x.com 으로 가입한 사람이 foo@x.com 으로 로그인할 때
        # 실패한다 - 로그인은 정확히 일치하는 이메일을 찾기 때문이다.
        # 본인 계정에 못 들어가면서 이유도 알 수 없는 상태가 된다.
        #
        # 규격상 @ 앞은 대소문자를 구분할 수 있지만 실제로 그렇게 쓰는
        # 메일 서버는 사실상 없다. 구글 로그인이 주는 이메일과도 여기서
        # 맞춰져야 계정이 갈라지지 않는다.
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra) -> User:
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra) -> User:
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)

        # 여기서 막지 않으면 is_staff=False 인 "슈퍼유저" 가 만들어져
        # Admin 에 로그인하지 못하는 상태가 된다.
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("슈퍼유저는 is_staff 와 is_superuser 가 True 여야 합니다.")

        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """이메일로 로그인하는 사용자.

    AbstractUser 를 상속해 권한·그룹·is_staff 같은 Django 기본 기능을 그대로
    쓴다. 검수 권한 판정(apps.vocab.views.can_review)이 is_staff 와
    is_active 를 보므로 그 구조를 유지해야 한다.
    """

    # username 을 없애지 않고 비운다. Django 내부와 서드파티가 이 필드를
    # 참조하는 곳이 있어, 지우면 예상 못 한 곳에서 터진다.
    username = None

    email = models.EmailField("이메일", unique=True)

    # 화면에 보여줄 이름. 구글 로그인은 이름을 함께 주고, 이메일 가입은
    # 비워둔 채 시작해 나중에 채울 수 있게 한다.
    display_name = models.CharField("표시 이름", max_length=50, blank=True)

    # 가입일은 AbstractUser 의 date_joined 를 그대로 쓴다. 따로 만들면
    # 컬럼이 둘이 되고, Admin 은 이쪽을 Django 기본 기능은 저쪽을 보게 된다.

    USERNAME_FIELD = "email"
    # createsuperuser 가 추가로 물어볼 항목. 이메일은 USERNAME_FIELD 라
    # 자동으로 묻고, 여기 또 넣으면 두 번 묻는다.
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        verbose_name = "사용자"
        verbose_name_plural = "사용자"

    def save(self, *args, **kwargs) -> None:
        """이메일을 항상 소문자로 저장한다.

        매니저가 아니라 여기서 하는 이유: Admin 의 계정 추가 폼은
        create_user 를 거치지 않고 곧바로 save() 를 부른다. 매니저에만
        두면 그 경로로 대문자가 섞인 행이 들어오고, 그러면 같은 주소가
        두 행으로 갈려 로그인이 MultipleObjectsReturned 로 터진다.
        """
        self.email = self.email.lower()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.email

    @property
    def name_for_display(self) -> str:
        """화면에 쓸 이름. 표시 이름이 없으면 이메일 앞부분을 쓴다."""
        return self.display_name or self.email.split("@")[0]
