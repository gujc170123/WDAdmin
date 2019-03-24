# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import re
from django.db.models import Func

class RegularUtils(object):
    u"""正则检查类"""

    @classmethod
    def phone_check(cls, phone_number):
        u"""电话号码检查"""
        # str = '^(13[0-9]|14[0-9]|15[0-9]|16[0-9]|17[0-9]|18[0-9])\d{8}$'
        str = '^\d{11}$'
        str_re = re.compile(str)
        if str_re.match(phone_number) is None:
            return False
        return True

    @classmethod
    def email_check(cls, email):
        str = r'^[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+){0,4}@[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+){0,4}$'
        str_re = re.compile(str)
        if str_re.match(email) is None:
            return False
        return True

    @classmethod
    def remove_illegal_char(cls, origin_value):
        ILLEGAL_CHARACTERS_RE = re.compile(r'[\000-\010]|[\013-\014]|[\016-\037]|\xef|\xbf')
        value = ILLEGAL_CHARACTERS_RE.sub('', origin_value)
        return value


class Convert(Func):
    # return qs.order_by(Convert('cn_name', 'gbk').asc())
    # "SELECT cn_name FROM wduser_enterpriseinfo order by CONVERT(cn_name USING gbk)"
    def __init__(self, expression, transcoding_name, **extra):
        super(Convert, self).__init__(expression, transcoding_name=transcoding_name, **extra)
        # super(Convert, self).__init__(expression, transcoding_name=Value(transcoding_name), **extra)

    def as_mysql(self, compiler, connection):
        self.function = 'CONVERT'
        # CONVERT(cn_name USING GBK)
        self.template = '%(function)s(%(expressions)s USING %(transcoding_name)s)'
        return super(Convert, self).as_sql(compiler, connection)