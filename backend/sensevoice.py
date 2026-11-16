"""SenseVoice 的本地 CPU 推理及 Windows 中文路径适配。"""
from pathlib import Path

import sentencepiece as spm
from funasr import AutoModel
from funasr.register import tables
from funasr.tokenizer.sentencepiece_tokenizer import SentencepiecesTokenizer


@tables.register('tokenizer_classes', 'LocalSentencepiecesTokenizer')
class LocalSentencepiecesTokenizer(SentencepiecesTokenizer):
    def _build_sentence_piece_processor(self):
        # SentencePiece C++文件接口在Windows中文路径下失败；直接读取原模型字节。
        if self.sp is None:
            self.sp = spm.SentencePieceProcessor(model_proto=Path(self.bpemodel).read_bytes())


def load_model(path):
    return AutoModel(model=str(path), tokenizer='LocalSentencepiecesTokenizer',
                     device='cpu', ncpu=2, disable_update=True, disable_pbar=True,
                     trust_remote_code=False, ignore_init_mismatch=False)
