# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json
from abc import abstractmethod
import random

import datetime
import time

from utils.cache.redis_storage import RedisStorage


class BaseCache(object):
    u"""maybe not only use redis as cache store"""
    cache_name = None
    store_class = None

    def __init__(self, key):
        assert self.cache_name is not None and self.store_class is not None, "please specify the cache name"
        self.key = self.make_key(key)

    def make_key(self, key):
        return self.__class__.__name__ + ":" + self.store_class.key_format % key

    @abstractmethod
    def get_cache(self): pass

    @abstractmethod
    def set_cache(self, value): pass

    cache = property(get_cache, set_cache)


class RedisBaseCache(BaseCache):
    u"""redis cache store base class"""
    cache_name = "redis"
    store_class = RedisStorage
    redis_server = 'default'

    def get_cache(self):
        return self.store_class(getattr(self, "key", ""), redis_server=self.redis_server).get_redis()

    def set_cache(self, value):
        self.store_class(self.key).set_redis(value)

    cache = property(get_cache, set_cache)

    def keys(self, prefix=""):
        return self.cache.keys("%s*" % self.make_key(prefix))

    def get(self):
        return self.get_by_name(self.key)

    def get_by_name(self, name):
        return self.cache.get(name)

    def delete(self):
        return self.delete_by_names(self.key)

    def delete_by_names(self, *names):
        return self.cache.delete(*names)


class BaseBusinessCache(RedisBaseCache):
    u"""业务层, 变更缓存方式, 仅变更此处的继承就好"""

    def direct_set(self, key, value):
        return self.cache.set(key, value)

    def direct_get(self, key):
        return self.cache.get(key)

    def direct_del(self, key):
        return self.cache.delete(key)

    def direct_expired(self, key, time):
        return self.cache.expire(key, time)

    def direct_setex(self, key, value, time):
        return self.cache.setex(key, time, value)

    def set(self, value):
        return self.cache.set(self.key, value)

    def setex(self, value, time=None):
        return self.cache.setex(self.key, time, value)

    def expired(self, time):
        return self.cache.expire(self.key, time)


class AutoExpireCache(BaseBusinessCache):
    """缓存自动过期基类"""
    # TODO: cache 优化 @2016/12/03 BaseBusinessCacheStore包含了AutoExpireStore现有的方法
    DEFAULT_EXPIRED_SECOND = 30*60

    def setex(self, value, time=None):
        if time is None:
            time = self.DEFAULT_EXPIRED_SECOND
        return self.cache.setex(self.key, time, value)

    def daily_setex(self, value):
        now = datetime.datetime.now()
        today = datetime.datetime.strptime(now.strftime("%Y-%m-%d"), "%Y-%m-%d")
        left_seconds = 24*3600 - (now-today).seconds
        self.setex(value, left_seconds)


class NormalHashSet(BaseBusinessCache):

    def set_field_value(self, field, obj):
        u"""

        :param field: str
        :param obj: obj that can dumps with json
        :return:
        """
        str_value = json.dumps(obj)
        return self.cache.hset(self.key, field, str_value)

    def get_field_value(self, field):
        str_value = self.cache.hget(self.key, field)
        if not str_value:
            return None
        return json.loads(str_value)

    def del_field(self, *field):
        return self.cache.hdel(self.key, *field)


class NormalSortedSet(BaseBusinessCache):

    def insert_sorted_list(self, value, score):
        u"""
        insert value to the sorted list with score
        :param value:  str
        :param score: int, sorted using it
        :return:
        """
        self.cache.zadd(self.key, score, value)

    def increment_sorted_value(self, value, inc_score=1):
        u"""
        增加排序分值
        :param value:
        :param inc_score:
        :return:
        """
        return self.cache.zincrby(self.key, value, inc_score)

    def get_sorted_list(self, start=0, limit=8, aes=False, with_scores=False):
        u"""
        获取排序后的list
        :param start:
        :param limit:
        :param aes:
        :param with_scores:
        :return:
        """
        if aes:
            return self.cache.zrange(self.key, start, start+limit-1, with_scores)
        else:
            return self.cache.zrevrange(self.key, start, start+limit-1, with_scores)


class VerifyCodeExpireCache(AutoExpireCache):
    """验证码自动过期缓存"""

    DEFAULT_EXPIRED_SECOND = 10*60

    def set_verify_code(self, value):
        self.setex(value)

    def check_verify_code(self, value, is_delete=True):
        if value is None:
            return False
        if value == self.get():
            if is_delete:
                self.delete()
            return True
        return False


class UserLogExpireCache(AutoExpireCache):
    """用户登陆自动过期缓存"""

    DEFAULT_EXPIRED_SECOND = 10*60

    def set_user_log(self, value):
        self.setex(value)

    def check_user_log(self, value):
        value = str(value)
        if value is None:
            return False
        if value == self.get():
            return True
        return False

    # 每次发请求都会刷新一次在线时间  中间件
    def setex(self, value, time=None):
        value = str(value)
        if time is None:
            time = self.DEFAULT_EXPIRED_SECOND
        return self.cache.setex(self.key, time, value)


class UserLogCookieExpireCache(BaseBusinessCache):

    def direct_set(self, key, value):
        return self.cache.set(key, value)

    def direct_get(self, key):
        return self.cache.get(key)


class FileStatusCache(AutoExpireCache):
    """验证码自动过期缓存"""

    DEFAULT_EXPIRED_SECOND = 30*60

    def set_verify_code(self, value):
        self.setex(value)

    def get_verify_code(self):
        value = self.get()
        if value in [100, '100']:
            self.delete()
        return value
