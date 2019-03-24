# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.conf.urls import url

from utils.api_views import AliWebUploadView, PicCodeGetView, VerifyCodeView, FileUploadView, VerifyCodeCheckView

urlpatterns = [
    # 阿里云OSS Web上传
    url(r"^web/upload/$", AliWebUploadView.as_view(), name="oss-web-upload-view"),
    # 获取图片验证码
    url(r"^piccode/$", PicCodeGetView.as_view(), name="piccode-get-view"),
    # 短信/邮件验证码
    url(r"^verify-code/$", VerifyCodeView.as_view(), name="verify-code-view"),
    url(r"^verify-code-check/$", VerifyCodeCheckView.as_view(), name="verify-code-check-view"),
    # 图片上传到本地
    url(r"^file-upload/$", FileUploadView.as_view(), name="file-upload-view")


]