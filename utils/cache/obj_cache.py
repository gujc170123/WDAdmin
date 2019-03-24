# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json

from utils.cache.cache_utils import AutoExpireCache
from utils.logger import get_logger

logger = get_logger('obj_cache')


class BaseObjCache(AutoExpireCache):
    DEFAULT_EXPIRED_SECOND = 24 * 60 * 60

    def __init__(self, class_name, obj_id, suffix=None):
        key = class_name
        if type(key) != str or type(key) != unicode:
            key = class_name.__name__
        key = '%s:%s' %(key, obj_id)
        if suffix:
            key = '%s:%s' % (key, suffix)
        super(BaseObjCache, self).__init__(key)

    def set_obj(self, obj):
        try:
            json_obj = json.dumps(obj)
            self.setex(json_obj)
        except Exception, e:
            logger.error('set cache obj error, msg: %s, key:%s' %(e, self.key))

    def get_obj(self):
        try:
            value = self.get()
            if value:
                return json.loads(value)
            else:
                return None
        except Exception, e:
            logger.error('get cache obj error, msg: %s, key:%s' % (e, self.key))
