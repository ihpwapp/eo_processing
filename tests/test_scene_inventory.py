import json
import unittest
from datetime import date
from unittest import mock

import functions2
from shapely.geometry import box


def items_response(features):
    return json.dumps({'type': 'FeatureCollection', 'features': features}).encode()


def feature(when, cloud, x=0.4, y=0.4, platform='sentinel-2a'):
    return {
        'type': 'Feature',
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[[x, y], [x + 0.5, y], [x + 0.5, y + 0.5], [x, y + 0.5], [x, y]]],
        },
        'properties': {'datetime': when, 'eo:cloud_cover': cloud, 'platform': platform},
    }


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


class SceneInventoryTest(unittest.TestCase):
    def setUp(self):
        self.polygon = box(0, 0, 1, 1)

    def test_returns_intersecting_scenes_sorted(self):
        features = [
            feature('2024-01-10T03:00:00Z', 20.0, x=50.0, y=50.0),
            feature('2024-01-13T03:31:09Z', 37.63, platform='sentinel-2b'),
            feature('2024-01-11T02:00:00Z', 5.0),
        ]
        with mock.patch.object(functions2, 'urlopen', return_value=FakeResponse(items_response(features))) as urlopen:
            scenes = functions2.scene_inventory(self.polygon, date(2024, 1, 1), date(2024, 2, 1))
        self.assertEqual([s.datetime for s in scenes], ['2024-01-11T02:00:00Z', '2024-01-13T03:31:09Z'])
        self.assertEqual(scenes[0].cloud_cover, 5.0)
        self.assertEqual(scenes[1].platform, 'sentinel-2b')
        request = urlopen.call_args.args[0]
        from urllib.parse import parse_qs, urlsplit
        query = parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(query['bbox'], ['0.000000,0.000000,1.000000,1.000000'])
        self.assertEqual(query['datetime'], ['2024-01-01T00:00:00Z/2024-02-01T00:00:00Z'])
        self.assertEqual(query['limit'], ['300'])
        self.assertEqual(request.headers.get('User-agent'), 'eo_processing')

    def test_skips_missing_cloud_cover(self):
        broken = dict(feature('2024-01-11T02:00:00Z', None))
        broken['properties'] = {'datetime': '2024-01-11T02:00:00Z'}
        valid = feature('2024-01-12T02:00:00Z', 3.0)
        with mock.patch.object(functions2, 'urlopen', return_value=FakeResponse(items_response([broken, valid]))):
            scenes = functions2.scene_inventory(self.polygon, date(2024, 1, 1), date(2024, 2, 1))
        self.assertEqual(len(scenes), 1)

    def test_network_failure_is_public_value_error(self):
        with mock.patch.object(functions2, 'urlopen', side_effect=RuntimeError('boom')):
            with self.assertRaisesRegex(ValueError, 'Acquisition report unavailable'):
                functions2.scene_inventory(self.polygon, date(2024, 1, 1), date(2024, 2, 1))

    def test_no_scenes_raises(self):
        with mock.patch.object(functions2, 'urlopen', return_value=FakeResponse(items_response([feature('2024-01-13T03:31:09Z', 1.0, x=50.0, y=50.0)]))):
            with self.assertRaisesRegex(ValueError, 'No Sentinel-2 scenes found'):
                functions2.scene_inventory(self.polygon, date(2024, 1, 1), date(2024, 2, 1))


if __name__ == '__main__':
    unittest.main()