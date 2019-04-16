# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from rest_framework import serializers


class WdTagListSerializer(serializers.ModelSerializer):
    u"""标签回显"""

    list_custom_attrs = serializers.SerializerMethodField()

    # class Meta:
        # model = None
        # fields = ('list_custom_attrs', )

    def get_list_custom_attrs(self, obj):
        with_tags = self.context.get("with_tags", True)
        if not with_tags:
            return []
        from research.models import *
        model_name = self.Meta.model.__name__
        if not Tag.TAG_MODEL_MAP.has_key(model_name):
            return []
        tag_map_info = Tag.TAG_MODEL_MAP[model_name]
        tag_rel_model = tag_map_info["relation"]
        return list(eval(tag_rel_model).objects.filter_active(object_id=obj.id).values("tag_value", "tag_id"))

    def get_field_names(self, declared_fields, info):
        field_names = super(WdTagListSerializer, self).get_field_names(declared_fields, info)
        return field_names + ('list_custom_attrs', )