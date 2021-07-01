import enum
from enum import auto
import oss2
import logging

class CloudUploadType(enum.Enum):
    BUFFER=auto()
    STRING=auto()

class CloudBucket:
    @staticmethod
    def imageBucket():
        return "whiteboard-kejian-image"
    
    @staticmethod
    def imageEndpoint():
        return "http://oss-cn-hangzhou-internal.aliyuncs.com"

    @staticmethod
    def jsonBucket():
        return "fudaojun-jboard"

    @staticmethod
    def jsonEndpoint():
        return "http://oss-cn-hangzhou-internal.aliyuncs.com"

    @staticmethod
    def pptBucket():
        return "whiteboard-kejian-image"
    
    @staticmethod
    def pptEndpoint():
        return "http://oss-cn-hangzhou-internal.aliyuncs.com"

class Cloud:
    def __init__(self):
        self.auth=oss2.Auth('BdFAtfGAKHrPxAQL','KqHSBj0tWGylscEDTb57u5Cb1a0rCW')

    def upload(self,endpoint,bucketName,objectName,cloudUploadType,file):
        """
        阿里云 OSS文件上传.
        """
        bucket=oss2.Bucket(self.auth,endpoint,bucketName)
        try:
            if cloudUploadType==CloudUploadType.BUFFER:
                result=bucket.put_object(objectName,b'%s'%(file))
                return result.status
            elif cloudUploadType==CloudUploadType.STRING:
                result=bucket.put_object(objectName,file)
                return result.status
        except Exception as e:
            logging.error("OSS上传失败：%s 原因: %s", str(bucketName)+"/"+str(objectName), e)
            # oss上传失败值
            return 203

    def download(self,endpoint,bucketName,objectName,file):
        bucket=oss2.Bucket(self.auth,endpoint,bucketName)
        try:
            result=bucket.get_object_to_file(objectName,file)
            return result.status
        except Exception as e:
            logging.error("OSS下载失败：%s 原因: %s", str(file), e)
            return 203
