# -*- coding:utf-8 -*-
from __future__ import unicode_literals

"""
settings related with environment: development or production
default is development env
deploy in production env, need replaced with env_pro.py
"""

import os

# base dir settings
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# debug settings
DEBUG = True

# allow host settings
ALLOWED_HOSTS = ['localhost:3000', 'wd-admin.exuetech.com', 'wd-user.exuetech.com']

# csrf setting
CORS_ORIGIN_ALLOW_ALL = True
CORS_ALLOW_CREDENTIALS = True
CORS_ORIGIN_WHITELIST = (
      'localhost:3000',
)

# Database
# database settings
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'backend',
        'USER': 'root',
        'PASSWORD': '123456',
        'HOST': '127.0.0.1',
        'PORT': '3306',
    },
    'front': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'front',
        'USER': 'root',
        'PASSWORD': '123456',
        'HOST': '127.0.0.1',
        'PORT': '3306',
    },

}
#
CLIENT_HOST = 'http://wd-user.exuetech.com'
REPORT_HOST = 'http://172.16.124.92'
REPORT_HOSTS = ['http://172.16.124.92']
CUSTOM_HOSTS = ['http://172.16.124.92']

# redis config
CACHE = {
    'redis': {
        'default': {
            'host': 'localhost',
            'port': 6379,
            'db': 0,
            'password': None
        },
        'celery': {
            'host': 'localhost',
            'port': 6379,
            'db': 0,
            'password': None
        }
    }
}
