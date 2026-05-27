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
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf
import tkinter as tk
from dotenv import load_dotenv
from groq import Groq

# ── 설정 로드 (.env) ──────────────────────────────────────
load_dotenv()

GROQ_API_KEY         : str           = os.getenv("GROQ_API_KEY", "")
CHUNK_SECONDS        : int           = int(os.getenv("CHUNK_SECONDS", "15"))
SOURCE_LANG          : str           = os.getenv("SOURCE_LANG", "en")
TARGET_LANG          : str           = os.getenv("TARGET_LANG", "ko")
WHISPER_MODEL        : str           = os.getenv("WHISPER_MODEL", "whisper-large-v3-turbo")
LLM_MODEL            : str           = os.getenv("LLM_MODEL",     "llama-3.3-70b-versatile")
CHANNELS             : int           = int(os.getenv("CHANNELS", "2"))
SILENCE_THRESHOLD    : float         = float(os.getenv("SILENCE_THRESHOLD", "0.01"))
LOOPBACK_DEVICE_INDEX: Optional[int] = int(os.getenv("LOOPBACK_DEVICE_INDEX")) if os.getenv("LOOPBACK_DEVICE_INDEX") else None


def validate_config() -> None:
    if not GROQ_API_KEY:
        sys.exit(
            "[오류] .env 파일에 GROQ_API_KEY가 없습니다.\n"
            "  1. .env.example 을 복사해 .env 로 저장\n"
            "  2. GROQ_API_KEY=gsk_... 형식으로 키 입력\n"
            "  3. 키 발급: https://console.groq.com"
        )
    if not GROQ_API_KEY.startswith("gsk_"):
        sys.exit("[오류] GROQ_API_KEY 형식이 올바르지 않습니다. (gsk_ 로 시작해야 함)")


# ── 로그 파일 ─────────────────────────────────────────────

class TranscriptLogger:
    """
    EN/KO 쌍을 타임스탬프와 함께 logs/ 폴더에 저장합니다.
    파일명: logs/YYYY-MM-DD_HH-MM-SS.txt
    """

    def __init__(self) -> None:
        self._log_dir  = Path("logs")
        self._log_dir.mkdir(exist_ok=True)
        filename       = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".txt"
        self._log_path = self._log_dir / filename
        self._start    = time.time()
        self._lock     = threading.Lock()
        self._write(f"=== Auto Subtitle Log ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===\n")
        print(f"[로그] {self._log_path}")

    def write(self, en: str, ko: str) -> None:
        elapsed  = int(time.time() - self._start)
        h, rem   = divmod(elapsed, 3600)
        m, s     = divmod(rem, 60)
        timestamp = f"{h:02d}:{m:02d}:{s:02d}"
        entry    = f"\n[{timestamp}]\nEN: {en}\nKO: {ko}\n"
        self._write(entry)

    def _write(self, text: str) -> None:
        with self._lock:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(text)


# ── 오디오 장치 ───────────────────────────────────────────

def find_loopback_device() -> Optional[int]:
    if LOOPBACK_DEVICE_INDEX is not None:
        return LOOPBACK_DEVICE_INDEX

    keywords = ("stereo mix", "스테레오 믹스", "loopback", "what u hear", "cable output", "vb-audio")
    devices  = list(enumerate(sd.query_devices()))

    # 1순위: MME (hostapi=0)
    for idx, device in devices:
        if device["max_input_channels"] > 0 and device["hostapi"] == 0:
            if any(kw in device["name"].lower() for kw in keywords):
                print(f"[장치 선택] {idx}: {device['name']} (MME)")
                return idx

    # 2순위: 방식 무관
    for idx, device in devices:
        if device["max_input_channels"] > 0:
            if any(kw in device["name"].lower() for kw in keywords):
                print(f"[장치 선택] {idx}: {device['name']}")
                return idx

    return None


# ── 오디오 캡처 ───────────────────────────────────────────

