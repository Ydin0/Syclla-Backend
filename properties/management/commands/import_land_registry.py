"""
Import Land Registry Price Paid Data (PPD) CSV files into PropertyTransaction,
then rebuild the OutcodePropertyStats and OutcodePropertyStatsByType aggregates.

Land Registry CSV format (no header, comma-delimited, double-quoted fields):
    0: transaction_id   (GUID)
    1: price            (int)
    2: date_of_transfer (YYYY-MM-DD HH:MM)
    3: postcode
    4: property_type    (D/S/T/F/O)
    5: old_new          (Y/N)
    6: duration         (F/L)
    7: paon
    8: saon
    9: street
   10: locality
   11: town_city
   12: district
   13: county
   14: ppd_category     (A/B)
   15: record_status    (A/C/D)

Usage:
    python manage.py import_land_registry pp-2024.csv pp-2023.csv
    python manage.py import_land_registry pp-complete.csv --min-date 2020-01-01
    python manage.py import_land_registry pp-complete.csv --skip-aggregation
"""

import csv
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Avg, Count, Max, Min

from properties.models import (
    OutcodePropertyStats,
    OutcodePropertyStatsByType,
    PropertyTransaction,
)


class Command(BaseCommand):
    help = "Import Land Registry Price Paid CSV files and rebuild outcode aggregates."

    def add_arguments(self, parser):
        parser.add_argument(
            "files",
            nargs="+",
            type=str,
            help="One or more Land Registry CSV file paths.",
        )
        parser.add_argument(
            "--min-date",
            type=str,
            default="2020-01-01",
            help="Skip transactions before this date (YYYY-MM-DD). Default: 2020-01-01",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=5000,
            help="bulk_create batch size. Default: 5000",
        )
        parser.add_argument(
            "--skip-aggregation",
            action="store_true",
            help="Import transactions only; skip aggregate table rebuild.",
        )

    def handle(self, *args, **options):
        min_date = self._parse_date(options["min_date"])
        batch_size = options["batch_size"]
        file_paths = [self._validate_path(f) for f in options["files"]]

        # --- Phase 1: Import transactions ---
        total_created = 0
        total_skipped = 0
        t0 = time.monotonic()

        for fp in file_paths:
            created, skipped = self._import_file(fp, min_date, batch_size)
            total_created += created
            total_skipped += skipped

        elapsed = time.monotonic() - t0
        self.stdout.write(self.style.SUCCESS(
            f"Import complete — {total_created:,} created, {total_skipped:,} skipped "
            f"in {elapsed:.1f}s across {len(file_paths)} file(s)."
        ))

        # --- Phase 2: Rebuild aggregates ---
        if not options["skip_aggregation"]:
            self._rebuild_aggregates()

    # ------------------------------------------------------------------
    # Phase 1 helpers
    # ------------------------------------------------------------------

    def _import_file(self, file_path: Path, min_date: date, batch_size: int):
        self.stdout.write(f"Reading {file_path.name} ...")
        batch = []
        created = 0
        skipped = 0
        row_num = 0

        with open(file_path, "r", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            for row in reader:
                row_num += 1

                if row_num % 100_000 == 0:
                    self.stdout.write(f"  ... {row_num:,} rows processed")

                obj = self._parse_row(row, min_date)
                if obj is None:
                    skipped += 1
                    continue

                batch.append(obj)

                if len(batch) >= batch_size:
                    created += self._flush(batch)
                    batch.clear()

            if batch:
                created += self._flush(batch)

        self.stdout.write(
            f"  {file_path.name}: {created:,} created, {skipped:,} skipped "
            f"({row_num:,} rows total)"
        )
        return created, skipped

    def _parse_row(self, row: list, min_date: date):
        """Return a PropertyTransaction instance or None to skip."""
        if len(row) < 16:
            return None

        postcode = row[3].strip()
        if not postcode or " " not in postcode:
            return None

        try:
            transfer_date = datetime.strptime(row[2].strip(), "%Y-%m-%d %H:%M").date()
        except ValueError:
            return None

        if transfer_date < min_date:
            return None

        outcode = postcode.rsplit(" ", 1)[0]

        try:
            price = int(row[1])
        except (ValueError, IndexError):
            return None

        return PropertyTransaction(
            transaction_id=row[0].strip(),
            price=price,
            date_of_transfer=transfer_date,
            postcode=postcode,
            outcode=outcode,
            property_type=row[4].strip() or "O",
            old_new=row[5].strip() or "N",
            duration=row[6].strip() or "F",
            paon=row[7].strip(),
            saon=row[8].strip(),
            street=row[9].strip(),
            locality=row[10].strip(),
            town_city=row[11].strip(),
            district=row[12].strip(),
            county=row[13].strip(),
            ppd_category=row[14].strip() or "A",
            record_status=row[15].strip() or "A",
        )

    def _flush(self, batch: list) -> int:
        objs = PropertyTransaction.objects.bulk_create(
            batch, ignore_conflicts=True, batch_size=len(batch),
        )
        return len(objs)

    # ------------------------------------------------------------------
    # Phase 2: Aggregate rebuild
    # ------------------------------------------------------------------

    def _rebuild_aggregates(self):
        self.stdout.write("Rebuilding outcode aggregates ...")
        t0 = time.monotonic()

        self._rebuild_outcode_stats()
        self._rebuild_outcode_stats_by_type()

        elapsed = time.monotonic() - t0
        self.stdout.write(self.style.SUCCESS(
            f"Aggregation complete in {elapsed:.1f}s."
        ))

    def _rebuild_outcode_stats(self):
        """Aggregate all transactions per outcode into OutcodePropertyStats."""
        # Basic aggregates via ORM
        agg_qs = (
            PropertyTransaction.objects
            .values("outcode")
            .annotate(
                avg_price=Avg("price"),
                min_price=Min("price"),
                max_price=Max("price"),
                transaction_count=Count("transaction_id"),
                avg_floor_area_sqm=Avg("total_floor_area_sqm"),
                avg_price_per_sqm=Avg("price_per_sqm"),
                data_from_date=Min("date_of_transfer"),
                data_to_date=Max("date_of_transfer"),
            )
        )

        # Pre-compute medians via SQL window function
        medians = self._compute_medians(
            group_by_cols=["outcode"],
            value_col="price",
        )

        rows = []
        for agg in agg_qs.iterator():
            oc = agg["outcode"]
            rows.append(OutcodePropertyStats(
                outcode=oc,
                avg_price=agg["avg_price"],
                median_price=medians.get(oc, agg["avg_price"]),
                avg_price_per_sqm=agg["avg_price_per_sqm"],
                min_price=agg["min_price"],
                max_price=agg["max_price"],
                transaction_count=agg["transaction_count"],
                avg_floor_area_sqm=agg["avg_floor_area_sqm"],
                data_from_date=agg["data_from_date"],
                data_to_date=agg["data_to_date"],
            ))

        OutcodePropertyStats.objects.all().delete()
        OutcodePropertyStats.objects.bulk_create(rows, batch_size=2000)
        self.stdout.write(f"  OutcodePropertyStats: {len(rows):,} outcodes")

    def _rebuild_outcode_stats_by_type(self):
        """Aggregate per (outcode, property_type) into OutcodePropertyStatsByType."""
        agg_qs = (
            PropertyTransaction.objects
            .values("outcode", "property_type")
            .annotate(
                avg_price=Avg("price"),
                transaction_count=Count("transaction_id"),
                avg_floor_area_sqm=Avg("total_floor_area_sqm"),
                avg_price_per_sqm=Avg("price_per_sqm"),
            )
        )

        medians = self._compute_medians(
            group_by_cols=["outcode", "property_type"],
            value_col="price",
        )

        rows = []
        for agg in agg_qs.iterator():
            key = (agg["outcode"], agg["property_type"])
            rows.append(OutcodePropertyStatsByType(
                outcode=agg["outcode"],
                property_type=agg["property_type"],
                avg_price=agg["avg_price"],
                median_price=medians.get(key, agg["avg_price"]),
                avg_price_per_sqm=agg["avg_price_per_sqm"],
                transaction_count=agg["transaction_count"],
                avg_floor_area_sqm=agg["avg_floor_area_sqm"],
            ))

        OutcodePropertyStatsByType.objects.all().delete()
        OutcodePropertyStatsByType.objects.bulk_create(rows, batch_size=2000)
        self.stdout.write(f"  OutcodePropertyStatsByType: {len(rows):,} rows")

    def _compute_medians(self, group_by_cols: list, value_col: str) -> dict:
        """
        Compute median of `value_col` grouped by `group_by_cols` using
        PostgreSQL's PERCENTILE_CONT window function.

        Returns dict mapping group key (str or tuple) -> Decimal median.
        """
        group_select = ", ".join(group_by_cols)
        table = PropertyTransaction._meta.db_table

        sql = f"""
            SELECT {group_select}, PERCENTILE_CONT(0.5)
                WITHIN GROUP (ORDER BY {value_col}) AS median_val
            FROM {table}
            GROUP BY {group_select}
        """

        result = {}
        with connection.cursor() as cursor:
            cursor.execute(sql)
            for row in cursor.fetchall():
                if len(group_by_cols) == 1:
                    key = row[0]
                else:
                    key = tuple(row[:-1])
                result[key] = Decimal(str(row[-1])) if row[-1] is not None else None

        return result

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _parse_date(self, date_str: str) -> date:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise CommandError(f"Invalid date format: {date_str!r}. Use YYYY-MM-DD.")

    def _validate_path(self, path_str: str) -> Path:
        p = Path(path_str)
        if not p.exists():
            raise CommandError(f"File not found: {p}")
        return p
