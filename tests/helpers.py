import tempfile
from pathlib import Path

import numpy as np
import rasterio


def write_tiff(path, data, nans=None):
    data = np.asarray(data, dtype='float32')
    if data.ndim == 2:
        data = data[np.newaxis, ...]
    if nans is not None:
        data = data.copy()
        data[nans] = np.nan
    with rasterio.open(
        str(path), 'w', driver='GTiff', count=data.shape[0],
        height=data.shape[1], width=data.shape[2], dtype='float32',
        crs='EPSG:4326', transform=rasterio.transform.from_origin(0, 0, 1, 1),
    ) as dataset:
        dataset.write(data)
    return path


class TiffFixture:
    def __init__(self):
        self._temp = tempfile.TemporaryDirectory()
        self.dir = Path(self._temp.name)

    def make(self, name, data, nans=None):
        return write_tiff(self.dir / name, data, nans)

    def cleanup(self):
        self._temp.cleanup()