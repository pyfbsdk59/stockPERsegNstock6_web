

# Create your models here.
from django.db import models

class StockData(models.Model):
    stock_id = models.CharField(max_length=10, primary_key=True, verbose_name="股票代碼")
    stock_name = models.CharField(max_length=50, verbose_name="股票名稱")
    update_date = models.DateField(auto_now=True, verbose_name="更新日期")
    raw_data = models.JSONField(verbose_name="完整分析數據") # 直接存整個 JSON 物件

    def __str__(self):
        return f"{self.stock_id} {self.stock_name}"