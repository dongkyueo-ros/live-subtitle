# live-subtitle

영어 오디오를 실시간으로 감지하여 한국어 자막을 화면에 오버레이합니다.
IT 솔루션 학습 영상에 최적화되어 있습니다.


## 동작 흐름

```
VB-Cable (시스템 오디오 캡처)
        ↓
Groq Whisper — 영어 음성 → 텍스트
        ↓
Groq LLaMA 4 Scout — 한국어 번역
        ↓
화면 하단 자막 오버레이 + logs/ 폴더 저장
```


## 파일 구조

```
live-subtitle/
├── auto_subtitle.py   # 메인 스크립트
├── requirements.txt   # 패키지 목록
├── .env               # API 키 & 설정 (직접 생성)
├── .env.example       # 설정 템플릿
├── .gitignore
├── nircmd.exe         # 오디오 장치 전환 도구
├── setup.bat          # 최초 1회 환경 설정
├── run.bat            # 실행
└── logs/              # 번역 로그 자동 저장
```

## 시작하기

### 1. 저장소 클론

```bash
git clone https://github.com/dongkyueo-ros/live-subtitle.git
cd live-subtitle
```

### 2. Groq API 키 발급 (무료)

1. https://console.groq.com 접속 후 회원가입
2. API Keys -> Create API Key 클릭
3. 생성된 키 복사 (gsk_ 로 시작)

### 3. .env 파일 생성

```bash
cp .env.example .env
```

.env 파일을 열어 API 키 입력:

```env
GROQ_API_KEY=gsk_여기에_키_입력
```

### 4. VB-Cable 설치 (최초 1회)

https://vb-audio.com/Cable 에서 다운로드 후 관리자 권한으로 설치.
설치 후 반드시 PC 재부팅.

### 5. nircmd.exe

`nircmd.exe` 는 이 저장소에 포함되어 있습니다.

> 출처: NirCmd by Nir Sofer — Freeware, 무료 재배포 허용 (수정 없이 배포)

### 6. 이어폰으로 소리 들으면서 자막 보기 설정 (최초 1회)

이 설정은 한 번만 하면 재부팅 후에도 영구 유지됩니다.

1. 작업표시줄 스피커 아이콘 우클릭 → **소리 설정**
2. 하단 **추가 소리 설정** 클릭
3. **녹음** 탭 클릭
4. `CABLE Output (VB-Audio Virtual Cable)` 더블클릭
5. **수신 대기** 탭 클릭
6. `이 장치로 듣기` ✅ 체크
7. 드롭다운에서 **헤드폰(Realtek(R) Audio)** 선택
8. **확인** 클릭

> 이 설정 후 이어폰으로 소리를 들으면서 동시에 자막도 볼 수 있습니다.

### 7. 환경 설정 (최초 1회)

```bash
setup.bat
```

### 8. 실행

```bash
run.bat
```

run.bat 이 자동으로:
- 출력 장치를 CABLE Input 으로 변경
- 자막 시작
- 종료 시 출력 장치를 헤드폰으로 복원


## 설정 옵션 (.env)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `GROQ_API_KEY` | — | Groq API 키 (필수) |
| `CHUNK_SECONDS` | `20` | 번역 주기 (초) |
| `CHANNELS` | `2` | 오디오 채널 수 |
| `SOURCE_LANG` | `en` | 원본 언어 |
| `TARGET_LANG` | `ko` | 번역 언어 |
| `WHISPER_MODEL` | `whisper-large-v3-turbo` | STT 모델 |
| `LLM_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` | 번역 모델 |
| `SILENCE_THRESHOLD` | `0.01` | 무음 감지 임계값 |
| `LOOPBACK_DEVICE_INDEX` | 자동 탐지 | 오디오 장치 인덱스 |

### 모델 선택 가이드

**STT 모델 (WHISPER_MODEL)**
```
whisper-large-v3        : 빠름
whisper-large-v3-turbo  : 억양에 강함, 인도식 영어 권장 (기본값)
```

**번역 모델 (LLM_MODEL)**
```
llama-3.1-8b-instant                      : 빠름, 가벼움
llama-3.3-70b-versatile                   : 고품질 (중국어 버그 간헐적 발생)
meta-llama/llama-4-scout-17b-16e-instruct : 최신, 고품질 (권장)
```

## 자막 창 조작

| 동작 | 방법 |
|------|------|
| 창 이동 | 상단 회색 바 드래그 |
| 창 크기 조절 | 우하단 ⇲ 핸들 드래그 |
| 투명도 조절 | 상단 바 우측 슬라이더 |
| 종료 | 상단 바 우측 X 클릭 |


## 번역 로그

실행할 때마다 `logs/` 폴더에 자동 저장됩니다.

```
logs/
└── 2026-05-26_19-00-44.txt
```

로그 형식:

```
=== Auto Subtitle Log (2026-05-26 19:00:44) ===

[00:00:24]
EN: for unified single platform in which you are able to manage your vendors...
KO: 통합된 단일 플랫폼을 통해 공급업체(vendor)를 관리할 수 있습니다...
```

## 의존성

| 패키지 | 용도 |
|--------|------|
| `groq` | Whisper STT + LLaMA 번역 |
| `sounddevice` | 시스템 오디오 캡처 |
| `soundfile` | 오디오 파일 처리 |
| `python-dotenv` | .env 환경변수 로드 |

## 문제 해결

### 오디오가 안 잡힐 때

```bash
python -c "
import sounddevice as sd
for i, d in enumerate(sd.query_devices()):
    if d['max_input_channels'] > 0:
        print(i, d['name'])
"
```

### 소리는 잡히는데 번역이 안 될 때

터미널에서 직접 실행해서 오류 메시지 확인:

```bash
source .venv/Scripts/activate
python auto_subtitle.py
```

### 번역에 중국어가 섞일 때

.env 에서 모델 변경:

```env
LLM_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
```

### 이어폰으로 소리가 안 들릴 때

6번 설정(수신 대기)이 되어 있는지 확인하세요.
이 설정은 최초 1회만 수동으로 해야 하며 자동화가 불가능합니다.
(Windows에서 공식 API를 제공하지 않음)


## 보안

- API 키는 `.env` 파일에서만 관리
- `.env` 는 `.gitignore` 에 등록되어 Git에 커밋되지 않음
- `.env.example` 에는 키 값 없이 형식만 포함


## 작성자

**Dongkyu Lee**
- GitHub: [@dongkyueo-ros](https://github.com/dongkyueo-ros)
- Repository: [live-subtitle](https://github.com/dongkyueo-ros/live-subtitle)


## 라이선스

MIT License - 자유롭게 사용, 수정, 배포 가능합니다.


## 기여 (Contributing)

버그 리포트, 기능 제안, PR 모두 환영합니다!

### PR 방법

1. 저장소 Fork
2. 브랜치 생성
   ```bash
   git checkout -b feature/기능명
   ```
3. 변경사항 커밋
   ```bash
   git commit -m "[feat] 기능 설명"
   ```
4. Push 후 Pull Request 생성
   ```bash
   git push origin feature/기능명
   ```

### 커밋 메시지 규칙

| 태그 | 설명 |
|------|------|
| `feat` | 새로운 기능 추가 |
| `fix` | 버그 수정 |
| `docs` | 문서 수정 |
| `refactor` | 코드 리팩토링 |
| `chore` | 기타 변경사항 |

### 이런 기여를 기다립니다

- 번역 품질 개선 아이디어
- 자막 UI 개선
- macOS / Linux 지원