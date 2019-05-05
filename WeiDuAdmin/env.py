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
ALLOWED_HOSTS = ['localhost:3000', 'wd-admin.exuetech.com', 'wd-user.exuetech.com', 'admin.yx.iwedoing.com']

# csrf setting
CORS_ORIGIN_ALLOW_ALL = True
CORS_ALLOW_CREDENTIALS = True
CORS_ORIGIN_WHITELIST = ('127.0.0.1:3000')
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
        'NAME': 'backend',
        'USER': 'root',
        'PASSWORD': '123456',
        'HOST': 'localhost',
        'PORT': '3306',
        'OPTIONS': {'charset':'utf8mb4'},
    },
    'front': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'front',
        'USER': 'root',
        'PASSWORD': '123456',
        'HOST': 'localhost',
        'PORT': '3306',
        'OPTIONS': {'charset':'utf8mb4'},
    },
}
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': 'wdadmin',
#         'USER': 'ad_wd',
#         'PASSWORD': 'Admin@Weidu2018',
#         'HOST': 'rm-bp1i2yah9e5d27k26bo.mysql.rds.aliyuncs.com',
#         'PORT': '3306',
#     },
#     'front': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': 'wdfront',
#         'USER': 'ad_wd',
#         'PASSWORD': 'Admin@Weidu2018',
#         'HOST': 'rm-bp1i2yah9e5d27k26bo.mysql.rds.aliyuncs.com',
#         'PORT': '3306',
#     }
# }
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': 'wdadmin_uat',
#         'USER': 'appserver',
#         'PASSWORD': 'AS@wdadmin',
#         'HOST': 'rm-bp1i2yah9e5d27k26bo.mysql.rds.aliyuncs.com',
#         'PORT': '3306',
#     },
#     'front': {
#          'ENGINE': 'django.db.backends.mysql',
#          'NAME': 'wdfront_uat',
#          'USER': 'appserver',
#          'PASSWORD': 'AS@wdadmin',
#          'HOST': 'rm-bp1i2yah9e5d27k26bo.mysql.rds.aliyuncs.com',
#          'PORT': '3306',
#      },
# }

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

