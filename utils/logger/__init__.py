# -*- coding:utf-8 -*-
from __future__ import unicode_literals
import logging
import platform
import os
import traceback

from django.conf import settings
import logging.config

log_root_path = '/var/log/wdadmin/'
if platform.system() == 'Windows':
    log_root_path = u'c:\\log\\wdadmin\\'

if not os.path.exists(log_root_path):
    os.makedirs(log_root_path)


def add_logger(logging, name):
    logging['handlers'][name] = {
        'level': 'DEBUG',
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': log_root_path + name + '.log',
        'maxBytes': 1024 * 1024 * 5,
        'backupCount': 100,
        'formatter': 'verbose',
    }
    logging['loggers'][name] = {
        'handlers': ['console', name],
        'level': 'DEBUG',
    }


# _has_initialized = False
log_file_name_cache = []


def get_logger(name=None):
    '''
    Just call logger without name in most cases. But on commands under
    'services/management/commands', please call it with a specified name at beginning
    (before other import sentences).
    For any new command, please add relative logging settings at settings.py
    '''
    global log_file_name_cache
    try:
        if name is None:
            name = settings.MAIN_LOG_NAME
        if name not in log_file_name_cache:
            add_logger(settings.LOGGING, name)
            logging.config.dictConfig(settings.LOGGING)
        return logging.getLogger(name)
    except Exception, e:
        traceback.print_exc()
        return logging.getLogger(settings.MAIN_LOG_NAME)