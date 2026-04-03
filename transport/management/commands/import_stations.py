"""
Import UK railway stations from a CSV file into the RailwayStation model.

Matches each station to a PostcodeDistrict via postcode, falling back to
Haversine nearest-neighbour against all PostcodeDistrict centroids.

Usage:
    python manage.py import_stations "data/GB Stations (1).csv"
"""

import csv
import math
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from areas.models import PostcodeDistrict
from transport.models import RailwayStation


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two points."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = (math.radians(v) for v in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class Command(BaseCommand):
    help = "Import railway stations from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("file", type=str, help="Path to the stations CSV file.")

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        # First pass: ensure a PostcodeDistrict exists for every outcode in the CSV
        self.stdout.write("Creating missing PostcodeDistrict records from CSV postcodes...")
        created_districts = 0
        with open(file_path, "r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                postcode = row.get("Postcode", "").strip()
                if not postcode or " " not in postcode:
                    continue
                oc_code = postcode.rsplit(" ", 1)[0].upper()
                try:
                    lat = float(row.get("Latitude", "").strip())
                    lon = float(row.get("Longitude", "").strip())
                except (ValueError, TypeError):
                    continue
                _, created = PostcodeDistrict.objects.get_or_create(
                    code=oc_code,
                    defaults={
                        "name": oc_code,
                        "region": "",
                        "latitude": lat,
                        "longitude": lon,
                    },
                )
                if created:
                    created_districts += 1
        self.stdout.write(f"Created {created_districts} new PostcodeDistrict records.")

        # Load all PostcodeDistricts into memory for matching
        districts = {
            pd.code: (float(pd.latitude), float(pd.longitude))
            for pd in PostcodeDistrict.objects.filter(
                latitude__isnull=False, longitude__isnull=False
            )
        }
        district_objects = {
            pd.code: pd
            for pd in PostcodeDistrict.objects.all()
        }
        self.stdout.write(f"Loaded {len(districts)} postcode districts for matching.")

        stats = {
            "total_rows": 0,
            "imported": 0,
            "matched_postcode": 0,
            "matched_haversine": 0,
            "skipped_no_tlc": 0,
            "skipped_no_coords": 0,
        }

        with open(file_path, "r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                stats["total_rows"] += 1
                self._process_row(row, districts, district_objects, stats)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Import summary:"))
        self.stdout.write(f"  Total CSV rows:              {stats['total_rows']}")
        self.stdout.write(f"  Stations imported:           {stats['imported']}")
        self.stdout.write(f"  Matched via postcode:        {stats['matched_postcode']}")
        self.stdout.write(f"  Matched via Haversine:       {stats['matched_haversine']}")
        self.stdout.write(f"  Skipped (missing TLC):       {stats['skipped_no_tlc']}")
        self.stdout.write(f"  Skipped (missing coords):    {stats['skipped_no_coords']}")

        # Top 10 busiest stations
        self.stdout.write("")
        self.stdout.write("Top 10 busiest stations:")
        top = RailwayStation.objects.filter(
            annual_entries_exits__isnull=False
        ).order_by("-annual_entries_exits")[:10]
        for i, s in enumerate(top, 1):
            self.stdout.write(
                f"  {i:>2}. {s.station_name:<30} {s.tlc_code}  "
                f"{s.annual_entries_exits:>12,}  ({s.outcode_id or '?'})"
            )

    def _process_row(self, row, districts, district_objects, stats):
        tlc = row.get("TLC", "").strip()
        if not tlc or len(tlc) != 3:
            stats["skipped_no_tlc"] += 1
            return

        try:
            lat = float(row.get("Latitude", "").strip())
            lon = float(row.get("Longitude", "").strip())
        except (ValueError, TypeError):
            stats["skipped_no_coords"] += 1
            return

        station_name = row.get("Station", "").strip()

        # Parse annual entries/exits
        raw_usage = row.get("Entries and exits 2025", "").strip().replace(",", "")
        try:
            annual = int(raw_usage)
        except (ValueError, TypeError):
            annual = None

        # Match to PostcodeDistrict
        postcode = row.get("Postcode", "").strip()
        district_obj = None
        match_method = None

        if postcode and " " in postcode:
            oc_code = postcode.rsplit(" ", 1)[0].upper()
            if oc_code in district_objects:
                district_obj = district_objects[oc_code]
                match_method = "postcode"

        if district_obj is None and districts:
            district_obj, match_method = self._find_nearest_district(
                lat, lon, districts, district_objects
            )

        RailwayStation.objects.update_or_create(
            tlc_code=tlc,
            defaults={
                "station_name": station_name,
                "latitude": lat,
                "longitude": lon,
                "outcode": district_obj,
                "annual_entries_exits": annual,
            },
        )

        stats["imported"] += 1
        if match_method == "postcode":
            stats["matched_postcode"] += 1
        elif match_method == "haversine":
            stats["matched_haversine"] += 1

    def _find_nearest_district(self, lat, lon, districts, district_objects):
        best_code = None
        best_dist = float("inf")
        for code, (d_lat, d_lon) in districts.items():
            d = haversine_km(lat, lon, d_lat, d_lon)
            if d < best_dist:
                best_dist = d
                best_code = code
        if best_code:
            return district_objects[best_code], "haversine"
        return None, None
