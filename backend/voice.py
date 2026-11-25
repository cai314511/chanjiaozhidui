import io
import importlib.util
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path

import av
import numpy as np
from opencc import OpenCC
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
_SENSEVOICE_DEPENDENCIES = {
    'sensevoice': ('SenseVoiceSmall', 'requirements-sensevoice.txt', ('funasr', 'torch', 'torchaudio', 'sentencepiece')),
    'sensevoice_int8': ('SenseVoiceSmall INT8', 'requirements-sensevoice-int8.txt', ('sherpa_onnx',)),
}
_model = None
_model_key = None
_lock = threading.Lock()


class VoiceUnavailable(RuntimeError):
    """本地模型服务无法完成识别，向调用方明确返回503。"""


def model_spec():
    local = dotenv_values(ROOT / '.env')
    configured = (os.getenv('CHZ_ASR_MODEL') or os.getenv('CHZ_WHISPER_MODEL')
                  or local.get('CHZ_ASR_MODEL') or local.get('CHZ_WHISPER_MODEL'))
    if configured:
        path = Path(configured).expanduser()
        paths = [path if path.is_absolute() else ROOT / path]
    elif (ROOT / 'models' / 'SenseVoiceSmall').exists():
        paths = [ROOT / 'models' / 'SenseVoiceSmall']
    else:
        cache = Path.home() / '.cache/huggingface/hub/models--Systran--faster-whisper-base/snapshots'
        paths = sorted(cache.glob('*')) if cache.exists() else []
    for path in paths:
        path = path.resolve()
        if all((path / name).is_file() and (path / name).stat().st_size > 0 for name in (
                'model.pt', 'config.yaml', 'configuration.json', 'tokens.json',
                'chn_jpn_yue_eng_ko_spectok.bpe.model', 'am.mvn')):
            return 'sensevoice', path
        if all((path / name).is_file() and (path / name).stat().st_size > 0 for name in (
                'model.int8.onnx', 'tokens.txt')):
            return 'sensevoice_int8', path
        if all((path / name).is_file() for name in ('model.bin', 'config.json', 'tokenizer.json')):
            return 'whisper', path
    raise ValueError('没有完整的本地语音模型，请配置 CHZ_ASR_MODEL 指向完整的 SenseVoiceSmall、SenseVoiceSmall INT8 或 Whisper 模型目录')


def model_path():
    return model_spec()[1]


def _check_sensevoice_dependencies(engine):
    model, requirements, packages = _SENSEVOICE_DEPENDENCIES[engine]
    missing = [name for name in packages if importlib.util.find_spec(name) is None]
    if missing:
        raise VoiceUnavailable(f'{model} 缺少推理依赖：' + '、'.join(missing)
                               + f'。请在服务使用的 Python 环境安装 {requirements}')


def status():
    engine, error, loaded = None, '', False
    try:
        engine, path = model_spec()
        if engine in _SENSEVOICE_DEPENDENCIES:
            _check_sensevoice_dependencies(engine)
        loaded = _model is not None and _model_key == (engine, str(path))
        ready = True
    except (ValueError, VoiceUnavailable) as exc:
        error = str(exc)
        ready = False
    recognition = 'Whisper' if engine == 'whisper' else '本地语音未配置'
    if engine in _SENSEVOICE_DEPENDENCIES:
        recognition = _SENSEVOICE_DEPENDENCIES[engine][0]
    return {'recognition_ready': ready, 'synthesis_ready': os.name == 'nt',
            'recognition': recognition + ' · 本机 CPU',
            'recognition_loaded': loaded, 'recognition_error': error,
            'synthesis': 'Windows 服务器本地语音' if os.name == 'nt' else '使用浏览器设备中文语音',
            'audio_leaves_device': True}


