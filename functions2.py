import openeo
import BCET
import LCE
from openeo.processes import ProcessBuilder
import matplotlib.pyplot as plt
import xarray as xr


def nbr(polygon, start_time, end_time):
    # Define a function to execute when the button is clicked
    connection = openeo.connect(url='openeo.dataspace.copernicus.eu').authenticate_oidc()

    # Get the bounding box of the polygon
    bbox = polygon.bounds

    cube = connection.load_collection(
        "SENTINEL2_L2A",
        temporal_extent=[start_time, end_time],
        spatial_extent=dict(zip(["west", "south", "east", "north"], bbox)),
        bands=["B08", "B12"])

    cube_b812_reduced = cube.mean_time()

    def nbr_function(x: ProcessBuilder):
        nir = x.array_element(0)  # B08
        swir = x.array_element(1)  # B12
        return (nir - swir) / (nir + swir)

    cube_nbr = cube_b812_reduced.apply(nbr_function)

    res = cube_nbr.save_result(format="GTIFF")
    res_png = cube_nbr.save_result(format="PNG")

    res_png.download('nbr_example.png')
    res.download('nbr_example.tiff')
    LCE.plot_result('nbr_example.tiff', 5)


def ndvi(polygon, start_time, end_time):
    # Define a function to execute when the button is clicked
    connection = openeo.connect(url='openeo.dataspace.copernicus.eu').authenticate_oidc()

    # Get the bounding box of the polygon
    bbox = polygon.bounds

    cube = (connection.load_collection(
        "SENTINEL2_L2A",
        temporal_extent=[start_time, end_time],
        spatial_extent=dict(zip(["west", "south", "east", "north"], bbox)),
        bands=["B04", "B08"]))

    cube_b48_reduced = cube.mean_time()

    def ndvi_function(x: ProcessBuilder):
        nir = x.array_element(1)  # B08
        red = x.array_element(0)  # B04

        return (nir - red)/(nir + red)

    cube_nbr = cube_b48_reduced.apply(ndvi_function)

    res = cube_nbr.save_result(format="GTIFF")
    res_png = cube_nbr.save_result(format="PNG")

    res_png.download('ndvi_example.png')
    res.download('ndvi_example.tiff')
    LCE.plot_result('ndvi_example.tiff', 5)


def tcc(polygon, start_time, end_time):
    # Define a function to execute when the button is clicked
    connection = openeo.connect(url='openeo.dataspace.copernicus.eu').authenticate_oidc()

    # Get the bounding box of the polygon
    bbox = polygon.bounds

    cube = (connection.load_collection(
        "SENTINEL2_L2A",
        temporal_extent=[start_time, end_time],
        spatial_extent=dict(zip(["west", "south", "east", "north"], bbox)),
        bands=["B02", "B03", "B04"]))

    cube_b234_reduced = cube.mean_time()

    def scale_function(x: ProcessBuilder):
        return x.linear_scale_range(0, 6000, 0, 255)

    cube_b234_reduced_lin = cube_b234_reduced.apply(scale_function)

    cube_b234_reduced_lin.download('tcc_example.nc')

    res_png = cube_b234_reduced_lin.save_result(format="PNG", options={
        "red": "B4",
        "green": "B3",
        "blue": "B2"
    })

    res_png.download('tcc_example.png')
    BCET.plot_input('tcc_example.nc')


def fcc(polygon, start_time, end_time):
    # Define a function to execute when the button is clicked
    connection = openeo.connect(url='openeo.dataspace.copernicus.eu').authenticate_oidc()

    # Get the bounding box of the polygon
    bbox = polygon.bounds

    cube = (connection.load_collection(
        "SENTINEL2_L2A",
        temporal_extent=[start_time, end_time],
        spatial_extent=dict(zip(["west", "south", "east", "north"], bbox)),
        bands=["B03", "B04", "B08"]))

    cube_b348_reduced = cube.mean_time()

    def scale_function(x: ProcessBuilder):
        return x.linear_scale_range(0, 6000, 0, 255)

    cube_b348_reduced_lin = cube_b348_reduced.apply(scale_function)

    cube_b348_reduced_lin.download('fcc_example.nc')

    res_png = cube_b348_reduced_lin.save_result(format="PNG", options={
        "red": "B4",
        "green": "B3",
        "blue": "B2"
    })

    res_png.download('fcc_example.png')
    BCET.plot_input('fcc_example.nc')


