# DeVoca Android 앱 (TWA)

Google Play 에 올리는 Android 앱의 껍데기다. 화면은 없다. 폰의 Chrome 이
`https://dev-voca.vercel.app/` 을 주소창 없이 띄운다(Trusted Web Activity).
화면을 고치려면 `frontend/` 를 고친다. main 에 머지하면 앱에도 바로 나간다.

Google 의 Bubblewrap 1.27 로 만들었다. 이름·색·아이콘 주소는 처음 만들 때 웹의
`/manifest.webmanifest`(`frontend/src/app/manifest.ts`)에서 읽어
`twa-manifest.json` 에 적어 두었다. 그 뒤로는 `twa-manifest.json` 이 기준이다.

기본값에서 바꾼 것:
- 최소 Android 버전 7.0(minSdkVersion 24): 같이 들어가는 androidbrowserhelper
  2.7 이 24 를 요구한다. 기본값 21 로는 빌드가 깨진다.
- 폰 맨 아래 시스템 바와 그 경계선 흰색(navigationColor, navigationDividerColor):
  탭바(흰색)와 맞췄다. 기본값은 검정·투명이다. Android 8.0 이상은 흰 바 위
  버튼을 어둡게 그린다. 7.x 는 그런 기능이 없어 바가 회색으로 보일 수 있다.
- 다크 모드 색(themeColorDark, navigationColorDark, navigationDividerColorDark):
  웹에 밝은 화면만 있어서 밝을 때와 같은 값으로 두었다. 기본값은 검정이다.
- 알림 끔(enableNotifications): 웹 푸시를 넣을 때 켠다.

## 웹과 앱을 잇는 확인 파일

`frontend/public/.well-known/assetlinks.json` 에 앱 서명 지문이 있어야 앱 위에
주소창이 안 보인다. 지문은 넷이고 모두 넣었다(2026-11-12).

- 업로드 키(`55:46:…`): 이 PC 에서 서명해 폰에 직접 설치한 앱.
- Play 앱 서명 키 세 개: Play 에서 내려받은 앱은 Google 이 가진 키로 다시
  서명된다. Play 는 새 앱에 양자 내성 하이브리드 서명을 기본으로 켜서 키가
  세 개이고, 폰의 Android 버전마다 확인하는 키가 다르다.
  - Android 16 이하용 키(`E4:B3:…`): Play Console 의 앱 서명 화면이 보여 주는
    Digital Asset Links JSON 에 들어 있는 값이다. 인증서 파일은 받지 않아
    화면 값을 그대로 옮겼다.
  - 하이브리드 RSA 키(`81:C5:…`)와 ML-DSA-65 키(`2C:0E:…`): Android 17 이상용.
    같은 화면에서 받은 인증서 파일 `hybrid_classical_cert.der`,
    `hybrid_pqc_cert.der` 의 SHA-256 이다. 아래 명령으로 다시 뽑을 수 있다.

```bash
openssl x509 -inform DER -in hybrid_pqc_cert.der -noout -fingerprint -sha256
```

