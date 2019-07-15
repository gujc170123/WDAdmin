from rest_framework.response import Response
from rest_framework import status,generics
from django_filters import rest_framework as filters
from rest_framework.generics import GenericAPIView
from utils.views import CustomModelViewSet
from utils.response import general_json_response, ErrorCode
from application import models,serializers
from wduser.serializers import EnterpriseBasicSerializer
from wduser.models import EnterpriseInfo,BaseOrganization

class ChoiceView(GenericAPIView):

    available_dicts = {
        "status": models.Event.STATUS_CHOICES,
        "progress": models.Application.PROGRESS_CHOICES,
        "industry": models.Applier.INDUSTRY_CHOICES,
        "size": models.Applier.SIZE_CHOICES,
        "source": models.Applier.SOURCE_CHOICES,
    }

    def get(self, request):
        option = request.GET.get("option", None)
        if option is not None and option in self.available_dicts:
            result_list = []
            chosen_dict = self.available_dicts[option]
            for i in chosen_dict:
                key, value = i
                tmp = {"key": key, "value": value}
                result_list.append(tmp)
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, result_list)            
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, {"Error": "Empty or invalid option given"})              

class ApplicationModelViewset(CustomModelViewSet):

    queryset = models.Application.objects.all()
    serializer_class = serializers.ApplicationSerializer

class ApplierModelViewset(CustomModelViewSet):

    queryset = models.Applier.objects.all()
    serializer_class = serializers.ApplierSerializer

class EventModelViewset(CustomModelViewSet):

    queryset = models.Event.objects.all()
    serializer_class = serializers.EventSerializer

class CustomerFilter(filters.FilterSet):

    class Meta:
        model = EnterpriseInfo
        fields = {
            'cn_name':['icontains'],
            'email':['icontains'],
        }

class CustomerModelView(CustomModelViewSet):

    queryset = EnterpriseInfo.objects.filter_active()
    serializer_class = EnterpriseBasicSerializer
    filter_backend = filters.DjangoFilterBackend
    filter_class = CustomerFilter

    def perform_destroy(self, instance):
        instance.is_active = False
        if hasattr(instance, 'last_modify_user_id'):
            instance.last_modify_user_id = 0
        instance.save()
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)            
        self.perform_create(serializer)
      
        BaseOrganization.objects.create(
            is_active=True,
            name = serializer.data['cn_name'],
            parent_id=0,
            enterprise_id=serializer.data['id']
        )

        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)          