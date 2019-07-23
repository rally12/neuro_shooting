import os
import argparse
import time
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.autograd as autograd
import random

# Command line arguments

parser = argparse.ArgumentParser('ODE demo')
parser.add_argument('--network', type=str, choices=['odenet', 'shooting'], default='shooting', help='Sets the network training appproach.')
parser.add_argument('--method', type=str, choices=['dopri5', 'adams','rk4'], default='rk4', help='Selects the desired integrator')
parser.add_argument('--stepsize', type=float, default=0.5, help='Step size for the integrator (if not adaptive).')
parser.add_argument('--data_size', type=int, default=250, help='Length of the simulated data that should be matched.')
parser.add_argument('--batch_time', type=int, default=25, help='Length of the training samples.')
parser.add_argument('--batch_size', type=int, default=10, help='Number of training samples.')
parser.add_argument('--niters', type=int, default=10000, help='Maximum nunber of iterations.')
parser.add_argument('--batch_validation_size', type=int, default=100, help='Length of the samples for validation.')
parser.add_argument('--seed', required=False, type=int, default=1234,
                    help='Sets the random seed which affects data shuffling')

parser.add_argument('--linear', action='store_true', help='If specified the ground truth system will be linear, otherwise nonlinear.')

parser.add_argument('--test_freq', type=int, default=20, help='Frequency with which the validation measures are to be computed.')
parser.add_argument('--viz_freq', type=int, default=100, help='Frequency with which the results should be visualized; if --viz is set.')

parser.add_argument('--validate_with_long_range', action='store_true', help='If selected, a long-range trajectory will be used; otherwise uses batches as for training')

parser.add_argument('--nr_of_particles', type=int, default=10, help='Number of particles to parameterize the initial condition')
parser.add_argument('--sim_norm', type=str, choices=['l1','l2'], default='l2', help='Norm for the similarity measure.')
parser.add_argument('--shooting_norm_penalty', type=float, default=0, help='Factor to penalize the norm with; default 0, but 0.1 or so might be a good value')
parser.add_argument('--nonlinearity', type=str, choices=['identity', 'relu', 'tanh', 'sigmoid'], default='tanh', help='Nonlinearity for shooting.')


parser.add_argument('--viz', action='store_true', help='Enable visualization.')
parser.add_argument('--gpu', type=int, default=0, help='Enable GPU computation on specified GPU.')
parser.add_argument('--adjoint', action='store_true', help='Use adjoint integrator to avoid storing values during forward pass.')

args = parser.parse_args()

print('Setting the random seed to {:}'.format(args.seed))
random.seed(args.seed)
torch.manual_seed(args.seed)

if args.adjoint:
    from torchdiffeq import odeint_adjoint as odeint
else:
    from torchdiffeq import odeint


device = torch.device('cuda:' + str(args.gpu) if torch.cuda.is_available() else 'cpu')

true_y0 = torch.tensor([[2., 0.]]).to(device)
t = torch.linspace(0., 25., args.data_size).to(device)
#true_A = torch.tensor([[-0.1, 2.0], [-2.0, -0.1]]).to(device)
#true_A = torch.tensor([[-0.025, 2.0], [-2.0, -0.025]]).to(device)
#true_A = torch.tensor([[-0.05, 2.0], [-2.0, -0.05]]).to(device)
true_A = torch.tensor([[-0.01, 0.25], [-0.25, -0.01]]).to(device)


options = dict()

# default tolerance settings
#rtol=1e-6
#atol=1e-12

rtol = 1e-8
atol = 1e-10

options  = {'step_size': args.stepsize}

class Lambda(nn.Module):

    def forward(self, t, y):
        if args.linear:
            return torch.mm(y, true_A)
        else:
            return torch.mm(y**3, true_A)

with torch.no_grad():
    true_y = odeint(Lambda(), true_y0, t, method=args.method, atol=atol, rtol=rtol, options=options)


def get_batch(batch_size=None):
    if batch_size is None:
        batch_size = args.batch_size
    s = torch.from_numpy(np.random.choice(np.arange(args.data_size - args.batch_time, dtype=np.int64), batch_size, replace=False)).to(device)
    batch_y0 = true_y[s]  # (M, D)
    batch_t = t[:args.batch_time]  # (T)
    batch_y = torch.stack([true_y[s + i] for i in range(args.batch_time)], dim=0)  # (T, M, D)
    return batch_y0, batch_t, batch_y

def visualize_batch(batch_t,batch_y,thetas=None,real_thetas=None,bias=None):

    # convention for batch_t: t x B x (row-vector)

    if args.viz:

        batch_size = batch_y.size()[1]

        if (thetas is None) or (bias is None) or (real_thetas is None):
            fig = plt.figure(figsize=(8, 4), facecolor='white')
            ax_traj = fig.add_subplot(121, frameon=False)
            ax_phase = fig.add_subplot(122, frameon=False)
        else:
            fig = plt.figure(figsize=(8, 8), facecolor='white')
            ax_traj = fig.add_subplot(221, frameon=False)
            ax_phase = fig.add_subplot(222, frameon=False)
            ax_thetas = fig.add_subplot(223, frameon=False)
            ax_bias = fig.add_subplot(224, frameon=False)

        ax_traj.cla()
        ax_traj.set_title('Trajectories')
        ax_traj.set_xlabel('t')
        ax_traj.set_ylabel('x,y')

        for b in range(batch_size):
            c_values = batch_y[:,b,0,:]

            ax_traj.plot(batch_t.numpy(), c_values.numpy()[:, 0], batch_t.numpy(), c_values.numpy()[:, 1], 'g-')

        ax_traj.set_xlim(batch_t.min(), batch_t.max())
        ax_traj.set_ylim(-2, 2)
        ax_traj.legend()

        ax_phase.cla()
        ax_phase.set_title('Phase Portrait')
        ax_phase.set_xlabel('x')
        ax_phase.set_ylabel('y')

        for b in range(batch_size):
            c_values = batch_y[:,b,0,:]

            ax_phase.plot(c_values.numpy()[:, 0], c_values.numpy()[:, 1], 'g-')

        ax_phase.set_xlim(-2, 2)
        ax_phase.set_ylim(-2, 2)

        if (thetas is not None) and (bias is not None) and (real_thetas is not None):
            ax_thetas.cla()
            ax_thetas.set_title('theta elements over time')
            nr_t_el = thetas.shape[1]
            colors = ['r','b','c','k']
            for n in range(nr_t_el):
                ax_thetas.plot(thetas[:,n],color=colors[n])
                ax_thetas.plot(real_thetas[:,n],'--', color=colors[n])

            ax_bias.cla()
            ax_bias.set_title('bias elements over time')
            nr_b_el = bias.shape[1]
            for n in range(nr_b_el):
                ax_bias.plot(bias[:,n])

        fig.tight_layout()

        print('Plotting')
        plt.show()


def makedirs(dirname):
    if not os.path.exists(dirname):
        os.makedirs(dirname)


if args.viz:
    makedirs('png')
    import matplotlib.pyplot as plt

def visualize(true_y, pred_y, sim_time, odefunc, itr, is_odenet=False, is_higher_order_model=False):

    if args.viz:

        quiver_scale = 2.5 # to scale the magnitude of the quiver vectors for visualization

        fig = plt.figure(figsize=(12, 4), facecolor='white')
        ax_traj = fig.add_subplot(131, frameon=False)
        ax_phase = fig.add_subplot(132, frameon=False)
        ax_vecfield = fig.add_subplot(133, frameon=False)

        ax_traj.cla()
        ax_traj.set_title('Trajectories')
        ax_traj.set_xlabel('t')
        ax_traj.set_ylabel('x,y')

        for n in range(true_y.size()[1]):
            ax_traj.plot(sim_time.numpy(), true_y.detach().numpy()[:, n, 0, 0], sim_time.numpy(), true_y.numpy()[:, n, 0, 1],
                     'g-')
            ax_traj.plot(sim_time.numpy(), pred_y.detach().numpy()[:, n, 0, 0], '--', sim_time.numpy(),
                     pred_y.detach().numpy()[:, n, 0, 1],
                     'b--')

        ax_traj.set_xlim(sim_time.min(), sim_time.max())
        ax_traj.set_ylim(-2, 2)
        ax_traj.legend()

        ax_phase.cla()
        ax_phase.set_title('Phase Portrait')
        ax_phase.set_xlabel('x')
        ax_phase.set_ylabel('y')

        for n in range(true_y.size()[1]):
            ax_phase.plot(true_y.detach().numpy()[:, n, 0, 0], true_y.detach().numpy()[:, n, 0, 1], 'g-')
            ax_phase.plot(pred_y.detach().numpy()[:, n, 0, 0], pred_y.detach().numpy()[:, n, 0, 1], 'b--')

        if not is_odenet:
            q = (odefunc.q_params)
            p = (odefunc.p_params)

            q_np = q.cpu().detach().squeeze(dim=1).numpy()
            p_np = p.cpu().detach().squeeze(dim=1).numpy()

            ax_phase.scatter(q_np[:,0],q_np[:,1],marker='+')
            ax_phase.quiver(q_np[:,0],q_np[:,1], p_np[:,0],p_np[:,1],color='r', scale=quiver_scale)

        ax_phase.set_xlim(-2, 2)
        ax_phase.set_ylim(-2, 2)


        ax_vecfield.cla()
        ax_vecfield.set_title('Learned Vector Field')
        ax_vecfield.set_xlabel('x')
        ax_vecfield.set_ylabel('y')

        y, x = np.mgrid[-2:2:21j, -2:2:21j]

        current_y = torch.Tensor(np.stack([x, y], -1).reshape(21 * 21, 2))

        # print("q_params",q_params.size())

        if not is_odenet:
            if is_higher_order_model:
                z_0 = odefunc.get_initial_condition(x=current_y.unsqueeze(dim=1))
            else:
                z_0 = torch.cat((q, p, current_y.unsqueeze(dim=1)))

            dydt_tmp = odefunc(0, z_0).cpu().detach().numpy()

            if is_higher_order_model:

                viz_time = t[:5] # just 5 timesteps ahead
                temp_pred_y = odeint(shooting, z_0, viz_time, method=args.method, atol=atol, rtol=rtol, options=options)
                _, _, _, _, dydt_pred_y, _ = shooting.disassemble(temp_pred_y, dim=1)
                dydt = (dydt_pred_y[-1,...]-dydt_pred_y[0,...]).detach().numpy()

                #dydt_tmp = odefunc(0, z_0).cpu().detach().numpy()
                #_,_,_,_,dydt,_ = odefunc.disassemble(dydt_tmp)
                dydt = dydt[:,0,...]
            else:
                dydt_tmp = odefunc(0, z_0).cpu().detach().numpy()
                dydt = dydt_tmp[2 * K:, 0,...]
        else:
            dydt = odefunc(0, current_y).cpu().detach().numpy()

        mag = np.sqrt(dydt[:, 0]**2 + dydt[:, 1]**2).reshape(-1, 1)
        dydt = (dydt / mag)
        dydt = dydt.reshape(21, 21, 2)

        ax_vecfield.streamplot(x, y, dydt[:, :, 0], dydt[:, :, 1], color="black")

        if not is_odenet:
            ax_vecfield.scatter(q_np[:, 0], q_np[:, 1], marker='+')
            ax_vecfield.quiver(q_np[:,0],q_np[:,1], p_np[:,0],p_np[:,1],color='r', scale=quiver_scale)

        ax_vecfield.set_xlim(-2, 2)
        ax_vecfield.set_ylim(-2, 2)

        fig.tight_layout()

        print('Plotting')
        # plt.savefig('png/{:03d}'.format(itr))
        # plt.draw()
        # plt.pause(0.001)
        plt.show()


