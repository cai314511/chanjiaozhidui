import base64
from pathlib import Path

from backend.voice import synthesize
from tests.test_browser import browser_system, register


def test_real_audio_stream_has_interim_and_final_text(browser_system):
    browser, base = browser_system
    page = browser.new_page()
    register(page, base, 'student', 'streaming-student')
    root = Path(__file__).resolve().parents[1] / 'runtime' / 'voice-verification'
    root.mkdir(parents=True, exist_ok=True)
    audio = synthesize('我完成了一个数据分析项目。我负责整理数据，分析结果，并且制作项目报告。', root)
    result = page.evaluate('''async encoded => {
      const {ContinuousTranscriber} = await import('/assets/transcription.js');
      const context = new AudioContext(); await context.resume();
      const buffer = await context.decodeAudioData(Uint8Array.from(atob(encoded), c=>c.charCodeAt(0)).buffer);
      const source = context.createBufferSource(); source.buffer=buffer;
      const destination=context.createMediaStreamDestination(); source.connect(destination);
      const interim=[], final=[], errors=[];const started=performance.now();
      const recorder=new ContinuousTranscriber({onInterim:t=>{if(t)interim.push({text:t,ms:performance.now()-started})},onFinal:t=>final.push(t),onError:e=>errors.push(e.message)});
      await recorder.start(destination.stream); source.start();
      await new Promise(resolve=>source.onended=resolve);
      await recorder.stop(); await context.close();
      return {interim,final,errors,duration:buffer.duration};
    }''', base64.b64encode(audio).decode())
    assert result['interim'], result
    assert result['errors'] == [], result
    assert result['interim'][0]['ms'] < result['duration'] * 1000, result
    assert '项目' in ''.join(result['final']), result
    import json
    (root / 'streaming-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    page.close()
