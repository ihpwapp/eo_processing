"""Session-owned job state. No global connections, tokens or result cache."""
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import os
import shutil
import tempfile
import time
import uuid

import matplotlib.pyplot as plt
from pyproj import Geod
from shapely.geometry import shape
import functions2

ROOT = Path(tempfile.gettempdir()) / 'eo-explorer-results'
TTL = 3600


def validate_request(geometry, start, end, products, period_b_start=None, period_b_end=None):
    if not geometry:
        raise ValueError('Draw a polygon on the map first.')
    polygon = shape(geometry)
    if polygon.geom_type != 'Polygon' or polygon.is_empty or not polygon.is_valid:
        raise ValueError('Draw one valid, non-intersecting polygon.')
    west, south, east, north = polygon.bounds
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90) or east - west > 180:
        raise ValueError('Select an area that does not cross the date line.')
    area, _ = Geod(ellps='WGS84').polygon_area_perimeter([west, east, east, west], [south, south, north, north])
    maximum = float(os.getenv('EO_MAX_AREA_KM2', '100'))
    if abs(area) / 1e6 > maximum:
        raise ValueError(f'Select a smaller area (bounding box maximum {maximum:g} km²).')
    if not start or not end or start >= end:
        raise ValueError('The end date must be after the start date (end date is exclusive).')
    if end > date.today():
        raise ValueError('Choose dates no later than today.')
    _validate_interval(start, end)
    if period_b_start is not None or period_b_end is not None:
        if not period_b_start or not period_b_end:
            raise ValueError('Provide both dates for period B.')
        if period_b_start >= period_b_end:
            raise ValueError('Period B: the end date must be after the start date (end date is exclusive).')
        if period_b_start < end:
            raise ValueError('Period B must start on or after the end of period A.')
        if period_b_end > date.today():
            raise ValueError('Choose period B dates no later than today.')
        _validate_interval(period_b_start, period_b_end)
    if not products or any(p not in functions2.PRODUCTS or p == 'sar' for p in products):
        raise ValueError('Select at least one optical product.')
    return polygon


def _validate_interval(first, last):
    days = int(os.getenv('EO_MAX_DAYS', '90'))
    if (last - first).days > days:
        raise ValueError(f'Select a date interval of at most {days} days.')


def cleanup():
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    now = time.time()
    for folder in ROOT.iterdir():
        try:
            if folder.is_dir() and not folder.is_symlink() and now - folder.stat().st_mtime > TTL:
                shutil.rmtree(folder)
        except FileNotFoundError:
            pass


def public_error(error):
    # Provider exceptions can contain request bodies or tokens: never show them verbatim.
    if getattr(error, 'http_status_code', None) in (401, 403):
        return 'Authentication expired or access denied. Reconnect to Copernicus.'
    return 'Processing failed. Check your Copernicus quota, area and dates, then retry.'


@dataclass
class Run:
    polygon: object
    start: date
    end: date
    products: list
    period_b_start: date = None
    period_b_end: date = None
    directory: Path = field(default_factory=lambda: ROOT / uuid.uuid4().hex)
    acquisitions: dict = field(default_factory=dict)
    index: int = 0
    job: object = None
    status: str = 'Waiting'
    results: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)
    canceled: bool = False
    started: float = field(default_factory=time.monotonic)
    stages: list = field(init=False, repr=False, default=None)
    periods: dict = field(init=False, repr=False, default=None)

    def __post_init__(self):
        self.stages = []
        self.periods = {}
        for product in self.products:
            self.stages.append((product, 'A'))
            self.periods[(product, 'A')] = functions2.Period('A', self.start, self.end, product)
            if self.period_b_start is not None or self.period_b_end is not None:
                self.stages.append((product, 'B'))
                self.periods[(product, 'B')] = functions2.Period('B', self.period_b_start, self.period_b_end, product)
                self.stages.append((product, 'diff'))

    @property
    def compare(self):
        return any(stage[1] != 'A' for stage in self.stages)

    @property
    def active(self):
        return not self.canceled and self.index < len(self.stages)

    def cancel(self):
        if self.job is not None:
            self.job.stop_job()  # Keep state active if stop fails; allow retry.
        self.canceled = True
        self.status = 'Canceled'

    def tick(self, connection):
        if not self.active:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        self.directory.touch()
        if time.monotonic() - self.started > TTL:
            self.cancel()
            self.status = 'Stopped after one hour'
            return
        product, phase = self.stages[self.index]
        if phase == 'diff':
            self._difference(product)
            return
        if self.job is None:
            try:
                self.job = functions2.submit_period(connection, self.periods[(product, phase)], self.polygon)
            except Exception as exc:
                self.errors[(product, phase)] = public_error(exc)
                self.index += 1
                return
            # Never automatically repeat an uncertain start request.
            try:
                self.job.start_job()
            except Exception:
                self.status = 'Start uncertain; checking job status'
                return
        try:
            status = self.job.status()
        except Exception as exc:
            self.status = public_error(exc) + ' Status check will retry; no new job submitted.'
            return
        self.status = f'{functions2.PRODUCTS[product][0]} · period {phase}: {status}'
        if status == 'created':
            self.status += ' · use Cancel and retry if the job does not start'
        if status == 'finished':
            try:
                result = functions2.collect_product(self.job, product, self.directory, label=phase)
                plt.close(result.figure)
                result.figure = None
                self.results[(product, phase)] = result
            except Exception as exc:
                self.errors[(product, phase)] = str(exc) if isinstance(exc, ValueError) else public_error(exc)
        elif status in ('error', 'canceled'):
            self.errors[(product, phase)] = f'Copernicus job {status}. Check your quota or try another area/date range.'
        else:
            return
        self.job = None
        self.index += 1
        if not self.active:
            self.status = 'Finished' if not self.errors else 'Finished with some failed products'

    def _difference(self, product):
        a = self.results.get((product, 'A'))
        b = self.results.get((product, 'B'))
        if a is None or b is None or not a.rasters or not b.rasters:
            self.errors[(product, 'diff')] = 'Period A or B result is missing, so no difference was computed.'
        else:
            try:
                result = functions2.difference(a.rasters[0], b.rasters[0], product, self.directory)
                plt.close(result.figure)
                result.figure = None
                self.results[(product, 'diff')] = result
            except Exception as exc:
                self.errors[(product, 'diff')] = str(exc) if isinstance(exc, ValueError) else public_error(exc)
        self.index += 1
        if not self.active:
            self.status = 'Finished' if not self.errors else 'Finished with some failed products'
