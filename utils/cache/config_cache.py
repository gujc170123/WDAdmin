# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json

from utils.cache.cache_utils import AutoExpireCache, NormalHashSet


class ConfigCache(NormalHashSet):
    REPORT_FILTER_CONFIG = 'report_filter'

    def __init__(self):
        key = self.__class__.__name__
        super(ConfigCache, self).__init__(key)

    def set_config_report_filter(self, data):
        self.set_field_value(self.REPORT_FILTER_CONFIG, data)

    def get_config_report_filter(self):
        try:
            return self.get_field_value(self.REPORT_FILTER_CONFIG)
        except:
            return None

    def del_config_report_filter(self):
        self.del_field(self.REPORT_FILTER_CONFIG)
