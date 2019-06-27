from utils.views import CustomModelViewSet
from assessment.models import AssessProject
fro
from assessment.serializers import AssessmentSurveyRelationDetailGetSerializer
from workspace.serializers import AssessListSerializer
from utils.response import general_json_response, ErrorCode
from rest_framework import generics, mixins, views
import django_filters

class AssessmentFilter(django_filters.FilterSet):

    class Meta:
        model = AssessProject
        fields = ['id']


class ProductsView(CustomModelViewSet):




class AssessmentFilter(django_filters.FilterSet):

    class Meta:
        model = AssessProject
        fields = ['enterprise_id']

class AssessViewset(CustomModelViewSet):

    queryset = AssessProject.objects.filter_active()
    serializer_class = AssessListSerializer
    detail_serializer_class = AssessmentSurveyRelationDetailGetSerializer
    filter_class = AssessmentFilter

    def get_serializer_class(self):
        if self.action == 'retrieve':
            if hasattr(self, 'detail_serializer_class'):
                return self.detail_serializer_class

        return super(CustomModelViewSet, self).get_serializer_class()