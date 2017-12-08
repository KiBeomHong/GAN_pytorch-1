import utils, torch, time, os, pickle
import numpy as np
import torch.nn as nn
import torch.optim as optim
from torch.autograd import Variable, grad
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

from utils_3D.visualize import plot_voxel
import pdb

class generator(nn.Module):
	# Network Architecture is exactly same as in infoGAN (https://arxiv.org/abs/1606.03657)
	# Architecture : FC1024_BR-FC7x7x128_BR-(64)4dc2s_BR-(1)4dc2s_S
	def __init__(self, dataset = 'mnist'):
		super(generator, self).__init__()
		if dataset == 'ShapeNet':
			self.input_height = 64 
			self.input_width = 64
			self.input_depth = 64
			self.input_dim = 200
			self.output_dim = 1

		self.deconv = nn.Sequential(
			nn.ConvTranspose3d(200, 512, 4),
			nn.BatchNorm3d(512),
			nn.ReLU(),
			nn.ConvTranspose3d(512, 256, 4, 2, 1),
			nn.BatchNorm3d(256),
			nn.ReLU(),
			nn.ConvTranspose3d(256, 128, 4, 2, 1),
			nn.BatchNorm3d(128),
			nn.ReLU(),
			nn.ConvTranspose3d(128, 64, 4, 2, 1),
			nn.BatchNorm3d(64),
			nn.ReLU(),
			nn.ConvTranspose3d(64, 1, 4, 2, 1),
			nn.Sigmoid(),
		)
		utils.initialize_weights(self)

	def forward(self, x):
		x = x.view(-1, self.input_dim, 1,1,1 )
		x = self.deconv(x)

		return x

class discriminator(nn.Module):
	# Network Architecture is exactly same as in infoGAN (https://arxiv.org/abs/1606.03657)
	# Architecture : (64)4c2s-(128)4c2s_BL-FC1024_BL-FC1_S
	def __init__(self, dataset = 'mnist'):
		super(discriminator, self).__init__()
		if dataset == 'ShapeNet':
			self.input_height = 64 
			self.input_width = 64
			self.input_depth = 64
			self.input_dim = 1
			self.output_dim = 1

		self.conv = nn.Sequential(
			nn.Conv3d(1, 64, 4, 2, 1),
			nn.BatchNorm3d(64),
			nn.LeakyReLU(0.2),
			nn.Conv3d(64, 128, 4, 2, 1),
			nn.BatchNorm3d(128),
			nn.LeakyReLU(0.2),
			nn.Conv3d(128, 256, 4, 2, 1),
			nn.BatchNorm3d(256),
			nn.LeakyReLU(0.2),
			nn.Conv3d(256, 512, 4, 2, 1),
			nn.BatchNorm3d(512),
			nn.LeakyReLU(0.2),
			nn.Conv3d(512, 1, 4),
			nn.Sigmoid(),
		)
		utils.initialize_weights(self)

	def forward(self, input):
		x = self.conv(input)
		x = x.squeeze(4).squeeze(3).squeeze(2)

		return x

