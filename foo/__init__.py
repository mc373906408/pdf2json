from flask import Flask,request
from celery import Celery
from foo.fdjWebService.celeryconfig import CeleryConfig
import logging
from foo.fdjAnalyzePDF.fdjAnalyzePDF import AnalyzePDF
from redis import Redis
import json
from flask_cors import CORS

app = Flask(__name__)

CORS(app,supports_credentials=True)

redis=Redis(host="127.0.0.1",port=6379,db=0)
rebbitmq_list="rebbitmq_list"

def make_celery(app=None):
    """
    启动项目：celery worker -A foo:client -n [name] --pool=gevent -l warning
    """
    celery=Celery(__name__)
    celery.config_from_object(CeleryConfig)
    celery.conf.update(app.config)
    TaskBase = celery.Task
    class ContextTask(TaskBase):
        abstract = True
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask
    return celery

client = make_celery(app)

@client.task(bind=True)
def ppt2json(self,url, *args, **kwargs):
    logging.warn(f"执行任务:{url}")
    # 删除list中第一个，因为任务进入执行阶段，去掉一个排队者
    redis.lpop(rebbitmq_list)
    m_AnalyzePDF=AnalyzePDF()
    return m_AnalyzePDF.run(url)

@app.route('/ppturl/', methods=['GET'])
def ppturl():
    url = request.args.get("url")
    redis_key=url.split('/')[-1].split('.')[0]
    if redis.exists(redis_key)==1:
        resmap={}
        resmap["data"]={}
        resmap["data"]["url"]=str(redis.get(redis_key),'utf-8')
        resmap["retcode"]=1
        return json.dumps(resmap)
    
    result=ppt2json.delay(url)
    # 将任务向后加入队列，增加排队者
    redis.rpush(rebbitmq_list,str(result.id))
    resmap={}
    resmap["data"]={}
    resmap["data"]["id"]=result.id
    resmap["data"]["progress_id"]=redis_key
    resmap["retcode"]=0
    return json.dumps(resmap)


@app.route('/result/',methods=['GET'])
def result():
    id=request.args.get('id')
    md5=request.args.get('progress_id')
    progress_id="progress_"+md5
    error_id="error_"+md5
    redis_key=f'celery-task-meta-{id}'
    if redis.exists(redis_key)==1:
        result = json.loads(redis.get(redis_key))
        res= result['result']
        if res == "error":
            # 失败
            resmap={}
            resmap["data"]={}
            if redis.exists(error_id)==1:
                resmap["errormsg"]=str(redis.get(error_id),'utf-8')
            resmap["retcode"]=-1
            return json.dumps(resmap)
        else:
            # 成功
            resmap={}
            resmap["data"]={}
            resmap["data"]["url"]=res
            resmap["retcode"]=1
            return json.dumps(resmap)
    else:
        # 进行中
        resmap={}
        resmap["data"]={}
        resmap["data"]["queue"]=0
        for index,i in enumerate(redis.lrange(rebbitmq_list,0,-1)):
            if str(i,'utf-8')==id:
                resmap["data"]["queue"]=index+1
                break
        
        resmap["data"]["progress"]=0
        if resmap["data"]["queue"]==0:
            if redis.exists(progress_id)==1:
                resmap["data"]["progress"]=int(str(redis.get(progress_id),'utf-8'))

        resmap["retcode"]=0
        return json.dumps(resmap)