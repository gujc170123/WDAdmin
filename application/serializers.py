# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import serializers
from application import models

class ApplierSerializer(serializers.ModelSerializer):

    industry_text = serializers.CharField(source='get_industry_display',read_only=True)
    size_text = serializers.CharField(source='get_size_display',read_only=True)
    source_text = serializers.CharField(source='get_source_display',read_only=True)
    
    class Meta:
        model = models.Applier
        fields = '__all__'

class EventSerializer(serializers.ModelSerializer):

    status_text = serializers.CharField(source='get_status_display',read_only=True)
    
    class Meta:
        model = models.Event
        fields = '__all__'

class ApplicationSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.Application
        fields = '__all__'

class ApplicationCRMSerializer(serializers.ModelSerializer):

    applier = ApplierSerializer()
    event = EventSerializer()
    progress_text = serializers.CharField(source='get_progress_display',read_only=True)

    class Meta:
        model = models.Application
        fields = '__all__'

    def update(self, instance, validated_data):
        instance.progress = validated_data.get('progress', instance.progress)
        instance.save()

        return instance