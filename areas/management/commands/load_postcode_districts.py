"""
Load UK postcode districts from the CSV file into the PostcodeDistrict model.

Usage:
    python manage.py load_postcode_districts "data/UK Postcode Districts (1).csv"
    python manage.py load_postcode_districts "data/UK Postcode Districts (1).csv" --clear
"""

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from areas.models import PostcodeDistrict


def safe_int(value):
    """Parse an integer, returning None for empty/invalid values."""
    if not value or not value.strip():
        return None
    try:
        return int(value.strip().replace(",", ""))
    except (ValueError, TypeError):
        return None


def safe_decimal(value):
    """Parse a decimal, returning None for empty/invalid values."""
    if not value or not value.strip():
        return None
    try:
        return Decimal(value.strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


class Command(BaseCommand):
    help = "Load UK postcode districts from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("file", type=str, help="Path to the CSV file")
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing PostcodeDistrict data before loading",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        if options["clear"]:
            self.stdout.write("Clearing existing PostcodeDistrict data...")
            PostcodeDistrict.objects.all().delete()

        self.stdout.write(f"Loading postcode districts from {file_path}...")

        created = 0
        updated = 0
        skipped = 0

        with open(file_path, "r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                code = row.get("Postcode", "").strip()
                if not code:
                    skipped += 1
                    continue

                name = row.get("Town/Area", "").strip() or code
                region = row.get("Region", "").strip()
                uk_region = row.get("UK region", "").strip()
                post_town = row.get("Post Town", "").strip()
                lat = safe_decimal(row.get("Latitude", ""))
                lng = safe_decimal(row.get("Longitude", ""))
                easting = safe_int(row.get("Easting", ""))
                northing = safe_int(row.get("Northing", ""))
                grid_ref = row.get("Grid Reference", "").strip()
                population = safe_int(row.get("Population", ""))
                households = safe_int(row.get("Households", ""))
                postcode_count = safe_int(row.get("Postcodes", ""))
                active_postcode_count = safe_int(row.get("Active postcodes", ""))
                nearby = row.get("Nearby districts", "").strip()

                _, was_created = PostcodeDistrict.objects.update_or_create(
                    code=code,
                    defaults={
                        "name": name,
                        "region": region,
                        "uk_region": uk_region,
                        "post_town": post_town,
                        "latitude": lat,
                        "longitude": lng,
                        "easting": easting,
                        "northing": northing,
                        "grid_reference": grid_ref,
                        "population": population,
                        "households": households,
                        "postcode_count": postcode_count,
                        "active_postcode_count": active_postcode_count,
                        "nearby_districts": nearby,
                    },
                )

                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done: {created} created, {updated} updated, {skipped} skipped"
        ))
        self.stdout.write(f"Total PostcodeDistrict records: {PostcodeDistrict.objects.count()}")
