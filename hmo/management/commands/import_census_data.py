"""
Import Census 2021 data from ONS CSV files into LocalAuthorityDemand.

Reads three files:
  - TS007 2021 Data.csv  (age by single year per LA)
  - TS003 2021 Data.csv  (household composition per LA)
  - TS054 2021 Data.csv  (tenure per LA)

Calculates demand metrics, percentile-weighted composite score,
and national/regional rankings.

Usage:
    python manage.py import_census_data
"""

import csv
import statistics
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from hmo.models import LocalAuthorityDemand


DATA_DIR = Path("data")

TS007_FILE = DATA_DIR / "TS007 2021 Data.csv"
TS003_FILE = DATA_DIR / "TS003 2021 Data.csv"
TS054_FILE = DATA_DIR / "TS054 2021 Data.csv"

# Composite score weights
W_YOUNG_RENTER_DENSITY = 0.50
W_RENTING_PROPENSITY = 0.25
W_SINGLE_HOUSEHOLD_DENSITY = 0.15
W_YOUNG_POP_SHARE = 0.10

# Region derivation from LA code prefix
REGION_MAP = {
    "E": "England",
    "W": "Wales",
    "S": "Scotland",
    "N": "Northern Ireland",
}


def _safe_int(val):
    try:
        return int(val.strip().replace(",", ""))
    except (ValueError, TypeError, AttributeError):
        return 0


def _percentile_rank(values):
    """Return a dict mapping each index to its percentile (0-100)."""
    n = len(values)
    if n <= 1:
        return {0: 50.0}
    sorted_with_idx = sorted(enumerate(values), key=lambda x: x[1])
    ranks = {}
    for rank_pos, (orig_idx, _) in enumerate(sorted_with_idx):
        ranks[orig_idx] = (rank_pos / (n - 1)) * 100
    return ranks


