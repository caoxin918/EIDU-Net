""" Wrapper functions for TensorFlow layers.

Author: Charles R. Qi
Date: November 2016

Upadted by Yue Wang and Yongbin Sun

Further improved by Liang PAN
"""

import numpy as np
import tensorflow as tf
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, '../tf_ops/grouping'))
sys.path.append(os.path.join(BASE_DIR, '../tf_ops/sampling'))
from tf_grouping import select_top_k
from tf_sampling import principal_feature_sample
import tf_grouping

def _variable_on_cpu(name, shape, initializer, use_fp16=False, trainable=True):
	"""Helper to create a Variable stored on CPU memory.
	Args:
		name: name of the variable
		shape: list of ints
		initializer: initializer for Variable
	Returns:
		Variable Tensor
	"""
	with tf.device('/cpu:0'):
		dtype = tf.float16 if use_fp16 else tf.float32
		var = tf.get_variable(name, shape, initializer=initializer, dtype=dtype, trainable=trainable)
	return var

def _variable_with_weight_decay(name, shape, stddev, wd, use_xavier=True):
	"""Helper to create an initialized Variable with weight decay.

	Note that the Variable is initialized with a truncated normal distribution.
	A weight decay is added only if one is specified.

	Args:
		name: name of the variable
		shape: list of ints
		stddev: standard deviation of a truncated Gaussian
		wd: add L2Loss weight decay multiplied by this float. If None, weight
				decay is not added for this Variable.
		use_xavier: bool, whether to use xavier initializer

	Returns:
		Variable Tensor
	"""
	if use_xavier:
		initializer = tf.contrib.layers.xavier_initializer()
	else:
		initializer = tf.truncated_normal_initializer(stddev=stddev)
	var = _variable_on_cpu(name, shape, initializer)
	if wd is not None:
		weight_decay = tf.multiply(tf.nn.l2_loss(var), wd, name='weight_loss')
		tf.add_to_collection('losses', weight_decay)
	return var


def conv1d(inputs,
           num_output_channels,
           kernel_size,
           scope=None,
           stride=1,
           padding='SAME',
           use_xavier=True,
           stddev=1e-3,
           weight_decay=0.00001,
           activation_fn=tf.nn.relu,
           bn=False,
           ibn=False,
           bn_decay=None,
           use_bias=True,
           is_training=None,
           reuse=None):
	""" 1D convolution with non-linear operation.

    Args:
        inputs: 3-D tensor variable BxHxWxC
        num_output_channels: int
        kernel_size: int
        scope: string
        stride: a list of 2 ints
        padding: 'SAME' or 'VALID'
        use_xavier: bool, use xavier_initializer if true
        stddev: float, stddev for truncated_normal init
        weight_decay: float
        activation_fn: function
        bn: bool, whether to use batch norm
        bn_decay: float or float tensor variable in [0,1]
        is_training: bool Tensor variable

    Returns:
        Variable tensor
    """
	with tf.variable_scope(scope, reuse=reuse):
		if use_xavier:
			initializer = tf.contrib.layers.xavier_initializer()
		else:
			initializer = tf.truncated_normal_initializer(stddev=stddev)

		outputs = tf.layers.conv1d(inputs, num_output_channels, kernel_size, stride, padding,
                                   kernel_initializer=initializer,
                                   kernel_regularizer=tf.contrib.layers.l2_regularizer(
                                       weight_decay),
                                   bias_regularizer=tf.contrib.layers.l2_regularizer(
                                       weight_decay),
                                   use_bias=use_bias, reuse=None)
		assert not (bn and ibn)
		if bn:
			outputs = tf.layers.batch_normalization(
                outputs, momentum=bn_decay, training=is_training, renorm=False, fused=True)
			# outputs = tf.contrib.layers.batch_norm(outputs,is_training=is_training)
		if ibn:
			outputs = instance_norm(outputs, is_training)

		if activation_fn is not None:
			outputs = activation_fn(outputs)

		return outputs




def conv2d(inputs,
           num_output_channels,
           kernel_size=[1, 1],
           scope=None,
           stride=[1, 1],
           padding='SAME',
           use_xavier=True,
           stddev=1e-3,
           weight_decay=0.00001,
           activation_fn=tf.nn.relu,
           use_bn=False,
           use_ibn=False,
           bn_decay=None,
           use_bias=True,
           is_training=None,
           reuse=tf.AUTO_REUSE):
	""" 2D convolution with non-linear operation.

    Args:
      inputs: 4-D tensor variable BxHxWxC
      num_output_channels: int
      kernel_size: a list of 2 ints
      scope: string
      stride: a list of 2 ints
      padding: 'SAME' or 'VALID'
      use_xavier: bool, use xavier_initializer if true
      stddev: float, stddev for truncated_normal init
      weight_decay: float
      activation_fn: function
      use_bn: bool, whether to use batch norm
      use_ibn: bool, whether to use instance norm
      use_bias: bool, whether to add bias
      bn_decay: float or float tensor variable in [0,1]
      is_training: bool Tensor variable

    Returns:
      Variable tensor
    """
	with tf.variable_scope(scope, reuse=reuse) as sc:
		if use_xavier:
			initializer = tf.contrib.layers.xavier_initializer()
		else:
			initializer = tf.truncated_normal_initializer(stddev=stddev)
		#print(scope)
		outputs = tf.layers.conv2d(inputs, num_output_channels, kernel_size, stride, padding,
                                   kernel_initializer=initializer,
                                   kernel_regularizer=tf.contrib.layers.l2_regularizer(weight_decay),
                                   bias_regularizer=tf.contrib.layers.l2_regularizer(weight_decay),
                                   use_bias=use_bias)
		assert not (use_bn and use_ibn)
		if use_bn:
			outputs = tf.layers.batch_normalization(outputs, momentum=bn_decay, training=is_training, renorm=False,
                                                    fused=True)
		if use_ibn:
			outputs = instance_norm(outputs)

		if activation_fn is not None:
			outputs = activation_fn(outputs)

		return outputs