def _load_model(engine, path):
    if engine in _SENSEVOICE_DEPENDENCIES:
        _check_sensevoice_dependencies(engine)
    if engine == 'sensevoice':
        from backend.sensevoice import load_model
        return load_model(path)
    if engine == 'sensevoice_int8':
        from sherpa_onnx import OfflineRecognizer
        return OfflineRecognizer.from_sense_voice(
            model=str(path / 'model.int8.onnx'), tokens=str(path / 'tokens.txt'),
            num_threads=1, language='auto', use_itn=True, provider='cpu')
    from faster_whisper import WhisperModel
    return WhisperModel(str(path), device='cpu', compute_type='int8', cpu_threads=2,
                        num_workers=1, local_files_only=True)


def _sensevoice_text(model, audio, int8=False):
    texts = []
    # 官方单段推理限制为30秒；沿用接口90秒上限，顺序识别且不共享跨用户cache。
    for offset in range(0, len(audio), 30 * 16000):
        segment = audio[offset:offset + 30 * 16000]
        if int8:
            stream = model.create_stream()
            stream.accept_waveform(16000, segment)
            model.decode_stream(stream)
            texts.append(stream.result.text.strip())
            continue
        result = model.generate(input=segment, cache={},
                                language='auto', use_itn=True, batch_size=1)
        if not isinstance(result, list) or not result or any(
                not isinstance(row, dict) or not isinstance(row.get('text'), str) for row in result):
            raise VoiceUnavailable('SenseVoice 返回了无效的转写结果，请重试或检查本地模型')
        texts.extend(re.sub(r'<\|[^|]*\|>', '', row['text']).strip() for row in result)
    return ' '.join(text for text in texts if text)


def _decode_mono(content):
    resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
    frames = []
    seconds = 0
    with av.open(io.BytesIO(content)) as container:
        for frame in container.decode(audio=0):
            seconds += frame.samples / frame.sample_rate
            if seconds > 90:
                raise ValueError('单段语音最多90秒，请分段输入')
            frame.pts = None
            frames.extend(part.to_ndarray().ravel() for part in resampler.resample(frame))
        frames.extend(part.to_ndarray().ravel() for part in resampler.resample(None))
    if not frames:
        raise ValueError('音频没有可识别的采样')
    return np.concatenate(frames).astype(np.float32) / 32768.0


def transcribe(content):
    global _model, _model_key
    if not content or len(content) > 12 * 1024 * 1024:
        raise ValueError('音频为空或超过12MB')
    if not _lock.acquire(timeout=2):
        raise ValueError('本地语音正在处理，请稍后重试')
    try:
        # 逐帧限制时长，避免解压超长录音，并保留单声道 16 kHz 输入口径。
        audio = _decode_mono(content)
        if len(audio) < 1600 or np.max(np.abs(audio)) < .002:
            return {'text': '', 'duration': round(len(audio) / 16000, 2), 'local': True}
        engine, path = model_spec()
        try:
            key = (engine, str(path))
            if _model is None or _model_key != key:
                model = _load_model(engine, path)
                _model, _model_key = model, key
            if engine in _SENSEVOICE_DEPENDENCIES:
                text = _sensevoice_text(_model, audio, int8=engine == 'sensevoice_int8')
            else:
                segments, _ = _model.transcribe(audio, language='zh', beam_size=3, vad_filter=True,
                                                condition_on_previous_text=False)
                text = ''.join(segment.text for segment in segments).strip()
        except (ImportError, OSError, RuntimeError, AssertionError, KeyError, TypeError) as exc:
            if isinstance(exc, VoiceUnavailable):
                raise
            raise VoiceUnavailable('本地语音模型加载或识别失败，请检查模型与推理依赖：' + type(exc).__name__) from exc
        text = OpenCC('t2s').convert(text)
        return {'text': text, 'duration': round(len(audio) / 16000, 2), 'local': True}
    finally:
        _lock.release()


def synthesize(text, root):
    if not text.strip() or len(text) > 1800:
        raise ValueError('播报文字长度需要在1至1800字符之间')
    if os.name != 'nt':
        raise VoiceUnavailable('此服务器未提供 Windows 中文朗读，请使用浏览器设备的本地中文语音')
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