class GAN3D(object):
	def __init__(self, args):
		# parameters
		self.epoch = args.epoch
		self.batch_size = args.batch_size
		self.save_dir = args.save_dir
		self.result_dir = args.result_dir
		self.dataset = args.dataset
		self.dataroot_dir = args.dataroot_dir
		self.log_dir = args.log_dir
		self.gpu_mode = args.gpu_mode
		self.model_name = args.gan_type
		self.lambda_ = 0.25

		# networks init
		self.G = generator(self.dataset)
		self.D = discriminator(self.dataset)
		self.G_optimizer = optim.Adam(self.G.parameters(), lr=args.lrG, betas=(args.beta1, args.beta2))
		self.D_optimizer = optim.Adam(self.D.parameters(), lr=args.lrD, betas=(args.beta1, args.beta2))

		if self.gpu_mode:
			self.G.cuda()
			self.D.cuda()
			self.BCE_loss = nn.BCELoss().cuda()
		else:
			self.BCE_loss = nn.BCELoss()

		# print('---------- Networks architecture -------------')
		# utils.print_network(self.G)
		# utils.print_network(self.D)
		# print('-----------------------------------------------')

		# load dataset
		data_dir = os.path.join( self.dataroot_dir, self.dataset )
		if self.dataset == 'ShapeNet':
			self.data_loader = DataLoader( utils.ShapeNet(data_dir,	transform=transforms.ToTensor()),
											batch_size=self.batch_size, shuffle=True)

		self.z_dim = 200

		# fixed noise
		if self.gpu_mode:
			self.sample_z_ = Variable(torch.rand((self.batch_size, self.z_dim)).cuda(), volatile=True)
		else:
			self.sample_z_ = Variable(torch.rand((self.batch_size, self.z_dim)), volatile=True)

	def train(self):
		self.train_hist = {}
		self.train_hist['D_loss'] = []
		self.train_hist['G_loss'] = []
		self.train_hist['per_epoch_time'] = []
		self.train_hist['total_time'] = []

		if self.gpu_mode:
			self.y_real_, self.y_fake_ = Variable(torch.ones(self.batch_size, 1).cuda()), Variable(torch.zeros(self.batch_size, 1).cuda())
		else:
			self.y_real_, self.y_fake_ = Variable(torch.ones(self.batch_size, 1)), Variable(torch.zeros(self.batch_size, 1))

		self.D.train()
		print('training start!!')
		start_time = time.time()
		for epoch in range(self.epoch):
			epoch_start_time = time.time()
			self.G.train()
			start_time_epoch = time.time()
			for iter, (x_, _) in enumerate(self.data_loader):
				if iter == self.data_loader.dataset.__len__() // self.batch_size:
					break

				z_ = torch.rand((self.batch_size, self.z_dim))

				if self.gpu_mode:
					x_, z_ = Variable(x_.cuda()), Variable(z_.cuda())
				else:
					x_, z_ = Variable(x_), Variable(z_)

				# update D network
				self.D_optimizer.zero_grad()

				D_real = self.D(x_)
				D_real_loss = self.BCE_loss(D_real, self.y_real_)
				num_correct_real = torch.sum(D_real>0.5)

				G_ = self.G(z_)
				D_fake = self.D(G_)
				D_fake_loss = self.BCE_loss(D_fake, self.y_fake_)
				num_correct_fake = torch.sum(D_fake<0.5)

#				""" DRAGAN Loss (Gradient penalty) """
#				# This is borrowed from https://github.com/jfsantos/dragan-pytorch/blob/master/dragan.py
#				if self.gpu_mode:
#					alpha = torch.rand(x_.size()).cuda()
#					x_hat = Variable(alpha * x_.data + (1 - alpha) * (x_.data + 0.5 * x_.data.std() * torch.rand(x_.size()).cuda()),
#								 requires_grad=True)
#				else:
#					alpha = torch.rand(x_.size())
#					x_hat = Variable(alpha * x_.data + (1 - alpha) * (x_.data + 0.5 * x_.data.std() * torch.rand(x_.size())),
#						requires_grad=True)
#				pred_hat = self.D(x_hat)
#				if self.gpu_mode:
#					gradients = grad(outputs=pred_hat, inputs=x_hat, grad_outputs=torch.ones(pred_hat.size()).cuda(),
#								 create_graph=True, retain_graph=True, only_inputs=True)[0]
#				else:
#					gradients = grad(outputs=pred_hat, inputs=x_hat, grad_outputs=torch.ones(pred_hat.size()),
#									 create_graph=True, retain_graph=True, only_inputs=True)[0]
#
#				gradient_penalty = self.lambda_ * ((gradients.view(gradients.size()[0], -1).norm(2, 1) - 1) ** 2).mean()

