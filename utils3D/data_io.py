#
# handling voxel data of ShapeNet dataset.
#

import sys, os, glob
import numpy as np
import scipy.ndimage as nd
import h5py
import binvox_rw
import struct

import pdb

def read_bnt(path):
	with open(path, 'rb') as f:
		nrows	= struct.unpack('h',f.read(2))[0]
		ncols	= struct.unpack('h',f.read(2))[0]
		zmin	= struct.unpack('d',f.read(8))[0]
		length	= struct.unpack('h',f.read(2))[0]
		imfile	= f.read(length)
		length	= struct.unpack('I',f.read(4))[0]
		pcl		= struct.unpack('d'*length,f.read(length*8))
		pcl		= np.array(pcl).reshape(5,length/5).transpose()
	
	return pcl, nrows, ncols, imfile

def bnt2voxel(pcl,shape=64, center=True):
	# compute ratio
	maxs = pcl[:,:3].max(0)
	mins = pcl[:,:3].min(0)
	centers = (maxs + mins)/2
	xmax, ymax, zmax = maxs
	xmin, ymin, zmin = mins
	xc, yc, zc = centers
	raw_shape = maxs-mins
	ratio =float(shape-1)/raw_shape
	ratio_min = min(ratio)
	ratio = [ratio_min,ratio_min,ratio_min]
	voxel_shape = (1,)+(shape,)*3
	voxel = np.zeros(voxel_shape)

	# fill voxel
	for i in range(pcl.shape[0]):
		x,y,z,_,_ = pcl[i]
		try:
			if center:
				xx,yy,zz = int(x)-xc,int(y)-yc,int(z)-zc
				voxel[0,int(xx*ratio[0]+shape/2),int(yy*ratio[1]+shape/2),int(zz*ratio[2]+shape/2)] = 1
			else:
				xx,yy,zz = int(x)-xmin,int(y)-ymin,int(z)-zmin
				voxel[0,int(xx*ratio[0]),int(yy*ratio[1]),int(zz*ratio[2])] = 1
		except:
			print( x,y,z )
			print( int(x)-xmin,int(y)-ymin,int(z)-zmin )
	return voxel

def bnt2voxel_wColor(pcl, image, shape=64, center=True):
	# compute ratio
	maxs = pcl[:,:3].max(0)
	mins = pcl[:,:3].min(0)
	centers = (maxs + mins)/2
	xmax, ymax, zmax = maxs
	xmin, ymin, zmin = mins
	xc, yc, zc = centers
	raw_shape = maxs-mins
	ratio =float(shape-1)/raw_shape
	ratio_min = min(ratio)
	ratio = [ratio_min,ratio_min,ratio_min]
	voxel_shape = (4,)+(shape,)*3
	voxel = np.zeros(voxel_shape)

	# fill voxel
	for i in range(pcl.shape[0]):
		x,y,z,u,v = pcl[i]
		r,g,b = image[:,v*image.shape[1],u*image.shape[2]]
		try:
			if center:
				xx,yy,zz = int(x)-xc,int(y)-yc,int(z)-zc
				voxel[0,int(xx*ratio[0]+shape/2),int(yy*ratio[1]+shape/2),int(zz*ratio[2]+shape/2)] = 1
				voxel[1,int(xx*ratio[0]+shape/2),int(yy*ratio[1]+shape/2),int(zz*ratio[2]+shape/2)] = r
				voxel[2,int(xx*ratio[0]+shape/2),int(yy*ratio[1]+shape/2),int(zz*ratio[2]+shape/2)] = g
				voxel[3,int(xx*ratio[0]+shape/2),int(yy*ratio[1]+shape/2),int(zz*ratio[2]+shape/2)] = b
			else:
				xx,yy,zz = int(x)-xmin,int(y)-ymin,int(z)-zmin
				voxel[0,int(xx*ratio[0]),int(yy*ratio[1]),int(zz*ratio[2])] = 1
				voxel[1,int(xx*ratio[0]),int(yy*ratio[1]),int(zz*ratio[2])] = r
				voxel[2,int(xx*ratio[0]),int(yy*ratio[1]),int(zz*ratio[2])] = g
				voxel[3,int(xx*ratio[0]),int(yy*ratio[1]),int(zz*ratio[2])] = b
		except:
			print( x,y,z )
			print( xx,yy,zz )
			print( xx*ratio[0]+shape/2, yy*ratio[1]+shape/2, zz*ratio[2]+shape/2 )
			pdb.set_trace()
	return voxel


def read_h5(path):
	"""
	read .h5 file
	"""
	f = h5py.File(path, 'r')
	voxel = f['data'][:]
	f.close()

	return voxel

def resize(voxel, shape, square=True):
	"""
	resize voxel shape
	"""
	if square:
		ratio = float(shape[0]) / voxel.shape[0]
	else:
		ratio = [float(s)/v for (s,v) in zip(shape,voxel.shape)]
	voxel = nd.zoom(voxel,
			ratio,
			order=1, 
			mode='nearest')
	voxel[np.nonzero(voxel)] = 1.0
	return voxel

def read_binvox(path, shape=(64,64,64), fix_coords=True):
	"""
	read voxel data from .binvox file
	"""
	with open(path, 'rb') as f:
		voxel = binvox_rw.read_as_3d_array(f, fix_coords)
	
	voxel_data = voxel.data.astype(np.float)
	if shape is not None and voxel_data.shape != shape:
		voxel_data = resize(voxel.data.astype(np.float64), shape)

	return voxel_data

def write_binvox(data, path):
	"""
	write out voxel data
	"""
	data = np.rint(data).astype(np.uint8)
	dims = data.shape
	translate = [0., 0., 0.]
	scale = 1.0
	axis_order = 'xyz'
	v = binvox_rw.Voxels( data, dims, translate, scale, axis_order)

	with open(path, 'bw') as f:
		v.write(f)

def read_all_binvox(directory):
	"""
	read all .binvox files in the direcotry
	"""
	input_files = [f for f in glob.glob(directory + "/**/*.binvox", recursive=True)]

	data = np.array([read_binvox(path) for path in input_files])
	n, w, h, d = data.shape

	return data.reshape(n, w, h, d, 1)

def main():
	data = read_all_binvox('./data')
	print(data.shape)

if __name__ == '__main__':
	main()