def instance_norm(net, weight_decay=0.00001):
	batch, rows, cols, channels = [i.value for i in net.get_shape()]
	var_shape = [channels]
	mu, sigma_sq = tf.nn.moments(net, [1, 2], keepdims=True)

	shift = tf.get_variable('shift', shape=var_shape,
                            initializer=tf.zeros_initializer,
                            regularizer=tf.contrib.layers.l2_regularizer(weight_decay))
	scale = tf.get_variable('scale', shape=var_shape,
                            initializer=tf.ones_initializer,
                            regularizer=tf.contrib.layers.l2_regularizer(weight_decay))
	epsilon = 1e-3
	normalized = (net - mu) / tf.square(sigma_sq + epsilon)
	return scale * normalized + shift


def conv2d_transpose(inputs,
					num_output_channels,
					kernel_size,
					scope,
					stride=[1, 1],
					padding='SAME',
					use_xavier=True,
					stddev=1e-3,
					weight_decay=0.0,
					activation_fn=tf.nn.relu,
					bn=False,
					bn_decay=None,
					is_training=None,
					is_dist=False):
	""" 2D convolution transpose with non-linear operation.

	Args:
		inputs: 4-D tensor variable BxHxWxC
		num_output_channels: int
		kernel_size: a list of 2 ints
		scope: string
		stride: a list of 2 ints
		padding: 'SAME' or 'VALID'
		use_xavier: bool, use xavier_initializer if true
		stddev: float, stddev for truncated_normal init
		weight_decay: float
		activation_fn: function
		bn: bool, whether to use batch norm
		bn_decay: float or float tensor variable in [0,1]
		is_training: bool Tensor variable

	Returns:
		Variable tensor

	Note: conv2d(conv2d_transpose(a, num_out, ksize, stride), a.shape[-1], ksize, stride) == a
	"""
	with tf.variable_scope(scope) as sc:
			kernel_h, kernel_w = kernel_size
			num_in_channels = inputs.get_shape()[-1].value
			kernel_shape = [kernel_h, kernel_w,
											num_output_channels, num_in_channels] # reversed to conv2d
			kernel = _variable_with_weight_decay('weights',
																					 shape=kernel_shape,
																					 use_xavier=use_xavier,
																					 stddev=stddev,
																					 wd=weight_decay)
			stride_h, stride_w = stride
			
			# from slim.convolution2d_transpose
			def get_deconv_dim(dim_size, stride_size, kernel_size, padding):
					dim_size *= stride_size

					if padding == 'VALID' and dim_size is not None:
						dim_size += max(kernel_size - stride_size, 0)
					return dim_size

			# caculate output shape
			batch_size = inputs.get_shape()[0].value
			height = inputs.get_shape()[1].value
			width = inputs.get_shape()[2].value
			out_height = get_deconv_dim(height, stride_h, kernel_h, padding)
			out_width = get_deconv_dim(width, stride_w, kernel_w, padding)
			output_shape = [batch_size, out_height, out_width, num_output_channels]

			outputs = tf.nn.conv2d_transpose(inputs, kernel, output_shape,
														 [1, stride_h, stride_w, 1],
														 padding=padding)
			biases = _variable_on_cpu('biases', [num_output_channels],
																tf.constant_initializer(0.0))
			outputs = tf.nn.bias_add(outputs, biases)

			if bn:
				outputs = batch_norm_for_conv2d(outputs, is_training,
																				bn_decay=bn_decay, scope='bn', is_dist=is_dist)

			if activation_fn is not None:
				outputs = activation_fn(outputs)
			return outputs

	 