class ODEFunc(nn.Module):

    def __init__(self):
        super(ODEFunc, self).__init__()

        self.net = nn.Sequential(
            nn.Linear(2, 50),
            nn.Tanh(),
            nn.Linear(50, 2),
        )

        for m in self.net.modules():
            if isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, mean=0, std=0.1)
                nn.init.constant_(m.bias, val=0)

    def forward(self, t, y):
        return self.net(y)

class ODESimpleFunc(nn.Module):

    def __init__(self):
        super(ODESimpleFunc, self).__init__()

        self.net = nn.Sequential(
            nn.Linear(2, 2),
            nn.Tanh(),
        )

        for m in self.net.modules():
            if isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, mean=0, std=0.1)
                nn.init.constant_(m.bias, val=0)

    def forward(self, t, y):
        return self.net(y)

class ODESimpleFuncWithIssue(nn.Module):
# order matters. If linear transform comes after the tanh it cannot move the nonlinearity to a point where it does not matter
# (and hence will produce the 45 degree tanh angle phenonmenon)

    def __init__(self):
        super(ODESimpleFuncWithIssue, self).__init__()

        self.net = nn.Sequential(
            nn.Tanh(),
            nn.Linear(2, 2),
        )

        for m in self.net.modules():
            if isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, mean=0, std=0.1)
                nn.init.constant_(m.bias, val=0)

    def forward(self, t, y):
        return self.net(y)

def drelu(x):
    # derivative of relu
    res = (x>=0)
    res = res.type(x.type())
    return res

def dtanh(x):
    # derivative of tanh
    return 1.0-torch.tanh(x)**2

def identity(x):
    return x

def didentity(x):
    return torch.ones_like(x)

class ShootingBlock(nn.Module):
    def __init__(self, batch_y0=None, Kbar=None, Kbar_b=None, nonlinearity=None, only_random_initialization=False):
        super(ShootingBlock, self).__init__()

        self.k = batch_y0.size()[0]
        self.d = batch_y0.size()[2]

        mult_theta = 1.0
        mult_b = 1.0

        if Kbar is None:
            self.Kbar = 1./mult_theta*torch.eye(self.d**2)
        else:
            self.Kbar = 1./mult_theta*Kbar
        if Kbar_b is None:
            self.Kbar_b = 1./mult_b*torch.eye(self.d)
        else:
            self.Kbar_b = 1./mult_b*Kbar_b

        self.Kbar = self.Kbar.to(device)
        self.Kbar_b = self.Kbar_b.to(device)

        self.inv_Kbar_b = self.Kbar_b.inverse()
        self.inv_Kbar = self.Kbar.inverse()

        self.rand_mag_q = 0.1
        self.rand_mag_p = 0.1

        if only_random_initialization:
            # do a fully random initialization
            self.q_params = nn.Parameter(self.rand_mag_q * torch.randn_like(batch_y0))
            self.p_params = nn.Parameter(self.rand_mag_p * torch.randn([self.k, 1, self.d]))
        else:
            self.q_params = nn.Parameter(batch_y0 + self.rand_mag_q * torch.randn_like(batch_y0))
            self.p_params = nn.Parameter(torch.zeros(self.k, 1, self.d) + self.rand_mag_p * torch.randn([self.k, 1, self.d]))

        supported_nonlinearities = ['identity', 'relu', 'tanh', 'sigmoid']

        if nonlinearity is None:
            use_nonlinearity = 'identity'
        else:
            use_nonlinearity = nonlinearity.lower()

        if use_nonlinearity not in supported_nonlinearities:
            raise ValueError('Unsupported nonlinearity {}'.format(use_nonlinearity))

        if use_nonlinearity=='relu':
            self.nl = nn.functional.relu
            self.dnl = drelu
        elif use_nonlinearity=='tanh':
            self.nl = torch.tanh
            self.dnl = dtanh
        elif use_nonlinearity=='identity':
            self.nl = identity
            self.dnl = didentity
        elif use_nonlinearity=='sigmoid':
            self.nl = torch.sigmoid
            self.dnl = torch.sigmoid
        else:
            raise ValueError('Unknown nonlinearity {}'.format(use_nonlinearity))


        # keeping track of variables
        self._number_of_calls = 0

    def get_norm_penalty(self):

        p = self.p_params.transpose(1,2)
        q = self.q_params.transpose(1,2)

        theta = self.compute_theta(q=q,p=p)
        bias = self.compute_bias(p=p)

        theta_penalty = torch.mm(theta.view(1,-1),torch.mm(self.inv_Kbar,theta.view(-1,1)))
        bias_penalty = torch.mm(bias.t(),torch.mm(self.inv_Kbar_b,bias))

        penalty = theta_penalty + bias_penalty
        return penalty

    def compute_theta(self,q,p):
        # Update theta according to the (p,q) equations
        # With Kbar = \bar M_\theta}^{-1}
        # \theta = Kbar(-\sum_i p_i \sigma(x_i)^T
        # computing the negative sum of the outer product

        temp = -torch.bmm(p, self.nl(q.transpose(1, 2))).mean(dim=0)

        # now multiply it with the inverse of the regularizer (needs to be vectorized first and then back)
        theta = (torch.mm(self.Kbar, temp.view(-1,1))).view(temp.size())

        return theta

    def compute_bias(self,p):
        # Update bias according to the (p,q)
        # With Kbar_b = \bar M_b^{-1}
        # b = Kbar_b(-\sum_i p_i)
        # temp = torch.matmul(-p.squeeze().transpose(0, 1), torch.ones([self.k, 1],device=device))
        # keep in mind that by convention the vectors are stored as row vectors here, hence the transpose

        #temp = -p.sum(dim=0)
        temp = -p.mean(dim=0)

        bias = torch.mm(self.Kbar_b, temp)

        return bias

    def forward(self, t,input):
        """
        :param input: containing q, p, x
        :param batch_t: 1D tensor holding time points for evaluation
        :return: |batch_t| x minibatch x 1 x feature dimension
        """

        self._number_of_calls += 1
        if (self._number_of_calls%10000==0):
            # just to test; this is a way we can keep track of state variables, for example to initialize iterative solvers
            print('Number of calls: {}'.format(self._number_of_calls))


        # q and p are K x 1 x feature dim tensors
        # x is a |batch| x 1 x feature dim tensor
        qt,pt,xt = input[:self.k, ...], input[self.k:2 * self.k, ...], input[2 * self.k:, ...]

        # let's first convert everything to column vectors (as this is closer to our notation)
        q = qt.transpose(1,2)
        p = pt.transpose(1,2)
        x = xt.transpose(1,2)


        # compute theta
        theta = self.compute_theta(q=q,p=p)

        # compute b
        bias = self.compute_bias(p=p)

        # let't first compute the right hand side of the evolution equation for q and the same for x
        # \dot x_i = \theta \sigma(x_i) + b
        # \dot q_i = \theta \sigma(q_i) + b

        temp_q = self.nl(q)
        temp_x = self.nl(x)

        dot_x = torch.matmul(theta, temp_x) + bias
        dot_q = torch.matmul(theta, temp_q) + bias

        # compute the advection equation for p
        # \dot p_i =  - [d\sigma(x_i)^T]\theta^T p_i
        # but here, d\sigma(x_i)^T = d\sigma(x_i) is a diagonal matrix composed with the derivative of the relu.

        # first compute \theta^T p_i
        tTp = torch.matmul(theta.t(),p)
        # now compute element-wise sigma-prime xi
        sigma_p = self.dnl(q)
        # and multiply the two
        dot_p = -sigma_p*tTp

        # as we transposed the vectors before we need to transpose on the way back
        dot_qt = dot_q.transpose(1, 2)
        dot_pt = dot_p.transpose(1, 2)
        dot_xt = dot_x.transpose(1, 2)

        return torch.cat((dot_qt,dot_pt,dot_xt))

