"""
Map PostcodeDistrict outcodes to LocalAuthorityDemand records via postcodes.io.

For each outcode, calls /outcodes/{code} to get admin_district names,
then matches the first name to a LocalAuthorityDemand.la_name.

Usage:
    python manage.py map_outcodes_to_la
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen, Request
import json

from django.core.management.base import BaseCommand

from areas.models import PostcodeDistrict
from hmo.models import LocalAuthorityDemand, OutcodeLAMapping


POSTCODES_IO = "https://api.postcodes.io/outcodes/"
BATCH_SIZE = 50  # concurrent requests
TIMEOUT = 10


def _fetch_outcode(code):
    """Fetch admin_district list from postcodes.io for a single outcode."""
    try:
        req = Request(
            f"{POSTCODES_IO}{code}",
            headers={"Accept": "application/json"},
        )
        with urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
            if data.get("status") == 200 and data.get("result"):
                return code, data["result"].get("admin_district", [])
    except Exception:
        pass
    return code, []


class Command(BaseCommand):
    help = "Map outcodes to local authorities using postcodes.io"

    def handle(self, *args, **options):
        # Build la_name -> LocalAuthorityDemand lookup (case-insensitive)
        la_by_name = {}
        for la in LocalAuthorityDemand.objects.all():
            la_by_name[la.la_name.lower()] = la

        self.stdout.write(f"LocalAuthorityDemand records loaded: {len(la_by_name)}")

        outcodes = list(
            PostcodeDistrict.objects.values_list("code", flat=True).order_by("code")
        )
        self.stdout.write(f"PostcodeDistricts to map: {len(outcodes)}")

        matched = 0
        no_api = 0
        no_la_match = 0
        mappings = []

        total = len(outcodes)
        done = 0

        for batch_start in range(0, total, BATCH_SIZE):
            batch = outcodes[batch_start : batch_start + BATCH_SIZE]

            with ThreadPoolExecutor(max_workers=BATCH_SIZE) as pool:
                futures = {pool.submit(_fetch_outcode, code): code for code in batch}
                for future in as_completed(futures):
                    code, districts = future.result()
                    done += 1

                    if not districts:
                        no_api += 1
                        continue

                    # Try each admin_district name until we find a census match
                    la = None
                    for name in districts:
                        la = la_by_name.get(name.lower())
                        if la:
                            break

                    if la is None:
                        no_la_match += 1
                        continue

                    mappings.append(
                        OutcodeLAMapping(outcode_id=code, local_authority=la)
                    )
                    matched += 1

            self.stdout.write(
                f"  {done}/{total} processed — "
                f"{matched} matched, {no_la_match} no LA, {no_api} no API result"
            )

            # Brief pause between batches to be polite
            if batch_start + BATCH_SIZE < total:
                time.sleep(0.2)

        # Bulk create
        OutcodeLAMapping.objects.bulk_create(mappings, ignore_conflicts=True)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("Outcode → LA mapping complete"))
        self.stdout.write(f"  Total outcodes:    {total}")
        self.stdout.write(f"  Mapped:            {matched}")
        self.stdout.write(f"  No API result:     {no_api}")
        self.stdout.write(f"  No LA match:       {no_la_match}")
        self.stdout.write(self.style.SUCCESS("=" * 60))
