"""部署时为缺少比赛资料的新实例补齐只读参考聚合。"""
import gzip
import json
from functools import lru_cache

from backend.demo_seed import REFERENCE


@lru_cache(maxsize=1)
def reference_bundle():
    if not REFERENCE.is_file():
        return []
    data=json.loads(gzip.decompress(REFERENCE.read_bytes()))
    allowed={'competition_evidence','demand_observatory','market_catalog'}
    if data.get('version')!=1 or any(e['kind'] not in allowed for e in data['entities']):
        raise ValueError('比赛参考包格式不正确')
    return data['entities']


def import_reference(store):
    added=0
    for entry in reference_bundle():
        if store.get(entry['id']) is None:
            store.save(entry['kind'],entry['owner'],entry['data'],entry['id'])
            added+=1
    return added
