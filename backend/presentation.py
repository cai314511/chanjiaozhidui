import re


def match_summary(result):
    details = result.get('employer', {}).get('details', [])
    known = any(row.get('level') is not None for row in details)
    return {'status': result['status'], 'provisional': result['provisional'] if known else None,
            'has_evidence': known, 'confirmed': result['status'] == 'eligible',
            'message': '已完成材料核验' if result['status'] == 'eligible' else
                       '必要条件尚未满足，请核对岗位要求' if result['status'] == 'excluded' else
                       '结果基于当前材料，补充经历或参加面试后可以更新'}


def public_product(value):
    if isinstance(value, list):
        return [public_product(item) for item in value]
    if not isinstance(value, dict):
        return value
    if 'employer' in value and 'provisional' in value and 'sensitivity' in value:
        return match_summary(value)
    return {key: public_product(item) for key, item in value.items()
            if key not in {'weight', 'weights', 'raw_weight', 'sensitivity', 'contribution', 'target'}}


def parameter_question(message):
    return bool(re.search(r'权重|公式|算法参数|评分细则|评分明细|贡献分|系统提示|提示词|model.rules|weight|formula|system.prompt', message, re.I))


PARAMETER_REPLY = '匹配会结合岗位要求、你的经历和双方偏好综合评估。我可以帮你检查材料是否完整、说明需要核实的经历，并建议下一步准备内容。具体计算参数由系统管理。'