class ShootingBlock2(nn.Module):
    def __init__(self, batch_y0=None, Kbar=None, Kbar_b=None, nonlinearity=None, only_random_initialization=False):
        super(ShootingBlock2, self).__init__()

        self.k = batch_y0.size()[0]
        self.d = batch_y0.size()[2]

        mult_theta = 1.0
        mult_b = 1.0

        if Kbar is None:
            self.Kbar = 1./mult_theta*torch.eye(self.d**2)
        else:
            self.Kbar = 1./mult_theta*Kbar
        if Kbar_b is None:
            self.Kbar_b = 1./mult_b*torch.eye(self.d)
        else:
            self.Kbar_b = 1./mult_b*Kbar_b

        self.Kbar = self.Kbar.to(device)
        self.Kbar_b = self.Kbar_b.to(device)

        self.inv_Kbar_b = self.Kbar_b.inverse()
        self.inv_Kbar = self.Kbar.inverse()

        self.rand_mag_q = 0.1
        self.rand_mag_p = 0.1

        if only_random_initialization:
            # do a fully random initialization
            self.q_params = nn.Parameter(self.rand_mag_q * torch.randn_like(batch_y0))
            self.p_params = nn.Parameter(self.rand_mag_p * torch.randn([self.k, 1, self.d]))
        else:
            self.q_params = nn.Parameter(batch_y0 + self.rand_mag_q * torch.randn_like(batch_y0))
            self.p_params = nn.Parameter(torch.zeros(self.k, 1, self.d) + self.rand_mag_p * torch.randn([self.k, 1, self.d]))

        supported_nonlinearities = ['identity', 'relu', 'tanh', 'sigmoid']

        if nonlinearity is None:
            use_nonlinearity = 'identity'
        else:
            use_nonlinearity = nonlinearity.lower()

        if use_nonlinearity not in supported_nonlinearities:
            raise ValueError('Unsupported nonlinearity {}'.format(use_nonlinearity))

        if use_nonlinearity=='relu':
            self.nl = nn.functional.relu
            self.dnl = drelu
        elif use_nonlinearity=='tanh':
            self.nl = torch.tanh
            self.dnl = dtanh
        elif use_nonlinearity=='identity':
            self.nl = identity
            self.dnl = didentity
        elif use_nonlinearity=='sigmoid':
            self.nl = torch.sigmoid
            self.dnl = torch.sigmoid
        else:
            raise ValueError('Unknown nonlinearity {}'.format(use_nonlinearity))

    def get_norm_penalty(self):

        p = self.p_params.transpose(1,2)
        q = self.q_params.transpose(1,2)

        theta = self.compute_theta(q=q,p=p)
        bias = self.compute_bias(p=p)

        theta_penalty = torch.mm(theta.view(1,-1),torch.mm(self.inv_Kbar,theta.view(-1,1)))
        bias_penalty = torch.mm(bias.t(),torch.mm(self.inv_Kbar_b,bias))

        penalty = theta_penalty + bias_penalty
        return penalty

    def compute_theta(self,q,p):
        # Update theta according to the (p,q) equations
        # With Kbar = \bar M_\theta}^{-1}
        # \theta = Kbar(-\sum_i p_i \sigma(x_i)^T
        # computing the negative sum of the outer product

        #temp = -torch.bmm(p, self.nl(q.transpose(1, 2))).sum(dim=0)
        temp = -torch.bmm(p, self.nl(q.transpose(1, 2))).mean(dim=0)

        # now multiply it with the inverse of the regularizer (needs to be vectorized first and then back)
        theta = (torch.mm(self.Kbar, temp.view(-1,1))).view(temp.size())

        return theta

    def compute_bias(self,p):
        # Update bias according to the (p,q)
        # With Kbar_b = \bar M_b^{-1}
        # b = Kbar_b(-\sum_i p_i)
        # temp = torch.matmul(-p.squeeze().transpose(0, 1), torch.ones([self.k, 1],device=device))
        # keep in mind that by convention the vectors are stored as row vectors here, hence the transpose

        #temp = -p.sum(dim=0)
        temp = -p.mean(dim=0)

        bias = torch.mm(self.Kbar_b, temp)

        return bias

    def advect_x(self,x,theta,bias):
        """
        Forward equation which  is applied on the data. In principle similar to advect_q
        :param x:
        :param theta:
        :param bias:
        :return: \dot x_i = \theta \sigma(x_i) + b
        """
        temp_x = self.nl(x)
        return torch.matmul(theta, temp_x) + bias

    def advect_q(self,q,theta,bias):
        """
        Forward equation which  is applied on the data. In principle similar to advect_q
        :param x:
        :param theta:
        :param bias:
        :return: \dot q_i = \theta \sigma(q_i) + b
        """
        temp_q = self.nl(q)
        return torch.matmul(theta, temp_q) + bias

    def advect_p(self,p,q,theta,bias):
        theta = theta.detach()
        bias = bias.detach()
        compute = torch.sum(p*self.advect_q(q,theta,bias))

        xgrad, = autograd.grad(compute, q,
                               grad_outputs=compute.data.new(compute.shape).fill_(1),
                               create_graph=True,
                               retain_graph=True,
                               allow_unused=True)
        return -xgrad

    def forward(self, t,input):
        """
        :param input: containing q, p, x
        :param batch_t: 1D tensor holding time points for evaluation
        :return: |batch_t| x minibatch x 1 x feature dimension
        """
        # q and p are K x 1 x feature dim tensors
        # x is a |batch| x 1 x feature dim tensor
        qt,pt,xt = input[:self.k, ...], input[self.k:2 * self.k, ...], input[2 * self.k:, ...]

        # let's first convert everything to column vectors (as this is closer to our notation)
        q = qt.transpose(1,2)
        p = pt.transpose(1,2)
        x = xt.transpose(1,2)

        # compute theta
        theta = self.compute_theta(q=q,p=p)

        # compute b
        bias = self.compute_bias(p=p)

        # let't first compute the right hand side of the evolution equation for q and the same for x
        dot_x = self.advect_x(x,theta,bias)
        dot_q = self.advect_q(q,theta,bias)

        # compute the advection equation for p
        # \dot p_i =  - [d\sigma(x_i)^T]\theta^T p_i
        # but here, d\sigma(x_i)^T = d\sigma(x_i) is a diagonal matrix composed with the derivative of the relu.

        # first compute \theta^T p_i

        dot_p =  self.advect_p(p,q,theta,bias)

        #theta_bis = torch.empty_like(theta).copy_(theta)
        #p_bis = torch.empty_like(p).copy_(p)
        #q_bis = torch.empty_like(q).copy_(q)
        #tTp = torch.matmul(theta_bis.t(), p_bis)
        # now compute element-wise sigma-prime xi
        #sigma_p = self.dnl(q_bis)
        # and multiply the two
        #dot_p_2 = -sigma_p * tTp
        #print("comparison",torch.sum((dot_p_2 - dot_p)**2))
        # as we transposed the vectors before we need to transpose on the way back
        dot_qt = dot_q.transpose(1, 2)
        dot_pt = dot_p.transpose(1, 2)
        dot_xt = dot_x.transpose(1, 2)

        return torch.cat((dot_qt,dot_pt,dot_xt))

