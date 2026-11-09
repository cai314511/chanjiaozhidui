"""检查密钥鉴权和配置的模型ID；不打印密钥或服务端原始错误正文。"""
import argparse
import sys
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.agent import configuration


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--call',action='store_true',help='额外发送一次极短生成请求')
    args=parser.parse_args()
    config=configuration()
    if not config['key']:
        raise SystemExit('未读取到DeepSeek密钥，请在服务器.env设置DEEPSEEK_API_KEY')
    try:
        with httpx.Client(timeout=45) as client:
            headers={'Authorization':'Bearer '+config['key']}
            response=client.get(config['base']+'/models',headers=headers)
            if response.status_code!=200:raise SystemExit('模型列表鉴权失败，HTTP '+str(response.status_code))
            models=[m['id'] for m in response.json()['data']]
            print('鉴权成功；当前模型：'+config['model'])
            if config['model'] not in models:raise SystemExit('模型ID无效，可用模型：'+', '.join(models))
            if args.call:
                response=client.post(config['base']+'/chat/completions',headers=headers,
                    json={'model':config['model'],'messages':[{'role':'user','content':'仅回复OK'}],
                          'thinking':{'type':'disabled'},'max_tokens':32})
                if response.status_code!=200:raise SystemExit('生成请求失败，HTTP '+str(response.status_code))
                message=response.json()['choices'][0]['message'].get('content','').strip()
                if not message:raise SystemExit('接口返回空回复')
                print('实际生成成功；回复：'+message)
    except httpx.HTTPError as exc:
        raise SystemExit('连接失败：'+type(exc).__name__) from None


if __name__=='__main__':main()
