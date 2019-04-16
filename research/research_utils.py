# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from research.models import ResearchSubstandard, ResearchDimension, ResearchModel, ModelTagRelation, \
    DimensionTagRelation, SubstandardTagRelation


class ResearchModelUtils(object):
    u"""模型操作类
    @version:20180621
    @summary: 新增model_category 组织模型 个人模型 继承
    """
    # TODO: 性能问题

    @classmethod
    def deep_copy(cls, src_model, new_model_cn_name, new_model_en_name):
        u"""

        :param src_model: id or object
        :param new_model_cn_name:
        :param new_model_en_name:
        :return:
        """
        src_obj = src_model  # 传入模型
        if type(src_obj) == int or type(src_obj) == long:
            src_obj = ResearchModel.objects.get(id=src_model)
        root_model_id = src_obj.root_model_id  # 根模型 就是传入的根模型
        if root_model_id == 0:
            root_model_id = src_obj.id  # 根是0， 那么就是传入的标准模型，那么它的根就是新模型
        obj = ResearchModel.objects.create(
            root_model_id=root_model_id,  # 根是标准模型
            parent_model_id=src_obj.id,   # 父模型是派生的
            name=new_model_cn_name,
            en_name=new_model_en_name,
            desc=src_obj.desc,
            en_desc=src_obj.en_desc,
            algorithm_id=src_obj.algorithm_id,
            model_category=src_obj.model_category
        )
        tags = ModelTagRelation.objects.filter_active(
            object_id=src_obj.id
        )
        tag_bulk_list = []
        for tag in tags:
            tag_bulk_list.append(ModelTagRelation(
                tag_id=tag.tag_id,
                object_id=obj.id,
                tag_value=tag.tag_value
            ))
        ModelTagRelation.objects.bulk_create(tag_bulk_list)
        dimensions = ResearchDimension.objects.filter_active(model_id=src_obj.id)
        for dimension in dimensions:
            ResearchDimensionUtils.deep_copy(dimension, obj.id)
        if root_model_id > 0:
            cls.add_inherit_count(root_model_id)
        if root_model_id != src_obj.id:
            cls.add_inherit_count(src_obj.id)
        return obj

    @classmethod
    def add_inherit_count(cls, model_instance, force_save=True):
        u"""

        :param model_instance: ResearchModel object or id
        :param forse_save: force save or not
        :return:
        """
        if type(model_instance) == int or type(model_instance) == long:
            model_instance = ResearchModel.objects.get(id=model_instance)
        model_instance.inherit_count += 1
        if force_save:
            model_instance.save()

    @classmethod
    def add_used_count(cls, model_instance, force_save=True):
        u"""
        :param model_instance: ResearchModel object or id
        :param force_save: after added, save or not
        :return:
        """
        # TODO: 模型的使用次数
        if type(model_instance) == int or type(model_instance) == long:
            model_instance = ResearchModel.objects.get(id=model_instance)
        model_instance.used_count += 1
        if force_save:
            model_instance.save()
        if model_instance.root_model_id:
            root_model = ResearchModel.objects.get(id=model_instance.root_model_id)
            root_model.used_count += 1
            if force_save:
                root_model.save()


class ResearchDimensionUtils(object):
    u"""维度操作类"""
    # TODO: 性能问题

    @classmethod
    def deep_copy(cls, src_dimension, model_id):
        u"""

        :param src_dimension: id or object
        :return:
        """
        src_obj = src_dimension
        if type(src_obj) == int or type(src_obj) == long:
            src_obj = ResearchDimension.objects.get(id=src_dimension)
        obj = ResearchDimension.objects.create(
            model_id=model_id,
            name=src_obj.name,
            en_name=src_obj.en_name,
            weight=src_obj.weight,
            model_category=src_obj.model_category
        )
        tags = DimensionTagRelation.objects.filter_active(
            object_id=src_obj.id
        )
        tag_bulk_list = []
        for tag in tags:
            tag_bulk_list.append(DimensionTagRelation(
                tag_id=tag.tag_id,
                object_id=obj.id,
                tag_value=tag.tag_value
            ))
        DimensionTagRelation.objects.bulk_create(tag_bulk_list)
        substandards = ResearchSubstandard.objects.filter_active(dimension_id=src_obj.id, parent_id=0)
        for substandard in substandards:
            ResearchSubstandardUtils.deep_copy(substandard, model_id, obj.id)
        return obj


class ResearchSubstandardUtils(object):
    u"""子标操作类"""
    # TODO: 性能问题，指标的拷贝

    @classmethod
    def deep_copy(cls, src_substandard, model_id, dimension_id, parent_id=0):
        u"""
        :param src_substandard: id or object
        :return:
        """
        src_substandard_obj = src_substandard
        if type(src_substandard) == int or type(src_substandard) == long:
            src_substandard_obj = ResearchSubstandard.objects.get(id=src_substandard)
        obj = ResearchSubstandard.objects.create(
            model_id=model_id,
            dimension_id=dimension_id,
            parent_id=parent_id,
            name=src_substandard_obj.name,
            en_name=src_substandard_obj.en_name,
            weight=src_substandard_obj.weight,
            model_category=src_substandard_obj.model_category
        )
        tags = SubstandardTagRelation.objects.filter_active(
            object_id=src_substandard_obj.id
        )
        tag_bulk_list = []
        for tag in tags:
            tag_bulk_list.append(SubstandardTagRelation(
                tag_id=tag.tag_id,
                object_id=obj.id,
                tag_value=tag.tag_value
            ))
        SubstandardTagRelation.objects.bulk_create(tag_bulk_list)
        children = ResearchSubstandard.objects.filter_active(parent_id=src_substandard_obj.id)
        for child in children:
            cls.deep_copy(child, model_id, dimension_id, obj.id)
        return obj

    @classmethod
    def del_children(cls, substandard_obj):
        qs = ResearchSubstandard.objects.filter_active(parent_id=substandard_obj.id)
        qs.update(is_active=False)
        for o in qs:
            cls.del_children(o)

