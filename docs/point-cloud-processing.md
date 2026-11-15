# Point-cloud processing

`motionproof/scans/pointcloud.py`

| Format | Read |
|---|---|
| PLY | vertices (and colours) through Trimesh; a PLY with faces is surface-sampled |
| PCD | ASCII only (binary PCD is refused with a message) |
| XYZ / TXT / PTS | whitespace columns; optional header row |
| CSV | named columns `x,y,z`, optional `nx,ny,nz`, `r,g,b`, `confidence`/`quality`/`intensity` |
| STL / OBJ | surface-sampled with a fixed seed and labelled "not raw scan data" |

Large text files are read in chunks of 200,000 rows; above `max_points` (default 2,000,000)
the retained density is halved repeatedly, so memory stays bounded. Thinning is recorded.

Cleaning steps, each recorded in the cloud's history:

* duplicate removal (relative tolerance);
* statistical outlier removal: mean distance to 12 neighbours, rejected beyond 3 robust
  standard deviations (median absolute deviation);
* voxel downsampling;
* normal estimation by local plane fit; the out-of-plane residual is the noise estimate.
  On small radii curvature inflates it.

Surface reconstruction is not performed: inspection works on points against the nominal
surface.
