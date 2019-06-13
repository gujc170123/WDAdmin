# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json
import os
import time
from django.http import FileResponse, HttpResponse
from io import BytesIO
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.renderers import TemplateHTMLRenderer

from utils import get_random_char_list, get_random_int, data2file
from utils.aliyun.email import EmailUtils
from utils.aliyun.oss import AliyunOss
from utils.aliyun.sms.newsms import Sms
from utils.cache.cache_utils import VerifyCodeExpireCache
from utils.piccode import create_piccode
from utils.regular import RegularUtils
from utils.response import general_json_response, ErrorCode
from utils.views import AuthenticationExceptView, WdAPIView, WdListAPIView, WdCreateAPIView
from wduser.tasks import send_general_code
from wduser.user_utils import UserAccountUtils


class AliWebUploadView(AuthenticationExceptView, WdAPIView):

    def get(self, request, *args, **kwargs):
        is_auth = False
        user_id = 0
        if hasattr(request, "user") and request.user.is_authenticated:
            is_auth = True
            user_id = request.user.id
        web_upload_param = AliyunOss.web_upload_param()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {
            "params": web_upload_param,
            "is_auth": is_auth,
            "user_id": user_id
        })


class PicCodeGetView(AuthenticationExceptView, WdAPIView):
    u"""生成图片验证"""

    renderer_classes = (TemplateHTMLRenderer,)

    def get(self, request, *args, **kwargs):
        codes = get_random_char_list(5)
        cache_code = "".join(codes)
        VerifyCodeExpireCache('picture-%s' % cache_code).set_verify_code(cache_code)
        value = create_piccode(codes)
        return HttpResponse(value)


class VerifyCodeView(AuthenticationExceptView, WdListAPIView):
    u"""验证码获取接口"""

    GET_CHECK_REQUEST_PARAMETER = ("pic_code", "account")

    def get(self, request, *args, **kwargs):
        verify_type = self.request.GET.get("verify_type", "forget_pwd")
        user = None
        if verify_type == "forget_pwd":
            user, check_code = UserAccountUtils.account_check(self.account)
            if check_code != ErrorCode.SUCCESS:
                return general_json_response(status.HTTP_200_OK, check_code)
        elif verify_type == "info_modify":
            user, check_code = UserAccountUtils.account_check(self.account)
            if check_code == ErrorCode.SUCCESS:
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_EXISTS)
        else:
            # register
            pass
        # account = request.data.get('account', None)
        # user, check_code = UserAccountUtils.account_check(account)
        # 不存在的用户，注册，也可以获取验证码
        # if check_code != ErrorCode.SUCCESS:
            # return general_json_response(status.HTTP_200_OK, check_code)
        pic_code_verify = VerifyCodeExpireCache('picture-%s' % self.pic_code).check_verify_code(self.pic_code)
        if not pic_code_verify:
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PIC_CODE_INVALID)
        code = get_random_int()
        # verify_key = self.account if user is None else user.id
        VerifyCodeExpireCache(self.account).set_verify_code(code)
        # send code
        if user is not None:
            send_general_code.delay(code, user.phone, user.email)
            # if user.phone:
            #     Sms.send_general_code(code, [user.phone])
            # if user.email:
            #     # TODO: 发送邮件验证码
            #     EmailUtils().send_general_code(code, user.email)
        else:

            if RegularUtils.phone_check(self.account):
                send_general_code.delay(code, phone=self.account)
                # Sms.send_general_code(code, [self.account])
            elif RegularUtils.email_check(self.account):
                send_general_code(code, email=self.account)
                # EmailUtils().send_general_code(code, self.account)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class VerifyCodeCheckView(AuthenticationExceptView, WdListAPIView):
    u"""校验码验证"""

    def get(self, request, *args, **kwargs):
        account = request.GET.get('account', None)
        verify_code = request.GET.get("verify_code", None)
        rst = VerifyCodeExpireCache(account).check_verify_code(verify_code, False)
        if not rst:
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_VERIFY_CODE_INVALID)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class FileUploadView(AuthenticationExceptView, WdCreateAPIView):
    u"""图片上传, 题干 选项 用到"""

    def post(self, request, *args, **kwargs):
        self.parser_classes = (MultiPartParser,)
        file_data = request.data["file"]
        file_name = request.data["original_filename"]
        # assess_id = request.data["assess_id"]
        # survey_id = request.data["survey_id"]
        # email = request.data.get("email", None)
        suffix = os.path.splitext(file_name)[1]
        file_name = '%s%s' % (str(int(time.time()*1000)), suffix)
        file_path = data2file(file_data, file_name)
        try:
            user_id = self.request.user.id
        except:
            user_id = 0
        url = AliyunOss().upload_file(user_id, file_name, file_path)
        return HttpResponse(json.dumps({
            "success": True,
            "msg": 'upload success',
            "file_path": url
        }))