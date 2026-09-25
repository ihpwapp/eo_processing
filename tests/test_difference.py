import unittest

import numpy as np

import functions2
from tests.helpers import TiffFixture


class DifferenceTest(unittest.TestCase):
    def setUp(self):
        self.fixture = TiffFixture()

    def tearDown(self):
        self.fixture.cleanup()

    def read_diff(self, product, a, b, expected_shape):
        path_a = self.fixture.make('a.tif', a)
        path_b = self.fixture.make('b.tif', b)
        result = functions2.difference(path_a, path_b, product, self.fixture.dir)
        with rasterio_open(result.rasters[0]) as dataset:
            data = dataset.read()
        self.assertEqual(data.shape, expected_shape)
        self.assertTrue(result.preview.exists())
        return data

    def test_index_subtraction_and_outputs(self):
        data = self.read_diff('ndvi', [[[0.6]]], [[[0.4]]], (1, 1, 1))
        self.assertAlmostEqual(float(data[0, 0, 0]), -0.2, places=5)

    def test_rgb_channel_preserved(self):
        a = np.array([[[100.0]], [[200.0]], [[250.0]]])
        b = np.array([[[110.0]], [[150.0]], [[130.0]]])
        data = self.read_diff('tcc', a, b, (3, 1, 1))
        np.testing.assert_allclose(data[..., 0, 0], [10.0, -50.0, -120.0], rtol=1e-5)

    def test_nodata_masked(self):
        a = np.array([[0.5, np.nan, 0.3]])
        b = np.array([[0.6, np.nan, 0.9]])
        path_a = self.fixture.make('a.tif', a)
        path_b = self.fixture.make('b.tif', b)
        result = functions2.difference(path_a, path_b, 'ndvi', self.fixture.dir)
        with rasterio_open(result.rasters[0]) as dataset:
            data = dataset.read()
        self.assertTrue(np.isnan(data[0, 0, 1]))
        self.assertAlmostEqual(float(data[0, 0, 0]), 0.1, places=5)
        self.assertAlmostEqual(float(data[0, 0, 2]), 0.6, places=5)

    def test_grid_mismatch_raises(self):
        path_a = self.fixture.make('a.tif', np.zeros((1, 4, 4)))
        path_b = self.fixture.make('b.tif', np.zeros((1, 2, 2)))
        with self.assertRaisesRegex(ValueError, 'different grids'):
            functions2.difference(path_a, path_b, 'ndvi', self.fixture.dir)

    def test_no_valid_pixels_raises(self):
        path_a = self.fixture.make('a.tif', np.zeros((1, 2, 2)), nans=np.ones((1, 2, 2), dtype=bool))
        path_b = self.fixture.make('b.tif', np.ones((1, 2, 2)))
        with self.assertRaisesRegex(ValueError, 'No valid pixels'):
            functions2.difference(path_a, path_b, 'ndvi', self.fixture.dir)

    def test_equal_bands_yield_zero_difference(self):
        base = np.array([[[0.5, 0.5, 0.5], [0.5, 0.5, 0.5]]])
        data = self.read_diff('nbr', base, base, (1, 2, 3))
        np.testing.assert_allclose(data, 0.0, atol=1e-6)


def rasterio_open(path):
    import rasterio
    return rasterio.open(path)


if __name__ == '__main__':
    unittest.main()