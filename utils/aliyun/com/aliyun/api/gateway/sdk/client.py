# -*- coding:utf-8 -*-
#  Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
# coding=utf-8

import json
import urllib

from utils.aliyun.com.aliyun.api.gateway.sdk.util import UUIDUtil, DateUtil
from utils.aliyun.com.aliyun.api.gateway.sdk.http.request import Request
from utils.aliyun.com.aliyun.api.gateway.sdk.http.response import Response
from utils.aliyun.com.aliyun.api.gateway.sdk.common import constant
from utils.aliyun.com.aliyun.api.gateway.sdk.auth import md5_tool, signature_composer, sha_hmac256


class DefaultClient:
    def __init__(self, app_key=None, app_secret=None, time_out=None):
        self.__app_key = app_key
        self.__app_secret = app_secret
        self.__time_out = time_out
        pass

    def execute(self, request=None):
        try:
            headers = self.build_headers(request)
            body = json.loads(str(request.get_body()))

            body["SignName"] = body["SignName"].encode("utf-8")
            body.update({"Signature": headers[constant.X_CA_SIGNATURE]})
            request.set_body(body)

            # body_keys = body.keys()
            # body_keys.sort()
            # new_body = {"Signature": headers[constant.X_CA_SIGNATURE]}
            # for k in body_keys:
            #     new_body[k] = body[k]
            # print new_body
            # # request.set_body(bytearray(source=json.dumps(body), encoding="utf8"))
            # # body.update({"Signature": headers[constant.X_CA_SIGNATURE]})
            # request.set_body(new_body)
            request.set_content_type(constant.CONTENT_TYPE_FORM)
            response = Response(host=request.get_host(), url=request.get_url(), method=request.get_method(),
                                headers=headers, protocol=request.get_protocol(), content_type=request.get_content_type(),
                                content=request.get_body(), time_out=request.get_time_out())
            if response.get_ssl_enable():
                return response.get_https_response()
            else:
                return response.get_http_response()
        except IOError:
            raise
        except AttributeError:
            raise

    def build_headers(self, request=None):
        headers = dict()
        header_params = request.get_headers()
        headers[constant.X_CA_TIMESTAMP] = DateUtil.get_timestamp()
        headers[constant.X_CA_KEY] = self.__app_key

        body = request.get_body()

        headers[constant.X_CA_NONCE] = UUIDUtil.get_uuid()

        if request.get_content_type():
            headers[constant.HTTP_HEADER_CONTENT_TYPE] = request.get_content_type()
        else:
            headers[constant.HTTP_HEADER_CONTENT_TYPE] = constant.CONTENT_TYPE_JSON

        if constant.HTTP_HEADER_ACCEPT in header_params \
                and header_params[constant.HTTP_HEADER_ACCEPT]:
            headers[constant.HTTP_HEADER_ACCEPT] = header_params[constant.HTTP_HEADER_ACCEPT]
        else:
            headers[constant.HTTP_HEADER_ACCEPT] = constant.CONTENT_TYPE_JSON

        if constant.POST == request.get_method() and constant.CONTENT_TYPE_STREAM == request.get_content_type():
            headers[constant.HTTP_HEADER_CONTENT_MD5] = md5_tool.get_md5_base64_str(request.get_body())
            str_to_sign = signature_composer.build_sign_str(uri="", method=request.get_method(),
                                                            headers=headers, body=json.loads(str(request.get_body()).encode("utf-8")))
        else:
            str_to_sign = signature_composer.build_sign_str(uri=request.get_url(), method=request.get_method(),
                                                            headers=headers, body=body)
        #str_to_sign = "POST&%2F&AccessKeyId%3Dtestid%26Action%3DSingleSendSms%26Format%3DXML%26ParamString%3D%257B%2522name%2522%253A%2522d%2522%252C%2522name1%2522%253A%2522d%2522%257D%26RecNum%3D13098765432%26RegionId%3Dcn-hangzhou%26SignName%3D%25E6%25A0%2587%25E7%25AD%25BE%25E6%25B5%258B%25E8%25AF%2595%26SignatureMethod%3DHMAC-SHA1%26SignatureNonce%3D9e030f6b-03a2-40f0-a6ba-157d44532fd0%26SignatureVersion%3D1.0%26TemplateCode%3DSMS_1650053%26Timestamp%3D2016-10-20T05%253A37%253A52Z%26Version%3D2016-09-27"
        # headers[constant.X_CA_SIGNATURE] = urllib.quote(
        #     sha_hmac256.sign(str_to_sign.encode("utf-8"), "testsecret&"), safe="")
        headers[constant.X_CA_SIGNATURE] = urllib.quote(sha_hmac256.sign(str_to_sign.encode("utf-8"), self.__app_secret + "&"), safe="")
        return headers