class ShootingModel_1(nn.Module):
    def __init__(self, batch_y0=None, Kbar1=None, Kbar2=None, Kbar_b1=None,Kbar_b2=None, nonlinearity=None, only_random_initialization=False):
        super(ShootingModel_1, self).__init__()

        nonlinearity = 'softmax'

        self.k = batch_y0.size()[0]
        self.d = batch_y0.size()[2]

        self.layer_dim = self.d

        mult_theta = 1.0
        mult_b = 1.0


        if Kbar1 is None:
            self.Kbar1 = 1./mult_theta*torch.eye(self.d*self.layer_dim)
        else:
            self.Kbar1 = 1./mult_theta*Kbar1
        if Kbar2 is None:
            self.Kbar2 = 1./mult_theta*torch.eye(self.d*self.layer_dim)
        else:
            self.Kbar2 = 1./mult_theta*Kbar2
        if Kbar_b1 is None:
            self.Kbar_b1 = 1./mult_b*torch.eye(self.d)
        else:
            self.Kbar_b1 = 1./mult_b*Kbar_b1
        if Kbar_b2 is None:
            self.Kbar_b2 = 1. / mult_b * torch.eye(self.layer_dim)
        else:
            self.Kbar_b2 = 1. / mult_b * Kbar_b2

        self.Kbar1 = self.Kbar1.to(device)
        self.Kbar_b1 = self.Kbar_b1.to(device)
        self.Kbar2 = self.Kbar2.to(device)
        self.Kbar_b2 = self.Kbar_b2.to(device)

        self.inv_Kbar_b1 = self.Kbar_b1.inverse()
        self.inv_Kbar1 = self.Kbar1.inverse()
        self.inv_Kbar_b2 = self.Kbar_b2.inverse()
        self.inv_Kbar2 = self.Kbar2.inverse()

        self.rand_mag_q = 0.1
        self.rand_mag_p = 0.1

        if only_random_initialization:
            # do a fully random initialization
            self.q_params = nn.Parameter(self.rand_mag_q * torch.randn_like(batch_y0))
            self.p_params = nn.Parameter(self.rand_mag_p * torch.randn([self.k, 1, self.d]))
        else:
            self.q_params = nn.Parameter(batch_y0 + self.rand_mag_q * torch.randn_like(batch_y0))
            self.p_params = nn.Parameter(torch.zeros(self.k, 1, self.d) + self.rand_mag_p * torch.randn([self.k, 1, self.d]))

        supported_nonlinearities = ['identity', 'relu', 'tanh', 'sigmoid',"softmax"]

        if nonlinearity is None:
            use_nonlinearity = 'identity'
        else:
            use_nonlinearity = nonlinearity.lower()
            print("linearity",nonlinearity)

        if use_nonlinearity not in supported_nonlinearities:
            raise ValueError('Unsupported nonlinearity {}'.format(use_nonlinearity))

        if use_nonlinearity=='relu':
            self.nl = nn.functional.relu
            self.dnl = drelu
        elif use_nonlinearity=='tanh':
            self.nl = torch.tanh
            self.dnl = dtanh
        elif use_nonlinearity=='identity':
            self.nl = identity
            self.dnl = didentity
        elif use_nonlinearity=='sigmoid':
            self.nl = torch.sigmoid
            self.dnl = torch.sigmoid
        elif use_nonlinearity == 'softmax':
            self.nl = softmax
            self.dnl = dsoftmax
        else:
            raise ValueError('Unknown nonlinearity {}'.format(use_nonlinearity))
        self.initialization_parameter()



    def get_norm_penalty(self):

        return 0


    def compute_bias_1(self,p):
        # Update bias according to the (p,q)
        # With Kbar_b = \bar M_b^{-1}
        # b = Kbar_b(-\sum_i p_i)
        # temp = torch.matmul(-p.squeeze().transpose(0, 1), torch.ones([self.k, 1],device=device))
        # keep in mind that by convention the vectors are stored as row vectors here, hence the transpose
        #temp = -p.sum(dim=0)
        temp = p.mean(dim=0)
        bias_1 = torch.mm(self.Kbar_b1, temp)
        return bias_1

    def initialization_parameter(self):
        self.theta_1_init = torch.eye(self.d, self.layer_dim)
        self.theta_2_init = torch.eye(self.layer_dim, self.d)
        self.bias_2_init = torch.zeros(self.layer_dim, 1)


    def compute_theta(self,q,p):
        try:
            result = self.theta_2
        except:
            result = self.theta_2_init
        return result

    def compute_bias(self,p):
        try:
            result = self.bias_2
        except:
            result = self.bias_2_init
        return result

    def compute_update_parameters(self,p,q,theta_1,theta_2,bias_2):
        z = torch.matmul(theta_2, q) + bias_2
        sigma_p = self.dnl(z)
        sigma = self.nl(z)

        temp = torch.matmul(theta_1.t(), p)
        temp_bias_2 = sigma_p * temp

        update_bias_2 = torch.mean(temp_bias_2,dim = 0)
        update_theta_2 = torch.bmm(temp_bias_2, q.transpose(1, 2)).mean(dim=0)


        # now multiply it with the inverse of the regularizer (needs to be vectorized first and then back
        update_bias_2 = (torch.mm(self.Kbar_b2, update_bias_2.view(-1,1))).view(update_bias_2.size())
        #
        update_theta_2 = (torch.mm(self.Kbar2, update_theta_2.view(-1, 1))).view(update_theta_2.size())

        z = torch.matmul(update_theta_2, q) + update_bias_2
        sigma = self.nl(z)
        update_theta_1 = torch.bmm(p, sigma.transpose(1, 2)).mean(dim=0)
        update_theta_1 = (torch.mm(self.Kbar1, update_theta_1.view(-1, 1))).view(update_theta_1.size())

        #print("square difference theta2",torch.sum((update_theta_2)**2))
        #print("square difference theat1", torch.sum(update_theta_1) ** 2)
        #print("square difference bias2", torch.sum(update_bias_2) ** 2)


        return update_theta_1,update_theta_2,update_bias_2


    def compute_parameters(self,p,q,theta_1,theta_2,bias_2,n_iterations = 1,alpha = 0.):
        bias_1 = self.compute_bias_1(p)
        #print("bias1",torch.sum(bias_1**2))
        for i in range(n_iterations):
            #print("iteration: ",i)
            update_theta_1,update_theta_2,update_bias_2 = self.compute_update_parameters(p,q,theta_1,theta_2,bias_2)
            update_bias_1 = self.compute_bias_1(p)
            theta_1,theta_2,bias_1,bias_2 = alpha * theta_1 + (1. - alpha) * update_theta_1, alpha * theta_2 + (
                        1. - alpha) * update_theta_2, alpha * bias_1 + (1. - alpha) * update_bias_1, alpha * bias_2 + (
                        1. - alpha) * update_bias_2

        self.theta_1,self.theta_2,self.bias_1,self.bias_2 = theta_1,self.theta_2_init,bias_1,bias_2
        #return self.theta_1_init,alpha*theta_2 + (1.-alpha)*update_theta_2,alpha*bias_1 + (1.-alpha)*update_bias_1,alpha*bias_2 + (1.-alpha)*update_bias_2
        #return 0.8*theta_1 + (1.-0.8)*update_theta_1,alpha*theta_2 + (1.-alpha)*update_theta_2,alpha*bias_1 + (1.-alpha)*update_bias_1,alpha*bias_2 + (1.-alpha)*update_bias_2
        return alpha*theta_1 + (1.-alpha)*update_theta_1,self.theta_2_init,alpha*bias_1 + (1.-alpha)*update_bias_1,torch.zeros_like(bias_2)

    def advect_x(self,x,theta_1,theta_2,bias_1,bias_2):
        """
        Forward equation which  is applied on the data. In principle similar to advect_q
        :param x:
        :param theta:
        :param bias:
        :return: \dot x_i = \theta \sigma(x_i) + b
        """
        temp = torch.matmul(theta_2, x) + bias_2
        temp_x = self.nl(temp)
        return torch.matmul(theta_1, temp_x) + bias_1

    def advect_q(self,q,theta_1,theta_2,bias_1,bias_2):
        """
        Forward equation which  is applied on the data. In principle similar to advect_q
        :param x:
        :param theta:
        :param bias:
        :return: \dot q_i = \theta \sigma(q_i) + b
        """
        temp = torch.matmul(theta_2, q) + bias_2
        temp_q = self.nl(temp)
        return torch.matmul(theta_1, temp_q) + bias_1

    def advect_p(self,p,q,theta_1,theta_2,bias_2):

        tTp = torch.matmul(theta_1.t(), p)
        # now compute element-wise sigma-prime xi
        sigma_p = self.dnl(torch.matmul(theta_2,q) + bias_2)
        # and multiply the two
        dot_p = -torch.matmul(theta_2.t(),sigma_p * tTp)

        return dot_p

    def forward(self, t,input):
        """
        :param input: containing q, p, x
        :param batch_t: 1D tensor holding time points for evaluation
        :return: |batch_t| x minibatch x 1 x feature dimension
        """
        # q and p are K x 1 x feature dim tensors
        # x is a |batch| x 1 x feature dim tensor
        qt,pt,xt = input[:self.k, ...], input[self.k:2 * self.k, ...], input[2 * self.k:, ...]

        # let's first convert everything to column vectors (as this is closer to our notation)
        q = qt.transpose(1,2)
        p = pt.transpose(1,2)
        x = xt.transpose(1,2)
        try:
            self.initialization_parameter()
            theta_1 = self.theta_1_init
            theta_2 = self.theta_2_init
            bias_2=self.bias_2_init
        except:
            pass
        # compute theta
        theta_1,theta_2,bias_1,bias_2 = self.compute_parameters(p,q,theta_1,theta_2,bias_2)
        #print("norm theta_1",torch.sum(theta_1**2))
        #print("norm theta_2",torch.sum(theta_2**2))
        #print("norm bias_1",torch.sum(bias_1**2))
        #print("norm bias_2",torch.sum(bias_2**2))

        # let't first compute the right hand side of the evolution equation for q and the same for x
        dot_x = self.advect_x(x,theta_1,theta_2,bias_1,bias_2)
        dot_q = self.advect_q(q,theta_1,theta_2,bias_1,bias_2)

        dot_p =  self.advect_p(p,q,theta_1,theta_2,bias_2)

        dot_qt = dot_q.transpose(1, 2)
        dot_pt = dot_p.transpose(1, 2)
        dot_xt = dot_x.transpose(1, 2)

        return torch.cat((dot_qt,dot_pt,dot_xt))

    
