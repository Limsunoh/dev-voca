"""일상 영어 표현을 넣는다. 소리내어 읽기 연습용이다.

사용:
    python manage.py seed_phrases          # 없는 것만 추가
    python manage.py seed_phrases --reset  # 같은 text 가 있으면 내용을 갱신

**데이터를 이 파일에 박아 둔다.** 관리 명령으로 부은 데이터는 입력 파일을
레포에 남겨야 한다 - 2026-09-06 에 발음 946건을 세션 임시 디렉터리에서
붓고 파일을 안 남겨서, 컴퓨터를 옮길 때 통째로 사라진 적이 있다. 그때
아무 신호도 없었다(스키마·화면·테스트 전부 정상으로 보였다).

## 왜 낱말이 아니라 표현인가

`restroom` 을 낱개로 외우는 것은 단어장이 이미 하는 일이다. 일상 영어에서
정작 막히는 것은 **"화장실이 어디예요" 를 통째로 말하는 것**이다. 그래서
text 에 여러 낱말이 들어온다.

채점도 그래서 낱말 단위다(talk.grade_one 참고). 통째로 비교하면 낱말이
빠져도 통과한다.

## 표기 규칙 - 어기면 화면이 낱말 강조를 포기한다

화면이 `wrong_at` 으로 받은 자리를 강조하려면 셋의 낱말 수가 같아야 한다.

    text           where is the restroom        4
    pronunciation  /wɛr ɪz ðə ˈrɛstruːm/        4   (바깥 슬래시 안쪽)
    reading        웨어r 이z 더 레스트룸         4

    - pronunciation 은 **전체를 슬래시로 한 번만** 감싼다. 낱말마다
      두르지 않는다(/wɛr/ /ɪz/ 는 기호가 글자만큼 많아 읽기 나쁘다).
      개발 용어 361개가 전부 이 모양이라 두 갈래가 같아진다.
    - reading 의 강세 `**` 는 **낱말 안에서 닫는다**(`**웨어r**`). 공백을
      걸치면(`**쏘r s**`) 공백으로 세는 낱말 수가 어긋난다 - 개발 용어의
      `source map` 이 실제로 그렇다.
    - 약어·숫자·기호를 넣지 않는다. 소리로 채점할 수 없다(talk.is_speakable).
      "OK" 나 "24/7" 을 넣으면 그 필터에 걸려 출제에서 조용히 빠진다.
    - **축약형은 넣어도 된다**("what's up"·"I don't understand"). normalize
      가 아포스트로피를 없애 한 낱말로 다루므로 낱말 수가 안 어긋나고,
      인식기가 아포스트로피를 빼고 적어도(whats) 자리까지 맞는다.

## 축약형을 쓰는 이유

**실제 대화에서 축약형이 기본이다.** "I do not understand" 를 소리내어
말하는 사람은 없고, 회의에서 듣는 것은 "I don't understand" 다. 풀어 쓴
것을 연습하면 정작 필요한 순간에 못 알아듣는다.

다만 **전부 축약하지는 않았다.** "I am lost" 는 풀어 뒀다 - 축약형이
어려운 사람도 있어서 두 형태를 다 만나는 편이 낫다.

## is_reviewed=True 로 넣는 근거

사람이 손으로 쓴 것이고 AI 생성물이 아니다. seed_words 와 같은 기준인데,
여기서 그것이 무엇이었는지 적어둔다.

    형식  : tests_phrases.py 가 전 항목에 기계적으로 건다 - 낱말 수 일치,
            슬래시 위치, 강세가 낱말 안에서 닫히는지, 약어·숫자 혼입.
    내용  : 60개를 상황별로 나눠 읽고, 실제로 그 상황에서 쓰는 말인지와
            발음 표기가 맞는지를 판정했다.

**검수 없이 붓는 통로로 쓰지 말 것.** 런타임에 외부에서 들어오는 데이터는
사람이 만들었더라도 항상 is_reviewed=False 여야 한다.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.vocab.models import DailyPhrase, PhraseScene

E = DailyPhrase.Difficulty.EASY
N = DailyPhrase.Difficulty.NORMAL
H = DailyPhrase.Difficulty.HARD

GREET = PhraseScene.GREETING
SHOP = PhraseScene.SHOPPING
ASK = PhraseScene.ASKING
TROUBLE = PhraseScene.TROUBLE
TALK = PhraseScene.SMALLTALK

# (표현, IPA, 한글발음, 뜻, 상황, 난이도)
#
# 난이도는 낱말 수가 아니라 **발음이 어려운 정도**로 준다. "comfortable" 은
# 한 낱말인데 영어가 약한 사람이 가장 많이 틀리는 발음이고, "thank you" 는
# 세 낱말이어도 누구나 안다.
PHRASES: list[tuple[str, str, str, str, str, int]] = [
    # 인사·소개
    ("thank you", "/θæŋk ju/", "**th앵**k 유", "고맙습니다", GREET, E),
    ("good morning", "/ɡʊd ˈmɔrnɪŋ/", "굿 **모r**닝", "좋은 아침입니다", GREET, E),
    ("nice to meet you", "/naɪs tə mit ju/", "**나**이s 투 밑 유", "만나서 반갑습니다", GREET, E),
    ("see you later", "/si ju ˈleɪtər/", "씨 유 **레**이터r", "나중에 봐요", GREET, E),
    ("take care", "/teɪk kɛr/", "테익 **케**어r", "잘 지내요", GREET, E),
    ("have a nice day", "/hæv ə naɪs deɪ/", "해v 어 **나**이s 데이", "좋은 하루 보내세요", GREET, E),
    ("how are you", "/haʊ ɑr ju/", "**하**우 아r 유", "어떻게 지내세요", GREET, E),
    ("my name is", "/maɪ neɪm ɪz/", "마이 **네**임 이z", "제 이름은", GREET, E),
    ("excuse me", "/ɪkˈskjuz mi/", "익**스큐**z 미", "잠시만요", GREET, E),
    ("no problem", "/noʊ ˈprɑbləm/", "노우 **프라**블럼", "괜찮습니다", GREET, E),
    # 쇼핑·주문
    ("how much is it", "/haʊ mʌtʃ ɪz ɪt/", "하우 **머**치 이z 잍", "얼마예요", SHOP, E),
    ("I would like to order", "/aɪ wʊd laɪk tə ˈɔrdər/", "아이 우d 라익 투 **오r**더r", "주문할게요", SHOP, N),
    ("can I get a refill", "/kæn aɪ ɡɛt ə ˈrifɪl/", "캔 아이 겥 어 **리**f일", "리필 해주세요", SHOP, N),
    ("for here or to go", "/fɔr hir ɔr tə ɡoʊ/", "f오r **히**어r 오r 투 고우", "먹고 가세요 아니면 가져가세요", SHOP, N),
    ("do you take card", "/du ju teɪk kɑrd/", "두 유 테익 **카**rd", "카드 받으세요", SHOP, E),
    ("just looking", "/dʒʌst ˈlʊkɪŋ/", "저s트 **루**킹", "그냥 보는 거예요", SHOP, E),
    ("can I try this on", "/kæn aɪ traɪ ðɪs ɔn/", "캔 아이 **트**라이 디s 온", "이거 입어봐도 되나요", SHOP, N),
    ("receipt please", "/rɪˈsit pliz/", "리**씨**t 플리z", "영수증 주세요", SHOP, N),
    ("one more please", "/wʌn mɔr pliz/", "원 **모**r 플리z", "하나 더 주세요", SHOP, E),
    ("check please", "/tʃɛk pliz/", "**첵** 플리z", "계산서 주세요", SHOP, E),
    # 묻기·길찾기
    ("where is the restroom", "/wɛr ɪz ðə ˈrɛstrum/", "웨어r 이z 더 **레**스트룸", "화장실이 어디예요", ASK, N),
    ("how do I get there", "/haʊ du aɪ ɡɛt ðɛr/", "하우 두 아이 겥 **데**어r", "거기 어떻게 가요", ASK, N),
    ("is it far from here", "/ɪz ɪt fɑr frʌm hir/", "이z 잍 **f아**r f럼 히어r", "여기서 먼가요", ASK, N),
    ("which way is it", "/wɪtʃ weɪ ɪz ɪt/", "**위**치 웨이 이z 잍", "어느 쪽이에요", ASK, N),
    ("how long does it take", "/haʊ lɔŋ dʌz ɪt teɪk/", "하우 **롱** 더z 잍 테익", "얼마나 걸려요", ASK, N),
    ("over there", "/ˈoʊvər ðɛr/", "**오**우버r 데어r", "저쪽이요", ASK, E),
    ("right now", "/raɪt naʊ/", "**라**잍 나우", "지금 바로요", ASK, E),
    ("what time is it", "/wʌt taɪm ɪz ɪt/", "**왓** 타임 이z 잍", "몇 시예요", ASK, E),
    ("is this seat taken", "/ɪz ðɪs sit ˈteɪkən/", "이z 디s 씯 **테**이컨", "이 자리 비었나요", ASK, N),
    ("can you help me", "/kæn ju hɛlp mi/", "캔 유 **헬**p 미", "도와주실 수 있나요", ASK, E),
    # 곤란할 때
    ("could you say that again", "/kʊd ju seɪ ðæt əˈɡɛn/", "쿠d 유 쎄이 댙 어**겐**", "다시 말씀해 주세요", TROUBLE, H),
    ("I don't understand", "/aɪ doʊnt ˌʌndərˈstænd/", "아이 도운t 언더r**스탠**d", "이해가 안 돼요", TROUBLE, N),
    ("speak slowly please", "/spik ˈsloʊli pliz/", "스핔 **슬**로울리 플리z", "천천히 말씀해 주세요", TROUBLE, N),
    ("I am lost", "/aɪ æm lɔst/", "아이 앰 **로**s트", "길을 잃었어요", TROUBLE, E),
    ("never mind", "/ˈnɛvər maɪnd/", "**네**버r 마인d", "괜찮아요 신경 쓰지 마세요", TROUBLE, E),
    ("just a moment", "/dʒʌst ə ˈmoʊmənt/", "저s트 어 **모**우먼t", "잠시만요", TROUBLE, N),
    ("I'm not sure", "/aɪm nɑt ʃʊr/", "아임 낱 **슈**어r", "잘 모르겠어요", TROUBLE, E),
    ("what does it mean", "/wʌt dʌz ɪt min/", "왓 더z 잍 **민**", "무슨 뜻이에요", TROUBLE, E),
    ("something is wrong", "/ˈsʌmθɪŋ ɪz rɔŋ/", "**썸**th잉 이z 롱", "뭔가 잘못됐어요", TROUBLE, N),
    ("I need help", "/aɪ nid hɛlp/", "아이 **니**d 헬p", "도움이 필요해요", TROUBLE, E),
    # 가벼운 대화
    ("how was your weekend", "/haʊ wʌz jʊr ˈwikɛnd/", "하우 워z 유어r **위**켄d", "주말 어땠어요", TALK, N),
    ("what do you do", "/wʌt du ju du/", "**왓** 두 유 두", "무슨 일 하세요", TALK, E),
    ("sounds good", "/saʊndz ɡʊd/", "**사**운dz 굿", "좋은 것 같아요", TALK, E),
    ("me too", "/mi tu/", "미 **투**", "저도요", TALK, E),
    ("that's too bad", "/ðæts tu bæd/", "댙s 투 **밷**", "그건 안타깝네요", TALK, E),
    ("I agree", "/aɪ əˈɡri/", "아이 어**그리**", "동의해요", TALK, E),
    ("what about you", "/wʌt əˈbaʊt ju/", "왓 어**바**웉 유", "당신은 어때요", TALK, N),
    ("not really", "/nɑt ˈrɪli/", "낱 **리**얼리", "그렇지는 않아요", TALK, E),
    ("maybe next time", "/ˈmeɪbi nɛkst taɪm/", "**메**이비 넥s트 타임", "다음에요", TALK, N),
    ("I'll let you know", "/aɪl lɛt ju noʊ/", "아일 렡 유 **노**우", "알려드릴게요", TALK, N),
    # 발음이 어려운 낱말 - 한 낱말이지만 가장 많이 틀리는 것들
    ("comfortable", "/ˈkʌmftərbəl/", "**컴**f터r벌", "편안한", TALK, H),
    ("vegetable", "/ˈvɛdʒtəbəl/", "**v에**지터벌", "채소", SHOP, H),
    ("refrigerator", "/rɪˈfrɪdʒəreɪtər/", "리**f리**저레이터r", "냉장고", SHOP, H),
    ("appointment", "/əˈpɔɪntmənt/", "어**포**인t먼t", "약속 예약", ASK, N),
    ("pharmacy", "/ˈfɑrməsi/", "**f아**r머씨", "약국", ASK, N),
    ("umbrella", "/ʌmˈbrɛlə/", "엄**브렐**러", "우산", SHOP, N),
    ("neighborhood", "/ˈneɪbərhʊd/", "**네**이버r훗", "동네", TALK, N),
    ("temperature", "/ˈtɛmprətʃər/", "**템**프러처r", "온도", TALK, H),
    ("jewelry", "/ˈdʒuəlri/", "**주**얼리", "장신구", SHOP, H),
    ("laundry", "/ˈlɔndri/", "**론**드리", "빨래", TALK, N),
]


# 이 명령이 넣은 행임을 나타내는 표시.
#
# `--reset` 이 소스에서 사라진 행을 지울 때, **지워도 되는 것과 사람이
# Admin 에서 넣은 것을 가르는 유일한 단서**다. 이 값을 바꾸면 그 전에
# 부어둔 행이 "남의 것" 으로 보여 지워지지 않는다.
#
# **사람이 손으로 칠 일이 없는 값이어야 한다.** 처음에는 다른 씨드들처럼
# "직접 작성" 을 썼는데, 그것은 사람이 표현을 손으로 넣으면서 출처 칸에
# 그대로 적을 법한 말이다(출처는 자유 입력이고 Admin 폼에 열려 있다).
# 그러면 그 사람의 행이 다음 --reset 에 조용히 지워진다.
#
# 다른 씨드 명령들은 이 값을 표시로만 쓰고 지우지 않으므로 겹쳐도 무해하다.
# 지우는 것은 이 명령뿐이라 여기만 기계 이름을 쓴다.
SEED_SOURCE = "seed_phrases"


class Command(BaseCommand):
    help = "일상 영어 표현을 넣는다(소리내어 읽기 연습용)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                "소스와 똑같이 맞춘다. 내용을 갱신하고, 소스에서 사라진 "
                "표현은 지운다(이 명령이 넣은 것만)."
            ),
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        reset: bool = options["reset"]
        added = skipped = updated = 0

        for text, pronunciation, reading, meaning, scene, difficulty in PHRASES:
            fields = {
                "pronunciation": pronunciation,
                "reading": reading,
                "meaning": meaning,
                "scene": scene,
                "difficulty": difficulty,
                # 손으로 쓴 것이라 검수를 거친 상태로 넣는다. 근거는 이
                # 파일 머리에 적었다.
                "is_reviewed": True,
                "source": SEED_SOURCE,
            }

            existing = DailyPhrase.objects.filter(text=text).first()
            if existing is None:
                DailyPhrase.objects.create(text=text, **fields)
                added += 1
            elif reset:
                for name, value in fields.items():
                    setattr(existing, name, value)
                existing.save(update_fields=[*fields])
                updated += 1
            else:
                skipped += 1

        removed = 0
        if reset:
            # **소스에서 사라진 표현을 지운다.**
            #
            # seed_words·seed_sentences 는 이것을 안 한다. 그래서
            # 2026-08-10 에 문장 하나를 소스에서 지웠는데 DB 에 남아
            # 사용자에게 계속 노출됐고, 이번에도 축약형으로 바꾼 넷의
            # 옛 형태가 남아 **한 뜻에 두 표현이 동시에 출제됐다.**
            #
            # 그때 결론이 "지우는 변경을 했으면 배포 후 별도로 확인한다"
            # 였는데 부족했다 - 사람이 기억해야 하는 절차는 잊힌다.
            #
            # 이 표에서만 지우는 이유: 우리가 통째로 소유하는 데이터다.
            # 단어·문장은 Admin 에서 사람이 손댄 것이 섞여 있을 수 있어
            # 함부로 지우면 안 된다.
            #
            # **source 로 좁힌다.** Admin 에서 사람이 추가한 표현은 이
            # 값이 다르므로 남는다 - 등록 화면이 열려 있어서(DailyPhraseAdmin)
            # 실제로 생길 수 있는 행이고, 그것까지 지우면 남의 작업을
            # 말없이 없애는 것이 된다.
            stale = DailyPhrase.objects.filter(source=SEED_SOURCE).exclude(
                text__in=[row[0] for row in PHRASES]
            )
            removed = stale.count()
            stale.delete()

        message = f"추가: {added}개 / 갱신: {updated}개 / 이미 있어 건너뜀: {skipped}개"
        if reset:
            message += f" / 소스에서 사라져 지움: {removed}개"
        self.stdout.write(message)