def conv3d(inputs,
			num_output_channels,
			kernel_size,
			scope,
			stride=[1, 1, 1],
			padding='SAME',
			use_xavier=True,
			stddev=1e-3,
			weight_decay=0.0,
			activation_fn=tf.nn.relu,
			bn=False,
			bn_decay=None,
			is_training=None,
			is_dist=False):
	""" 3D convolution with non-linear operation.

	Args:
		inputs: 5-D tensor variable BxDxHxWxC
		num_output_channels: int
		kernel_size: a list of 3 ints
		scope: string
		stride: a list of 3 ints
		padding: 'SAME' or 'VALID'
		use_xavier: bool, use xavier_initializer if true
		stddev: float, stddev for truncated_normal init
		weight_decay: float
		activation_fn: function
		bn: bool, whether to use batch norm
		bn_decay: float or float tensor variable in [0,1]
		is_training: bool Tensor variable

	Returns:
		Variable tensor
	"""
	with tf.variable_scope(scope) as sc:
		kernel_d, kernel_h, kernel_w = kernel_size
		num_in_channels = inputs.get_shape()[-1].value
		kernel_shape = [kernel_d, kernel_h, kernel_w,
										num_in_channels, num_output_channels]
		kernel = _variable_with_weight_decay('weights',
											 shape=kernel_shape,
											 use_xavier=use_xavier,
											 stddev=stddev,
											 wd=weight_decay)
		stride_d, stride_h, stride_w = stride
		outputs = tf.nn.conv3d(inputs, kernel,
													 [1, stride_d, stride_h, stride_w, 1],
													 padding=padding)
		biases = _variable_on_cpu('biases', [num_output_channels],
															tf.constant_initializer(0.0))
		outputs = tf.nn.bias_add(outputs, biases)
		
		if bn:
			outputs = batch_norm_for_conv3d(outputs, is_training,
											bn_decay=bn_decay, scope='bn', is_dist=is_dist)

		if activation_fn is not None:
			outputs = activation_fn(outputs)
		return outputs

def fully_connected(inputs,
					num_outputs,
					scope,
					use_xavier=True,
					stddev=1e-3,
					weight_decay=0.0,
					activation_fn=tf.nn.relu,
					bn=False,
					bn_decay=None,
					is_training=None,
					is_dist=False):
	""" Fully connected layer with non-linear operation.
	
	Args:
		inputs: 2-D tensor BxN
		num_outputs: int
	
	Returns:
		Variable tensor of size B x num_outputs.
	"""
	with tf.variable_scope(scope) as sc:
		num_input_units = inputs.get_shape()[-1].value
		weights = _variable_with_weight_decay('weights',
											shape=[num_input_units, num_outputs],
											use_xavier=use_xavier,
											stddev=stddev,
											wd=weight_decay)
		outputs = tf.matmul(inputs, weights)
		biases = _variable_on_cpu('biases', [num_outputs],
														 tf.constant_initializer(0.0))
		outputs = tf.nn.bias_add(outputs, biases)
		 
		if bn:
			outputs = batch_norm_for_fc(outputs, is_training, bn_decay, 'bn', is_dist=is_dist)

		if activation_fn is not None:
			outputs = activation_fn(outputs)
		return outputs


def max_pool2d(inputs,
	kernel_size,
	scope,
	stride=[2, 2],
	padding='VALID'):
	""" 2D max pooling.

	Args:
		inputs: 4-D tensor BxHxWxC
		kernel_size: a list of 2 ints
		stride: a list of 2 ints
	
	Returns:
		Variable tensor
	"""
	with tf.variable_scope(scope) as sc:
		kernel_h, kernel_w = kernel_size
		stride_h, stride_w = stride
		outputs = tf.nn.max_pool(inputs,
		ksize=[1, kernel_h, kernel_w, 1],
		strides=[1, stride_h, stride_w, 1],
		padding=padding,
		name=sc.name)
		return outputs

def avg_pool2d(inputs,
				kernel_size,
				scope,
				stride=[2, 2],
				padding='VALID'):
	""" 2D avg pooling.

	Args:
		inputs: 4-D tensor BxHxWxC
		kernel_size: a list of 2 ints
		stride: a list of 2 ints
	
	Returns:
		Variable tensor
	"""
	with tf.variable_scope(scope) as sc:
		kernel_h, kernel_w = kernel_size
		stride_h, stride_w = stride
		outputs = tf.nn.avg_pool(inputs,
		ksize=[1, kernel_h, kernel_w, 1],
		strides=[1, stride_h, stride_w, 1],
		padding=padding,
		name=sc.name)
		return outputs


def max_pool3d(inputs,
			kernel_size,
			scope,
			stride=[2, 2, 2],
			padding='VALID'):
	""" 3D max pooling.

	Args:
		inputs: 5-D tensor BxDxHxWxC
		kernel_size: a list of 3 ints
		stride: a list of 3 ints
	
	Returns:
		Variable tensor
	"""
	with tf.variable_scope(scope) as sc:
		kernel_d, kernel_h, kernel_w = kernel_size
		stride_d, stride_h, stride_w = stride
		outputs = tf.nn.max_pool3d(inputs,
					ksize=[1, kernel_d, kernel_h, kernel_w, 1],
					strides=[1, stride_d, stride_h, stride_w, 1],
					padding=padding,
					name=sc.name)
		return outputs

