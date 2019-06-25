# -*- coding:utf-8 -*-
from __future__ import unicode_literals

"""
settings related with environment: development or production
default is development env
deploy in production env, need replaced with env_pro.py
"""

import os

# debug settings
DEBUG = False

# allow host settings
ALLOWED_HOSTS = ['*']

# csrf setting
CORS_ORIGIN_ALLOW_ALL = True
CORS_ALLOW_CREDENTIALS = True
CORS_ORIGIN_WHITELIST = ('127.0.0.1:8000')
CORS_ALLOW_METHODS = (
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
    'VIEW',
)

CORS_ALLOW_HEADERS = (
    'XMLHttpRequest',
    'X_FILENAME',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'Pragma',
)
# Database
# database settings


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'wdadmin_uat',
        'USER': 'appserver',
        'PASSWORD': 'AS@wdadmin',
        'HOST': 'rm-bp1i2yah9e5d27k26bo.mysql.rds.aliyuncs.com',
        'PORT': '3306',
    },
    'front': {
         'ENGINE': 'django.db.backends.mysql',
         'NAME': 'wdfront_uat',
         'USER': 'appserver',
         'PASSWORD': 'AS@wdadmin',
         'HOST': 'rm-bp1i2yah9e5d27k26bo.mysql.rds.aliyuncs.com',
         'PORT': '3306',
     },
}
Reports = {
    'mbti2019':"http://reporttest.iwedoing.com:9090/api/render?url=http://reporttest.iwedoing.com/NewBehavioralStyle?people_result_id=%s&emulateScreenMedia=false",
    'disc2019':"http://reporttest.iwedoing.com:9090/api/render?url=http://reporttest.iwedoing.com/ProfessionalPersonality?people_result_id=%s&emulateScreenMedia=false",
    'co2019':"http://reporttest.iwedoing.com:9090/api/render?url=http://reporttest.iwedoing.com/ProfessionalOrientation?people_result_id=%s&emulateScreenMedia=false",
    'mc2019':"http://reporttest.iwedoing.com:9090/api/render?url=http://reporttest.iwedoing.com/TheHighLevel?people_result_id=%s&emulateScreenMedia=false",
    'peoi2019':"http://yx.iwedoing.com/#/report/%s",
}
#
# CLIENT_HOST = 'http://wd-user.exuetech.com'
CLIENT_HOST = 'http://yx.iwedoing.com'
REPORT_HOST = 'http://172.16.124.92'
REPORT_HOSTS = ['http://172.16.124.92']
CUSTOM_HOSTS = ['http://172.16.124.92']
FRONT_HOST ='wdfront_uat'
ROOT_HOST='http://admin.yx.iwedoing.com/#/'

# redis config
CACHE = {
    'redis': {
        'default': {
            'host': '127.0.0.1',
            'port': 6379,
            'db': 0,
            'password': None
        },
        'celery': {
            'host': '127.0.0.1',
            'port': 6379,
            'db': 0,
            'password': None
        }
    }
}