#				D_loss = D_real_loss + D_fake_loss + gradient_penalty
				D_loss = D_real_loss + D_fake_loss
				self.train_hist['D_loss'].append(D_loss.data[0])
				D_loss.backward()

				# D gets updated only if its accuracy is below 80%
				D_acc = float(num_correct_real.data[0] + num_correct_fake.data[0]) / (self.batch_size*2)
				if D_acc < 0.8:
					self.D_optimizer.step()

				# update G network
				self.G_optimizer.zero_grad()

				G_ = self.G(z_)
				D_fake = self.D(G_)

				G_loss = self.BCE_loss(D_fake, self.y_real_)
				self.train_hist['G_loss'].append(G_loss.data[0])

				G_loss.backward()
				self.G_optimizer.step()

				if ((iter + 1) % 10) == 0:
					secs = time.time()-start_time_epoch
					hours = secs//3600
					mins = secs/60%60
					print("%2dh%2dm E[%2d] B[%d/%d] D_loss: %.4f, G_loss: %.4f, D_acc:%.4f" %
						  (hours,mins, (epoch + 1), (iter + 1), self.data_loader.dataset.__len__() // self.batch_size,
						  D_loss.data[0], G_loss.data[0], D_acc))
					self.visualize_results((epoch+1)*1000+iter+1)
					for iS in range(3):
						plot_voxel( G_[iS], save_file='text_e{}i{}s{}.png'.format(epoch+1,iter+1,iS) )

			self.train_hist['per_epoch_time'].append(time.time() - epoch_start_time)
			self.visualize_results((epoch+1))

		self.train_hist['total_time'].append(time.time() - start_time)
		print("Avg one epoch time: %.2f, total %d epochs time: %.2f" % (np.mean(self.train_hist['per_epoch_time']),
			  self.epoch, self.train_hist['total_time'][0]))
		print("Training finish!... save training results")

		self.save()
		utils.generate_animation(self.result_dir + '/' + self.dataset + '/' + self.model_name + '/' + self.model_name, self.epoch)
		utils.loss_plot(self.train_hist, os.path.join(self.save_dir, self.dataset, self.model_name), self.model_name)

	def visualize_results(self, epoch, fix=True):
		self.G.eval()

		if not os.path.exists(self.result_dir + '/' + self.dataset + '/' + self.model_name):
			os.makedirs(self.result_dir + '/' + self.dataset + '/' + self.model_name)

		if fix:
			""" fixed noise """
			samples = self.G(self.sample_z_).squeeze()
		else:
			""" random noise """
			if self.gpu_mode:
				sample_z_ = Variable(torch.rand((self.batch_size, self.z_dim)).cuda(), volatile=True)
			else:
				sample_z_ = Variable(torch.rand((self.batch_size, self.z_dim)), volatile=True)

			samples = self.G(sample_z_).squeeze()

		if self.gpu_mode:
			samples = samples.cpu().data.numpy()
		else:
			samples = samples.data.numpy()

		#for i in range( self.batch_size ):
		for i in range( 5 ):
			filename = os.path.join( self.result_dir, self.dataset, self.model_name,
										self.model_name+'_e%03d_sample%02d.png'%(epoch,i))
			plot_voxel( samples[i] , save_file=filename )

	def save(self):
		save_dir = os.path.join(self.save_dir, self.dataset, self.model_name)

		if not os.path.exists(save_dir):
			os.makedirs(save_dir)

		torch.save(self.G.state_dict(), os.path.join(save_dir, self.model_name + '_G.pkl'))
		torch.save(self.D.state_dict(), os.path.join(save_dir, self.model_name + '_D.pkl'))

		with open(os.path.join(save_dir, self.model_name + '_history.pkl'), 'wb') as f:
			pickle.dump(self.train_hist, f)

	def load(self):
		save_dir = os.path.join(self.save_dir, self.dataset, self.model_name)

		self.G.load_state_dict(torch.load(os.path.join(save_dir, self.model_name + '_G.pkl')))
		self.D.load_state_dict(torch.load(os.path.join(save_dir, self.model_name + '_D.pkl')))