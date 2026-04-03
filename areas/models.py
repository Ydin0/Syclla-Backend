from django.db import models


class PostcodeDistrict(models.Model):
    """Represents a UK postcode district (e.g., SS1, CO1, CM1)"""
    code = models.CharField(max_length=10, unique=True, db_index=True)
    name = models.TextField(help_text='Town/Area name')
    region = models.CharField(max_length=100, help_text='Local region (e.g. Aberdeen, London)')
    uk_region = models.CharField(max_length=100, blank=True, default='', help_text='UK region (e.g. Scotland, London)')
    post_town = models.CharField(max_length=255, blank=True, default='')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    easting = models.IntegerField(null=True, blank=True)
    northing = models.IntegerField(null=True, blank=True)
    grid_reference = models.CharField(max_length=20, blank=True, default='')
    population = models.IntegerField(null=True, blank=True)
    households = models.IntegerField(null=True, blank=True)
    postcode_count = models.IntegerField(null=True, blank=True, help_text='Total postcodes in district')
    active_postcode_count = models.IntegerField(null=True, blank=True, help_text='Active postcodes in district')
    nearby_districts = models.CharField(max_length=500, blank=True, default='', help_text='Comma-separated nearby district codes')
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Postcode District'
        verbose_name_plural = 'Postcode Districts'

    def __str__(self):
        return f"{self.code} - {self.region}"


