from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class HmoScore(models.Model):
    """HMO investment scores and metrics for a postcode district"""
    postcode_district = models.OneToOneField(
        'areas.PostcodeDistrict',
        on_delete=models.CASCADE,
        related_name='score'
    )
    hmo_score = models.IntegerField(default=0, help_text='Overall HMO investment score (0-100)')
    average_yield = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Average rental yield percentage'
    )
    average_price = models.IntegerField(null=True, blank=True, help_text='Average property price in GBP')
    average_rent = models.IntegerField(null=True, blank=True, help_text='Average monthly room rent in GBP')
    demand_score = models.IntegerField(
        default=50,
        help_text='Room demand score (0-100)'
    )
    transport_score = models.IntegerField(
        default=0,
        help_text='Transport connectivity score (0-100)'
    )
    nearest_station_name = models.CharField(max_length=200, null=True, blank=True)
    nearest_station_distance_km = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    london_journey_mins = models.IntegerField(null=True, blank=True)
    nearest_city_journey_mins = models.IntegerField(null=True, blank=True)
    nearest_city_name = models.CharField(max_length=100, null=True, blank=True)
    cities_within_60_mins = models.IntegerField(default=0)
    council_attitude_score = models.IntegerField(
        default=5,
        help_text='Council attitude towards HMOs (1-10)'
    )
    has_article_4 = models.BooleanField(
        default=False,
        help_text='Whether Article 4 Direction applies'
    )
    student_area = models.BooleanField(
        default=False,
        help_text='Whether this is a student-heavy area'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'HMO Score'
        verbose_name_plural = 'HMO Scores'

    def __str__(self):
        return f"{self.postcode_district.code} - Score: {self.hmo_score}"


class LocalAuthorityDemand(models.Model):
    """Census-derived demand metrics per local authority."""
    la_code = models.CharField(max_length=50, primary_key=True)
    la_name = models.CharField(max_length=200, db_index=True)
    region = models.CharField(max_length=100, db_index=True)

    # Population counts
    total_population = models.IntegerField(null=True, blank=True)
    population_20_34 = models.IntegerField(null=True, blank=True)
    private_renters_20_34 = models.IntegerField(null=True, blank=True)
    single_person_households_under66 = models.IntegerField(null=True, blank=True)

    # Computed density / share metrics
    young_renter_density = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
    )
    young_population_share = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
    )
    renting_propensity = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
    )
    single_household_density = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
    )

    # Scores and rankings
    demand_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        db_index=True,
    )
    demand_classification = models.CharField(max_length=20, null=True, blank=True)
    national_rank = models.IntegerField(null=True, blank=True)
    regional_rank = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['la_name']
        verbose_name = 'Local Authority Demand'
        verbose_name_plural = 'Local Authority Demand Records'

    def __str__(self):
        return f"{self.la_name} ({self.la_code})"


class SpareRoomRent(models.Model):
    """Quarterly average room rent data from SpareRoom."""
    location_name = models.CharField(max_length=200, db_index=True)
    avg_room_rent = models.DecimalField(
        max_digits=8, decimal_places=2,
        help_text='Average monthly room rent in GBP',
    )
    quarter = models.CharField(max_length=4, help_text='e.g. Q4')
    year = models.IntegerField(help_text='e.g. 2024')

    class Meta:
        unique_together = ['location_name', 'quarter', 'year']
        ordering = ['-year', 'quarter', 'location_name']
        verbose_name = 'SpareRoom Rent'
        verbose_name_plural = 'SpareRoom Rents'

    def __str__(self):
        return f"{self.location_name} — £{self.avg_room_rent}/mo ({self.quarter} {self.year})"


class OutcodeLAMapping(models.Model):
    """Maps an outcode to its primary local authority."""
    outcode = models.OneToOneField(
        'areas.PostcodeDistrict',
        on_delete=models.CASCADE,
        to_field='code',
        primary_key=True,
        related_name='la_mapping',
    )
    local_authority = models.ForeignKey(
        LocalAuthorityDemand,
        on_delete=models.CASCADE,
        related_name='outcodes',
    )

    class Meta:
        verbose_name = 'Outcode → LA Mapping'
        verbose_name_plural = 'Outcode → LA Mappings'

    def __str__(self):
        return f"{self.outcode_id} → {self.local_authority_id}"