def avg_pool3d(inputs,
							 kernel_size,
							 scope,
							 stride=[2, 2, 2],
							 padding='VALID'):
	""" 3D avg pooling.

	Args:
		inputs: 5-D tensor BxDxHxWxC
		kernel_size: a list of 3 ints
		stride: a list of 3 ints
	
	Returns:
		Variable tensor
	"""
	with tf.variable_scope(scope) as sc:
		kernel_d, kernel_h, kernel_w = kernel_size
		stride_d, stride_h, stride_w = stride
		outputs = tf.nn.avg_pool3d(inputs,
						ksize=[1, kernel_d, kernel_h, kernel_w, 1],
						strides=[1, stride_d, stride_h, stride_w, 1],
						padding=padding,
						name=sc.name)
		return outputs





def batch_norm_template(inputs, is_training, scope, moments_dims, bn_decay):
	""" Batch normalization on convolutional maps and beyond...
	Ref.: http://stackoverflow.com/questions/33949786/how-could-i-use-batch-normalization-in-tensorflow
	
	Args:
			inputs:        Tensor, k-D input ... x C could be BC or BHWC or BDHWC
			is_training:   boolean tf.Varialbe, true indicates training phase
			scope:         string, variable scope
			moments_dims:  a list of ints, indicating dimensions for moments calculation
			bn_decay:      float or float tensor variable, controling moving average weight
	Return:
			normed:        batch-normalized maps
	"""
	with tf.variable_scope(scope) as sc:
		num_channels = inputs.get_shape()[-1].value
		beta = tf.Variable(tf.constant(0.0, shape=[num_channels]),
											 name='beta', trainable=True)
		gamma = tf.Variable(tf.constant(1.0, shape=[num_channels]),
												name='gamma', trainable=True)
		batch_mean, batch_var = tf.nn.moments(inputs, moments_dims, name='moments')
		decay = bn_decay if bn_decay is not None else 0.9
		ema = tf.train.ExponentialMovingAverage(decay=decay)
		# Operator that maintains moving averages of variables.
		ema_apply_op = tf.cond(is_training,
													 lambda: ema.apply([batch_mean, batch_var]),
													 lambda: tf.no_op())
		
		# Update moving average and return current batch's avg and var.
		def mean_var_with_update():
			with tf.control_dependencies([ema_apply_op]):
				return tf.identity(batch_mean), tf.identity(batch_var)
		
		# ema.average returns the Variable holding the average of var.
		mean, var = tf.cond(is_training,
												mean_var_with_update,
												lambda: (ema.average(batch_mean), ema.average(batch_var)))
		normed = tf.nn.batch_normalization(inputs, mean, var, beta, gamma, 1e-3)
	return normed


def batch_norm_dist_template(inputs, is_training, scope, moments_dims, bn_decay):
	""" The batch normalization for distributed training.
	Args:
			inputs:        Tensor, k-D input ... x C could be BC or BHWC or BDHWC
			is_training:   boolean tf.Varialbe, true indicates training phase
			scope:         string, variable scope
			moments_dims:  a list of ints, indicating dimensions for moments calculation
			bn_decay:      float or float tensor variable, controling moving average weight
	Return:
			normed:        batch-normalized maps
	"""
	with tf.variable_scope(scope) as sc:
		num_channels = inputs.get_shape()[-1].value
		beta = _variable_on_cpu('beta', [num_channels], initializer=tf.zeros_initializer())
		gamma = _variable_on_cpu('gamma', [num_channels], initializer=tf.ones_initializer())

		pop_mean = _variable_on_cpu('pop_mean', [num_channels], initializer=tf.zeros_initializer(), trainable=False)
		pop_var = _variable_on_cpu('pop_var', [num_channels], initializer=tf.ones_initializer(), trainable=False)

		def train_bn_op():
			batch_mean, batch_var = tf.nn.moments(inputs, moments_dims, name='moments')
			decay = bn_decay if bn_decay is not None else 0.9
			train_mean = tf.assign(pop_mean, pop_mean * decay + batch_mean * (1 - decay)) 
			train_var = tf.assign(pop_var, pop_var * decay + batch_var * (1 - decay))
			with tf.control_dependencies([train_mean, train_var]):
				return tf.nn.batch_normalization(inputs, batch_mean, batch_var, beta, gamma, 1e-3)

		def test_bn_op():
			return tf.nn.batch_normalization(inputs, pop_mean, pop_var, beta, gamma, 1e-3)

		normed = tf.cond(is_training,
										 train_bn_op,
										 test_bn_op)
		return normed



def batch_norm_for_fc(inputs, is_training, bn_decay, scope, is_dist=False):
	""" Batch normalization on FC data.
	
	Args:
			inputs:      Tensor, 2D BxC input
			is_training: boolean tf.Varialbe, true indicates training phase
			bn_decay:    float or float tensor variable, controling moving average weight
			scope:       string, variable scope
			is_dist:     true indicating distributed training scheme
	Return:
			normed:      batch-normalized maps
	"""
	if is_dist:
		return batch_norm_dist_template(inputs, is_training, scope, [0,], bn_decay)
	else:
		return batch_norm_template(inputs, is_training, scope, [0,], bn_decay)


