import logging

from celery._state import get_current_task

class Formatter(logging.Formatter):
    """Formatter for tasks, adding the task name and id."""

    def format(self, record):
        task = get_current_task()
        if task and task.request:
            record.__dict__.update(task_id='%s ' % task.request.id,
                                   task_name='%s ' % task.name)
        else:
            record.__dict__.setdefault('task_name', '')
            record.__dict__.setdefault('task_id', '')
        return logging.Formatter.format(self, record)

root_logger = logging.getLogger() # 返回logging.root
root_logger.setLevel(logging.DEBUG)

# 将日志输出到文件
fh = logging.FileHandler('log\celery_worker.log') # 这里注意不要使用TimedRotatingFileHandler，celery的每个进程都会切分，导致日志丢失
formatter = Formatter('[%(task_name)s%(task_id)s%(process)s %(thread)s %(asctime)s %(pathname)s:%(lineno)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
fh.setFormatter(formatter)
fh.setLevel(logging.DEBUG)
root_logger.addHandler(fh)

# 将日志输出到控制台
sh = logging.StreamHandler()
formatter = Formatter('[%(task_name)s%(task_id)s%(process)s %(thread)s %(asctime)s %(pathname)s:%(lineno)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
sh.setFormatter(formatter)
sh.setLevel(logging.INFO)
root_logger.addHandler(sh)

class CeleryConfig(object):
    BROKER_URL = 'amqp://root:123456@localhost:5672/develop'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
    CELERY_ENABLE_UTC = True # 启用UTC时区
    CELERY_TIMEZONE = 'Asia/Shanghai' # 上海时区
    CELERYD_HIJACK_ROOT_LOGGER = False # 拦截根日志配置
    CELERYD_MAX_TASKS_PER_CHILD = 1 # 每个进程最多执行1个任务后释放进程（再有任务，新建进程执行，解决内存泄漏）