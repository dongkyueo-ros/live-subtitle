# live-subtitle

영어 오디오를 실시간으로 감지하여 한국어 자막을 화면에 오버레이합니다.

- 녹화 불필요 — 시스템 오디오를 직접 캡처
- Groq Whisper로 영어 텍스트 추출
- Google Translate로 한국어 번역
- 화면 하단 반투명 자막 오버레이 표시

---

## 📁 프로젝트 구조

```
live-subtitle/
├── auto_subtitle.py   # 메인 스크립트
├── requirements.txt   # 패키지 목록
├── .env.example       # 환경변수 템플릿
├── .env               # API 키 (Git 제외 — 직접 생성)
├── .gitignore
├── setup.bat          # 최초 1회 환경 설정
└── run.bat            # 실행
```

---

## 🚀 시작하기

### 1. 저장소 클론

```bash
git clone https://github.com/{username}/live-subtitle.git
cd live-subtitle
```

### 2. Groq API 키 발급

1. [https://console.groq.com](https://console.groq.com) 접속 후 회원가입
2. **API Keys → Create API Key** 클릭
3. 생성된 키 복사 (`gsk_` 로 시작)

> 무료 플랜으로 충분합니다. 신용카드 불필요.

### 3. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 API 키 입력:

```env
GROQ_API_KEY=gsk_여기에_키_입력
```

### 4. 환경 설정 (최초 1회)

```bash
setup.bat
```

가상환경 생성 및 패키지 설치를 자동으로 진행합니다.

### 5. 실행

```bash
run.bat
```

---

## ⚙️ 설정 옵션

`.env` 파일에서 조정 가능합니다.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `GROQ_API_KEY` | — | Groq API 키 **(필수)** |
| `CHUNK_SECONDS` | `15` | 번역 주기 (초) |
| `SAMPLE_RATE` | `16000` | 오디오 샘플레이트 |
| `SOURCE_LANG` | `en` | 원본 언어 |
| `TARGET_LANG` | `ko` | 번역 언어 |

---

## 🖱 자막 창 조작

| 동작 | 방법 |
|------|------|
| 창 이동 | 자막 창 드래그 |
| 투명도 조절 | 우상단 슬라이더 |
| 종료 | 우상단 **✕** 클릭 |

---

## ❗ 스테레오 믹스 설정 (최초 1회)

시스템 오디오 캡처를 위해 Windows의 스테레오 믹스를 활성화해야 합니다.

1. 작업표시줄 스피커 아이콘 우클릭 → **소리 설정**
2. **녹음** 탭 클릭
3. 빈 곳 우클릭 → **사용 안 하는 장치 표시** 체크
4. **스테레오 믹스** 우클릭 → **사용** 선택

### 스테레오 믹스가 없는 경우

[VB-Audio Virtual Cable](https://vb-audio.com/Cable) (무료) 설치 후:

1. 소리 설정 → 출력 장치를 **CABLE Input** 으로 변경
2. 녹음 탭 → **CABLE Output** 을 기본 장치로 설정

---

## 🛠 수동 실행 (bat 파일 없이)

bash
```bash
# 가상환경 생성
python -m venv .venv

# 가상환경 활성화
source .venv/Scripts/activate

# 패키지 설치
pip install -r requirements.txt

# 실행
python auto_subtitle.py
```

cmd
```bash
# 가상환경 활성화
.venv\Scripts\activate

# 실행
python auto_subtitle.py
```

---

## 📦 의존성

| 패키지 | 용도 |
|--------|------|
| `groq` | Whisper 음성 인식 API |
| `deep-translator` | Google 번역 |
| `sounddevice` | 시스템 오디오 캡처 |
| `soundfile` | 오디오 파일 처리 |
| `python-dotenv` | `.env` 환경변수 로드 |

---

## 🔒 보안

- API 키는 `.env` 파일에서만 관리하며 코드에 포함되지 않습니다.
- `.env` 는 `.gitignore` 에 등록되어 있어 Git에 커밋되지 않습니다.
- `.env.example` 에는 키 값 없이 형식만 포함되어 있습니다.