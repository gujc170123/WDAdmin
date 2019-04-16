# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.conf.urls import url

from question.views import QuestionBankListCreateView, QuestionFolderListCreateView, QuestionBankDetailView, \
    QuestionFolderDetailView, QuestionFacetListCreateView, QuestionFacetDetailView, QuestionListCreateView, \
    QuestionDetailView, QuestionOptionListCreateView, QuestionPassageCreateView, QuestionCategoryListView, \
    QuestionPassageDetailView, QuestionOptionAllListView

urlpatterns = [
    # 新建题库，题库列表
    url(r"^bank/$", QuestionBankListCreateView.as_view(), name="bank-list-create-view"),
    # 题库编辑，删除
    url(r"^bank/(?P<pk>\d+)/$", QuestionBankDetailView.as_view(), name="bank-detail-view"),
    # 新建文件夹，文件夹列表
    url(r"^folder/$", QuestionFolderListCreateView.as_view(), name="folder-list-create-view"),
    # 文件夹编辑，文件夹删除
    url(r"^folder/(?P<pk>\d+)/$", QuestionFolderDetailView.as_view(), name="folder-detail-view"),
    # 构面新建 构面列表
    url(r"^facet/$", QuestionFacetListCreateView.as_view(), name="facet-list-create-view"),
    # 构面编辑 构面删除
    url(r"^facet/(?P<pk>\d+)/$", QuestionFacetDetailView.as_view(), name="facet-detail-view"),
    # 新建题目
    url(r"^$", QuestionListCreateView.as_view(), name="facet-list-create-view"),
    # 题目列表
    url(r"^category/questions/$", QuestionCategoryListView.as_view(), name="category-question-list-view"),
    # 题目修改 删除
    url(r"^(?P<pk>\d+)/$", QuestionDetailView.as_view(), name="question-detail-view"),
    # 题目的文章创建
    url(r"^passage/$", QuestionPassageCreateView.as_view(), name="passage-create-view"),
    # 文章的修改
    url(r"^passage/(?P<pk>\d+)/$", QuestionPassageDetailView.as_view(), name="passage-detail-view"),
    # 选项的创建
    url(r"^option/$", QuestionOptionListCreateView.as_view(), name="question-detail-view"),
    # 获得构面下题目的所有选项
    url(r"^facet/option/$", QuestionOptionAllListView.as_view(), name="facet-detail-view")
]