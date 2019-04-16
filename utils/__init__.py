# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import hashlib
import os
import random
import time

import datetime
import zipfile

from django.core.files.uploadedfile import InMemoryUploadedFile


def str_check(str_obj):
    u"""excel import str check"""
    if type(str_obj) == int or type(str_obj) == long:
        str_obj = str(long(str_obj))
    elif type(str_obj) == float:
        str_obj = str(long(str_obj))
    return str_obj


def get_random_int(length=6):
    seed = int(time.time()*1000)
    random.seed(seed)
    code_list = []
    count = length
    for i in range(count):
        if i == 0:
            code_list.append(str(random.randint(1, 9)))
        else:
            code_list.append(str(random.randint(0, 9)))
    code_str = "".join(code_list)
    return int(code_str)


def get_random_char(length=6):
    random_str = ""
    seed = int(time.time())
    random.seed(seed)
    for i in range(length):
        random_str += chr(ord('a') + random.randint(0, 25))
    return random_str


def get_random_char_list(length=6):
    random_list = []
    seed = int(time.time())
    random.seed(seed)
    for i in range(length):
        random_list.append(chr(ord('a') + random.randint(0, 25)))
    return random_list


def get_md5(msg):
    m = hashlib.md5()
    m.update(msg)
    return m.hexdigest()


def str2time(strtime):
    return datetime.datetime.strptime(strtime, '%Y-%m-%d %H:%M:%S')


def time_format(date_time):
    return date_time.strftime('%Y-%m-%d %H:%M:%S')


def time_format2(date_time):
    return date_time.strftime('%Y-%m-%d')


def time_format3(date_time):
    return date_time.strftime('%Y/%m/%d')


def time_format4(date_time):
    return date_time.strftime('%Y.%m.%d')


def time_format5(date_time):
    return u'%s年%s月%s日' %(date_time.year, date_time.month, date_time.day)


def get_random_str(length=32):
    if length < 13:
        raise Exception
    return str(int(time.time()*1000)) + "".join(random.sample("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", length-13))


def get_request_ip(request):
    try:
        if 'HTTP_X_FORWARDED_FOR' in request.META:
            return request.META['HTTP_X_FORWARDED_FOR']
        else:
            return request.META['REMOTE_ADDR']
    except:
        return "127.0.0.1"


def id2str(data, *args):

    def __id2str(d):
        for field in args:
            if field.find(".") > -1:
                fields = field.split(".")
                td = None
                v = None
                for f in fields:
                    if td is None:
                        v = d[f]
                        td = d[f]

                    else:
                        v = td[f]
                        if type(td[f]) == dict:
                            td = td[f]
                td[f] = str(v)
            else:
                d[field] = str(d[field])
    if data:
        if type(data) == list:
            for d in data:
                __id2str(d)
            return data
        else:
            __id2str(data)
            return data
    return data


def data2file(data, filename, director=None):
    u"""数据保存文件"""
    now = datetime.datetime.now()
    str_now = time_format2(now)
    if director is None:
        director = os.path.join("download", str_now)
        if not os.path.exists(director):
            os.mkdir(director)
    filepath = os.path.join(director, filename)
    f = open(filepath, "wb")
    if type(data) == str or type(data) == unicode:
        f.write(data)
    elif type(data) == InMemoryUploadedFile:
        for chunk in data.chunks():
            f.write(chunk)
    f.close()
    return filepath


def zip_folder(file_path, zip_file_path_name):
    z = zipfile.ZipFile(zip_file_path_name, 'w', zipfile.ZIP_DEFLATED)
    for dirpath, dirnames, filenames in os.walk(file_path):
        fpath = dirpath.replace(file_path, '')
        fpath = fpath and fpath + os.sep or ''
        for filename in filenames:
            z.write(os.path.join(dirpath, filename), fpath + filename)
    z.close()
