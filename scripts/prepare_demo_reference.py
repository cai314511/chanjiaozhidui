"""只导出比赛资料白名单聚合，不包含账号、会话、简历和用户上传。"""
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.store import Store

ALLOWED = {
    'competition-evidence-v1': ('competition_evidence', 'competition-reference'),
    'demand-observatory-v1': ('demand_observatory', 'local-demand-import'),
    'market-catalog-v1': ('market_catalog', 'local-market-import'),
}


def main():
    store=Store(ROOT/'data/private')
    rows=[]
    for ident,(kind,owner) in ALLOWED.items():
        item=store.get(ident,kind)
        if item is None or item['owner']!=owner:
            raise ValueError('缺少已导入的比赛聚合：'+ident)
        rows.append({k:item[k] for k in ['id','kind','owner','data']})
    folder=ROOT/'data/demo-reference'
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/'reference.json.gz'
    path.write_bytes(gzip.compress(json.dumps({'version':1,'entities':rows},ensure_ascii=False).encode(),mtime=0))
    print('已导出3类比赛聚合，压缩大小：',path.stat().st_size)


if __name__=='__main__':main()
