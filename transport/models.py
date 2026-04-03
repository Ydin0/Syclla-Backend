from django.db import models


class RailwayStation(models.Model):
    """UK railway station with location and usage data."""
    station_name = models.CharField(max_length=200, db_index=True)
    tlc_code = models.CharField(max_length=3, unique=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=8)
    longitude = models.DecimalField(max_digits=11, decimal_places=8)
    outcode = models.ForeignKey(
        'areas.PostcodeDistrict',
        on_delete=models.SET_NULL,
        to_field='code',
        null=True, blank=True,
        related_name='stations',
    )
    annual_entries_exits = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['station_name']

    def __str__(self):
        return f"{self.station_name} ({self.tlc_code})"


class StationCityJourney(models.Model):
    """Journey time from a railway station to a major city."""
    station = models.ForeignKey(
        RailwayStation,
        on_delete=models.CASCADE,
        related_name='journeys',
    )
    city_name = models.CharField(max_length=100)
    destination_station = models.CharField(max_length=200, null=True, blank=True)
    journey_time_mins = models.IntegerField(null=True, blank=True)

    class Meta:
        unique_together = ['station', 'city_name']

    def __str__(self):
        return f"{self.station.station_name} → {self.city_name}: {self.journey_time_mins} mins"


class MajorCity(models.Model):
    """Major UK city used as a journey time destination."""
    name = models.CharField(max_length=100, unique=True)
    station_codes = models.JSONField()
    latitude = models.DecimalField(max_digits=10, decimal_places=8)
    longitude = models.DecimalField(max_digits=11, decimal_places=8)
    population = models.IntegerField()

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Major Cities'

    def __str__(self):
        return self.name