def batch_norm_for_conv1d(inputs, is_training, bn_decay, scope, is_dist=False):
	""" Batch normalization on 1D convolutional maps.
	
	Args:
			inputs:      Tensor, 3D BLC input maps
			is_training: boolean tf.Varialbe, true indicates training phase
			bn_decay:    float or float tensor variable, controling moving average weight
			scope:       string, variable scope
			is_dist:     true indicating distributed training scheme
	Return:
			normed:      batch-normalized maps
	"""
	if is_dist:
		return batch_norm_dist_template(inputs, is_training, scope, [0,1], bn_decay)
	else:
		return batch_norm_template(inputs, is_training, scope, [0,1], bn_decay)



	
def batch_norm_for_conv2d(inputs, is_training, bn_decay, scope, is_dist=False):
	""" Batch normalization on 2D convolutional maps.
	
	Args:
			inputs:      Tensor, 4D BHWC input maps
			is_training: boolean tf.Varialbe, true indicates training phase
			bn_decay:    float or float tensor variable, controling moving average weight
			scope:       string, variable scope
			is_dist:     true indicating distributed training scheme
	Return:
			normed:      batch-normalized maps
	"""
	if is_dist:
		return batch_norm_dist_template(inputs, is_training, scope, [0,1,2], bn_decay)
	else:
		return batch_norm_template(inputs, is_training, scope, [0,1,2], bn_decay)



def batch_norm_for_conv3d(inputs, is_training, bn_decay, scope, is_dist=False):
	""" Batch normalization on 3D convolutional maps.
	
	Args:
			inputs:      Tensor, 5D BDHWC input maps
			is_training: boolean tf.Varialbe, true indicates training phase
			bn_decay:    float or float tensor variable, controling moving average weight
			scope:       string, variable scope
			is_dist:     true indicating distributed training scheme
	Return:
			normed:      batch-normalized maps
	"""
	if is_dist:
		return batch_norm_dist_template(inputs, is_training, scope, [0,1,2,3], bn_decay)
	else:
		return batch_norm_template(inputs, is_training, scope, [0,1,2,3], bn_decay)


def dropout(inputs,
			is_training,
			scope,
			keep_prob=0.5,
			noise_shape=None):
	""" Dropout layer.

	Args:
		inputs: tensor
		is_training: boolean tf.Variable
		scope: string
		keep_prob: float in [0,1]
		noise_shape: list of ints

	Returns:
		tensor variable
	"""
	with tf.variable_scope(scope) as sc:
		outputs = tf.cond(is_training,
		lambda: tf.nn.dropout(inputs, keep_prob, noise_shape),
		lambda: inputs)
		return outputs


def pairwise_distance(point_cloud):
	"""Compute pairwise distance of a point cloud.            计算点云中的欧氏距离

	Args:
		point_cloud: tensor (batch_size, num_points, num_dims)

	Returns:
		pairwise distance: (batch_size, num_points, num_points)
	"""
	og_batch_size = point_cloud.get_shape().as_list()[0]
	num_points = point_cloud.get_shape().as_list()[1]

	point_cloud = tf.squeeze(point_cloud)
	if og_batch_size == 1:
		point_cloud = tf.expand_dims(point_cloud, 0)

	if num_points == 1:
		point_cloud = tf.expand_dims(point_cloud, 1)
		
	point_cloud_transpose = tf.transpose(point_cloud, perm=[0, 2, 1])
	point_cloud_inner = tf.matmul(point_cloud, point_cloud_transpose)
	point_cloud_inner = -2*point_cloud_inner
	point_cloud_square = tf.reduce_sum(tf.square(point_cloud), axis=-1, keepdims=True)
	point_cloud_square_tranpose = tf.transpose(point_cloud_square, perm=[0, 2, 1])
	return point_cloud_square + point_cloud_inner + point_cloud_square_tranpose


def knn(adj_matrix, k=20):
	"""Get KNN based on the pairwise distance.
	Args:
		pairwise distance: (batch_size, num_points, num_points)
		k: int

	Returns:
		nearest neighbors: (batch_size, num_points, k)
	"""
	neg_adj = -adj_matrix
	_, nn_idx = tf.nn.top_k(neg_adj, k=k)
	return nn_idx


def get_edge_feature(point_cloud, k=16, idx=None):
	"""Construct edge feature for each point
    Args:
        point_cloud: (batch_size, num_points, 1, num_dims)
        nn_idx: (batch_size, num_points, k, 2)
        k: int
    Returns:
        edge features: (batch_size, num_points, k, num_dims)
    """
	if idx is None:
		_, idx = tf_grouping.knn_point_2(k + 1, point_cloud, point_cloud, unique=True, sort=True)
		idx = idx[:, :, 1:, :]


	point_cloud_neighbors = tf.gather_nd(point_cloud, idx)      	# [N, P, K, Dim]
	point_cloud_central = tf.expand_dims(point_cloud, axis=-2)

	point_cloud_central = tf.tile(point_cloud_central, [1, 1, k, 1])

	edge_feature = tf.concat(
        [point_cloud_central, point_cloud_neighbors - point_cloud_central], axis=-1)
	return edge_feature, idx

