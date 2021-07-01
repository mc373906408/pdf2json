# 部署
## 依赖库安装
- pip install pymupdf
- pip install pdfplumber
- pip install oss2
- pip install pythonnet
- pip install redis
- pip install flask
- pip install celery
- pip install gevent
- pip install wfastcgi
- pip install flask_cors

## 数据库安装
- https://github.com/microsoftarchive/redis/releases/tag/win-3.0.504
- https://www.rabbitmq.com/install-windows.html
- 需要设置下RabbitMQ，添加root 123456 用户名为管理员，再加到 / 项目内，新建develop项目作为测试环境队列

## 搭建网站
- https://www.jianshu.com/p/8b6b263144ba

## 启动
- 启动celery
- celery worker -A foo:client -n [name] --pool=gevent -l warning

## 正式环境与测试环境切换
- *_master和*_develop重命名替换原文件
- 替换根目录下web.config
- 替换foo/fdjWebService/celeryconfig.py

# 规范
## 代码规范
1. 外部自定义变量前面加'm_'
2. 外部自定义方法前面加'f_'
3. pymupdf对象前面加'mu_'
4. pdfplumber对象前面加'pl_'

## 目录规范
- 代码类文件放在foo/fdj[Name]/fdj[Name].py内

## 文档
1. https://blog.csdn.net/robolinux/article/details/43318229
2. https://blog.csdn.net/shao824714565/article/details/84792089
3. https://blog.csdn.net/zyc121561/article/details/77877912
4. https://www.jiqizhixin.com/articles/2018-11-28-9
5. https://pymupdf.readthedocs.io/en/latest/faq.html

## log
- info等级会输出pdf解析库中一些乱七八糟的信息，所以手动输出的用warn来替代info输出需要的数据


### 发布日志

#### 1.0.2

- 1. 增加日志追踪功能.

> 2021-02-20


#### 1.0.1

- 1. 修改文档的粗体样式.

> 2020-12-29
