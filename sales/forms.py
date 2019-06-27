from sales import models
from eav.forms import BaseDynamicEntityForm


class Product_SpecificationForm(BaseDynamicEntityForm):
    model = models.Product_Specification