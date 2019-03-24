# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from utils.rpc_service import HttpService


class ClientService(HttpService):
    HOST = "http://192.168.0.117:8080"

    @classmethod
    def send_survey_question(cls, data):
        uri = "/api/v1/admin/questionnaire"
        rst = cls.do_request(uri, data)
        print rst