Play Console 이 보여 주는 JSON 에는 첫 키 하나만 있다. 그것만 넣으면 Android
17 이상 폰에서 Play 로 받은 앱에만 주소창이 뜰 수 있어 놓치기 쉽다. Google 의
Play 앱 서명 도움말(https://support.google.com/googleplay/android-developer/answer/9842756)
도 하이브리드 서명이면 키 세 개를 모두 등록하라고 한다.

Play 가 키를 바꾸거나 올리면 이 파일과 `frontend/src/app/manifest.test.mts` 의
지문 표를 같이 고친다. `assetlinks.json` 은 손으로 관리한다.
`twa-manifest.json` 의 `fingerprints` 는 비어 있어서, `bubblewrap fingerprint
generateAssetLinks` 가 만드는 파일은 지문이 빈 채로 나온다. 그 결과로 이 파일을
바꾸지 않는다.

## 다시 빌드하기

한 번만 준비한다: `npm i -g @bubblewrap/cli@1.27.0`. JDK 17 과 Android SDK 를
어디에 받았는지는 `~/.bubblewrap/config.json` 에 적혀 있다.

서명 키는 저장소에 없다. `~/.devvoca-android/upload-key.jks` 에 있다. 이 키와
비밀번호는 따로따로 백업한다(키 파일은 USB 나 개인 클라우드, 비밀번호는 비밀번호
관리자). 둘을 한곳에 두면 한 번에 같이 샌다.

Git Bash 에서:

```bash
cd android
export PATH="$HOME/.bubblewrap/jdk/bin:$PATH"   # AAB 서명 도구(jarsigner)를 찾게 한다
read -rsp '키 비밀번호: ' BUBBLEWRAP_KEYSTORE_PASSWORD && echo && export BUBBLEWRAP_KEYSTORE_PASSWORD   # 쳐도 화면·기록에 안 남는다
export BUBBLEWRAP_KEY_PASSWORD="$BUBBLEWRAP_KEYSTORE_PASSWORD"
env -u NoDefaultCurrentDirectoryInExePath bubblewrap build --skipPwaValidation \
  --signingKeyPath="$(cygpath -w ~/.devvoca-android/upload-key.jks)" --signingKeyAlias=upload
```

`app-release-bundle.aab` 를 Play Console 에 올린다. `app-release-signed.apk` 는
폰에 직접 설치해 볼 때 쓴다. 둘 다 저장소에는 넣지 않는다(`.gitignore`).

함정 셋:
- `env -u NoDefaultCurrentDirectoryInExePath` 를 빼면 Windows 에서 Bubblewrap 이
  `gradlew.bat` 을 못 찾는다. 이 변수가 켜진 셸은 현재 폴더의 실행 파일을 찾지 않는다.
- PATH 줄을 빼면 APK 는 나오는데 AAB 서명에서 `jarsigner` 를 못 찾아 멈춘다.
- 빌드가 실패하면 Bubblewrap 이 서명 명령을 **비밀번호째** 화면에 찍는다. 그
  출력을 어디에 붙여 넣거나 로그로 남기지 않는다(`.gitignore` 가 `*.log` 를 막는다).

## 새 버전을 올릴 때

웹 화면만 바뀐 것이면 새 버전이 필요 없다. 앱 이름·아이콘·색을 바꿀 때만 다시
올린다.

1. 웹의 이름·색을 바꿨으면 `twa-manifest.json` 의 같은 칸을 고친다. 또는 웹
   PR 이 배포된 뒤 `bubblewrap merge --skipVersionUpgrade` 로 운영 주소의 웹
   manifest 를 다시 합친다(배포 전에 돌리면 옛 값이 합쳐진다). `bubblewrap update`
   는 웹 manifest 를 다시 읽지 않는다. 아이콘은 같은 주소의 그림을 바꿔
   배포했으면 다음 단계에서 다시 받아 온다.
2. `bubblewrap update --appVersionName=1.0.1` 처럼 돌린다. `appVersionCode` 가 1
   오르고 `app/build.gradle` 에도 옮겨진다. Play 는 같은 버전 번호를 두 번 받지 않는다.
3. 위 빌드 명령으로 빌드한다.

`frontend/src/app/manifest.test.mts` 와 `assetlinks.test.mts` 가 웹 manifest,
`twa-manifest.json`, `app/build.gradle`, `assetlinks.json` 이 서로 맞는지 본다.
테스트가 빨개지면 위 1·2 단계를 빠뜨린 것이다.

`twa-manifest.json` 은 줄바꿈을 바꾸지 않게 해 두었다(`.gitattributes`). 바뀌면
`manifest-checksum.txt` 와 어긋나, 빌드할 때 "프로젝트를 다시 만들까" 를 묻고
수락하면 버전 번호가 몰래 오른다.