class Command(BaseCommand):
    help = "Import Census 2021 data and calculate demand scores for Local Authorities"

    def handle(self, *args, **options):
        for f in (TS007_FILE, TS003_FILE, TS054_FILE):
            if not f.exists():
                raise CommandError(f"File not found: {f}")

        self.stdout.write("Reading TS007 (age data)...")
        age_data = self._read_age_data()
        self.stdout.write(f"  {len(age_data)} LAs found")

        self.stdout.write("Reading TS003 (household composition)...")
        household_data = self._read_household_data()
        self.stdout.write(f"  {len(household_data)} LAs found")

        self.stdout.write("Reading TS054 (tenure)...")
        tenure_data = self._read_tenure_data()
        self.stdout.write(f"  {len(tenure_data)} LAs found")

        # Intersect all three datasets
        all_codes = set(age_data) & set(household_data) & set(tenure_data)
        self.stdout.write(f"LAs present in all 3 files: {len(all_codes)}")

        # Build per-LA records
        la_records = []
        for code in sorted(all_codes):
            age = age_data[code]
            hh = household_data[code]
            ten = tenure_data[code]

            total_pop = age["total_population"]
            pop_20_34 = age["population_20_34"]
            total_private_renters = ten["private_renters"]
            single_person_under66 = hh["single_person_under66"]

            # Proxy: private_renters_20_34
            if total_pop > 0:
                private_renters_20_34 = round(
                    (total_private_renters / total_pop) * pop_20_34
                )
            else:
                private_renters_20_34 = 0

            # Density / share metrics
            if total_pop > 0:
                young_renter_density = (private_renters_20_34 / total_pop) * 1000
                young_pop_share = (pop_20_34 / total_pop) * 100
                single_hh_density = (single_person_under66 / total_pop) * 1000
            else:
                young_renter_density = 0
                young_pop_share = 0
                single_hh_density = 0

            if pop_20_34 > 0:
                renting_propensity = (private_renters_20_34 / pop_20_34) * 100
            else:
                renting_propensity = 0

            region = REGION_MAP.get(code[0], "Unknown")

            la_records.append({
                "la_code": code,
                "la_name": age["la_name"],
                "region": region,
                "total_population": total_pop,
                "population_20_34": pop_20_34,
                "private_renters_20_34": private_renters_20_34,
                "single_person_households_under66": single_person_under66,
                "young_renter_density": young_renter_density,
                "young_population_share": young_pop_share,
                "renting_propensity": renting_propensity,
                "single_household_density": single_hh_density,
            })

        # Percentile rankings
        self.stdout.write("Calculating percentile rankings...")
        yrd_vals = [r["young_renter_density"] for r in la_records]
        rp_vals = [r["renting_propensity"] for r in la_records]
        shd_vals = [r["single_household_density"] for r in la_records]
        yps_vals = [r["young_population_share"] for r in la_records]

        yrd_pct = _percentile_rank(yrd_vals)
        rp_pct = _percentile_rank(rp_vals)
        shd_pct = _percentile_rank(shd_vals)
        yps_pct = _percentile_rank(yps_vals)

        # Raw composite scores
        raw_scores = []
        for i, r in enumerate(la_records):
            raw = (
                yrd_pct[i] * W_YOUNG_RENTER_DENSITY
                + rp_pct[i] * W_RENTING_PROPENSITY
                + shd_pct[i] * W_SINGLE_HOUSEHOLD_DENSITY
                + yps_pct[i] * W_YOUNG_POP_SHARE
            )
            raw_scores.append(raw)

        # Normalise to 0-100
        min_raw = min(raw_scores)
        max_raw = max(raw_scores)
        score_range = max_raw - min_raw if max_raw != min_raw else 1

        for i, r in enumerate(la_records):
            r["demand_score"] = round(
                ((raw_scores[i] - min_raw) / score_range) * 100, 2
            )

        # National rank (1 = highest demand)
        sorted_national = sorted(
            range(len(la_records)),
            key=lambda i: la_records[i]["demand_score"],
            reverse=True,
        )
        for rank, idx in enumerate(sorted_national, 1):
            la_records[idx]["national_rank"] = rank

        # Regional rank
        region_groups = defaultdict(list)
        for i, r in enumerate(la_records):
            region_groups[r["region"]].append(i)

        for region, indices in region_groups.items():
            sorted_regional = sorted(
                indices,
                key=lambda i: la_records[i]["demand_score"],
                reverse=True,
            )
            for rank, idx in enumerate(sorted_regional, 1):
                la_records[idx]["regional_rank"] = rank

        # Save to database
        self.stdout.write("Saving to database...")
        created = 0
        updated = 0
        for r in la_records:
            _, was_created = LocalAuthorityDemand.objects.update_or_create(
                la_code=r["la_code"],
                defaults={
                    "la_name": r["la_name"],
                    "region": r["region"],
                    "total_population": r["total_population"],
                    "population_20_34": r["population_20_34"],
                    "private_renters_20_34": r["private_renters_20_34"],
                    "single_person_households_under66": r["single_person_households_under66"],
                    "young_renter_density": Decimal(str(round(r["young_renter_density"], 4))),
                    "young_population_share": Decimal(str(round(r["young_population_share"], 4))),
                    "renting_propensity": Decimal(str(round(r["renting_propensity"], 4))),
                    "single_household_density": Decimal(str(round(r["single_household_density"], 4))),
                    "demand_score": Decimal(str(r["demand_score"])),
                    "national_rank": r["national_rank"],
                    "regional_rank": r["regional_rank"],
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        # Summary
        scores = [r["demand_score"] for r in la_records]
        mean_score = statistics.mean(scores)
        median_score = statistics.median(scores)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("Census import complete"))
        self.stdout.write(f"  Total LAs processed:  {len(la_records)}")
        self.stdout.write(f"  Created:              {created}")
        self.stdout.write(f"  Updated:              {updated}")
        self.stdout.write(f"  Mean demand score:    {mean_score:.1f}")
        self.stdout.write(f"  Median demand score:  {median_score:.1f}")

        self.stdout.write("")
        self.stdout.write(
            "NOTE: private_renters_20_34 is approximated as "
            "(total_private_renters / total_population) * population_20_34 "
            "because TS054 does not cross-tabulate tenure by age."
        )

        self.stdout.write("")
        self.stdout.write("Top 10 LAs by demand score:")
        top10 = sorted(la_records, key=lambda r: r["demand_score"], reverse=True)[:10]
        for i, r in enumerate(top10, 1):
            self.stdout.write(
                f"  {i:>2}. {r['la_name']:<35} ({r['la_code']})  "
                f"score={r['demand_score']:>5.1f}  pop={r['total_population']:>9,}"
            )

        self.stdout.write("")
        self.stdout.write("Bottom 10 LAs by demand score:")
        bottom10 = sorted(la_records, key=lambda r: r["demand_score"])[:10]
        for i, r in enumerate(bottom10, 1):
            self.stdout.write(
                f"  {i:>2}. {r['la_name']:<35} ({r['la_code']})  "
                f"score={r['demand_score']:>5.1f}  pop={r['total_population']:>9,}"
            )

        self.stdout.write(self.style.SUCCESS("=" * 60))

    def _read_age_data(self):
        """Parse TS007: age by single year. Returns {la_code: {la_name, total_population, population_20_34}}."""
        result = {}
        with open(TS007_FILE, "r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                code = row["Lower tier local authorities Code"].strip()
                name = row["Lower tier local authorities"].strip()
                age_code = _safe_int(row["Age (101 categories) Code"])
                count = _safe_int(row["Observation"])

                if code not in result:
                    result[code] = {
                        "la_name": name,
                        "total_population": 0,
                        "population_20_34": 0,
                    }

                result[code]["total_population"] += count
                if 20 <= age_code <= 34:
                    result[code]["population_20_34"] += count

        return result

    def _read_household_data(self):
        """Parse TS003: household composition. Returns {la_code: {single_person_under66}}."""
        result = {}
        with open(TS003_FILE, "r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                code = row["Lower Tier Local Authorities Code"].strip()
                cat_code = _safe_int(row["Household composition (15 categories) Code"])
                count = _safe_int(row["Observation"])

                if code not in result:
                    result[code] = {"single_person_under66": 0}

                # Code 2 = "One person household: Other" (i.e. under 66)
                if cat_code == 2:
                    result[code]["single_person_under66"] = count

        return result

    def _read_tenure_data(self):
        """Parse TS054: tenure. Returns {la_code: {private_renters}}."""
        result = {}
        with open(TS054_FILE, "r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                code = row["Lower Tier Local Authorities Code"].strip()
                cat_code = _safe_int(row["Tenure of household (9 categories) Code"])
                count = _safe_int(row["Observation"])

                if code not in result:
                    result[code] = {"private_renters": 0}

                # Code 5 = Private landlord/letting agency
                # Code 6 = Other private rented
                if cat_code in (5, 6):
                    result[code]["private_renters"] += count

        return result
