from django.db import models

class StockData(models.Model):
    # 移除 primary_key=True，改用預設 ID
    stock_id = models.CharField(max_length=10, verbose_name="股票代碼")
    stock_name = models.CharField(max_length=50, verbose_name="股票名稱")
    
    # 新增年與月欄位，用來區分不同時間點的資料
    data_year = models.IntegerField(verbose_name="資料年份")
    data_month = models.IntegerField(verbose_name="資料月份")
    
    update_date = models.DateField(auto_now=True, verbose_name="上傳日期")
    raw_data = models.JSONField(verbose_name="完整分析數據")

    class Meta:
        # 設定聯合約束：同一股票、同一年、同一月，只能有一筆資料
        # 如果重複上傳同一個月的資料，會執行更新
        unique_together = ('stock_id', 'data_year', 'data_month')
        verbose_name = "股票歷史數據"

    def __str__(self):
        return f"{self.stock_id} {self.stock_name} ({self.data_year}/{self.data_month})"