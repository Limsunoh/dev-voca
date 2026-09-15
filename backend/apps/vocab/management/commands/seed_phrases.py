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

**전부 축약한다. 풀어 쓴 형태를 남기지 않는다.** 처음에는 "I am lost" 를
일부러 풀어 뒀다 - 축약형이 어려운 사람도 두 형태를 다 만나라고. 그런데
채점이 비대칭이다. 화면이 풀어 쓴 형태를 보여주면 사람은 대개 줄여
읽고(I'm lost), 그러면 낱말 수가 어긋나 **제대로 읽었는데 통째로 오답이
되고 틀린 자리 표시도 안 나온다**(talk.grade_one). 두 형태를 만나게 하려던
것이 "맞게 읽어도 틀린다" 가 됐다. tests_talk 의 SeedStaysContractedTest 가
풀어 쓴 형태가 다시 들어오는 것을 막는다.

## is_reviewed=True 로 넣는 근거

이 표는 검수 게이트를 스스로 켜고 들어간다. DailyPhrase 에는 Word 의
reading_reviewed 같은 칸 단위 게이트가 없어서(visible_reading 이 없는 칸을
검수된 것으로 읽는다) **이 데이터와 사용자 사이에 서 있는 것은 이 문단
하나뿐이다.** 화면은 이 표기를 본보기로 제시하며 따라 읽으라고 시킨다.

그래서 무엇을 확인했는지 범위째 적는다.

    형식(207개 전부)
        tests_phrases.py 가 기계적으로 건다 - 낱말 수 일치, 슬래시 위치,
        강세가 낱말 안에서 닫히는지, 약어·숫자 혼입, 출제 필터 통과,
        뜻 중복, 같은 낱말의 한글 표기 일관성.

    내용(처음 60개)
        상황별로 나눠 읽고, 실제로 그 상황에서 쓰는 말인지와 발음 표기가
        맞는지를 판정했다.

    내용(더한 147개, 2026-09-12)
        쓴 것도 1차로 읽은 것도 Claude 다. 사람이 읽은 것은 아니다.
        독립된 검토를 한 번 더 거쳐 다섯 건을 고쳤다 - either is fine 의
        뜻이 "둘 다" 로 잘못된 것, what's up 이 질문인데 대답처럼 적힌 것,
        같은 뜻이 글자까지 겹친 다섯 쌍, 상황 분류가 틀린 하나, 그리고
        **제대로 읽어도 틀리는 여섯 개**(where is the fitting room 처럼
        축약을 안 한 형태는 사람이 where's 로 읽으면 낱말 수가 어긋나
        통째로 오답이 되고 틀린 자리 표시도 안 된다).

        그 검토에서 나온 축 둘을 위 형식 검사에 더했다(뜻 중복, 표기
        일관성). 눈으로만 걸리던 것을 기계가 잡게 한 것이다.

        그 뒤 동적 테스트가 풀어 쓴 채 남은 넷(where is the restroom,
        I would like to order, that would be great, I am lost)을 더 찾아
        축약했고, 재검토가 how's everything 의 뜻이 대답처럼 적힌 것을
        찾아 고쳤다.

        **2026-09-15 사용자가 "사람이 안 읽었다" 는 사실을 안내받고 검수됨
        으로 넣기로 정했다.** 이 True 의 근거는 그 결정이다. 형식 검사와
        Claude 의 검토만으로 켠 것이 아니다.

**다음에 크게 늘릴 때도 이 문단을 같이 고쳐야 한다.** 숫자만 바꾸지 말
것 - 여기는 근거를 적는 자리이고, 근거 없는 숫자는 게이트를 여는 데 쓸
수 없다. tests_phrases 의 개수 테스트가 그 질문을 강제한다.

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
# 두 낱말이어도 누구나 안다.
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
    ("excuse me", "/ɪkˈskjuz mi/", "익**스큐**z 미", "실례합니다", GREET, E),
    ("no problem", "/noʊ ˈprɑbləm/", "노우 **프라**블럼", "괜찮습니다", GREET, E),
    # 쇼핑·주문
    ("how much is it", "/haʊ mʌtʃ ɪz ɪt/", "하우 **머**치 이z 잍", "얼마예요", SHOP, E),
    ("I'd like to order", "/aɪd laɪk tə ˈɔrdər/", "아이d 라익 투 **오r**더r", "주문할게요", SHOP, N),
    ("can I get a refill", "/kæn aɪ ɡɛt ə ˈrifɪl/", "캔 아이 겥 어 **리**f일", "리필 해주세요", SHOP, N),
    ("for here or to go", "/fɔr hir ɔr tə ɡoʊ/", "f오r **히**어r 오r 투 고우", "먹고 가세요 아니면 가져가세요", SHOP, N),
    ("do you take card", "/du ju teɪk kɑrd/", "두 유 테익 **카**rd", "카드 받으세요", SHOP, E),
    ("just looking", "/dʒʌst ˈlʊkɪŋ/", "저s트 **루**킹", "그냥 보는 거예요", SHOP, E),
    ("can I try this on", "/kæn aɪ traɪ ðɪs ɔn/", "캔 아이 **트**라이 디s 온", "이거 입어봐도 되나요", SHOP, N),
    ("receipt please", "/rɪˈsit pliz/", "리**씨**t 플리z", "영수증 주세요", SHOP, N),
    ("one more please", "/wʌn mɔr pliz/", "원 **모**r 플리z", "하나 더 주세요", SHOP, E),
    ("check please", "/tʃɛk pliz/", "**첵** 플리z", "계산서 주세요", SHOP, E),
    # 묻기·길찾기
    ("where's the restroom", "/wɛrz ðə ˈrɛstrum/", "웨어rz 더 **레**스트룸", "화장실이 어디예요", ASK, N),
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
    ("I'm lost", "/aɪm lɔst/", "아임 **로**s트", "길을 잃었어요", TROUBLE, E),
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

    # --- 인사·소개 (추가) ---
    ("good afternoon", "/ɡʊd ˌæftərˈnun/", "굿 애f터r**눈**", "좋은 오후입니다", GREET, E),
    ("good evening", "/ɡʊd ˈivnɪŋ/", "굿 **이**v닝", "좋은 저녁입니다", GREET, E),
    ("how have you been", "/haʊ hæv ju bɪn/", "하우 해v 유 **빈**", "그동안 어떻게 지냈어요", GREET, N),
    ("long time no see", "/lɔŋ taɪm noʊ si/", "롱 타임 노우 **씨**", "오랜만이에요", GREET, N),
    ("nice to see you again", "/naɪs tə si ju əˈɡɛn/", "나이s 투 씨 유 어**겐**", "다시 만나 반가워요", GREET, N),
    ("how's it going", "/haʊz ɪt ˈɡoʊɪŋ/", "하우z 잍 **고**우잉", "어떻게 지내요", GREET, N),
    ("what's up", "/wʌts ʌp/", "왓s **업**", "잘 지내? 하고 묻는 인사", GREET, E),
    ("see you tomorrow", "/si ju təˈmɑroʊ/", "씨 유 터**마**로우", "내일 봐요", GREET, E),
    ("have a good one", "/hæv ə ɡʊd wʌn/", "해v 어 굿 **원**", "좋은 하루 보내요", GREET, N),
    ("talk to you later", "/tɔk tə ju ˈleɪtər/", "톡 투 유 **레**이터r", "나중에 얘기해요", GREET, N),
    ("thanks for coming", "/θæŋks fɔr ˈkʌmɪŋ/", "th앵ks f오r **커**밍", "와줘서 고마워요", GREET, N),
    ("you're welcome", "/jʊr ˈwɛlkəm/", "유어r **웰**컴", "천만에요", GREET, E),
    ("my pleasure", "/maɪ ˈplɛʒər/", "마이 **플레**저r", "제가 더 기쁩니다", GREET, N),
    ("how's everything", "/haʊz ˈɛvriθɪŋ/", "하우z **에**v리th잉", "요즘 다 괜찮아요? 하고 묻는 인사", GREET, N),
    ("this is my colleague", "/ðɪs ɪz maɪ ˈkɑliɡ/", "디s 이z 마이 **칼**리그", "제 동료입니다", GREET, N),
    ("glad to hear that", "/ɡlæd tə hir ðæt/", "글랟 투 히어r **댙**", "그렇다니 다행이에요", GREET, N),
    ("I appreciate it", "/aɪ əˈpriʃieɪt ɪt/", "아이 어**프리**시에잍 잍", "감사합니다", GREET, H),
    ("congratulations", "/kənˌɡrætʃəˈleɪʃənz/", "컨그래추**레**이션z", "축하합니다", GREET, H),
    ("take it easy", "/teɪk ɪt ˈizi/", "테익 잍 **이**지", "편하게 지내요", GREET, E),
    ("good luck", "/ɡʊd lʌk/", "굿 **럭**", "행운을 빌어요", GREET, E),
    ("welcome back", "/ˈwɛlkəm bæk/", "**웰**컴 백", "돌아온 걸 환영해요", GREET, E),

    # --- 쇼핑·주문 (추가) ---
    ("do you have this in blue", "/du ju hæv ðɪs ɪn blu/", "두 유 해v 디s 인 **블루**", "이거 파란색 있나요", SHOP, N),
    ("what size is this", "/wʌt saɪz ɪz ðɪs/", "왓 **사**이z 이z 디s", "이거 무슨 사이즈예요", SHOP, N),
    ("do you have a smaller size", "/du ju hæv ə ˈsmɔlər saɪz/", "두 유 해v 어 **스몰**러r 사이z", "더 작은 사이즈 있나요", SHOP, N),
    ("where's the fitting room", "/wɛrz ðə ˈfɪtɪŋ rum/", "웨어rz 더 **f이**팅 룸", "탈의실이 어디예요", SHOP, N),
    ("I'm just browsing", "/aɪm dʒʌst ˈbraʊzɪŋ/", "아임 저s트 **브라**우징", "그냥 구경 중이에요", SHOP, N),
    ("can I pay by card", "/kæn aɪ peɪ baɪ kɑrd/", "캔 아이 페이 바이 **카**rd", "카드로 결제해도 되나요", SHOP, N),
    ("do you accept cash", "/du ju əkˈsɛpt kæʃ/", "두 유 억**셉**t 캐시", "현금 받으세요", SHOP, N),
    ("can I get a discount", "/kæn aɪ ɡɛt ə ˈdɪskaʊnt/", "캔 아이 겥 어 **디**s카운t", "할인 되나요", SHOP, N),
    ("is this on sale", "/ɪz ðɪs ɔn seɪl/", "이z 디s 온 **쎄**일", "이거 세일 중이에요", SHOP, E),
    ("I'd like to return this", "/aɪd laɪk tə rɪˈtɜrn ðɪs/", "아이d 라익 투 리**턴** 디s", "이거 반품하고 싶어요", SHOP, H),
    ("can I exchange this", "/kæn aɪ ɪksˈtʃeɪndʒ ðɪs/", "캔 아이 익s**체**인지 디s", "교환 되나요", SHOP, N),
    ("do you have a bag", "/du ju hæv ə bæɡ/", "두 유 해v 어 **백**", "봉투 있나요", SHOP, E),
    ("I'll take it", "/aɪl teɪk ɪt/", "아일 **테**익 잍", "이걸로 할게요", SHOP, E),
    ("let me think about it", "/lɛt mi θɪŋk əˈbaʊt ɪt/", "렡 미 th잉k 어**바**웉 잍", "좀 생각해 볼게요", SHOP, N),
    ("can I see the menu", "/kæn aɪ si ðə ˈmɛnju/", "캔 아이 씨 더 **메**뉴", "메뉴 좀 볼게요", SHOP, E),
    ("what do you recommend", "/wʌt du ju ˌrɛkəˈmɛnd/", "왓 두 유 레커**멘**d", "뭘 추천하세요", SHOP, N),
    ("I'm allergic to nuts", "/aɪm əˈlɜrdʒɪk tə nʌts/", "아임 얼**러**r직 투 넡s", "견과류 알레르기가 있어요", SHOP, H),
    ("no onions please", "/noʊ ˈʌnjənz pliz/", "노우 **어**니언z 플리z", "양파 빼주세요", SHOP, N),
    ("can I have some water", "/kæn aɪ hæv sʌm ˈwɔtər/", "캔 아이 해v 썸 **워**터r", "물 좀 주세요", SHOP, E),
    ("it was delicious", "/ɪt wʌz dɪˈlɪʃəs/", "잍 워z 딜**리**셔s", "맛있었어요", SHOP, N),
    ("can we split the bill", "/kæn wi splɪt ðə bɪl/", "캔 위 스플맅 더 **빌**", "나눠서 계산할 수 있나요", SHOP, H),
    ("keep the change", "/kip ðə tʃeɪndʒ/", "킾 더 **체**인지", "거스름돈은 됐어요", SHOP, E),
    ("can I have the receipt", "/kæn aɪ hæv ðə rɪˈsit/", "캔 아이 해v 더 리**씨**t", "영수증 받을 수 있을까요", SHOP, N),
    ("is delivery available", "/ɪz dɪˈlɪvəri əˈveɪləbəl/", "이z 딜**리**버리 어v에일러벌", "배달 되나요", SHOP, H),
    ("how long is the wait", "/haʊ lɔŋ ɪz ðə weɪt/", "하우 **롱** 이z 더 웨잍", "얼마나 기다려야 해요", SHOP, N),
    ("table for two please", "/ˈteɪbəl fɔr tu pliz/", "**테**이벌 f오r 투 플리z", "두 명 자리 주세요", SHOP, N),
    ("I have a reservation", "/aɪ hæv ə ˌrɛzərˈveɪʃən/", "아이 해v 어 레저r**v에**이션", "예약했어요", SHOP, H),
    ("can I get this to go", "/kæn aɪ ɡɛt ðɪs tə ɡoʊ/", "캔 아이 겥 디s 투 **고**우", "이거 포장해 주세요", SHOP, N),
    ("it's too expensive", "/ɪts tu ɪkˈspɛnsɪv/", "잍s 투 익**스펜**시v", "너무 비싸요", SHOP, N),
    ("do you have this in stock", "/du ju hæv ðɪs ɪn stɑk/", "두 유 해v 디s 인 **스탁**", "이거 재고 있나요", SHOP, N),
    ("where can I pay", "/wɛr kæn aɪ peɪ/", "웨어r 캔 아이 **페**이", "어디서 계산해요", SHOP, E),
    ("that's all thank you", "/ðæts ɔl θæŋk ju/", "댙s 올 **th앵**k 유", "그게 전부예요 감사합니다", SHOP, N),

    # --- 묻기·길찾기 (추가) ---
    ("sorry to bother you", "/ˈsɑri tə ˈbɑðər ju/", "쏘리 투 **바**더r 유", "귀찮게 해서 죄송해요", ASK, N),
    ("could you show me the way", "/kʊd ju ʃoʊ mi ðə weɪ/", "쿠d 유 쇼우 미 더 **웨**이", "길 좀 알려주실 수 있나요", ASK, H),
    ("is there a bank nearby", "/ɪz ðɛr ə bæŋk ˈnɪrbaɪ/", "이z 데어r 어 뱅k **니**어r바이", "근처에 은행 있나요", ASK, N),
    ("how far is it", "/haʊ fɑr ɪz ɪt/", "하우 **f아**r 이z 잍", "얼마나 멀어요", ASK, N),
    ("can I walk there", "/kæn aɪ wɔk ðɛr/", "캔 아이 **워**k 데어r", "걸어갈 수 있나요", ASK, N),
    ("which bus should I take", "/wɪtʃ bʌs ʃʊd aɪ teɪk/", "위치 버s **슈**d 아이 테익", "어느 버스를 타야 해요", ASK, N),
    ("where does this bus go", "/wɛr dʌz ðɪs bʌs ɡoʊ/", "웨어r 더z 디s 버s **고**우", "이 버스 어디로 가요", ASK, N),
    ("does this train stop there", "/dʌz ðɪs treɪn stɑp ðɛr/", "더z 디s 트레인 **스탑** 데어r", "이 기차 거기 서나요", ASK, N),
    ("when is the next one", "/wɛn ɪz ðə nɛkst wʌn/", "웬 이z 더 **넥**s트 원", "다음 건 언제예요", ASK, N),
    ("what time do you open", "/wʌt taɪm du ju ˈoʊpən/", "왓 타임 두 유 **오**우펀", "몇 시에 열어요", ASK, N),
    ("what time do you close", "/wʌt taɪm du ju kloʊz/", "왓 타임 두 유 **클**로우z", "몇 시에 닫아요", ASK, N),
    ("are you open on Sunday", "/ɑr ju ˈoʊpən ɔn ˈsʌndeɪ/", "아r 유 **오**우펀 온 썬데이", "일요일에 여나요", ASK, N),
    ("is there wifi here", "/ɪz ðɛr ˈwaɪfaɪ hir/", "이z 데어r **와**이f아이 히어r", "여기 와이파이 있나요", ASK, N),
    ("what's the password", "/wʌts ðə ˈpæswɜrd/", "왓s 더 **패**s워rd", "비밀번호가 뭐예요", ASK, N),
    ("can I charge my phone", "/kæn aɪ tʃɑrdʒ maɪ foʊn/", "캔 아이 **차**r지 마이 f오운", "휴대폰 충전해도 되나요", ASK, N),
    ("could you take a picture", "/kʊd ju teɪk ə ˈpɪktʃər/", "쿠d 유 테익 어 **픽**처r", "사진 좀 찍어주실래요", ASK, N),
    ("is this the right way", "/ɪz ðɪs ðə raɪt weɪ/", "이z 디s 더 **라**잍 웨이", "이 길이 맞나요", ASK, N),
    ("where can I find it", "/wɛr kæn aɪ faɪnd ɪt/", "웨어r 캔 아이 **f아**인d 잍", "어디서 찾을 수 있어요", ASK, N),
    ("do you know where it is", "/du ju noʊ wɛr ɪt ɪz/", "두 유 노우 **웨**어r 잍 이z", "어디인지 아세요", ASK, N),
    ("may I ask you something", "/meɪ aɪ æsk ju ˈsʌmθɪŋ/", "메이 아이 애s크 유 **썸**th잉", "뭐 좀 여쭤봐도 될까요", ASK, N),
    ("how much does it cost", "/haʊ mʌtʃ dʌz ɪt kɔst/", "하우 머치 더z 잍 **코**s트", "얼마나 드나요", ASK, N),
    ("is it free", "/ɪz ɪt fri/", "이z 잍 **f리**", "무료인가요", ASK, E),
    ("do I need a ticket", "/du aɪ nid ə ˈtɪkɪt/", "두 아이 니d 어 **티**킽", "표가 필요한가요", ASK, N),
    ("where do I sign", "/wɛr du aɪ saɪn/", "웨어r 두 아이 **사**인", "어디에 서명해요", ASK, E),
    ("can I use this", "/kæn aɪ juz ðɪs/", "캔 아이 **유**z 디s", "이거 써도 되나요", ASK, E),
    ("is anyone sitting here", "/ɪz ˈɛniwʌn ˈsɪtɪŋ hir/", "이z **에**니원 씨팅 히어r", "여기 자리 있나요", ASK, N),
    ("could you repeat the address", "/kʊd ju rɪˈpit ðə ˈædrɛs/", "쿠d 유 리**핕** 더 애드레s", "주소 좀 다시 말해주실래요", ASK, H),
    ("how do you spell it", "/haʊ du ju spɛl ɪt/", "하우 두 유 **스펠** 잍", "철자가 어떻게 되나요", ASK, N),
    ("what's this called", "/wʌts ðɪs kɔld/", "왓s 디s **콜**d", "이거 뭐라고 불러요", ASK, N),
    ("where should I go", "/wɛr ʃʊd aɪ ɡoʊ/", "웨어r 슈d 아이 **고**우", "어디로 가야 해요", ASK, E),
    ("is it walking distance", "/ɪz ɪt ˈwɔkɪŋ ˈdɪstəns/", "이z 잍 **워**킹 디s턴s", "걸어갈 만한 거리인가요", ASK, H),
    ("when are you free", "/wɛn ɑr ju fri/", "웬 아r 유 **f리**", "언제 시간 되세요", ASK, N),

    # --- 곤란할 때 (추가) ---
    ("I missed my flight", "/aɪ mɪst maɪ flaɪt/", "아이 미s트 마이 **f라**잍", "비행기를 놓쳤어요", TROUBLE, N),
    ("I lost my wallet", "/aɪ lɔst maɪ ˈwɔlɪt/", "아이 로s트 마이 **월**맅", "지갑을 잃어버렸어요", TROUBLE, N),
    ("my phone is dead", "/maɪ foʊn ɪz dɛd/", "마이 f오운 이z **뎃**", "휴대폰이 꺼졌어요", TROUBLE, N),
    ("it's not working", "/ɪts nɑt ˈwɜrkɪŋ/", "잍s 낱 **워**r킹", "작동이 안 돼요", TROUBLE, N),
    ("can you fix it", "/kæn ju fɪks ɪt/", "캔 유 **f익**s 잍", "고쳐주실 수 있나요", TROUBLE, N),
    ("I need a doctor", "/aɪ nid ə ˈdɑktər/", "아이 니d 어 **닥**터r", "의사가 필요해요", TROUBLE, N),
    ("I don't feel well", "/aɪ doʊnt fil wɛl/", "아이 도운t f일 **웰**", "몸이 안 좋아요", TROUBLE, N),
    ("it hurts here", "/ɪt hɜrts hir/", "잍 **허**r츠 히어r", "여기가 아파요", TROUBLE, N),
    ("call an ambulance", "/kɔl ən ˈæmbjələns/", "콜 언 **앰**뷸런s", "구급차 불러주세요", TROUBLE, H),
    ("I'm in trouble", "/aɪm ɪn ˈtrʌbəl/", "아임 인 **트러**벌", "곤란한 상황이에요", TROUBLE, N),
    ("there's a problem", "/ðɛrz ə ˈprɑbləm/", "데어rz 어 **프라**블럼", "문제가 있어요", TROUBLE, N),
    ("sorry I'm late", "/ˈsɑri aɪm leɪt/", "**쏘**리 아임 레잍", "늦어서 죄송해요", TROUBLE, E),
    ("it was an accident", "/ɪt wʌz ən ˈæksɪdənt/", "잍 워z 언 **액**시던t", "일부러 그런 게 아니에요", TROUBLE, N),
    ("I didn't mean that", "/aɪ ˈdɪdənt min ðæt/", "아이 **디**던t 민 댙", "진심으로 한 말은 아니었어요", TROUBLE, N),
    ("could you speak up", "/kʊd ju spik ʌp/", "쿠d 유 스핔 **업**", "좀 크게 말씀해 주세요", TROUBLE, N),
    ("I can't hear you", "/aɪ kænt hir ju/", "아이 캔t **히**어r 유", "안 들려요", TROUBLE, N),
    ("one more time please", "/wʌn mɔr taɪm pliz/", "원 모r **타**임 플리z", "한 번만 더요", TROUBLE, E),
    ("how do you say this", "/haʊ du ju seɪ ðɪs/", "하우 두 유 **쎄**이 디s", "이거 어떻게 말해요", TROUBLE, N),
    ("my English isn't good", "/maɪ ˈɪŋɡlɪʃ ˈɪzənt ɡʊd/", "마이 **잉**글리시 이전t 굿", "영어를 잘 못해요", TROUBLE, N),
    ("bear with me", "/bɛr wɪð mi/", "베어r 위th **미**", "잠시만 기다려 주세요", TROUBLE, H),
    ("I forgot my password", "/aɪ fərˈɡɑt maɪ ˈpæswɜrd/", "아이 f어r**같** 마이 패s워rd", "비밀번호를 잊어버렸어요", TROUBLE, N),
    ("the door is locked", "/ðə dɔr ɪz lɑkt/", "더 도r 이z **락**t", "문이 잠겼어요", TROUBLE, N),
    ("I think I'm lost", "/aɪ θɪŋk aɪm lɔst/", "아이 th잉k 아임 **로**s트", "길을 잃은 것 같아요", TROUBLE, N),
    ("that's not what I meant", "/ðæts nɑt wʌt aɪ mɛnt/", "댙s 낱 왓 아이 **멘**t", "그런 뜻이 아니었어요", TROUBLE, N),
    ("can you write it down", "/kæn ju raɪt ɪt daʊn/", "캔 유 **라**잍 잍 다운", "적어주실 수 있나요", TROUBLE, N),
    ("I need more time", "/aɪ nid mɔr taɪm/", "아이 니d 모r **타**임", "시간이 더 필요해요", TROUBLE, E),
    ("something came up", "/ˈsʌmθɪŋ keɪm ʌp/", "**썸**th잉 케임 업", "일이 생겼어요", TROUBLE, N),
    ("let me check again", "/lɛt mi tʃɛk əˈɡɛn/", "렡 미 첵 어**겐**", "다시 확인해 볼게요", TROUBLE, N),
    ("it's my fault", "/ɪts maɪ fɔlt/", "잍s 마이 **f올**t", "제 잘못이에요", TROUBLE, N),
    ("please be patient", "/pliz bi ˈpeɪʃənt/", "플리z 비 **페**이션t", "조금만 기다려 주세요", TROUBLE, N),

    # --- 가벼운 대화 (추가) ---
    ("what are you up to", "/wʌt ɑr ju ʌp tu/", "왓 아r 유 **업** 투", "뭐 하고 있어요", TALK, N),
    ("I'm working on it", "/aɪm ˈwɜrkɪŋ ɔn ɪt/", "아임 **워**r킹 온 잍", "하고 있어요", TALK, N),
    ("that makes sense", "/ðæt meɪks sɛns/", "댙 메익s **쎈**s", "말이 되네요", TALK, N),
    ("I see what you mean", "/aɪ si wʌt ju min/", "아이 씨 왓 유 **민**", "무슨 말인지 알겠어요", TALK, N),
    ("let me get back to you", "/lɛt mi ɡɛt bæk tə ju/", "렡 미 겥 **백** 투 유", "다시 연락드릴게요", TALK, N),
    ("sounds like a plan", "/saʊndz laɪk ə plæn/", "사운dz 라익 어 **플랜**", "그렇게 해요", TALK, N),
    ("I'm not sure yet", "/aɪm nɑt ʃʊr jɛt/", "아임 낱 **슈**어r 옡", "아직 확실하지 않아요", TALK, N),
    ("it depends", "/ɪt dɪˈpɛndz/", "잍 디**펜**dz", "상황에 따라 달라요", TALK, N),
    ("that's a good point", "/ðæts ə ɡʊd pɔɪnt/", "댙s 어 굿 **포**인t", "좋은 지적이에요", TALK, N),
    ("I couldn't agree more", "/aɪ ˈkʊdənt əˈɡri mɔr/", "아이 **쿠**던t 어그리 모r", "전적으로 동의해요", TALK, H),
    ("I'm looking forward to it", "/aɪm ˈlʊkɪŋ ˈfɔrwərd tə ɪt/", "아임 **루**킹 f오r워rd 투 잍", "기대하고 있어요", TALK, H),
    ("long story short", "/lɔŋ ˈstɔri ʃɔrt/", "롱 **스토**리 쇼r트", "간단히 말하면", TALK, N),
    ("it's been a while", "/ɪts bɪn ə waɪl/", "잍s 빈 어 **와**일", "꽤 됐네요", TALK, N),
    ("what a coincidence", "/wʌt ə koʊˈɪnsɪdəns/", "왓 어 코우**인**시던s", "이런 우연이", TALK, H),
    ("I'm on my way", "/aɪm ɔn maɪ weɪ/", "아임 온 마이 **웨**이", "가는 중이에요", TALK, E),
    ("I'll be right back", "/aɪl bi raɪt bæk/", "아일 비 라잍 **백**", "금방 올게요", TALK, E),
    ("give me a second", "/ɡɪv mi ə ˈsɛkənd/", "기v 미 어 **쎄**컨d", "잠깐만요", TALK, N),
    ("it's up to you", "/ɪts ʌp tə ju/", "잍s **업** 투 유", "편하신 대로 하세요", TALK, E),
    ("either is fine", "/ˈiðər ɪz faɪn/", "**이**더r 이z f아인", "둘 중 아무거나 괜찮아요", TALK, N),
    ("I don't mind", "/aɪ doʊnt maɪnd/", "아이 도운t **마**인d", "저는 상관없어요", TALK, E),
    ("that'd be great", "/ðætəd bi ɡreɪt/", "대터d 비 **그레**잍", "그러면 좋겠어요", TALK, N),
    ("let's keep in touch", "/lɛts kip ɪn tʌtʃ/", "렡s 킾 인 **터**치", "연락하고 지내요", TALK, N),
    ("how was your day", "/haʊ wʌz jʊr deɪ/", "하우 워z 유어r **데**이", "오늘 어땠어요", TALK, E),
    ("I'm exhausted", "/aɪm ɪɡˈzɔstɪd/", "아임 익**조**s티d", "너무 피곤해요", TALK, H),
    ("the weather is nice", "/ðə ˈwɛðər ɪz naɪs/", "더 **웨**더r 이z 나이s", "날씨가 좋네요", TALK, N),
    ("it's freezing outside", "/ɪts ˈfrizɪŋ ˌaʊtˈsaɪd/", "잍s **f리**징 아웉사이d", "밖이 너무 추워요", TALK, N),
    ("traffic was terrible", "/ˈtræfɪk wʌz ˈtɛrəbəl/", "**트래**f익 워z 테러벌", "차가 너무 막혔어요", TALK, H),
    ("I'm almost there", "/aɪm ˈɔlmoʊst ðɛr/", "아임 **올**모우s트 데어r", "거의 다 왔어요", TALK, N),
    ("see you around", "/si ju əˈraʊnd/", "씨 유 어**라**운d", "또 봐요", TALK, E),
    ("I'd love to", "/aɪd lʌv tu/", "아이d **러**v 투", "그러고 싶어요", TALK, N),
    ("maybe another time", "/ˈmeɪbi əˈnʌðər taɪm/", "**메**이비 어너더r 타임", "다음 기회에요", TALK, N),
    ("good to know", "/ɡʊd tə noʊ/", "굿 투 **노**우", "좋은 정보네요", TALK, E),
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
                "source": SEED_SOURCE,
            }

            existing = DailyPhrase.objects.filter(text=text).first()
            if existing is None:
                # 검수를 거친 상태로 넣는다. 누가 무엇을 확인했는지와
                # 사용자가 그것을 알고 정한 날은 이 파일 머리에 적었다.
                #
                # **새로 만들 때만 켠다.** --reset 의 갱신에 넣으면 Admin 에서
                # 사람이 검수를 끈 표현이 다음 --reset 에 조용히 다시 노출된다.
                DailyPhrase.objects.create(text=text, is_reviewed=True, **fields)
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