class AudioCapture:
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
        while not self._stop_event.is_set():
            time.sleep(self._chunk_seconds)
            with self._lock:
                if not self._buffer:
                    continue
                chunk = np.concatenate(self._buffer, axis=0)
                self._buffer.clear()

            # 무음 필터 — RMS 가 임계값 이하면 Whisper 호출 안 함
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            if rms < SILENCE_THRESHOLD:
                continue

            self.queue.put(chunk)

    def start(self) -> None:
        self._stream = sd.InputStream(
            device=self._device_idx,
            channels=CHANNELS,
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


# ── 전사 & 번역 ───────────────────────────────────────────

class TranscribeWorker:
    def __init__(
        self,
        audio_queue : queue.Queue[np.ndarray],
        groq_client : Groq,
        sample_rate : int,
        logger      : TranscriptLogger,
        on_result,
        on_status,
    ) -> None:
        self._queue       = audio_queue
        self._client      = groq_client
        self._sample_rate = sample_rate
        self._logger      = logger
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
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    tmp_path = f.name
                sf.write(tmp_path, chunk, self._sample_rate)

                with open(tmp_path, "rb") as audio_file:
                    transcription = self._client.audio.transcriptions.create(
                        model=WHISPER_MODEL,
                        file=audio_file,
                        language=SOURCE_LANG,
                    )

                en_text = transcription.text.strip()
                if not en_text or en_text in (".", "...", "Thank you."):
                    self._on_status("🎙  오디오 감지 중 ...")
                    continue

                # Groq LLaMA 번역
                chat = self._client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": (
                            "You are a professional Korean translator specializing in IT security and identity management. ""Always use formal polite Korean speech ending in 합니다/습니다/입니다 (하십시오체). Never use informal endings like 이다/한다/된다. "
                            "Translate the given English text to Korean. "
                            "CRITICAL RULES: "
                            "1. Output ONLY Korean text. Never output Chinese, Japanese, or any other language. "
                            "2. If you are unsure, write in Korean regardless. "
                            "3. Keep these terms in English as-is: Saviynt, Wiz, IAM, SSO, vendor, lifecycle, onboarding, governance, compliance, zero day, self-service, non-employee. "
                            "4. Do not add explanations or extra sentences not in the original. "
                            "5. Output only the translated Korean text, nothing else."
                        )},
                        {"role": "user", "content": en_text},
                    ],
                    max_tokens=512,
                )
                ko_text = chat.choices[0].message.content.strip()

                # 중국어/일본어 문자 감지 시 재시도 (최대 2회)
                def has_cjk(text: str) -> bool:
                    return any("一" <= c <= "鿿" or "㐀" <= c <= "䶿" for c in text)

                retry = 0
                while has_cjk(ko_text) and retry < 2:
                    retry += 1
                    print(f"[재번역 {retry}/2] 중국어 감지됨")
                    chat = self._client.chat.completions.create(
                        model=LLM_MODEL,
                        messages=[
                            {"role": "system", "content": (
                                "You are a Korean translator. "
                                "Translate English to Korean ONLY. "
                                "NEVER use Chinese characters (漢字/中文). "
                                "NEVER use Japanese characters. "
                                "Use ONLY Korean Hangul (가-힣), spaces, punctuation, and English technical terms. "
                                "Output only the translation, nothing else."
                            )},
                            {"role": "user", "content": en_text},
                        ],
                        max_tokens=512,
                    )
                    ko_text = chat.choices[0].message.content.strip()

                # 로그 저장
                self._logger.write(en_text, ko_text)

                self._on_result(en_text, ko_text)

            except Exception as exc:
                self._on_status(f"⚠️  {exc!s:.70}")
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)


# ── 자막 오버레이 ─────────────────────────────────────────