def pagget_edge_feature(point_cloud, nn_idx, k=20):
	"""Construct edge feature for each point
	Args:
		point_cloud: (batch_size, num_points, 1, num_dims)
		nn_idx: (batch_size, num_points, k)
		k: int

	Returns:
		edge features: (batch_size, num_points, k, num_dims)
	"""
	og_batch_size = point_cloud.get_shape().as_list()[0]
	point_cloud = tf.squeeze(point_cloud)
	if og_batch_size == 1:
		point_cloud = tf.expand_dims(point_cloud, 0)

	point_cloud_central = point_cloud

	point_cloud_shape = point_cloud.get_shape()
	batch_size = point_cloud_shape[0].value
	num_points = point_cloud_shape[1].value
	num_dims = point_cloud_shape[2].value

	idx_ = tf.range(batch_size) * num_points
	idx_ = tf.reshape(idx_, [batch_size, 1, 1])

	point_cloud_flat = tf.reshape(point_cloud, [-1, num_dims])
	point_cloud_neighbors = tf.gather(point_cloud_flat, nn_idx+idx_)
	point_cloud_central = tf.expand_dims(point_cloud_central, axis=-2)

	point_cloud_central = tf.tile(point_cloud_central, [1, 1, k, 1])

	edge_feature = tf.concat([point_cloud_central, point_cloud_neighbors-point_cloud_central], axis=-1)
	return edge_feature
def get_atrous_knn(adj_matrix, k, dilation, dist_matrix=None, min_radius=0, max_radius=0):
	""" Select samples based on the feature distance, dilation, metric distance and search radius
	Args:
		feature distance: (batch_size, num_points, num_points)
		k: int
		dilation: int
		metric distance: (batch_size, num_points, num_points)
		radius: float
	
	Returns:
		selected samples: (batch_size, num_points, k)
	"""

	point_cloud_shape = adj_matrix.get_shape()
	batch_size = point_cloud_shape[0].value
	num_points = point_cloud_shape[1].value

	# Bug Notice: if the maximum is selected, then chaos.
	# Hence, need double check
	if (dist_matrix is not None):
		
		invalid_mask1 = tf.greater(dist_matrix, max_radius)
		invalid_mask2 = tf.less(dist_matrix, min_radius)
		invalid_mask = tf.logical_or(invalid_mask1, invalid_mask2)
		
		valid_mask = tf.logical_not(invalid_mask)

		# adj_maximum = tf.reduce_max(adj_matrix, axis=2, keepdims=True)
		# maximum = tf.reduce_max(tf.reduce_max(adj_maximum, axis=1, keepdims=True), axis=0, keepdims=True) + 0.1
		
		# # adj_matrix[invalid_mask] = -1
		# # False => 0; True => 1
		# invalid_maskf = tf.to_float(invalid_mask)
		# valid_maskf = tf.to_float(valid_mask)
		# # adj_matrix = adj_matrix * valid_mask - invalid_mask

		# # adj_matrix[invalid_mask] = maximum
		# # adj_matrix = adj_matrix + (invalid_mask * (maximum + 1))
		# # adj_matrix = tf.minimum(adj_matrix, tf.expand_dims(adj_maximum, 2) )

		# adj_matrix = adj_matrix * valid_maskf + maximum * invalid_maskf

		maximum = tf.reduce_max(adj_matrix, axis=None, keepdims=True) + 0.1
		maximum = tf.tile(maximum, [batch_size, num_points, num_points])
		adj_matrix = tf.where(valid_mask, adj_matrix, maximum,  name='value')



	# neg_adj = -adj_matrix
	max_index = k * dilation
	_, nn_idx_altrous = tf.nn.top_k(-adj_matrix, k=max_index)

	# nn_idx_altrous, _ = select_top_k(max_index, adj_matrix)
	# nn_idx_altrous = tf.slice(nn_idx_altrous, [0,0,0], [-1,-1,max_index])

	if dilation > 1:

		selected_sequence = tf.range(k) * dilation

		selected_sequence = tf.expand_dims( tf.expand_dims(selected_sequence, axis=0), axis=0 )
		selected_sequence = tf.tile(selected_sequence, [batch_size, num_points, 1])

		idx_ = tf.range(batch_size) * num_points * max_index
		idx_ = tf.reshape(idx_, [batch_size, 1, 1])

		idy_ = tf.range(num_points) * max_index
		idy_ = tf.reshape(idy_, [1, num_points, 1])

		nn_idx_flat = tf.reshape(nn_idx_altrous, [-1, 1])
		nn_idx_altrous = tf.gather(nn_idx_flat, selected_sequence + idx_ + idy_)

		nn_idx_altrous = tf.squeeze(nn_idx_altrous)
		if batch_size == 1:
			nn_idx_altrous = tf.expand_dims(nn_idx_altrous, 0)

	if (dist_matrix is not None):

		idx_ = tf.range(batch_size) * num_points * num_points
		idx_ = tf.reshape(idx_, [batch_size, 1, 1])

		idy_ = tf.range(num_points) * num_points
		idy_ = tf.reshape(idy_, [1, num_points, 1])

		invalid_mask_flat = tf.reshape(invalid_mask, [-1, 1])
		selected_invalid_mask=tf.gather(invalid_mask_flat, nn_idx_altrous + idx_ + idy_)

		selected_invalid_mask = tf.squeeze(selected_invalid_mask)
		if batch_size == 1:
			selected_invalid_mask = tf.expand_dims(selected_invalid_mask, 0)

		selected_valid_mask = tf.logical_not(selected_invalid_mask)

		idn_ = tf.expand_dims(tf.expand_dims(tf.range(num_points), axis=-1), axis=0)
		idn_ = tf.tile(idn_, [batch_size, 1, k])

		# selected_invalid_maskf = tf.to_float(selected_invalid_mask)
		# selected_valid_maskf = tf.to_float(selected_valid_mask)

		# nn_idx_altrous = tf.to_float(nn_idx_altrous)
		# idn_ = tf.to_float(idn_)

		# nn_idx_altrous = nn_idx_altrous * selected_valid_maskf + idn_ * selected_invalid_maskf

		# nn_idx_altrous = tf.to_int32(nn_idx_altrous)

		idn_ = tf.to_int32(idn_)
		nn_idx_altrous = tf.where(selected_valid_mask, nn_idx_altrous, idn_, name='value')

	return nn_idx_altrous


