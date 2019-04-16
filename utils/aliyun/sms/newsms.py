# -*- coding: utf-8 -*-
import time
from aliyunsdkcore.profile import region_provider

from utils import get_random_str
from utils.aliyun.aliyunsdkdysmsapi.request.v20170525 import SendSmsRequest
from aliyunsdkcore.client import AcsClient

from utils.logger import get_logger

u"""
短信产品-发送短信接口
Created on 2017-06-12
https://help.aliyun.com/document_detail/55491.html?spm=5176.10629532.106.3.4a7ac541cSg5o3
"""

logger = get_logger("utils")


class Sms(object):
    SIGN = u"格略"
    REGION = "cn-hangzhou"  # 暂时不支持多region
    PRODUCT_NAME = "Dysmsapi"
    DOMAIN = "dysmsapi.aliyuncs.com"
    ACCESS_KEY_ID = "h8fxi7Zp48PaOVqJ"
    ACCESS_KEY_SECRET = "Wfj7oFtsuPQ7q1myrRpACRAonv5oLf"
    acs_client = AcsClient(ACCESS_KEY_ID, ACCESS_KEY_SECRET, REGION)
    region_provider.add_endpoint(PRODUCT_NAME, REGION, DOMAIN)

    @classmethod
    def __send_sms(cls, business_id, phone_number, template_code, template_param=None):
        smsRequest = SendSmsRequest.SendSmsRequest()
        # 申请的短信模板编码,必填
        smsRequest.set_TemplateCode(template_code)
        # 短信模板变量参数,友情提示:如果JSON中需要带换行符,请参照标准的JSON协议对换行符的要求,比如短信内容中包含\r\n的情况在JSON中需要表示成\\r\\n,否则会导致JSON在服务端解析失败
        if template_param is not None:
            smsRequest.set_TemplateParam(template_param)
        # 设置业务请求流水号，必填。
        smsRequest.set_OutId(business_id)
        # 短信签名
        smsRequest.set_SignName(Sms.SIGN.encode("utf-8"))
        # 短信发送的号码，必填。支持以逗号分隔的形式进行批量调用，批量上限为1000个手机号码,批量调用相对于单条调用及时性稍有延迟,验证码类型的短信推荐使用单条调用的方式
        smsRequest.set_PhoneNumbers(phone_number)
        # 发送请求
        smsResponse = Sms.acs_client.do_action_with_exception(smsRequest)
        return smsResponse

    @classmethod
    def send_general_code(cls, code, phone_list):
        try:
            business_id = str(get_random_str(24))
            phone_nums = ",".join(phone_list)
            phone_param = {"code": code}
            template_code = "SMS_145596097"
            cls.__send_sms(business_id, phone_nums, template_code, phone_param)
        except Exception, e:
            logger.error("send sms error, msg(%s)" % e)

    @classmethod
    def send_activate_code(cls, code, phone_list):
        # TODO: 批量发送大量的，需要异步处理
        try:
            business_id = str(get_random_str(24))
            phone_param = {"code": str(code)}
            template_code = "SMS_143715662"
            index = 0
            send_phone_list = phone_list[index: index+1000]
            while len(send_phone_list) > 0:
                phone_nums = ",".join(send_phone_list)
                cls.__send_sms(business_id, phone_nums, template_code, phone_param)
                time.sleep(3)
                index += 1000
                send_phone_list = phone_list[index: index + 1000]
        except Exception, e:
            logger.error("send sms error, msg(%s)" % e)