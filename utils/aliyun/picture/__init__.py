# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json
import urllib2


class PictureUtils(object):

    @classmethod
    def get_pic_info(cls, url):
        try:
            url += "?x-oss-process=image/info"
            request = urllib2.Request(url)
            response = urllib2.urlopen(request)
            info = json.loads(response.read())
            return info
        except:
            return None