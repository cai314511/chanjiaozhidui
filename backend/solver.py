"""统一本机HiGHS运行配置，保持所有求解目标和硬约束。"""
import sys
from scipy.optimize import milp as scipy_milp


def milp(*args, options=None, **kwargs):
    configured = dict(options or {})
    if sys.platform == 'win32':
        # Windows原生并行MIP存在访问冲突；显式使用单线程，仍执行真实求解。
        configured['threads'] = 1
    return scipy_milp(*args, options=configured, **kwargs)
