# SenseVoice 本地语音接入与验收

## 发现及修复

原系统只支持 faster-whisper 的 `model.bin/config.json/tokenizer.json`；将 `.env.example` 的 `CHZ_WHISPER_MODEL` 指向 SenseVoice 权重不能启用新模型。语音模块原来仅读取进程环境，也不会读取这个模板。

本轮增加 SenseVoiceSmall 的 FunASR CPU 推理，实际加载当前 `models/SenseVoiceSmall` 下的 `model.pt`。支持从项目 `.env` 或进程环境读取 `CHZ_ASR_MODEL`，相对路径以项目根目录为准；保留旧 Whisper 配置和默认缓存。未显式配置时优先选择已存在的本地 SenseVoiceSmall 目录。

SentencePiece 在本机 Windows 中文路径下发生 `NOT_FOUND`。适配类使用 Python 读取原 BPE 模型字节交给 SentencePiece，不修改第三方安装文件、不改动训练词表。实际权重加载报告全部键匹配，并启用严格权重匹配。

保留12MB、90秒限制；SenseVoice 按30秒顺序分段，各段独立 cache。输出移除模型语言、情感及事件控制标签，仅填入可编辑文字。模型初始化和推理错误明确返回503，不使用其他模型掩盖失败。静音返回空文本，无效音频返回422，未登录请求返回401。

关闭 FunASR 更新检查及远程代码加载，使用已安装的模型实现；不配置在线 VAD，不自动下载权重。PyAV 负责解码，模型接收16kHz单声道数组，当前流程不要求系统 ffmpeg 命令。模型及录音保持在被忽略的本地目录；公开配置模板中的密钥值已清空。

## 实际验证

环境：Windows、项目 `.venv`，FunASR 1.4.26，PyTorch 2.13.0 CPU，Torchaudio 2.11.1。`python -m pip check` 返回无依赖冲突。

使用真实本地权重及目录中的中文、英文、粤语、日语、韩语五个示例音频，经登录后的 `/api/voice/transcribe` 调用，五次均返回200、非空文字、`local=true`，无控制标签。它们证明接口及语言处理能运行，不构成真实场景准确率评测。

已知内容的 Windows SAPI 合成音频：“你好，我希望申请数据分析岗位。我最近完成了一个项目。”，7.2秒，接口完整识别该句。随后在 Edge 中分别登录学生、企业、高校隔离账号，用该音频替代麦克风源，经过真实 MediaRecorder 编码和真实转写接口，三端均完整回填同一句，可手动修改，停止后音轨释放，页面无 JavaScript 错误。没有模拟识别结果、没有调用 DeepSeek。

实际样例耗时：首次中文请求19.880秒（含导入和加载）；其后英文1.677秒、粤语1.455秒、日语1.664秒、韩语1.345秒。音频长度4.64—7.22秒；该数字仅代表本机本轮短音频结果，不是响应时延保证。

验收进程禁止 Python 向外部地址建立连接，五个模型样例与三端浏览器流程全部完成，外网连接尝试记录为空。仅允许本机测试服务连接。状态显示 `SenseVoiceSmall · 本机 CPU`、`recognition_ready=true`、`recognition_loaded=true`。

证据位于 `runtime/sensevoice-check/acceptance.json` 及 `student.png`、`employer.png`、`university.png`；该目录不随 Git 上传。配置、30秒分段、独立cache、无效输出、初始化失败、503、身份认证及中文相对路径的自动化回归见 `tests/test_sensevoice.py`；连同既有本地合成识别、Agent录音及故障回归执行。

回归命令：`python -m pytest tests/test_sensevoice.py tests/test_local_voice.py tests/test_product_experience.py tests/test_agent_orb_browser.py tests/test_agent_capture_failures_browser.py -q -p no:cacheprovider --disable-warnings`，结果26项通过、4条依赖警告、无失败，101.70秒。`pip check` 及 `git diff --check` 通过。

## 使用与验收边界

先安装 `requirements.txt`，使用 SenseVoice 时再安装 `requirements-sensevoice.txt`。从[官方模型页](https://huggingface.co/FunAudioLLM/SenseVoiceSmall)自行放置完整模型目录，再设置 `CHZ_ASR_MODEL` 并重启；服务端不会下载模型。官方[短音频推理说明](https://huggingface.co/FunAudioLLM/SenseVoiceSmall/blob/main/README.md)给出30秒单段限制，系统保持现有90秒接口契约并顺序分段。

本轮确认的是本机真实模型与浏览器编码、转写、编辑全链路。实体麦克风、噪声、口音、长时间连续输入准确率及 AWS 上的 CPU/内存、依赖和权重尚未验收。GitHub 更新包含接入代码、配置说明和测试，模型权重不会上传；服务器仅拉取代码不会自动具备 SenseVoice 推理条件。