class ShootingBlockMN(nn.Module):
    def __init__(self, batch_y0=None, Kbar=None, Kbar_b=None, nonlinearity=None, only_random_initialization=False):
        super(ShootingBlockMN, self).__init__()

        self.k = batch_y0.size()[0]
        self.d = batch_y0.size()[2]

        mult_theta = 1.0
        mult_b = 1.0

        if Kbar is None:
            self.Kbar = 1./mult_theta*torch.eye(self.d**2)
        else:
            self.Kbar = 1./mult_theta*Kbar
        if Kbar_b is None:
            self.Kbar_b = 1./mult_b*torch.eye(self.d)
        else:
            self.Kbar_b = 1./mult_b*Kbar_b

        self.Kbar = self.Kbar.to(device)
        self.Kbar_b = self.Kbar_b.to(device)

        self.inv_Kbar_b = self.Kbar_b.inverse()
        self.inv_Kbar = self.Kbar.inverse()

        self.rand_mag_q = 0.1
        self.rand_mag_p = 0.1

        if only_random_initialization:
            # do a fully random initialization
            self.q_params = nn.Parameter(self.rand_mag_q * torch.randn_like(batch_y0))
            self.p_params = nn.Parameter(self.rand_mag_p * torch.randn([self.k, 1, self.d]))
        else:
            self.q_params = nn.Parameter(batch_y0 + self.rand_mag_q * torch.randn_like(batch_y0))
            self.p_params = nn.Parameter(torch.zeros(self.k, 1, self.d) + self.rand_mag_p * torch.randn([self.k, 1, self.d]))

        supported_nonlinearities = ['identity', 'relu', 'tanh', 'sigmoid']

        if nonlinearity is None:
            use_nonlinearity = 'identity'
        else:
            use_nonlinearity = nonlinearity.lower()

        if use_nonlinearity not in supported_nonlinearities:
            raise ValueError('Unsupported nonlinearity {}'.format(use_nonlinearity))

        if use_nonlinearity=='relu':
            self.nl = nn.functional.relu
            self.dnl = drelu
        elif use_nonlinearity=='tanh':
            self.nl = torch.tanh
            self.dnl = dtanh
        elif use_nonlinearity=='identity':
            self.nl = identity
            self.dnl = didentity
        elif use_nonlinearity=='sigmoid':
            self.nl = torch.sigmoid
            self.dnl = torch.sigmoid
        else:
            raise ValueError('Unknown nonlinearity {}'.format(use_nonlinearity))

        self.current_theta = None
        self.current_bias = None

    def get_norm_penalty(self):

        p = self.p_params.transpose(1,2)
        q = self.q_params.transpose(1,2)

        theta = self.compute_theta(q=q,p=p)
        bias = self.compute_bias(p=p)

        theta_penalty = torch.mm(theta.view(1,-1),torch.mm(self.inv_Kbar,theta.view(-1,1)))
        bias_penalty = torch.mm(bias.t(),torch.mm(self.inv_Kbar_b,bias))

        penalty = theta_penalty + bias_penalty
        return penalty

    def compute_theta(self,q,p):
        # Update theta according to the (p,q) equations
        # With Kbar = \bar M_\theta}^{-1}
        # \theta = Kbar(-\sum_i p_i \sigma(x_i)^T
        # computing the negative sum of the outer product

        #temp = -torch.bmm(p, self.nl(q.transpose(1, 2))).sum(dim=0)
        temp = -torch.bmm(p, self.nl(q.transpose(1, 2))).mean(dim=0)

        # now multiply it with the inverse of the regularizer (needs to be vectorized first and then back)
        theta = (torch.mm(self.Kbar, temp.view(-1,1))).view(temp.size())

        return theta

    def compute_bias(self,p):
        # Update bias according to the (p,q)
        # With Kbar_b = \bar M_b^{-1}
        # b = Kbar_b(-\sum_i p_i)
        # temp = torch.matmul(-p.squeeze().transpose(0, 1), torch.ones([self.k, 1],device=device))
        # keep in mind that by convention the vectors are stored as row vectors here, hence the transpose

        #temp = -p.sum(dim=0)
        temp = -p.mean(dim=0)

        bias = torch.mm(self.Kbar_b, temp)

        return bias

    def advect_x(self,x,theta,bias):
        """
        Forward equation which  is applied on the data. In principle similar to advect_q
        :param x:
        :param theta:
        :param bias:
        :return: \dot x_i = \theta \sigma(x_i) + b
        """
        temp_x = self.nl(x)
        return torch.matmul(theta, temp_x) + bias

    def advect_q(self,q,theta,bias):
        """
        Forward equation which  is applied on the data. In principle similar to advect_q
        :param x:
        :param theta:
        :param bias:
        :return: \dot q_i = \theta \sigma(q_i) + b
        """
        temp_q = self.nl(q)
        return torch.matmul(theta, temp_q) + bias

    def advect_p(self,p,q,theta,bias):
        theta = theta.detach()
        bias = bias.detach()
        compute = torch.sum(p*self.advect_q(q,theta,bias))

        xgrad, = autograd.grad(compute, q,
                               grad_outputs=compute.data.new(compute.shape).fill_(1),
                               create_graph=True,
                               retain_graph=True,
                               allow_unused=True)
        return -xgrad

    def compute_lagrangian(self,p,q,theta,bias):

        theta_penalty = torch.mm(theta.view(1,-1),torch.mm(self.inv_Kbar,theta.view(-1,1)))
        bias_penality = torch.mm(bias.t(),torch.mm(self.inv_Kbar_b,bias))

        kinetic_energy = 0.5*(theta_penalty + bias_penality)

        # this is really only how one propagates through the system given the parameterization
        potential_energy = torch.mean(p*self.advect_q(q,theta,bias))

        L = kinetic_energy - potential_energy

        return L

    def compute_gradients(self,x,p,q,old_theta,old_bias):

        nr_of_fixed_point_iterations = 5

        theta = torch.randn(2,2,requires_grad=True).to(device)
        bias = torch.randn(2,1,requires_grad=True).to(device)

        #theta = old_theta.detach().requires_grad_(True)
        #bias = old_bias.detach().requires_grad_(True)

        #print(theta)
        #print(bias)

        for n in range(nr_of_fixed_point_iterations):

            current_lagrangian = self.compute_lagrangian(p=p,q=q,theta=theta,bias=bias)

            theta_grad,bias_grad, = autograd.grad(current_lagrangian, (theta,bias),
                               grad_outputs=current_lagrangian.data.new(current_lagrangian.shape).fill_(1),
                               create_graph=True,
                               retain_graph=True,
                               allow_unused=True)

            theta = theta - theta_grad
            bias = bias - bias_grad

            #print(theta)
            #print(bias)

        # now that we have the bias and theta we can compute the evolution equation for p

        current_lagrangian = self.compute_lagrangian(p=p, q=q, theta=theta, bias=bias)

        dot_p, = autograd.grad(current_lagrangian, q,
                               grad_outputs=current_lagrangian.data.new(current_lagrangian.shape).fill_(1),
                               create_graph=True,
                               retain_graph=True,
                               allow_unused=True)

        # let't first compute the right hand side of the evolution equation for q and the same for x
        dot_x = self.advect_x(x, theta, bias)
        dot_q = self.advect_q(q, theta, bias)

        return dot_x,dot_p,dot_q



    def forward(self, t,input):
        """
        :param input: containing q, p, x
        :param batch_t: 1D tensor holding time points for evaluation
        :return: |batch_t| x minibatch x 1 x feature dimension
        """
        # q and p are K x 1 x feature dim tensors
        # x is a |batch| x 1 x feature dim tensor
        qt,pt,xt = input[:self.k, ...], input[self.k:2 * self.k, ...], input[2 * self.k:, ...]

        # let's first convert everything to column vectors (as this is closer to our notation)
        q = qt.transpose(1,2)
        p = pt.transpose(1,2)
        x = xt.transpose(1,2)

        # compute theta
        theta = self.compute_theta(q=q,p=p)

        # compute b
        bias = self.compute_bias(p=p)

        # let't first compute the right hand side of the evolution equation for q and the same for x
        dot_x_old = self.advect_x(x,theta,bias)
        dot_q_old = self.advect_q(q,theta,bias)

        # compute the advection equation for p
        # \dot p_i =  - [d\sigma(x_i)^T]\theta^T p_i
        # but here, d\sigma(x_i)^T = d\sigma(x_i) is a diagonal matrix composed with the derivative of the relu.

        # first compute \theta^T p_i

        dot_p_old =  self.advect_p(p,q,theta,bias)

        dot_x,dot_p,dot_q = self.compute_gradients(x=x,p=p,q=q,old_theta=theta,old_bias=bias)

        #theta_bis = torch.empty_like(theta).copy_(theta)
        #p_bis = torch.empty_like(p).copy_(p)
        #q_bis = torch.empty_like(q).copy_(q)
        #tTp = torch.matmul(theta_bis.t(), p_bis)
        # now compute element-wise sigma-prime xi
        #sigma_p = self.dnl(q_bis)
        # and multiply the two
        #dot_p_2 = -sigma_p * tTp
        #print("comparison",torch.sum((dot_p_2 - dot_p)**2))
        # as we transposed the vectors before we need to transpose on the way back
        dot_qt = dot_q.transpose(1, 2)
        dot_pt = dot_p.transpose(1, 2)
        dot_xt = dot_x.transpose(1, 2)

        return torch.cat((dot_qt,dot_pt,dot_xt))


