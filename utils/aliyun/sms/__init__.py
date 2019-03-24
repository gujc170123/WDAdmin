# -*- coding: utf-8 -*-
import json
import random

# from utils import get_random_str
from utils.aliyun.com.aliyun.api.gateway.sdk import client
from utils.aliyun.com.aliyun.api.gateway.sdk.http import request
from utils.aliyun.com.aliyun.api.gateway.sdk.common import constant
from utils.aliyun.com.aliyun.api.gateway.sdk.util import DateUtil
# from utils.logger import xd_logger
from utils.logger import get_logger

logger = get_logger("sms")


class Sms(object):
    HOST = "http://sms.aliyuncs.com"
    SIGN = u"维度平台"
    # HOST = "http://sms.market.alicloudapi.com"
    body = {
        "AccessKeyId": "",
        "Action": "SingleSendSms",
        "ParamString": "",
        "RecNum": "",
        "SignName": SIGN.encode("utf-8"),
        "TemplateCode": "",
        "Format": "JSON",
        "Version": "2016-09-27",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": "",
        "Timestamp": DateUtil.get_iso_8061_date()
    }
    URL = "/?Action=SingleSendSms" \
          + "AccessKeyId=" \
          + '&ParamString=%(param_str)s' \
          + "&RecNum=%(phone_numbers)s" \
          + "&SignName=维度平台" \
          + "&TemplateCode=%(template_code)s"\
          + "&Format=JSON"\
          + "&Version=2015-04-01"\
          + "&SignatureMethod=HMAC-SHA1"\
          + "&SignatureVersion=1.0"\
          + "&SignatureNonce=" + str("12345")\
          + "&Timestamp=" + DateUtil.get_iso_8061_date()

    @classmethod
    def __send_sms(cls, url, method="POST", time_out=30000):
        cli = client.DefaultClient(app_key="", app_secret="")
        req_post = request.Request(host=cls.HOST, protocol=constant.HTTP, url=cls.HOST, method=method, time_out=30000)
        # req = request.Request(host=cls.HOST, url=url, method=method, time_out=time_out)
        req_post.set_body(bytearray(source=json.dumps(cls.body), encoding="utf8"))
        req_post.set_content_type(constant.CONTENT_TYPE_STREAM)
        return cli.execute(req_post)

    @classmethod
    def __get_url(cls, param_str, phone_list, template_code):
        cls.body["ParamString"] = param_str
        cls.body["RecNum"] = ",".join(phone_list)
        cls.body["TemplateCode"] = template_code
        # cls.body["SignatureNonce"] = str(get_random_str(24))
        cls.body["Timestamp"] = DateUtil.get_iso_8061_date()

    @classmethod
    def send_general_code(cls, code, phone_list):
        try:
            result = cls.__send_sms(cls.__get_url(json.dumps({"code": code}), phone_list, "SMS_34905145"))
            logger.debug("send sms end: result is %s" %result[2])
        except Exception, e:
            logger.error("send sms error, msg(%s)" %e)

