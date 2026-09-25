import os
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from shapely.geometry import box, mapping, shape

import functions2
from web_runtime import Run, validate_request


def geometry_dict():
    return mapping(box(0, 0, 0.01, 0.01))


class FakeJob:
    def __init__(self, job_id, statuses=('finished',)):
        self.job_id = job_id
        self._statuses = list(statuses)
        self.stopped = False

    def start_job(self):
        pass

    def status(self):
        if len(self._statuses) == 1:
            return self._statuses[0]
        return self._statuses.pop(0)

    def stop_job(self):
        self.stopped = True


class RunTest(unittest.TestCase):
    def setUp(self):
        self.today = date.today()
        self.polygon = box(0, 0, 1, 1)
        self.submitted = []
        self.collected = []
        self.diffs = []
        patches = [
            mock.patch.object(functions2, 'submit_period', self._submit),
            mock.patch.object(functions2, 'collect_product', self._collect),
            mock.patch.object(functions2, 'difference', self._difference),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _submit(self, connection, period, polygon):
        self.submitted.append((period.label, period.product))
        return FakeJob(f'job_{period.label}_{period.product}', statuses=('created', 'finished'))

    def _collect(self, job, product, output_dir, label=None):
        self.collected.append((product, label))
        path = Path(output_dir) / f'{product}_{label}.tif'
        return functions2.ProcessingResult(product, [path], path.with_suffix('.png'), None)

    def _difference(self, path_a, path_b, product, output_dir):
        self.diffs.append(product)
        path = Path(output_dir) / f'{product}_diff.tif'
        return functions2.ProcessingResult(f'{product}_diff', [path], path.with_suffix('.png'), None)

    def run_idle(self, run):
        while run.active:
            run.tick(object())

    def test_single_period_stages_and_finish(self):
        run = Run(self.polygon, self.today - timedelta(days=10), self.today, ['tcc', 'ndvi'])
        self.assertEqual([(p, ph) for p, ph in run.stages], [('tcc', 'A'), ('ndvi', 'A')])
        self.assertEqual(run.active, True)
        self.run_idle(run)
        self.assertEqual(list(run.results), [('tcc', 'A'), ('ndvi', 'A')])
        self.assertFalse(run.errors)
        self.assertEqual(run.status, 'Finished')
        self.assertEqual(run.active, False)
        self.assertEqual(self.collected, [('tcc', 'A'), ('ndvi', 'A')])

    def test_compare_stages_order(self):
        run = Run(self.polygon, self.today - timedelta(days=40), self.today - timedelta(days=30),
                  ['ndvi'], self.today - timedelta(days=10), self.today)
        self.assertEqual(run.compare, True)
        self.assertEqual([(p, ph) for p, ph in run.stages], [('ndvi', 'A'), ('ndvi', 'B'), ('ndvi', 'diff')])
        self.run_idle(run)
        self.assertEqual(list(run.results), [('ndvi', 'A'), ('ndvi', 'B'), ('ndvi', 'diff')])
        self.assertEqual(self.submitted, [('A', 'ndvi'), ('B', 'ndvi')])
        self.assertEqual(self.diffs, ['ndvi'])
        self.assertEqual(run.status, 'Finished')
        self.assertEqual(run.index, len(run.stages))

    def test_before_diff_missing_resource_reports_error(self):
        original = self._collect

        def fail_b(job, product, output_dir, label=None):
            if product == 'ndvi' and label == 'B':
                raise ValueError('no data')
            return original(job, product, output_dir, label)

        with mock.patch.object(functions2, 'collect_product', fail_b):
            run = Run(self.polygon, self.today - timedelta(days=40), self.today - timedelta(days=30),
                      ['ndvi'], self.today - timedelta(days=10), self.today)
            self.run_idle(run)
        self.assertIn(('ndvi', 'B'), run.errors)
        self.assertIn(('ndvi', 'diff'), run.errors)
        self.assertIn('missing', str(run.errors[('ndvi', 'diff')]).lower())
        self.assertEqual(run.status, 'Finished with some failed products')

    def test_cancel_stops_current_job(self):
        run = Run(self.polygon, self.today - timedelta(days=10), self.today, ['tcc'])
        run.tick(object())
        job = run.job
        self.assertIsNotNone(job)
        run.cancel()
        self.assertEqual(run.active, False)
        self.assertEqual(run.status, 'Canceled')
        self.assertTrue(job.stopped)

    def test_acquisitions_kept_on_run(self):
        run = Run(self.polygon, self.today - timedelta(days=10), self.today, ['tcc'],
                  acquisitions={'A': []})
        self.assertEqual(run.acquisitions, {'A': []})

    def test_compare_flag_false_for_single_period(self):
        run = Run(self.polygon, self.today - timedelta(days=10), self.today, ['tcc'])
        self.assertEqual(run.compare, False)


class ValidateRequestTest(unittest.TestCase):
    def setUp(self):
        self.today = date.today()
        self.geometry = geometry_dict()

    def test_valid_single_period(self):
        polygon = validate_request(self.geometry, self.today - timedelta(days=10), self.today, ['tcc'])
        self.assertEqual(polygon.geom_type, 'Polygon')

    def test_missing_geometry(self):
        with self.assertRaisesRegex(ValueError, 'Draw a polygon'):
            validate_request(None, self.today - timedelta(days=10), self.today, ['tcc'])

    def test_bad_products(self):
        with self.assertRaisesRegex(ValueError, 'Select at least one optical product'):
            validate_request(self.geometry, self.today - timedelta(days=10), self.today, [])
        with self.assertRaisesRegex(ValueError, 'Select at least one optical product'):
            validate_request(self.geometry, self.today - timedelta(days=10), self.today, ['sar'])

    def test_period_b_before_period_a_rejected(self):
        a_start, a_end = self.today - timedelta(days=30), self.today - timedelta(days=20)
        with self.assertRaisesRegex(ValueError, 'on or after the end of period A'):
            validate_request(self.geometry, a_start, a_end, ['tcc'], self.today - timedelta(days=25), self.today)

    def test_period_b_adjacent_allowed(self):
        a_start, a_end = self.today - timedelta(days=30), self.today - timedelta(days=20)
        polygon = validate_request(self.geometry, a_start, a_end, ['tcc'], a_end, self.today)
        self.assertEqual(polygon.geom_type, 'Polygon')

    def test_period_b_too_long_rejected(self):
        a_start, a_end = self.today - timedelta(days=101), self.today - timedelta(days=91)
        with self.assertRaisesRegex(ValueError, 'at most'):
            validate_request(self.geometry, a_start, a_end, ['tcc'], a_end, self.today)

    def test_period_b_in_future_rejected(self):
        a_start, a_end = self.today - timedelta(days=40), self.today - timedelta(days=30)
        with self.assertRaisesRegex(ValueError, 'no later than today'):
            validate_request(self.geometry, a_start, a_end, ['tcc'], a_end, self.today + timedelta(days=1))

    def test_day_interval_bounds_via_environment(self):
        with mock.patch.dict('os.environ', {'EO_MAX_DAYS': '7'}):
            with self.assertRaisesRegex(ValueError, 'at most 7 days'):
                validate_request(self.geometry, self.today - timedelta(days=30), self.today - timedelta(days=10), ['tcc'])

    def test_crossing_date_line_rejected(self):
        big = dict(self.geometry)
        big['coordinates'] = [[[170.0, 0.0], [190.0, 0.0], [190.0, 10.0], [170.0, 10.0], [170.0, 0.0]]]
        with self.assertRaisesRegex(ValueError, 'date line'):
            validate_request(big, self.today - timedelta(days=10), self.today, ['tcc'])


if __name__ == '__main__':
    unittest.main()