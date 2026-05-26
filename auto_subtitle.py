"""
auto_subtitle.py
================
영어 오디오 → 실시간 한국어 자막 오버레이

의존성: requirements.txt 참고
설정:  .env 파일에서 관리 (.env.example 참고)
실행:  가상환경 활성화 후 python auto_subtitle.py
"""

from __future__ import annotations

import os
import queue
import sys
import tempfile
import threading
import time
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf
import tkinter as tk
from dotenv import load_dotenv
from groq import Groq
from deep_translator import GoogleTranslator

# ── 설정 로드 (.env) ──────────────────────────────────────
load_dotenv()

GROQ_API_KEY  : str = os.getenv("GROQ_API_KEY", "")
CHUNK_SECONDS : int = int(os.getenv("CHUNK_SECONDS", "15"))
SAMPLE_RATE   : int = int(os.getenv("SAMPLE_RATE",   "16000"))
SOURCE_LANG   : str = os.getenv("SOURCE_LANG", "en")
TARGET_LANG   : str = os.getenv("TARGET_LANG", "ko")


def validate_config() -> None:
    """시작 전 필수 설정값 검증"""
    if not GROQ_API_KEY:
        sys.exit(
            "[오류] .env 파일에 GROQ_API_KEY가 없습니다.\n"
            "  1. .env.example 을 복사해 .env 로 저장\n"
            "  2. GROQ_API_KEY=gsk_... 형식으로 키 입력\n"
            "  3. 키 발급: https://console.groq.com"
        )
    if not GROQ_API_KEY.startswith("gsk_"):
        sys.exit("[오류] GROQ_API_KEY 형식이 올바르지 않습니다. (gsk_ 로 시작해야 함)")


# ── 오디오 장치 ───────────────────────────────────────────

def find_loopback_device() -> Optional[int]:
    """스테레오 믹스 / VB-Cable 등 루프백 장치 인덱스 반환"""
    keywords = ("loopback", "stereo mix", "스테레오 믹스", "what u hear", "cable output")
    for idx, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] > 0 and any(
            kw in device["name"].lower() for kw in keywords
        ):
            return idx
    return None


# ── 오디오 캡처 스레드 ────────────────────────────────────

class AudioCapture:
    """
    sounddevice 콜백으로 오디오를 수집하고
    thread-safe Queue 에 청크 단위로 넣습니다.
    """

    def __init__(self, device_idx: int, chunk_seconds: int, sample_rate: int) -> None:
        self._device_idx    = device_idx
        self._chunk_seconds = chunk_seconds
        self._sample_rate   = sample_rate
        self._buffer: list[np.ndarray] = []
        self._lock          = threading.Lock()
        self.queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stop_event    = threading.Event()
        self._stream: Optional[sd.InputStream] = None

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        with self._lock:
            self._buffer.append(indata.copy())

    def _flush_loop(self) -> None:
        """주기적으로 버퍼를 비워 Queue에 넣는 루프"""
        while not self._stop_event.is_set():
            time.sleep(self._chunk_seconds)
            with self._lock:
                if not self._buffer:
                    continue
                chunk = np.concatenate(self._buffer, axis=0)
                self._buffer.clear()
            self.queue.put(chunk)

    def start(self) -> None:
        self._stream = sd.InputStream(
            device=self._device_idx,
            channels=1,
            samplerate=self._sample_rate,
            callback=self._callback,
        )
        self._stream.start()
        threading.Thread(target=self._flush_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._stream:
            self._stream.stop()
            self._stream.close()


# ── 전사 & 번역 스레드 ────────────────────────────────────

class TranscribeWorker:
    """
    AudioCapture.queue 에서 청크를 꺼내
    Groq Whisper → Google Translate 순으로 처리합니다.
    """

    def __init__(
        self,
        audio_queue: queue.Queue[np.ndarray],
        groq_client: Groq,
        translator: GoogleTranslator,
        sample_rate: int,
        on_result,      # Callable[[str, str], None]
        on_status,      # Callable[[str], None]
    ) -> None:
        self._queue       = audio_queue
        self._client      = groq_client
        self._translator  = translator
        self._sample_rate = sample_rate
        self._on_result   = on_result
        self._on_status   = on_status
        self._stop_event  = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._stop_event.set()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                chunk = self._queue.get(timeout=1)
            except queue.Empty:
                continue

            self._on_status("🔄  분석 중 ...")
            tmp_path: Optional[str] = None
            try:
                # 임시 파일 생성 → Whisper 호출 → 반드시 삭제
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    tmp_path = f.name
                sf.write(tmp_path, chunk, self._sample_rate)

                with open(tmp_path, "rb") as audio_file:
                    transcription = self._client.audio.transcriptions.create(
                        model="whisper-large-v3",
                        file=audio_file,
                        language=SOURCE_LANG,
                    )

                en_text = transcription.text.strip()
                if not en_text:
                    self._on_status("🎙  오디오 감지 중 ...")
                    continue

                ko_text = self._translator.translate(en_text)
                self._on_result(en_text, ko_text)

            except Exception as exc:
                self._on_status(f"⚠️  {exc!s:.70}")
            finally:
                # 예외 발생 여부와 무관하게 임시 파일 삭제
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)


