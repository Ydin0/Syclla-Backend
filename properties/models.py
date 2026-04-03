from django.db import models
from django.utils import timezone


class PropertyTransaction(models.Model):
    """Individual Land Registry Price Paid transaction, enriched with EPC data."""

    PROPERTY_TYPE_CHOICES = [
        ('D', 'Detached'),
        ('S', 'Semi-Detached'),
        ('T', 'Terraced'),
        ('F', 'Flat'),
        ('O', 'Other'),
    ]
    OLD_NEW_CHOICES = [
        ('Y', 'New Build'),
        ('N', 'Established'),
    ]
    DURATION_CHOICES = [
        ('F', 'Freehold'),
        ('L', 'Leasehold'),
    ]
    PPD_CATEGORY_CHOICES = [
        ('A', 'Standard Price Paid'),
        ('B', 'Additional Price Paid'),
    ]
    RECORD_STATUS_CHOICES = [
        ('A', 'Addition'),
        ('C', 'Change'),
        ('D', 'Delete'),
    ]

    # Land Registry core fields
    transaction_id = models.CharField(max_length=38, primary_key=True)
    price = models.PositiveIntegerField()
    date_of_transfer = models.DateField(db_index=True)
    postcode = models.CharField(max_length=8, db_index=True)
    outcode = models.CharField(max_length=4, db_index=True)
    property_type = models.CharField(max_length=1, choices=PROPERTY_TYPE_CHOICES, db_index=True)
    old_new = models.CharField(max_length=1, choices=OLD_NEW_CHOICES)
    duration = models.CharField(max_length=1, choices=DURATION_CHOICES)

    # Address fields
    paon = models.CharField(max_length=100, blank=True)
    saon = models.CharField(max_length=100, blank=True)
    street = models.CharField(max_length=200, blank=True)
    locality = models.CharField(max_length=200, blank=True)
    town_city = models.CharField(max_length=200, blank=True)
    district = models.CharField(max_length=200, blank=True)
    county = models.CharField(max_length=200, blank=True)

    # Classification
    ppd_category = models.CharField(max_length=1, choices=PPD_CATEGORY_CHOICES)
    record_status = models.CharField(max_length=1, choices=RECORD_STATUS_CHOICES)

    # EPC enrichment fields (populated later)
    total_floor_area_sqm = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
    )
    price_per_sqm = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Calculated: price / total_floor_area_sqm',
    )
    property_type_epc = models.CharField(
        max_length=50, null=True, blank=True,
        help_text='Detailed EPC type e.g. "End-Terrace", "Ground-Floor Flat"',
    )
    number_habitable_rooms = models.IntegerField(null=True, blank=True)
    construction_age_band = models.CharField(
        max_length=50, null=True, blank=True,
        help_text='e.g. "1976-1982"',
    )

    class Meta:
        ordering = ['-date_of_transfer']
        verbose_name = 'Property Transaction'
        verbose_name_plural = 'Property Transactions'
        indexes = [
            models.Index(
                fields=['outcode', 'date_of_transfer'],
                name='idx_proptx_outcode_date',
            ),
            models.Index(
                fields=['outcode', 'property_type'],
                name='idx_proptx_outcode_type',
            ),
        ]

    def __str__(self):
        return f"{self.postcode} — £{self.price:,} ({self.date_of_transfer})"


class OutcodePropertyStats(models.Model):
    """Aggregate property price statistics per outcode."""

    outcode = models.CharField(max_length=4, primary_key=True)
    avg_price = models.DecimalField(max_digits=12, decimal_places=2)
    median_price = models.DecimalField(max_digits=12, decimal_places=2)
    avg_price_per_sqm = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    min_price = models.DecimalField(max_digits=12, decimal_places=2)
    max_price = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_count = models.IntegerField()
    avg_floor_area_sqm = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
    )
    data_from_date = models.DateField()
    data_to_date = models.DateField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['outcode']
        verbose_name = 'Outcode Property Stats'
        verbose_name_plural = 'Outcode Property Stats'

    def __str__(self):
        return f"{self.outcode} — avg £{self.avg_price:,.0f} ({self.transaction_count} txns)"


class OutcodePropertyStatsByType(models.Model):
    """Aggregate property price statistics per outcode and property type."""

    PROPERTY_TYPE_CHOICES = PropertyTransaction.PROPERTY_TYPE_CHOICES

    outcode = models.CharField(max_length=4, db_index=True)
    property_type = models.CharField(
        max_length=1, choices=PROPERTY_TYPE_CHOICES, db_index=True,
    )
    avg_price = models.DecimalField(max_digits=12, decimal_places=2)
    median_price = models.DecimalField(max_digits=12, decimal_places=2)
    avg_price_per_sqm = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    transaction_count = models.IntegerField()
    avg_floor_area_sqm = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['outcode', 'property_type']
        ordering = ['outcode', 'property_type']
        verbose_name = 'Outcode Property Stats by Type'
        verbose_name_plural = 'Outcode Property Stats by Type'

    def __str__(self):
        return f"{self.outcode} [{self.get_property_type_display()}] — avg £{self.avg_price:,.0f}"


class EPCImportProgress(models.Model):
    """Tracks EPC data import progress per outcode."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('complete', 'Complete'),
        ('error', 'Error'),
    ]

    outcode = models.CharField(max_length=4, primary_key=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    records_fetched = models.IntegerField(default=0)
    records_matched = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['outcode']
        verbose_name = 'EPC Import Progress'
        verbose_name_plural = 'EPC Import Progress'

    def __str__(self):
        return f"{self.outcode} — {self.status} ({self.records_fetched} fetched, {self.records_matched} matched)"