def sar(polygon, start_time, end_time):

    connection = openeo.connect(url='openeo.dataspace.copernicus.eu').authenticate_oidc()

    bbox = polygon.bounds

    cube = (connection.load_collection(
        "SENTINEL1_GRD",
        temporal_extent=[start_time, end_time],
        spatial_extent=dict(zip(["west", "south", "east", "north"], bbox)),
        bands=["VV", "VH"]))

    s1bs_linear = cube.sar_backscatter(coefficient="sigma0-ellipsoid")
    s1bs = s1bs_linear.apply(lambda x: 10 * x.log(base=10))
    s1bs.download("sar_example.nc", format="NetCDF")
    s1bs_netcdf = s1bs.save_result(format="NetCDF")

    job_bs = s1bs_netcdf.create_job(title="SAR_backscatter")
    job_id_bs = job_bs.job_id

    if job_id_bs:
        print("Batch job created with id: ", job_id_bs)
        job_bs.start_job()
    else:
        print("Error! Job ID is None")

    job_bs = connection.job(job_id_bs)
    job_description = job_bs.describe_job()
    print("Batch job with id: ", job_id_bs, ' is ', job_description['status'])

    job_bs.get_results()

    S1_ard = xr.open_dataset("sar_example.nc", engine='netcdf4')

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 20))
    ax1.imshow(S1_ard.VV[0].values, cmap='Greys_r', vmin=-30, vmax=30)
    ax1.set_title('VV gamma0')
    ax2.imshow(S1_ard.VH[0].values, cmap='Greys_r', vmin=-30, vmax=30)
    ax2.set_title('VH gamma0')
    plt.show()


def tcc_masked(polygon, start_time, end_time):
    # Define a function to execute when the button is clicked
    connection = openeo.connect(url='openeo.dataspace.copernicus.eu').authenticate_oidc()

    # Get the bounding box of the polygon
    bbox = polygon.bounds

    cube = connection.load_collection(
        "SENTINEL2_L2A",
        temporal_extent=[start_time, end_time],
        spatial_extent=dict(zip(["west", "south", "east", "north"], bbox)),
        bands=["B02", "B03", "B04", "SCL"])

    scl_band = cube.band("SCL")
    cloud_mask = (scl_band == 3) | (scl_band == 8) | (scl_band == 9)
    cloud_mask = cloud_mask.resample_cube_spatial(cube)
    cube_masked = cube.mask(cloud_mask)
    composite_masked = cube_masked.mean_time()

    def scale_function(x: ProcessBuilder):
        return x.linear_scale_range(0, 6000, 0, 255)

    composite_masked = composite_masked.apply(scale_function)

    composite_masked.download('tcc_masked_example_cdf.nc')

    res_png = composite_masked.save_result(format="PNG", options={
        "red": "B4",
        "green": "B3",
        "blue": "B2"
    })

    res_png.download('tcc_masked_example.png')
    BCET.plot_bcet('tcc_masked_example_cdf.nc')


def fcc_masked(polygon, start_time, end_time):
    # Define a function to execute when the button is clicked
    connection = openeo.connect(url='openeo.dataspace.copernicus.eu').authenticate_oidc()

    # Get the bounding box of the polygon
    bbox = polygon.bounds

    cube = (connection.load_collection(
        "SENTINEL2_L2A",
        temporal_extent=[start_time, end_time],
        spatial_extent=dict(zip(["west", "south", "east", "north"], bbox)),
        bands=["B03", "B04", "B08", "SCL"]))

    scl_band = cube.band("SCL")
    cloud_mask = (scl_band == 3) | (scl_band == 8) | (scl_band == 9)
    cloud_mask = cloud_mask.resample_cube_spatial(cube)
    cube_masked = cube.mask(cloud_mask)
    composite_masked = cube_masked.mean_time()

    def scale_function(x: ProcessBuilder):
        return x.linear_scale_range(0, 6000, 0, 255)

    composite_masked = composite_masked.apply(scale_function)

    composite_masked.download('fcc_masked_example.nc')

    res_png = composite_masked.save_result(format="PNG", options={
        "red": "B4",
        "green": "B3",
        "blue": "B2"
    })

    res_png.download('fcc_masked_example.png')
    BCET.plot_bcet('fcc_masked_example.nc')