class ShootingBlockMNModel1(nn.Module):
    def __init__(self, batch_y0=None, Kbar=None, Kbar_b=None, nonlinearity=None, only_random_initialization=False):
        super(ShootingBlockMNModel1, self).__init__()

        self.k = batch_y0.size()[0]
        self.d = batch_y0.size()[2]

        mult_theta = 1.0
        mult_b = 1.0

        if Kbar is None:
            self.Kbar = 1./mult_theta*torch.eye(self.d**2)
        else:
            self.Kbar = 1./mult_theta*Kbar
        if Kbar_b is None:
            self.Kbar_b = 1./mult_b*torch.eye(self.d)
        else:
            self.Kbar_b = 1./mult_b*Kbar_b

        self.Kbar = self.Kbar.to(device)
        self.Kbar_b = self.Kbar_b.to(device)

        self.inv_Kbar_b = self.Kbar_b.inverse()
        self.inv_Kbar = self.Kbar.inverse()

        self.rand_mag_q = 0.5
        self.rand_mag_p = 0.5

        if only_random_initialization:
            # do a fully random initialization
            self.q_params = nn.Parameter(self.rand_mag_q * torch.randn_like(batch_y0))
            self.p_params = nn.Parameter(self.rand_mag_p * torch.randn([self.k, 1, self.d]))
        else:
            self.q_params = nn.Parameter(batch_y0 + self.rand_mag_q * torch.randn_like(batch_y0))
            self.p_params = nn.Parameter(torch.zeros(self.k, 1, self.d) + self.rand_mag_p * torch.randn([self.k, 1, self.d]))

        supported_nonlinearities = ['identity', 'relu', 'tanh', 'sigmoid']

        if nonlinearity is None:
            use_nonlinearity = 'identity'
        else:
            use_nonlinearity = nonlinearity.lower()

        if use_nonlinearity not in supported_nonlinearities:
            raise ValueError('Unsupported nonlinearity {}'.format(use_nonlinearity))

        if use_nonlinearity=='relu':
            self.nl = nn.functional.relu
            self.dnl = drelu
        elif use_nonlinearity=='tanh':
            self.nl = torch.tanh
            self.dnl = dtanh
        elif use_nonlinearity=='identity':
            self.nl = identity
            self.dnl = didentity
        elif use_nonlinearity=='sigmoid':
            self.nl = torch.sigmoid
            self.dnl = torch.sigmoid
        else:
            raise ValueError('Unknown nonlinearity {}'.format(use_nonlinearity))

        self.current_theta = None
        self.current_bias = None

    def get_norm_penalty(self):

        p = self.p_params.transpose(1,2)
        q = self.q_params.transpose(1,2)

        return 0

    def compute_theta(self,p,q):
        theta = torch.zeros(2, 2, requires_grad=False).to(device)
        return theta

    def compute_bias(self,p):
        bias = torch.zeros(2, 1, requires_grad=False).to(device)
        return bias

    def advect_x(self,x,theta1,bias1,theta2,bias2):
        """
        Forward equation which  is applied on the data. In principle similar to advect_q
        :param x:
        :param theta:
        :param bias:
        :return: \dot x_i = \theta \sigma(x_i) + b
        """

        temp_x_inner = torch.matmul(theta2, x) + bias2
        temp_x = self.nl(temp_x_inner)
        return torch.matmul(theta1, temp_x) + bias1

    def advect_q(self,q,theta1,bias1,theta2,bias2):
        """
        Forward equation which  is applied on the data. In principle similar to advect_q
        :param x:
        :param theta:
        :param bias:
        :return: \dot q_i = \theta \sigma(q_i) + b
        """
        temp_q_inner = torch.matmul(theta2, q) + bias2
        temp_q = self.nl(temp_q_inner)
        return torch.matmul(theta1, temp_q) + bias1

    def compute_lagrangian(self,p,q,theta1,bias1,theta2,bias2):

        theta1_penalty = torch.mm(theta1.view(1,-1),torch.mm(self.inv_Kbar,theta1.view(-1,1)))
        bias1_penality = torch.mm(bias1.t(),torch.mm(self.inv_Kbar_b,bias1))

        #theta2_penalty = torch.mm(theta2.view(1, -1), torch.mm(self.inv_Kbar, theta2.view(-1, 1)))

        theta2_penalty = torch.mm((theta2-torch.eye(2)).view(1, -1), torch.mm(self.inv_Kbar, (theta2-torch.eye(2)).view(-1, 1)))

        #theta2_penalty = torch.norm((torch.mm(theta2,theta2.t())-torch.eye(2)))
        #theta2_penalty = ((torch.mm(theta2,theta2.t())-torch.eye(2))**2).sum()

        bias2_penality = torch.mm(bias2.t(), torch.mm(self.inv_Kbar_b, bias2))

        kinetic_energy = 0.5*(theta1_penalty + theta2_penalty + bias1_penality + bias2_penality)

        # this is really only how one propagates through the system given the parameterization
        potential_energy = torch.mean(p*self.advect_q(q,theta1,bias1,theta2,bias2))

        L = kinetic_energy - potential_energy

        return L

    def compute_gradients(self,x,p,q,old_theta=None,old_bias=None):


        theta1 = torch.randn(2,2,requires_grad=True).to(device)
        bias1 = torch.randn(2,1,requires_grad=True).to(device)

        theta2 = torch.randn(2, 2, requires_grad=True).to(device)
        bias2 = torch.randn(2, 1, requires_grad=True).to(device)

        #theta = old_theta.detach().requires_grad_(True)
        #bias = old_bias.detach().requires_grad_(True)

        #print(theta)
        #print(bias)

        vars = [theta1, theta2, bias1, bias2]
        learning_rate = 0.25
        nr_of_fixed_point_iterations = 20
        compute_simple_gradient_descent = True

        # optimizer = optim.Adam(vars, lr=learning_rate)
        optimizer = optim.SGD(vars, lr=learning_rate, momentum=0.9, nesterov=True)

        for n in range(nr_of_fixed_point_iterations):

            current_lagrangian = self.compute_lagrangian(p=p,q=q,theta1=theta1,bias1=bias1, theta2=theta2, bias2=bias2)

            theta_grad1,bias_grad1,theta_grad2,bias_grad2, = autograd.grad(current_lagrangian, (theta1,bias1,theta2,bias2),
                               grad_outputs=current_lagrangian.data.new(current_lagrangian.shape).fill_(1),
                               create_graph=True,
                               retain_graph=True,
                               allow_unused=True)

            if compute_simple_gradient_descent:

                theta1 = theta1 - learning_rate * theta_grad1
                bias1 = bias1 - learning_rate * bias_grad1

                theta2 = theta2 - learning_rate * theta_grad2
                bias2 = bias2 - learning_rate * bias_grad2

            else:

                theta1.grad = theta_grad1
                theta2.grad = theta_grad2
                bias1.grad = bias_grad1
                bias2.grad = bias_grad2

                optimizer.step()

            #print(theta)
            #print(bias)

        # now that we have the bias and theta we can compute the evolution equation for p

        current_lagrangian = self.compute_lagrangian(p=p, q=q, theta1=theta1, bias1=bias1, theta2=theta2, bias2=bias2)

        dot_p, = autograd.grad(current_lagrangian, q,
                               grad_outputs=current_lagrangian.data.new(current_lagrangian.shape).fill_(1),
                               create_graph=True,
                               retain_graph=True,
                               allow_unused=True)

        # let't first compute the right hand side of the evolution equation for q and the same for x
        dot_x = self.advect_x(x, theta1, bias1, theta2, bias2)
        dot_q = self.advect_q(q, theta1, bias1, theta2, bias2)

        return dot_x,dot_p,dot_q



    def forward(self, t,input):
        """
        :param input: containing q, p, x
        :param batch_t: 1D tensor holding time points for evaluation
        :return: |batch_t| x minibatch x 1 x feature dimension
        """
        # q and p are K x 1 x feature dim tensors
        # x is a |batch| x 1 x feature dim tensor
        qt,pt,xt = input[:self.k, ...], input[self.k:2 * self.k, ...], input[2 * self.k:, ...]

        # let's first convert everything to column vectors (as this is closer to our notation)
        q = qt.transpose(1,2)
        p = pt.transpose(1,2)
        x = xt.transpose(1,2)

        # compute the advection equation for p
        # \dot p_i =  - [d\sigma(x_i)^T]\theta^T p_i
        # but here, d\sigma(x_i)^T = d\sigma(x_i) is a diagonal matrix composed with the derivative of the relu.

        # first compute \theta^T p_i

        dot_x,dot_p,dot_q = self.compute_gradients(x=x,p=p,q=q)

        #theta_bis = torch.empty_like(theta).copy_(theta)
        #p_bis = torch.empty_like(p).copy_(p)
        #q_bis = torch.empty_like(q).copy_(q)
        #tTp = torch.matmul(theta_bis.t(), p_bis)
        # now compute element-wise sigma-prime xi
        #sigma_p = self.dnl(q_bis)
        # and multiply the two
        #dot_p_2 = -sigma_p * tTp
        #print("comparison",torch.sum((dot_p_2 - dot_p)**2))
        # as we transposed the vectors before we need to transpose on the way back
        dot_qt = dot_q.transpose(1, 2)
        dot_pt = dot_p.transpose(1, 2)
        dot_xt = dot_x.transpose(1, 2)

        return torch.cat((dot_qt,dot_pt,dot_xt))


