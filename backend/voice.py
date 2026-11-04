import io
import os
import subprocess
import tempfile
import threading
from pathlib import Path

import av
import numpy as np
from opencc import OpenCC
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio


ROOT = Path(__file__).resolve().parents[1]
_model = None
_lock = threading.Lock()


def model_path():
    configured = os.getenv('CHZ_WHISPER_MODEL')
    if configured:
        paths = [Path(configured)]
    else:
        cache = Path.home() / '.cache/huggingface/hub/models--Systran--faster-whisper-base/snapshots'
        paths = sorted(cache.glob('*')) if cache.exists() else []
    for path in paths:
        if all((path / name).is_file() for name in ('model.bin', 'config.json', 'tokenizer.json')):
            return path
    raise ValueError('没有完整的本地语音模型，请配置 CHZ_WHISPER_MODEL 指向 Whisper 模型目录')


def status():
    try:
        model_path()
        ready = True
    except ValueError:
        ready = False
    return {'recognition_ready': ready, 'synthesis_ready': os.name == 'nt',
            'recognition': 'Whisper base · 本机 CPU', 'synthesis': 'Windows 本地语音',
            'audio_leaves_device': False}


def transcribe(content):
    global _model
    if not content or len(content) > 12 * 1024 * 1024:
        raise ValueError('音频为空或超过12MB')
    if not _lock.acquire(timeout=2):
        raise ValueError('本地语音正在处理，请稍后重试')
    try:
        # 先逐帧检查时长，避免压缩音频解码后无限增长。
        with av.open(io.BytesIO(content)) as container:
            seconds = 0
            for frame in container.decode(audio=0):
                seconds += frame.samples / frame.sample_rate
                if seconds > 90:
                    raise ValueError('单段语音最多90秒，请分段输入')
        audio = decode_audio(io.BytesIO(content), sampling_rate=16000)
        if len(audio) < 1600 or np.max(np.abs(audio)) < .002:
            return {'text': '', 'duration': round(len(audio) / 16000, 2), 'local': True}
        if _model is None:
            _model = WhisperModel(str(model_path()), device='cpu', compute_type='int8', cpu_threads=2,
                                 num_workers=1, local_files_only=True)
        segments, _ = _model.transcribe(audio, language='zh', beam_size=3, vad_filter=True,
                                        condition_on_previous_text=False)
        text = OpenCC('t2s').convert(''.join(segment.text for segment in segments).strip())
        return {'text': text, 'duration': round(len(audio) / 16000, 2), 'local': True}
    finally:
        _lock.release()


def synthesize(text, root):
    if not text.strip() or len(text) > 1800:
        raise ValueError('播报文字长度需要在1至1800字符之间')
    if os.name != 'nt':
        raise ValueError('当前合成服务需要 Windows 本地语音组件')
    folder = root / 'voice'
    folder.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder) as directory:
        work = Path(directory)
        (work / 'text.txt').write_text(text, encoding='utf-8')
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-File',
                        str(ROOT / 'scripts/local-speech.ps1'), '-InputFile', str(work / 'text.txt'),
                        '-OutputFile', str(work / 'speech.wav')], check=True, capture_output=True,
                       timeout=35, creationflags=subprocess.CREATE_NO_WINDOW)
        return (work / 'speech.wav').read_bytes()
