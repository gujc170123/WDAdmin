# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json

import time
from aliyunsdkcore import client
from aliyunsdkvod.request.v20170321 import CreateUploadVideoRequest, RefreshUploadVideoRequest, GetVideoPlayAuthRequest
from aliyunsdkvod.request.v20170321 import GetPlayInfoRequest
from aliyunsdkvod.request.v20170321 import GetVideoInfoRequest

access_key_id = ""
access_key_secret = ""

clt = client.AcsClient(access_key_id, access_key_secret, 'cn-shanghai')


class AliyunVodUtils(object):
    u"""阿里云视频点播、短视频操作类"""

    def __init__(self):
        pass

    @classmethod
    def create_upload_video(cls, user_id=None, title=None, file_name=None, file_size=None, file_desc=None,
                            file_cover_url=None, file_ip=None, file_permission=None):
        u"""

        :param title: 视频标题
        :param file_name: 视频源文件名称
        :param file_size: 视频文件大小
        :param file_desc: 视频描述
        :param file_cover_url: 自定义视频封面URL地址
        :param file_permission: 视频观看权限
        :param file_ip: 上传所在IP地址
        :return:
        """
        if user_id is None:
            user_id = int(time.time()*100)
        if title is None:
            title = "%s-video" % user_id
        if file_name is None:
            file_name = "%s.mp4" % user_id
        request = CreateUploadVideoRequest.CreateUploadVideoRequest()
        request.set_accept_format('JSON')
        request.set_Title(title)
        request.set_FileName(file_name)
        if file_size:
            request.set_FileSize(file_size)
        if file_desc:
            request.set_Description(file_desc)
        if file_cover_url:
            request.set_CoverURL(file_cover_url)
        # request.set_Privilege(file_permission)
        if file_ip:
            request.set_IP(file_ip)
        rst = clt.do_action_with_exception(request)
        response = json.loads(rst)
        return response

    @classmethod
    def refresh_upload_token(cls, vod_id):
        u"""
        刷新视频token
        :param vod_id:
        :return:
        """
        request = RefreshUploadVideoRequest.RefreshUploadVideoRequest()
        request.set_accept_format('JSON')
        request.set_VideoId(vod_id)
        rst = clt.do_action_with_exception(request)
        response = json.loads(rst)
        return response

    @classmethod
    def get_play_auth(cls, vod_id):
        u"""
        获取播放凭证
        :param vod_id:
        :return:
        """
        request = GetVideoPlayAuthRequest.GetVideoPlayAuthRequest()
        request.set_accept_format('JSON')
        request.set_VideoId(vod_id)
        response = json.loads(clt.do_action_with_exception(request))
        return response

    @classmethod
    def get_play_info(cls, vod_id):
        u"""
        获取播放地址/信息
        :param vod_id:
        :return: https://help.aliyun.com/document_detail/56124.html?spm=5176.doc57292.2.5.Hz0W9z
        """
        try_times = 20
        default_cover_url = "http://xd-cache-1.oss-cn-shanghai.aliyuncs.com/xd-cover/2.jpg"
        for try_time in range(try_times):
            try:
                request = GetPlayInfoRequest.GetPlayInfoRequest()
                request.set_accept_format('JSON')
                request.set_VideoId(vod_id)
                response = json.loads(clt.do_action_with_exception(request))
                video_base_info = response["VideoBase"]
                if video_base_info["Status"] == "Normal":
                    cover_url = default_cover_url
                    # fix bug, CoverURL may not return from video_base_info,
                    # but needed in work created (not little video)
                    if "CoverURL" in video_base_info:
                        cover_url = video_base_info["CoverURL"]
                    else:
                        video_info = cls.get_video_info(vod_id)[0]
                        if video_info is not None and "CoverURL" in video_info:
                            cover_url = video_info['CoverURL']
                    return response["PlayInfoList"]["PlayInfo"][0]["PlayURL"], cover_url, response
                else:
                    time.sleep(0.5)
                    continue
            except Exception, e:
                print e
                time.sleep(0.5)
                continue
        return None, None, None

    @classmethod
    def get_video_info(cls, vod_id):
        u"""
        获取播视频信息
        :param vod_id:
        :return: https://help.aliyun.com/document_detail/52835.html?spm=5176.doc56124.6.629.rBJfHZ
        """
        try_times = 20
        for try_time in range(try_times):
            try:
                request = GetVideoInfoRequest.GetVideoInfoRequest()
                request.set_accept_format('JSON')
                request.set_VideoId(vod_id)
                response = json.loads(clt.do_action_with_exception(request))
                video_info = response["Video"]
                if video_info["Status"] == "Normal":
                    return video_info["Snapshots"]["Snapshot"], video_info
                else:
                    time.sleep(0.5)
                    continue
            except Exception, e:
                print e
                time.sleep(0.5)
                continue
        return None, None