def gather_labels(input_labels, index):
	batch_size = input_labels.get_shape()[0].value
	num_points = input_labels.get_shape()[1].value

	idx_ = tf.range(batch_size) * num_points
	idx_ = tf.reshape(idx_, [batch_size, 1])

	input_labels_flat = tf.reshape(input_labels, [-1, 1])
	selected_labels = tf.gather(input_labels_flat, index + idx_)

	selected_labels = tf.squeeze(selected_labels)
	if batch_size == 1:
		selected_labels = tf.expand_dims(selected_labels, 0)

	return selected_labels


def gather_principal_feature(featrue_map, n):
	""" Select points with most principal features in all point features
	Args:
		featrue_map: (batch_size, num_points, channels)
		n: int
	
	Returns:
		selected index: (batch_size, n)
	"""
	feature_map_shape = featrue_map.get_shape()
	batch_size = feature_map_shape[0]
	num_points = feature_map_shape[1]

	feature_dist_matrix = pairwise_distance(featrue_map)
	feature_dist_sum = tf.reduce_sum(feature_dist_matrix, axis=-1, keepdims=False)

	# naive method
	# _, nn_idx = tf.nn.top_k(feature_dist_sum, k=n)

	# novel method
	cur_selected_index = tf.to_int32(tf.argmax(feature_dist_sum, axis=-1))
	# cur_selected_index = tf.expand_dims(cur_selected_index, axis=-1)

	nn_idx = principal_feature_sample(n, feature_dist_matrix, cur_selected_index)

	# # nn_idx = np.zeros((batch_size, n), dtype=np.int32)
	# nn_idx = tf.zeros((batch_size, n), tf.int32)
	# # org_mesh = tf.constant(list(range(num_points)))
	# # feature_mesh = tf.tile(tf.expand_dims(tf.expand_dims(org_mesh, 0), 0), [batch_size, num_points, 1])
	# # points_mesh = tf.tile(tf.expand_dims(tf.expand_dims(org_mesh, 0), -1), [batch_size, 1, num_points])

	# feature_mesh, points_mesh = tf.meshgrid(list(range(num_points)), list(range(num_points)))

	# feature_mesh = tf.tile(tf.expand_dims(feature_mesh, axis=0), [batch_size, 1, 1])
	# points_mesh = tf.tile(tf.expand_dims(points_mesh, axis=0), [batch_size, 1, 1])

	# index_mesh, _ = tf.meshgrid(list(range(n)), list(range(batch_size)))

	# for i in range(n):
	# 	cur_selected_index = tf.to_int32(tf.expand_dims(cur_selected_index, axis=-1))
	# 	# tf.assign(tf.slice(nn_idx, [0, i], [batch_size, 1]), cur_selected_index)
	# 	update_index = tf.ones([batch_size, n], tf.int32) * i
	# 	valid_mask = tf.equal(index_mesh, update_index)
	# 	valid_maskf = tf.to_int32(valid_mask)
	# 	nn_idx = nn_idx + valid_maskf * cur_selected_index
		
	# 	cur_selected_index = tf.expand_dims(cur_selected_index, axis=-1)
		
	# 	valid_mask = tf.equal(feature_mesh, cur_selected_index)
	# 	invalid_mask = tf.logical_not(valid_mask)
	# 	invalid_maskf = tf.to_float(invalid_mask)

	# 	feature_dist_matrix = feature_dist_matrix * invalid_maskf

	# 	valid_mask = tf.equal(points_mesh, cur_selected_index)
	# 	valid_maskf = tf.to_float(valid_mask)

	# 	cur_feature_dist_matrix = feature_dist_matrix * valid_maskf
	# 	feature_dist_sum = tf.reduce_sum(cur_feature_dist_matrix, axis=1, keepdims=False)
	# 	cur_selected_index = tf.argmax(feature_dist_sum, axis=-1)

	return nn_idx

