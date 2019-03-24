# -*- coding: utf-8 -*-
import base64
import hashlib
import hmac
import json
import os

import time

import datetime
from aliyunsdkcore import client
from aliyunsdksts.request.v20150401 import AssumeRoleRequest

import oss2


# 以下代码展示了STS的用法，包括角色扮演获取临时用户的密钥、使用临时用户的密钥访问OSS。

# STS入门教程请参看  https://yq.aliyun.com/articles/57895
# STS的官方文档请参看  https://help.aliyun.com/document_detail/28627.html
# https://help.aliyun.com/document_detail/32033.html?spm=a2c4g.11186623.6.697.8ydFD0
# https://develop.aliyun.com/tools/sdk?#/python



class StsToken(object):
    """AssumeRole返回的临时用户密钥
    :param str access_key_id: 临时用户的access key id
    :param str access_key_secret: 临时用户的access key secret
    :param int expiration: 过期时间，UNIX时间，自1970年1月1日UTC零点的秒数
    :param str security_token: 临时用户Token
    :param str request_id: 请求ID
    """
    def __init__(self):
        self.access_key_id = ''
        self.access_key_secret = ''
        self.expiration = 3600
        self.security_token = ''
        self.request_id = ''

    @property
    def data(self):
        return {
            "access_key_id": self.access_key_id,
            "access_key_secret": self.access_key_secret,
            "expiration": self.expiration,
            "security_token": self.security_token,
            "request_id": self.request_id
        }


class AliyunOss(object):
    u"""
    首先初始化AccessKeyId、AccessKeySecret、Endpoint等信息。
    通过环境变量获取，或者把诸如“<你的AccessKeyId>”替换成真实的AccessKeyId等。
    注意：AccessKeyId、AccessKeySecret为子用户的密钥。
    RoleArn可以在控制台的“访问控制  > 角色管理  > 管理  > 基本信息  > Arn”上查看。

    以杭州区域为例，Endpoint可以是：
      http://oss-cn-hangzhou.aliyuncs.com
      https://oss-cn-hangzhou.aliyuncs.com
    分别以HTTP、HTTPS协议访问。
    """
    access_key_id = os.getenv('OSS_TEST_ACCESS_KEY_ID', 'LTAIPyZc9b1YAHZu')
    access_key_secret = os.getenv('OSS_TEST_ACCESS_KEY_SECRET', 'eCE3wwpde1LATG8fioBRoCXkjEtIfm')
    bucket_name = os.getenv('OSS_TEST_BUCKET', 'iwedoing-1')
    endpoint = os.getenv('OSS_TEST_ENDPOINT', 'oss-cn-hangzhou.aliyuncs.com')
    internal_endpoint = os.getenv('OSS_TEST_ENDPOINT', 'oss-cn-hangzhou-internal.aliyuncs.com')
    sts_role_arn = os.getenv('OSS_STS_ARN', 'acs:ram::1757413438297970:role/aliyunosstokengeneratorrole')
    backet_host = "https://"+bucket_name + "." + endpoint
    internal_backet_host = "https://"+bucket_name + "." + internal_endpoint

    def __init__(self):
        # 确认上面的参数都填写正确了
        for param in (self.access_key_id, self.access_key_secret, self.bucket_name, self.endpoint, self.sts_role_arn):
            assert '<' not in param, '请设置参数：' + param

    @classmethod
    def fetch_sts_token(cls):
        """子用户角色扮演获取临时用户的密钥
        :param access_key_id: 子用户的 access key id
        :param access_key_secret: 子用户的 access key secret
        :param role_arn: STS角色的Arn
        :return StsToken: 临时用户密钥
        """
        clt = client.AcsClient(cls.access_key_id, cls.access_key_secret, 'cn-shanghai')
        req = AssumeRoleRequest.AssumeRoleRequest()

        req.set_accept_format('json')
        req.set_RoleArn(cls.sts_role_arn)
        req.set_RoleSessionName('oss-python-sdk-example')

        body = clt.do_action_with_exception(req)

        j = json.loads(body)

        token = StsToken()

        token.access_key_id = j['Credentials']['AccessKeyId']
        token.access_key_secret = j['Credentials']['AccessKeySecret']
        token.security_token = j['Credentials']['SecurityToken']
        token.request_id = j['RequestId']
        token.expiration = oss2.utils.to_unixtime(j['Credentials']['Expiration'], '%Y-%m-%dT%H:%M:%SZ')

        return token

    @classmethod
    def web_upload_param(cls):
        # token = cls.fetch_sts_token()
        expire_time = (datetime.datetime.now()+datetime.timedelta(hours=12)).strftime('%Y-%m-%dT%H:%M:%SZ')
        policy = "{\"expiration\":\"%s\",\"conditions\":[[\"content-length-range\", 0, 104857600]]}" % expire_time
        base64policy = base64.b64encode(policy)
        signature = base64.encodestring(hmac.new(cls.access_key_secret, base64policy, hashlib.sha1).digest()).strip()
        return {
            "policy": base64policy,
            "signature": signature,
            "access_id": cls.access_key_id,
            "host": cls.backet_host
        }

    def upload_file(self, user_id, file_name, file_full_path, prefix='wdadmin'):
        now = int(time.time())
        if not hasattr(self, "token") or self.token is None or self.token.expiration < now-1:
            self.token = self.fetch_sts_token()
        auth = oss2.StsAuth(self.token.access_key_id, self.token.access_key_secret, self.token.security_token)
        bucket = oss2.Bucket(auth, AliyunOss.endpoint, AliyunOss.bucket_name)
        # bucket.put_object('test2/motto.txt', 'Never give up. - Jack Ma')
        file_key = "%s/%s/%s" % (prefix, user_id, file_name)
        bucket.put_object_from_file(file_key, file_full_path)
        return self.backet_host + "/" + file_key

    def upload_data(self, user_id, data, file_name):
        now = int(time.time())
        if not hasattr(self, "token") or self.token is None or self.token.expiration < now - 1:
            self.token = self.fetch_sts_token()
        auth = oss2.StsAuth(self.token.access_key_id, self.token.access_key_secret, self.token.security_token)
        bucket = oss2.Bucket(auth, AliyunOss.endpoint, AliyunOss.bucket_name)
        # bucket.put_object('test2/motto.txt', 'Never give up. - Jack Ma')
        file_key = "%s/%s" % (user_id, file_name)
        bucket.put_object(file_key, data)
        return self.backet_host + "/" + file_key

# token = AliyunOss.fetch_sts_token()

# 创建Bucket对象，所有Object相关的接口都可以通过Bucket对象来进行
# token = AliyunOss.fetch_sts_token()
# auth = oss2.StsAuth(token.access_key_id, token.access_key_secret, token.security_token)
# bucket = oss2.Bucket(auth, AliyunOss.endpoint, AliyunOss.bucket_name)
#
#
# # 上传一段字符串。Object名是motto.txt，内容是一段名言。
# bucket.put_object('test2/motto.txt', 'Never give up. - Jack Ma')