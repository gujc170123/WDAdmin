from rest_framework import status
from utils.views import CustomModelViewSet
from sales import models,serializers
from datetime import date
from utils.response import general_json_response, ErrorCode

class OrderModelViewset(CustomModelViewSet):

    queryset = models.Order.objects.all()
    serializer_class = serializers.OrderSerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        data['enterprise_id'] = self.kwargs['enterprise_id']    
        serializer = self.get_serializer(data=data)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)            
        self.perform_create(serializer)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def list(self, request, *args, **kwargs):        
        enterprise_id = self.kwargs['enterprise_id']    
        queryset = models.Order.objects.filter(enterprise_id=enterprise_id)
        return super(OrderModelViewset, self).list(request, *args, **kwargs)

class OrderDetailModelViewset(CustomModelViewSet):

    queryset = models.OrderDetail.objects.all()
    serializer_class = serializers.OrderDetailSerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        data['enterprise_id'] = self.kwargs['enterprise_id']    
        serializer = self.get_serializer(data=data)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)            
        self.perform_create(serializer)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def list(self, request, *args, **kwargs):        
        enterprise_id = self.kwargs['enterprise_id']    
        queryset = models.OrderDetail.objects.filter(enterprise_id=enterprise_id)
        return super(OrderDetailModelViewset, self).list(request, *args, **kwargs)

class BalanceModelViewset(CustomModelViewSet):

    serializer_class = serializers.ProductSerializer

    def get_serializer_class(self):
        if self.action == 'retrieve':
            if hasattr(self, 'detail_serializer_class'):
                return self.detail_serializer_class

        return super(CustomModelViewSet, self).get_serializer_class()

    def retrieve(self, request, *args, **kwargs):

        return super(BalanceModelViewset, self).retrieve(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        
        enterprise_id = self.kwargs['enterprise_id']        
        skulist = models.Balance.objects.filter(enterprise=enterprise_id,validto__gte=date.today()).values("sku")
        # list all bought products except platform
        queryset = models.Product_Specification.objects.filter(id__in=skulist).exclude(id=1)        

        serializer = self.get_serializer(queryset, many=True)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)            