# def get_atrous_knn(adj_matrix, k, dilation):
# 	""" Select KNN based on the pairwise distance and dilation
# 	Args:
# 		pairwise distance: (batch_size, num_points, num_points)
# 		k: int
# 		dilation: int
	
# 	Returns:
# 		selected neighbors: (batch_size, num_points, k)
# 	"""
# 	neg_adj = -adj_matrix
# 	max_index = k * dilation
# 	_, nn_idx = tf.nn.top_k(neg_adj, k=max_index)
# 	# selected_sequence = (np.arange(k) * dilation).astype(np.int32)
# 	selected_sequence = tf.range(k) * dilation

# 	# nn_idx_altrous = nn_idx[ :, :, selected_sequence ]

# 	point_cloud_shape = adj_matrix.get_shape()
# 	batch_size = point_cloud_shape[0].value
# 	num_points = point_cloud_shape[1].value

# 	selected_sequence = tf.expand_dims( tf.expand_dims(selected_sequence, axis=0), axis=0 )
# 	# print(selected_sequence.get_shape())
# 	selected_sequence = tf.tile(selected_sequence, [batch_size, num_points, 1])
# 	# print(selected_sequence.get_shape())

# 	idx_ = tf.range(batch_size) * num_points * max_index
# 	idx_ = tf.reshape(idx_, [batch_size, 1, 1])

# 	idy_ = tf.range(num_points) * max_index
# 	idy_ = tf.reshape(idy_, [1, num_points, 1])

# 	# print(idx_.get_shape())

# 	nn_idx_flat = tf.reshape(nn_idx, [-1, 1])
# 	nn_idx_altrous = tf.gather(nn_idx_flat, selected_sequence + idx_ + idy_)

# 	nn_idx_altrous = tf.squeeze(nn_idx_altrous)
# 	if batch_size == 1:
# 		nn_idx_altrous = tf.expand_dims(nn_idx_altrous, 0)

# 	# print(nn_idx_altrous.get_shape())

# 	return nn_idx_altrous


# def get_atrous_knn(adj_matrix, k, dilation, dist_matrix=None, radius=0):
# 	""" Select samples based on the feature distance, dilation, metric distance and search radius
# 	Args:
# 		feature distance: (batch_size, num_points, num_points)
# 		k: int
# 		dilation: int
# 		metric distance: (batch_size, num_points, num_points)
# 		radius: float
	
# 	Returns:
# 		selected samples: (batch_size, num_points, k)
# 	"""
# 	if (dist_matrix != None) and (radius > 0):
# 		invalid_mask = tf.greater(dist_matrix, radius)
# 		valid_mask = tf.logical_not(invalid_mask)

# 		# adj_matrix[invalid_mask] = -1
# 		# False => 0; True => 1
# 		invalid_mask = tf.to_float(invalid_mask)
# 		valid_mask = tf.to_float(valid_mask)
# 		adj_matrix = adj_matrix * valid_mask - invalid_mask

# 		adj_maximum = tf.reduce_max(adj_matrix, axis=2, keepdims=False)
# 		maximum = tf.reduce_max(tf.reduce_max(adj_maximum, axis=1, keepdims=False), axis=0, keepdims=False)
		
# 		# adj_matrix[invalid_mask] = maximum
# 		adj_matrix = adj_matrix + (invalid_mask * (maximum + 1))
# 		adj_matrix = tf.minimum(adj_matrix, tf.expand_dims(adj_maximum, 2) )

# 	neg_adj = -adj_matrix
# 	max_index = k * dilation
# 	_, nn_idx = tf.nn.top_k(neg_adj, k=max_index)

# 	selected_sequence = tf.range(k) * dilation

# 	point_cloud_shape = adj_matrix.get_shape()
# 	batch_size = point_cloud_shape[0].value
# 	num_points = point_cloud_shape[1].value

# 	selected_sequence = tf.expand_dims( tf.expand_dims(selected_sequence, axis=0), axis=0 )
# 	selected_sequence = tf.tile(selected_sequence, [batch_size, num_points, 1])

# 	idx_ = tf.range(batch_size) * num_points * max_index
# 	idx_ = tf.reshape(idx_, [batch_size, 1, 1])

# 	idy_ = tf.range(num_points) * max_index
# 	idy_ = tf.reshape(idy_, [1, num_points, 1])

# 	nn_idx_flat = tf.reshape(nn_idx, [-1, 1])
# 	nn_idx_altrous = tf.gather(nn_idx_flat, selected_sequence + idx_ + idy_)

# 	nn_idx_altrous = tf.squeeze(nn_idx_altrous)
# 	if batch_size == 1:
# 		nn_idx_altrous = tf.expand_dims(nn_idx_altrous, 0)

# 	return nn_idx_altrous