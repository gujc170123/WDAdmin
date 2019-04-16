# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import os

import datetime
import time
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import random

from io import BytesIO

import base64

from utils import get_random_char


class Picture(object):
    def __init__(self, text_str, size=(150, 50), background='white'):
        u'''
        text_str: 验证码显示的字符组成的字符串
        size:  图片大小
        background: 背景颜色
        '''
        self.text_str = text_str
        self.size = size
        self.background = background

    def create_pic(self):
        u'''
        创建一张图片
        '''
        self.width, self.height = self.size
        self.img = Image.new("RGB", self.size, self.background)
        # 实例化画笔
        self.draw = ImageDraw.Draw(self.img)

    def create_point(self, num, color):
        u'''
        num: 画点的数量
        color: 点的颜色
        功能：画点
        '''
        for i in range(num):
            self.draw.point(
                (random.randint(0, self.width), random.randint(0, self.height)),
                fill=color
            )

    def create_line(self, num, color):
        u'''
        num: 线条的数量
        color: 线条的颜色
        功能：画线条
        '''
        for i in range(num):
            self.draw.line(
                [
                    (random.randint(0, self.width), random.randint(0, self.height)),
                    (random.randint(0, self.width), random.randint(0, self.height))
                ],
                fill=color
            )

    def create_text(self, font_size, font_color, start_xy, font_type="utils/fonts/simsun.ttc"):
        u'''
        font_type: 字体
        font_size: 文字大小
        font_color: 文字颜色
        font_num:  文字数量
        start_xy:  第一个字左上角坐标,元组类型，如 (5,5)
        功能： 画文字
        '''
        font = ImageFont.truetype(font_type, font_size)
        self.draw.text(start_xy, self.text_str, font=font, fill=font_color)

    def opera(self):
        u'''
        功能：给画出来的线条，文字，扭曲一下，缩放一下，位移一下，滤镜一下。
        就是让它看起来有点歪，有点扭。
        '''
        params = [
            1 - float(random.randint(1, 2)) / 100,
            0,
            0,
            0,
            1 - float(random.randint(1, 10)) / 100,
            float(random.randint(1, 2)) / 500,
            0.001,
            float(random.randint(1, 2)) / 500
        ]
        self.img = self.img.transform(self.size, Image.PERSPECTIVE, params)
        self.img = self.img.filter(ImageFilter.EDGE_ENHANCE_MORE)


def create_piccode(text_str_list):
    f = BytesIO()
    now = datetime.datetime.now()
    str_today = now.strftime("%Y-%m-%d")
    pwd = os.path.join("download", "piccodes", str_today)
    if not os.path.exists(pwd):
        os.makedirs(pwd)
    full_path = os.path.join(pwd, "int(time.time()*1000).png")
    text_str = " ".join(text_str_list)
    size = (150, 50)
    background = 'white'
    pic = Picture(text_str, size, background)
    pic.create_pic()
    pic.create_point(500, (220, 220, 220))
    pic.create_line(30, (220, 220, 220))
    pic.create_text(24, (0, 0, 205), (7, 7))
    pic.img.save(f, 'PNG')
    # return base64.b32encode(f.getvalue())
    return f.getvalue()


def test():
    # strings = "abcdefghjkmnpqrstwxyz23456789ABCDEFGHJKLMNPQRSTWXYZ"
    strings = get_random_char(5)
    size = (150, 50)
    background = 'white'
    pic = Picture(strings, size, background)
    pic.create_pic()
    pic.create_point(500, (220, 220, 220))
    pic.create_line(30, (220, 220, 220))
    pic.create_text(24, (0, 0, 205), (7, 7))
    pic.opera()
    pic.img.show()