class SubtitleOverlay:
    _MIN_W, _MIN_H = 400, 80
    _DEF_W, _DEF_H = 1200, 250

    def __init__(self, on_close) -> None:
        self._on_close = on_close

        self.root = tk.Tk()
        self.root.title("")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.90)
        self.root.configure(bg="#0a0a0a")
        self.root.minsize(self._MIN_W, self._MIN_H)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = (sw - self._DEF_W) // 2
        y  = sh - self._DEF_H - 60
        self.root.geometry(f"{self._DEF_W}x{self._DEF_H}+{x}+{y}")

        # 드래그 이동
        self._drag_x = self._drag_y = 0

        # ── 상단 컨트롤 바 (드래그 + 버튼) ──
        self._bar = tk.Frame(self.root, bg="#1a1a1a", height=22, cursor="fleur")
        self._bar.pack(fill="x", side="top")
        self._bar.bind("<ButtonPress-1>", self._drag_start)
        self._bar.bind("<B1-Motion>",     self._drag_move)

        tk.Button(self._bar, text="✕", command=self._close,
                  font=("Malgun Gothic", 9), fg="#888", bg="#1a1a1a",
                  bd=0, cursor="hand2", padx=6).pack(side="right")

        tk.Scale(self._bar, from_=40, to=100, orient="horizontal",
                 command=lambda v: self.root.attributes("-alpha", int(v) / 100),
                 bg="#1a1a1a", fg="#555", troughcolor="#333",
                 highlightthickness=0, length=70, showvalue=False,
                 ).pack(side="right", pady=1)

        tk.Label(self._bar, text="☰ Auto Subtitle",
                 font=("Malgun Gothic", 8), fg="#555", bg="#1a1a1a",
                 cursor="fleur").pack(side="left", padx=6)

        # ── 자막 영역 ──
        self._content = tk.Frame(self.root, bg="#0a0a0a")
        self._content.pack(fill="both", expand=True)

        self._en_var = tk.StringVar(value="🎙  오디오 감지 중 ...")
        self._ko_var = tk.StringVar(value="")

        self._en_label = tk.Label(self._content, textvariable=self._en_var,
                 font=("Malgun Gothic", 11), fg="#666", bg="#0a0a0a",
                 wraplength=900, justify="center")
        self._en_label.pack(pady=(8, 2))

        self._ko_label = tk.Label(self._content, textvariable=self._ko_var,
                 font=("Malgun Gothic", 15, "bold"), fg="#ffffff", bg="#0a0a0a",
                 wraplength=900, justify="center")
        self._ko_label.pack(pady=(2, 8))

        # ── 우하단 리사이즈 핸들 ──
        self._grip = tk.Label(self.root, text="⇲", fg="#444", bg="#0a0a0a",
                              cursor="size_nw_se", font=("Arial", 10))
        self._grip.place(relx=1.0, rely=1.0, anchor="se")
        self._grip.bind("<ButtonPress-1>",  self._resize_start)
        self._grip.bind("<B1-Motion>",      self._resize_move)

        self._resize_x = self._resize_y = 0
        self._resize_w = self._resize_h = 0

        # 창 크기 변경 시 wraplength 자동 조정
        self.root.bind("<Configure>", self._on_resize)

    # ── 외부 호출 ──────────────────────────────────────────

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
        self._drag_x = event.x_root
        self._drag_y = event.y_root

    def _drag_move(self, event) -> None:
        dx = event.x_root - self._drag_x
        dy = event.y_root - self._drag_y
        x  = self.root.winfo_x() + dx
        y  = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")
        self._drag_x = event.x_root
        self._drag_y = event.y_root

    def _resize_start(self, event) -> None:
        self._resize_x = event.x_root
        self._resize_y = event.y_root
        self._resize_w = self.root.winfo_width()
        self._resize_h = self.root.winfo_height()

    def _resize_move(self, event) -> None:
        w = max(self._MIN_W, self._resize_w + event.x_root - self._resize_x)
        h = max(self._MIN_H, self._resize_h + event.y_root - self._resize_y)
        self.root.geometry(f"{w}x{h}")

    def _on_resize(self, event) -> None:
        w = self.root.winfo_width()
        wrap = max(200, w - 40)
        self._en_label.configure(wraplength=wrap)
        self._ko_label.configure(wraplength=wrap)


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
    device_info = sd.query_devices(device_idx)
    sample_rate = int(os.getenv("SAMPLE_RATE") or device_info["default_samplerate"])
    print(f"[설정] 샘플레이트: {sample_rate}Hz / 채널: {CHANNELS} / 무음 임계값: {SILENCE_THRESHOLD}")

    def on_close():
        capture.stop()
        worker.stop()

    logger  = TranscriptLogger()
    capture = AudioCapture(device_idx=device_idx, chunk_seconds=CHUNK_SECONDS, sample_rate=sample_rate)
    overlay = SubtitleOverlay(on_close=on_close)
    worker  = TranscribeWorker(
        audio_queue=capture.queue,
        groq_client=groq_client,
        sample_rate=sample_rate,
        logger=logger,
        on_result=overlay.set_result,
        on_status=overlay.set_status,
    )

    capture.start()
    worker.start()
    overlay.run()


if __name__ == "__main__":
    main()