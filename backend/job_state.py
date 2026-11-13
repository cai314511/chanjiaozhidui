"""统一可接受新投递、进入需求统计和新增招聘分配的岗位范围。"""


def active_job(job):
    return (not job.get('deleted') and not job.get('closed')
            and job.get('status', 'published') == 'published')
