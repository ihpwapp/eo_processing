# Satellite Image Processing

This is a program that lets users view satellite images of a selected area. Image processing steps are performed to help the user gain a better insight into their area of interest.

## Description

In the main file, run.ipynb, you will be able to draw a polygon on the world map and select a time range. Several images of your selected area will be shown, with a BCET (Balanced Contrast Enhancement Technique) applied to view a clearer version of the image. Below the images, you will be able to see the image histograms. These histograms show the DN range (brightness values of the pixels) of the images. 

Images are taken from the European Union's Sentinel-2A satellite at 30m optical resolution.

The image processing operations done are listed below:

* TCC (True Colour Composite) - this is simply an RGB picture of the selected area
* FCC (Standard False Colour Composite) - a multispectral image interpretation using the standard visual RGB band range
* NBR (Normalised Burn Ratio) - used to identify burned areas and provide a measure of burn severity
* NDVI (Normallised Difference Vegetation Index) - used to quantify vegetation greenness

## Getting Started

### Dependencies

* listed in the requirements.txt file


### Executing program

Type the following commands into your terminal

* Clone the Repository
```
git clone <repository_url>
```
* Navigate to the Repository Directory
```
cd <repository_name>
```
* Install dependencies
```
pip install -r requirements.txt

```
* Install dependencies
```
Register a CDSE account https://dataspace.copernicus.eu

```
* Run the Project
```
jupyter notebook run.ipynb
```


## Authors

Imran Idham Sabki
Hariz Imzan