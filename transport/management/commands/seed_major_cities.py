"""Seed the MajorCity table with UK major cities."""

from django.core.management.base import BaseCommand
from transport.models import MajorCity

CITIES = [
    {"name": "London", "station_codes": ["LBG", "VIC", "WAT", "PAD", "EUS", "KGX", "LST", "STP", "CHX", "FST", "MYB", "CTK"], "latitude": 51.5074, "longitude": -0.1278, "population": 8982000},
    {"name": "Birmingham", "station_codes": ["BHM", "BHI"], "latitude": 52.4862, "longitude": -1.8904, "population": 1144900},
    {"name": "Manchester", "station_codes": ["MAN", "MCV", "MPL"], "latitude": 53.4808, "longitude": -2.2426, "population": 553230},
    {"name": "Leeds", "station_codes": ["LDS"], "latitude": 53.7965, "longitude": -1.5478, "population": 503388},
    {"name": "Liverpool", "station_codes": ["LIV", "LPY"], "latitude": 53.4084, "longitude": -2.9916, "population": 498042},
    {"name": "Sheffield", "station_codes": ["SHF"], "latitude": 53.3811, "longitude": -1.4701, "population": 584853},
    {"name": "Bristol", "station_codes": ["BRI", "BPW"], "latitude": 51.4545, "longitude": -2.5879, "population": 467099},
    {"name": "Newcastle", "station_codes": ["NCL"], "latitude": 54.9783, "longitude": -1.6178, "population": 302820},
    {"name": "Nottingham", "station_codes": ["NOT"], "latitude": 52.9548, "longitude": -1.1581, "population": 321500},
    {"name": "Leicester", "station_codes": ["LEI"], "latitude": 52.6369, "longitude": -1.1398, "population": 354224},
    {"name": "Edinburgh", "station_codes": ["EDB", "HYM"], "latitude": 55.9533, "longitude": -3.1883, "population": 488050},
    {"name": "Glasgow", "station_codes": ["GLC", "GLQ"], "latitude": 55.8642, "longitude": -4.2518, "population": 635130},
    {"name": "Cardiff", "station_codes": ["CDF"], "latitude": 51.4816, "longitude": -3.1791, "population": 362400},
    {"name": "Belfast", "station_codes": ["BFT", "BFC"], "latitude": 54.5973, "longitude": -5.9301, "population": 345418},
]


class Command(BaseCommand):
    help = "Seed the MajorCity table with UK major cities."

    def handle(self, *args, **options):
        for city in CITIES:
            obj, created = MajorCity.objects.update_or_create(
                name=city["name"],
                defaults={
                    "station_codes": city["station_codes"],
                    "latitude": city["latitude"],
                    "longitude": city["longitude"],
                    "population": city["population"],
                },
            )
            action = "Created" if created else "Updated"
            self.stdout.write(f"  {action}: {obj.name}")

        self.stdout.write(self.style.SUCCESS(f"Done — {len(CITIES)} major cities seeded."))