# ── 자막 오버레이 (tkinter) ───────────────────────────────

class SubtitleOverlay:
    """
    화면 하단에 고정되는 반투명 자막 창.
    모든 tkinter 조작은 메인 스레드에서만 수행합니다.
    """

    _W, _H = 960, 120

    def __init__(self, on_close) -> None:
        self._on_close = on_close

        self.root = tk.Tk()
        self.root.title("")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.90)
        self.root.configure(bg="#0a0a0a")

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = (sw - self._W) // 2
        y  = sh - self._H - 60
        self.root.geometry(f"{self._W}x{self._H}+{x}+{y}")

        # 드래그 이동
        self._drag_x = self._drag_y = 0
        self.root.bind("<ButtonPress-1>", self._drag_start)
        self.root.bind("<B1-Motion>",     self._drag_move)

        # 레이블
        self._en_var = tk.StringVar(value="🎙  오디오 감지 중 ...")
        self._ko_var = tk.StringVar(value="")

        tk.Label(self.root, textvariable=self._en_var,
                 font=("Malgun Gothic", 11), fg="#666", bg="#0a0a0a",
                 wraplength=920, justify="center").pack(pady=(10, 2))
        tk.Label(self.root, textvariable=self._ko_var,
                 font=("Malgun Gothic", 15, "bold"), fg="#ffffff", bg="#0a0a0a",
                 wraplength=920, justify="center").pack(pady=(2, 6))

        # 컨트롤 (투명도 슬라이더 + 닫기)
        tk.Scale(
            self.root, from_=40, to=100, orient="horizontal",
            command=lambda v: self.root.attributes("-alpha", int(v) / 100),
            bg="#0a0a0a", fg="#555", troughcolor="#222",
            highlightthickness=0, length=80, showvalue=False,
        ).place(x=self._W - 130, y=2)

        tk.Button(
            self.root, text="✕", command=self._close,
            font=("Malgun Gothic", 9), fg="#555", bg="#0a0a0a",
            bd=0, cursor="hand2",
        ).place(x=self._W - 22, y=4)

    # ── 외부에서 호출 (다른 스레드 → after 로 메인 스레드에 위임) ──

    def set_result(self, en: str, ko: str) -> None:
        self.root.after(0, lambda: (
            self._en_var.set(f"🇺🇸  {en}"),
            self._ko_var.set(f"🇰🇷  {ko}"),
        ))

    def set_status(self, msg: str) -> None:
        self.root.after(0, lambda: (
            self._en_var.set(msg),
            self._ko_var.set(""),
        ))

    def run(self) -> None:
        self.root.mainloop()

    # ── 내부 ──────────────────────────────────────────────

    def _close(self) -> None:
        self._on_close()
        self.root.destroy()

    def _drag_start(self, event) -> None:
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_move(self, event) -> None:
        x = self.root.winfo_x() + event.x - self._drag_x
        y = self.root.winfo_y() + event.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")


# ── 진입점 ────────────────────────────────────────────────

def main() -> None:
    validate_config()

    device_idx = find_loopback_device()
    if device_idx is None:
        sys.exit(
            "[오류] 루프백 오디오 장치를 찾을 수 없습니다.\n"
            "  Windows: 소리 설정 → 녹음 탭 → 스테레오 믹스 활성화\n"
            "  또는 VB-Cable 설치: https://vb-audio.com/Cable"
        )

    groq_client = Groq(api_key=GROQ_API_KEY)
    translator  = GoogleTranslator(source=SOURCE_LANG, target=TARGET_LANG)

    capture = AudioCapture(
        device_idx=device_idx,
        chunk_seconds=CHUNK_SECONDS,
        sample_rate=SAMPLE_RATE,
    )

    overlay = SubtitleOverlay(on_close=lambda: (capture.stop(), worker.stop()))

    worker = TranscribeWorker(
        audio_queue=capture.queue,
        groq_client=groq_client,
        translator=translator,
        sample_rate=SAMPLE_RATE,
        on_result=overlay.set_result,
        on_status=overlay.set_status,
    )

    capture.start()
    worker.start()
    overlay.run()   # 메인 스레드 — 여기서 블로킹


if __name__ == "__main__":
    main()