class ShootingBlockMNModel2(nn.Module):
    def __init__(self, batch_y0=None, Kbar=None, Kbar_b=None, nonlinearity=None, only_random_initialization=False):
        super(ShootingBlockMNModel2, self).__init__()

        self.k = batch_y0.size()[0]
        self.d = batch_y0.size()[2]

        mult_theta = 1.0
        mult_b = 1.0

        if Kbar is None:
            self.Kbar = 1./mult_theta*torch.eye(self.d**2)
        else:
            self.Kbar = 1./mult_theta*Kbar
        if Kbar_b is None:
            self.Kbar_b = 1./mult_b*torch.eye(self.d)
        else:
            self.Kbar_b = 1./mult_b*Kbar_b

        self.Kbar = self.Kbar.to(device)
        self.Kbar_b = self.Kbar_b.to(device)

        self.inv_Kbar_b = self.Kbar_b.inverse()
        self.inv_Kbar = self.Kbar.inverse()

        self.rand_mag_q = 0.5
        self.rand_mag_p = 0.5

        if only_random_initialization:
            # do a fully random initialization
            self.q1_params = nn.Parameter(self.rand_mag_q * torch.randn_like(batch_y0))
            self.p1_params = nn.Parameter(self.rand_mag_p * torch.randn([self.k, 1, self.d]))
            self.q2_params = nn.Parameter(self.rand_mag_q * torch.randn_like(batch_y0))
            self.p2_params = nn.Parameter(self.rand_mag_p * torch.randn([self.k, 1, self.d]))
        else:
            self.q1_params = nn.Parameter(batch_y0 + self.rand_mag_q * torch.randn_like(batch_y0))
            self.p1_params = nn.Parameter(torch.zeros(self.k, 1, self.d) + self.rand_mag_p * torch.randn([self.k, 1, self.d]))
            self.q2_params = nn.Parameter(batch_y0 + self.rand_mag_q * torch.randn_like(batch_y0))
            self.p2_params = nn.Parameter(torch.zeros(self.k, 1, self.d) + self.rand_mag_p * torch.randn([self.k, 1, self.d]))

        # TODO: remove the following lines. Only put here so that the code does not break when it tries to access them to compute theta and bias
        self.q_params = self.q1_params
        self.p_params = self.p1_params

        supported_nonlinearities = ['identity', 'relu', 'tanh', 'sigmoid']

        if nonlinearity is None:
            use_nonlinearity = 'identity'
        else:
            use_nonlinearity = nonlinearity.lower()

        if use_nonlinearity not in supported_nonlinearities:
            raise ValueError('Unsupported nonlinearity {}'.format(use_nonlinearity))

        if use_nonlinearity=='relu':
            self.nl = nn.functional.relu
            self.dnl = drelu
        elif use_nonlinearity=='tanh':
            self.nl = torch.tanh
            self.dnl = dtanh
        elif use_nonlinearity=='identity':
            self.nl = identity
            self.dnl = didentity
        elif use_nonlinearity=='sigmoid':
            self.nl = torch.sigmoid
            self.dnl = torch.sigmoid
        else:
            raise ValueError('Unknown nonlinearity {}'.format(use_nonlinearity))

        self.current_theta = None
        self.current_bias = None

    def get_norm_penalty(self):

        p = self.p_params.transpose(1,2)
        q = self.q_params.transpose(1,2)

        return 0

    def compute_theta(self,p,q):
        theta = torch.zeros(2, 2, requires_grad=False).to(device)
        return theta

    def compute_bias(self,p):
        bias = torch.zeros(2, 1, requires_grad=False).to(device)
        return bias

    def advect_x1(self,x,theta,bias):
        """
        Forward equation which  is applied on the data. In principle similar to advect_q
        :param x:
        :param theta:
        :param bias:
        :return: \dot x_i = \theta \sigma(x_i) + b
        """

        return self.advect_q1(x,theta,bias)


    def advect_x2(self,x,theta,bias):
        """
        Forward equation which  is applied on the data. In principle similar to advect_q
        :param x:
        :param theta:
        :param bias:
        :return: \dot x_i = \theta \sigma(x_i) + b
        """

        return self.advect_q2(x,theta,bias)

    def advect_q1(self,q,theta,bias):
        """
        Forward equation which  is applied on the data. In principle similar to advect_q
        :param x:
        :param theta:
        :param bias:
        :return: \dot q_i = \theta \sigma(q_i) + b
        """
        temp_q = self.nl(q)
        return torch.matmul(theta, temp_q) + bias

    def advect_q2(self,q,theta,bias):
        """
        Forward equation which  is applied on the data. In principle similar to advect_q
        :param x:
        :param theta:
        :param bias:
        :return: \dot q_i = \theta \sigma(q_i) + b
        """
        temp_q = q # self.nl(q) (use the identity here)
        return torch.matmul(theta, temp_q) + bias

    def compute_lagrangian(self,p1,q1,p2,q2,theta1,bias1,theta2,bias2):

        theta1_penalty = torch.mm(theta1.view(1,-1),torch.mm(self.inv_Kbar,theta1.view(-1,1)))
        bias1_penality = torch.mm(bias1.t(),torch.mm(self.inv_Kbar_b,bias1))

        theta2_penalty = torch.mm(theta2.view(1, -1), torch.mm(self.inv_Kbar, theta2.view(-1, 1)))
        bias2_penality = torch.mm(bias2.t(), torch.mm(self.inv_Kbar_b, bias2))

        kinetic_energy = 0.5*(theta1_penalty + theta2_penalty + bias1_penality + bias2_penality)

        # this is really only how one propagates through the system given the parameterization
        potential_energy = torch.mean(p1*self.advect_q1(q2,theta1,bias1)) + torch.mean(p2*self.advect_q2(q1,theta2,bias2))

        L = kinetic_energy - potential_energy

        return L

    def compute_gradients(self,x1,x2,p1,q1,p2,q2,old_theta=None,old_bias=None):


        theta1 = torch.randn(2,2,requires_grad=True).to(device)
        bias1 = torch.randn(2,1,requires_grad=True).to(device)

        theta2 = torch.randn(2, 2, requires_grad=True).to(device)
        bias2 = torch.randn(2, 1, requires_grad=True).to(device)

        #theta = old_theta.detach().requires_grad_(True)
        #bias = old_bias.detach().requires_grad_(True)

        #print(theta)
        #print(bias)

        vars = [theta1, theta2, bias1, bias2]
        learning_rate = 0.5
        nr_of_fixed_point_iterations = 5


        for n in range(nr_of_fixed_point_iterations):

            current_lagrangian = self.compute_lagrangian(p1=p1,q1=q1,p2=p2,q2=q2,theta1=theta1,bias1=bias1, theta2=theta2, bias2=bias2)

            theta1_grad,bias1_grad,theta2_grad,bias2_grad, = autograd.grad(current_lagrangian, (theta1,bias1,theta2,bias2),
                               grad_outputs=current_lagrangian.data.new(current_lagrangian.shape).fill_(1),
                               create_graph=True,
                               retain_graph=True,
                               allow_unused=True)

            theta1 = theta1 - learning_rate * theta1_grad
            bias1 = bias1 - learning_rate * bias1_grad

            theta2 = theta2 - learning_rate * theta2_grad
            bias2 = bias2 - learning_rate * bias2_grad

            #print(theta)
            #print(bias)

        # now that we have the bias and theta we can compute the evolution equation for p1 and p2

        current_lagrangian = self.compute_lagrangian(p1=p1, q1=q1, p2=p2, q2=q2, theta1=theta1, bias1=bias1, theta2=theta2, bias2=bias2)

        dot_p1,dot_p2, = autograd.grad(current_lagrangian, (q1,q2),
                               grad_outputs=current_lagrangian.data.new(current_lagrangian.shape).fill_(1),
                               create_graph=True,
                               retain_graph=True,
                               allow_unused=True)

        # let't first compute the right hand side of the evolution equation for q and the same for x
        dot_x1 = self.advect_x1(x2, theta1, bias1)
        dot_x2 = self.advect_x2(x1, theta2, bias2)
        dot_q1 = self.advect_q1(q2,theta1, bias1)
        dot_q2 = self.advect_q2(q1,theta2, bias2)

        return dot_x1,dot_x2,dot_p1,dot_q1,dot_p2,dot_q2

    def assemble(self,q1,q2,p1,p2,x1,x2):
        return torch.cat((q1,q2,p1,p2,x1,x2))

    def disassemble(self, input,dim=0):

        if dim==0:
            q1 = input[:self.k,...]
            q2 = input[self.k:2*self.k,...]
            p1 = input[2*self.k:3*self.k,...]
            p2 = input[3*self.k:4*self.k,...]

            x12 = input[4*self.k:,...]
            # now subdivide the x's
            x12_nr = int((x12.shape[0])/2)
            x1 = x12[0:x12_nr,...]
            x2 = x12[x12_nr:,...]
        elif dim==1:
            q1 = input[:,:self.k, ...]
            q2 = input[:,self.k:2 * self.k, ...]
            p1 = input[:,2 * self.k:3 * self.k, ...]
            p2 = input[:,3 * self.k:4 * self.k, ...]

            x12 = input[:,4 * self.k:, ...]
            # now subdivide the x's
            x12_nr = int((x12.size()[1]) / 2)
            x1 = x12[:,0:x12_nr, ...]
            x2 = x12[:,x12_nr:, ...]
        else:
            raise ValueError('Do not know how to disassemble along dimension {}'.format(dim))

        return q1,q2,p1,p2,x1,x2

    def get_initial_condition(self,x):
        # initialize the second state of x with zero so far
        return self.assemble(q1=self.q1_params,q2=self.q2_params,p1=self.p1_params,p2=self.p2_params,x1=x,x2=torch.zeros_like(x))


    def forward(self, t,input):
        """
        :param input: containing q, p, x
        :param batch_t: 1D tensor holding time points for evaluation
        :return: |batch_t| x minibatch x 1 x feature dimension
        """
        # q and p are K x 1 x feature dim tensors
        # x is a |batch| x 1 x feature dim tensor
        q1t,q2t,p1t,p2t,x1t,x2t = self.disassemble(input)

        # let's first convert everything to column vectors (as this is closer to our notation)
        q1 = q1t.transpose(1,2)
        q2 = q2t.transpose(1,2)

        p1 = p1t.transpose(1,2)
        p2 = p2t.transpose(1, 2)

        x1 = x1t.transpose(1, 2)
        x2 = x2t.transpose(1,2)

        # compute the advection equation for p
        # \dot p_i =  - [d\sigma(x_i)^T]\theta^T p_i
        # but here, d\sigma(x_i)^T = d\sigma(x_i) is a diagonal matrix composed with the derivative of the relu.

        # first compute \theta^T p_i

        dot_x1,dot_x2,dot_p1,dot_p2,dot_q1,dot_q2 = self.compute_gradients(x1=x1,x2=x2,p1=p1,p2=p2,q1=q1,q2=q2)

        # as we transposed the vectors before we need to transpose on the way back
        dot_q1t = dot_q1.transpose(1, 2)
        dot_q2t = dot_q2.transpose(1, 2)

        dot_p1t = dot_p1.transpose(1, 2)
        dot_p2t = dot_p2.transpose(1, 2)

        dot_x1t = dot_x1.transpose(1, 2)
        dot_x2t = dot_x2.transpose(1, 2)

        return self.assemble(q1=dot_q1t,q2=dot_q2t,p1=dot_p1t,p2=dot_p2t,x1=dot_x1t,x2=dot_x2t)

