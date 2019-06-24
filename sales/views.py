from rest_framework.response import Response
from rest_framework import status
from sales import models,serializers

class OrderViewSet(viewsets.ModelViewSet):

    queryset = models.Order
    serializer_class = serializers.OrderSerializer

class OrderDetailViewSet(viewsets.ModelViewSet):

    serializer_class = serializers.OrderDetailSerializer

    def get_queryset(self):
        order_id = self.kwargs['order_id']
        return models.OrderDetail.objects.filter(order=order_id)

class ProductViewSet(viewsets.ModelViewSet):
    
    serializer_class = serializers.ProductSerializer

    def get_queryset(self):
        category_id = self.kwargs['category_id']
        return models.Product.objects.filter(category=category_id)

class SpecificationViewSet(viewsets.ModelViewSet):
    
    serializer_class = serializers.SpecificationSerializer

    def get_queryset(self):
        product_id = self.kwargs['product_id']
        return models.Product_Specification.objects.filter(product=product_id)