if __name__ == '__main__':

    t_0 = time.time()
    ii = 0

    is_odenet = args.network == 'odenet'

    is_higher_order_model = True

    if is_odenet:
        #func = ODEFunc()
        func = ODESimpleFuncWithIssue()
        optimizer = optim.RMSprop(func.parameters(), lr=1e-3)
        #optimizer = optim.SGD(func.parameters(), lr=2.5e-3, momentum=0.5, dampening=0.0, nesterov=True)

    else:

        # parameters to play with for shooting
        K = args.nr_of_particles

        batch_y0, batch_t, batch_y = get_batch(K)
        #shooting = ShootingBlock2(batch_y0,only_random_initialization=True,nonlinearity=args.nonlinearity)
        #shooting = ShootingBlockMN(batch_y0,only_random_initialization=True,nonlinearity=args.nonlinearity)
        #shooting = ShootingBlockMNModel1(batch_y0, only_random_initialization=True, nonlinearity=args.nonlinearity)
        shooting = ShootingBlockMNModel2(batch_y0, only_random_initialization=True, nonlinearity=args.nonlinearity)

        shooting = shooting.to(device)

        #optimizer = optim.RMSprop(shooting.parameters(), lr=5e-3)
        optimizer = optim.Adam(shooting.parameters(), lr=2.5e-2)
        #optimizer = optim.SGD(shooting.parameters(), lr=2.5e-3, momentum=0.5, dampening=0.0, nesterov=True)
        #optimizer = custom_optimizers.LBFGS_LS(shooting.parameters())

    all_thetas = None
    all_real_thetas = None
    all_bs = None

    validate_with_batch_data = not args.validate_with_long_range
    validate_with_random_batch_each_time = False

    if validate_with_batch_data:
        if not validate_with_random_batch_each_time:
            val_batch_y0, val_batch_t, val_batch_y = get_batch(batch_size=args.batch_validation_size)

    for itr in range(0, args.niters):

        optimizer.zero_grad()
        batch_y0, batch_t, batch_y = get_batch()

        if itr % args.test_freq == 0:
            if itr % args.viz_freq == 0:

                if not is_odenet:
                    theta_np = (shooting.compute_theta(q=shooting.q_params.transpose(1,2),p=shooting.p_params.transpose(1,2))).view(1,-1).detach().cpu().numpy()
                    bias_np = (shooting.compute_bias(p=shooting.p_params.transpose(1,2))).view(1,-1).detach().cpu().numpy()

                    if all_thetas is None:
                        all_thetas = theta_np
                    else:
                        all_thetas = np.append(all_thetas,theta_np,axis=0)

                    c_true_A = true_A.view(1,-1).detach().cpu().numpy()
                    if all_real_thetas is None:
                        all_real_thetas = c_true_A
                    else:
                        all_real_thetas = np.append(all_real_thetas,c_true_A,axis=0)

                    if all_bs is None:
                        all_bs = bias_np
                    else:
                        all_bs = np.append(all_bs,bias_np,axis=0)

                visualize_batch(batch_t,batch_y,thetas=all_thetas,real_thetas=all_real_thetas,bias=all_bs)

        if is_odenet:
            pred_y = odeint(func, batch_y0, batch_t, method=args.method, atol=atol, rtol=rtol, options=options)
        else:

            if is_higher_order_model:
                z_0 = shooting.get_initial_condition(x=batch_y0)
            else:
                q = (shooting.q_params)
                p = (shooting.p_params)
                z_0 = torch.cat((q,p,batch_y0))

            temp_pred_y = odeint(shooting,z_0 , batch_t, method=args.method, atol=atol, rtol=rtol, options=options)

            # we are actually only interested in the prediction of the batch itself (not the parameterization)
            if is_higher_order_model:
                _,_,_,_,pred_y,_ = shooting.disassemble(temp_pred_y,dim=1)
            else:
                pred_y = temp_pred_y[:, 2 * K:, ...]

        # todo: figure out wht the norm penality does not work
        if args.sim_norm == 'l1':
            loss = torch.mean(torch.abs(pred_y - batch_y))
        elif args.sim_norm == 'l2':
            loss = torch.mean(torch.norm(pred_y-batch_y,dim=3))
        else:
            raise ValueError('Unknown norm {}.'.format(args.sim_norm))

        if not is_odenet:
            loss = loss + args.shooting_norm_penalty * shooting.get_norm_penalty()

        loss.backward()

        optimizer.step()

        if itr % args.test_freq == 0:
            # we need to keep computing the gradient here as the forward model may require gradient computations

            if validate_with_batch_data:
                if validate_with_random_batch_each_time:
                    # draw new batch. This will be like a moving target for the evaluation
                    val_batch_y0, val_batch_t, val_batch_y = get_batch()
                val_y0 = val_batch_y0
                val_t = val_batch_t
                val_y = val_batch_y
            else:
                val_y0 = true_y0.unsqueeze(dim=0)
                val_t = t
                val_y = true_y.unsqueeze(dim=1)

            if is_odenet:
                val_pred_y = odeint(func, val_y0, val_t, method=args.method, atol=atol, rtol=rtol, options=options)

                if args.sim_norm=='l1':
                    loss = torch.mean(torch.abs(val_pred_y - val_y))
                elif args.sim_norm=='l2':
                    loss = torch.mean(torch.norm(val_pred_y - val_y, dim=3))
                else:
                    raise ValueError('Unknown norm {}.'.format(args.sim_norm))

                print('Iter {:04d} | Total Loss {:.6f}'.format(itr, loss.item()))

                if itr % args.viz_freq == 0:
                    visualize(val_y, val_pred_y, val_t, func, ii, is_odenet=is_odenet, is_higher_order_model=is_higher_order_model)
                    ii += 1

            else:
                ### time clock
                t_1 = time.time()

                print("time",t_1 - t_0)
                t_0 = t_1

                if is_higher_order_model:
                    val_z_0 = shooting.get_initial_condition(x=val_y0)
                else:
                    q = (shooting.q_params)
                    p = (shooting.p_params)
                    val_z_0 = torch.cat((q, p, val_y0))

                temp_pred_y = odeint(shooting, val_z_0, val_t, method=args.method, atol=atol, rtol=rtol,
                                     options=options)

                # we are actually only interested in the prediction of the batch itself (not the parameterization)
                if is_higher_order_model:
                    _, _, _, _, val_pred_y, _ = shooting.disassemble(temp_pred_y,dim=1)
                else:
                    val_pred_y = temp_pred_y[:, 2 * K:, ...]

                if args.sim_norm=='l1':
                    loss = torch.mean(torch.abs(val_pred_y - val_y))
                elif args.sim_norm=='l2':
                    loss = torch.mean(torch.norm(val_pred_y - val_y, dim=3))
                else:
                    raise ValueError('Unknown norm {}.'.format(args.sim_norm))

                loss = loss + args.shooting_norm_penalty * shooting.get_norm_penalty()

                print('Iter {:04d} | Total Loss {:.6f}'.format(itr, loss.item()))

                if itr % args.viz_freq == 0:
                    visualize(val_y, val_pred_y, val_t, shooting, ii, is_odenet=is_odenet, is_higher_order_model=is_higher_order_model)
                    ii += 1


        end = time.time()
