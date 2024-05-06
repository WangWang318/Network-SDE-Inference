import numpy as np
import torch
from torch import nn
from torch.functional import F
from torch.optim import Adam
from torch_geometric.nn import MetaLayer, MessagePassing
from torch.nn import Sequential as Seq, Linear as Lin, ReLU, Softplus
from torch.autograd import Variable, grad

"""
Structure: SDIweighted
SDIweighted is a network structure for identification of stochastic dynamics on weighted network

Layers weights' std: set for different dynamics

"""
class SDIw(MessagePassing):
    def __init__(self, model, n_f, msg_dim, ndim, delt_t, weights, hidden=50, aggr='add', flow='source_to_target'):

        """If flow is 'source_to_target', the relation is (j,i), means information is passed from x_j to x_i'"""
        super(SDIw, self).__init__(aggr=aggr, flow=flow)
        self.msg_fnc_ret = Seq(
            Lin(2,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,msg_dim)
        )
        for layer in self.msg_fnc_ret:
            if isinstance(layer,nn.Linear):
                param_shape = layer.weight.shape
                torch.nn.init.normal_(layer.weight, mean=0.0, std = 1e-1)
                
            self.msg_fnc_ant = Seq(
            Lin(2,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,msg_dim)
        )
        for layer in self.msg_fnc_ant:
            if isinstance(layer,nn.Linear):
                param_shape = layer.weight.shape
                torch.nn.init.normal_(layer.weight, mean=0.0, std = 1e-1)


        self.node_fnc_x = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,1)
        )
        for layer in self.node_fnc_x:
            if isinstance(layer,nn.Linear):
                param_shape = layer.weight.shape
                torch.nn.init.normal_(layer.weight, mean=0.0, std=1e-1)
        
        self.node_fnc_y = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,1)
        )
        for layer in self.node_fnc_y:
            if isinstance(layer,nn.Linear):
                param_shape = layer.weight.shape
                torch.nn.init.normal_(layer.weight, mean=0.0, std=1e-1)
        
        self.node_fnc_z = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,1)
        )
        if model == 'HR':
            for layer in self.node_fnc_z:
                if isinstance(layer,nn.Linear):
                    param_shape = layer.weight.shape
                    torch.nn.init.normal_(layer.weight, mean=0.0, std=1e-3)
        else:
            for layer in self.node_fnc_z:
                if isinstance(layer,nn.Linear):
                    param_shape = layer.weight.shape
                    torch.nn.init.normal_(layer.weight, mean=0.0, std=1e-1)
        
        self.stochastic_x = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,1),
            Softplus()
        )
        for layer in self.stochastic_x:
            if isinstance(layer,nn.Linear):
                param_shape = layer.weight.shape
                torch.nn.init.normal_(layer.weight, mean=0.0, std=1e-4)
        
        self.stochastic_y = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,1),
            Softplus()
        )
        for layer in self.stochastic_y:
            if isinstance(layer,nn.Linear):
                param_shape = layer.weight.shape
                torch.nn.init.normal_(layer.weight, mean=0.0, std=1e-3)

        
        self.stochastic_z = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,1),
            Softplus()
        )
        for layer in self.stochastic_z:
            if isinstance(layer,nn.Linear):
                param_shape = layer.weight.shape
                torch.nn.init.normal_(layer.weight, mean=0.0, std=1e-3)

    def forward(self, x, edge_index):
        # x has shape [N, number_of_features]
        # edge_index has shape [2,E]
        x = x
        return self.propagate(edge_index, x=x)

    def message(self, x_i, x_j):

        tmp = torch.cat([x_i[:,0], x_j[:,0]])
        tmp = tmp.reshape(2,-1)
        tmp = tmp.t()
        Len = int(x_j[:,0].shape[0])/int(self.weights.shape[0])
        w = self.weights.repeat(int(Len),1)
        w = w.clone().detach()
        w = w.to(torch.float32)
        w = w.cuda()
#         tmpW = torch.cat([x_j[:,0],w[:,0].float()])
#         tmpW = tmpW.reshape(2,-1)
#         tmpW = tmpW.t()
        return self.msg_fnc_ret(tmp)*w[:,0].reshape(-1,1)+self.msg_fnc_ant(tmp)*w[:,1].reshape(-1,1)
    

    def update(self, aggr_out, x=None):
        if self.ndim==1:
            fx = self.node_fnc_x(x)
            dxdt = fx+aggr_out
            x_update = x+dxdt*self.delt_t
            x_mean = x+dxdt*self.delt_t
            x_var = self.stochastic_x(x)
            return torch.distributions.Normal(x_mean, x_var),x_update,dxdt
        elif self.ndim==2:
            fx = self.node_fnc_x(x)
            fy = self.node_fnc_y(x)
            dxdt = fx+aggr_out
            dydt = fy
            x_update = x[:,0].reshape(-1,1)+dxdt*self.delt_t
            y_update = x[:,1].reshape(-1,1)+dydt*self.delt_t
            x_mean = x[:,0].reshape(-1,1)+dxdt*self.delt_t
            y_mean = x[:,1].reshape(-1,1)+dydt*self.delt_t
            x_var = self.stochastic_x(x)
            y_var = self.stochastic_y(x)
            return torch.distributions.Normal(x_mean, x_var),torch.distributions.Normal(y_mean, y_var),x_update,y_update
        elif self.ndim==3:
            fx = self.node_fnc_x(x)
            fy = self.node_fnc_y(x)
            fz = self.node_fnc_z(x)
            dxdt = fx+aggr_out
            dydt = fy
            dzdt = fz
            x_update = x[:,0].reshape(-1,1)+dxdt*self.delt_t
            y_update = x[:,1].reshape(-1,1)+dydt*self.delt_t
            z_update = x[:,2].reshape(-1,1)+dzdt*self.delt_t
            x_mean = x[:,0].reshape(-1,1)+dxdt*self.delt_t
            y_mean = x[:,1].reshape(-1,1)+dydt*self.delt_t
            z_mean = x[:,2].reshape(-1,1)+dzdt*self.delt_t
            x_var = self.stochastic_x(x)
            y_var = self.stochastic_y(x)
            z_var = self.stochastic_z(x)
            return torch.distributions.Normal(x_mean, x_var),torch.distributions.Normal(y_mean, y_var),torch.distributions.Normal(z_mean, z_var),x_update,y_update,z_update


class SDIweighted(SDIw):
     def __init__(
 		self, model, n_f, msg_dim, ndim, delt_t,weights,
 		edge_index, aggr='add', hidden=50, nt=1):
            super(SDIweighted, self).__init__(model, n_f, msg_dim, ndim, delt_t, weights, hidden=hidden, aggr=aggr)
            self.delt_t = delt_t
            self.nt = nt
            self.edge_index = edge_index
            self.ndim = ndim
            self.weights = weights
    
     def SDI_weighted(self, g, augment=False, augmentation=3):
            #x is [n, n_f]f
            x = g.x
            ndim = self.ndim
            if augment:
                augmentation = torch.randn(1, ndim)*augmentation
                augmentation = augmentation.repeat(len(x), 1).to(x.device)
                x = x.index_add(1, torch.arange(ndim).to(x.device), augmentation)
        
            edge_index = g.edge_index
            return self.propagate(
                    edge_index, size=(x.size(0), x.size(0)),
                    x=x)

     def loss(self, g, **kwargs):
            if self.ndim==1:
                out_dist,xUpdate,dxdt = self.SDI_weighted(g)
                neg_log_likelihood = -out_dist.log_prob(g.y[:,0].reshape(-1,1))
                mseloss1 = torch.abs(g.y[:,0].reshape(-1,1)-xUpdate)
                mseloss2 = torch.abs(g.y[:,1].reshape(-1,1)-dxdt)
                return torch.sum(neg_log_likelihood)*0.1+torch.sum(mseloss1)+torch.sum(mseloss2)
            if self.ndim==2:
                out_dist_x,out_dist_y,xUpdate,yUpdate = self.SDI_weighted(g)
                neg_log_likelihood_x = -out_dist_x.log_prob(g.y[:,0].reshape(-1,1))
                neg_log_likelihood_y = -out_dist_y.log_prob(g.y[:,1].reshape(-1,1))
                return torch.sum(neg_log_likelihood_x)+torch.sum(neg_log_likelihood_y)
            if self.ndim==3:
                out_dist_x,out_dist_y,out_dist_z,xUpdate,yUpdate,zUpdate = self.SDI_weighted(g)
                neg_log_likelihood_x = -out_dist_x.log_prob(g.y[:,0].reshape(-1,1))
                neg_log_likelihood_y = -out_dist_y.log_prob(g.y[:,1].reshape(-1,1))
                neg_log_likelihood_z = -out_dist_z.log_prob(g.y[:,2].reshape(-1,1))
                return torch.mean(neg_log_likelihood_x)+torch.mean(neg_log_likelihood_y)+torch.mean(neg_log_likelihood_z)
     def sample_trajectories(self, g, **kwargs):
            if self.ndim == 1:
                out_dist,xUpdate,dxdt = self.SDI_weighted(g)
                xUpdate_sample = out_dist.sample()
                return xUpdate_sample
            if self.ndim == 2:
                out_dist_x,out_dist_y,xUpdate,yUpdate = self.SDI_weighted(g)
                xUpdate_sample = out_dist_x.sample()
                yUpdate_sample = out_dist_y.sample()
                return xUpdate_sample, yUpdate_sample
            if self.ndim == 3:
                out_dist_x,out_dist_y,out_dist_z,xUpdate,yUpdate,zUpdate = self.SDI_weighted(g)
                xUpdate_sample = out_dist_x.sample()
                yUpdate_sample = out_dist_y.sample()
                zUpdate_sample = out_dist_z.sample()
                return xUpdate_sample, yUpdate_sample, zUpdate_sample

     def average_trajectories(self, g, **kwargs):
            if self.ndim == 1:
                out_dist,xUpdate,dxdt = self.SDI_weighted(g)
                return xUpdate
            if self.ndim == 2:
                out_dist_x,out_dist_y,xUpdate,yUpdate = self.SDI_weighted(g)
                return xUpdate, yUpdate
            if self.ndim == 3:
                out_dist_x,out_dist_y,out_dist_z,xUpdate,yUpdate,zUpdate = self.SDI_weighted(g)
                return xUpdate, yUpdate, zUpdate
            

class wNGN(MessagePassing):
    def __init__(self, n_f, msg_dim, ndim, delt_t, weights, hidden=50, aggr='add', flow='source_to_target'):

        """If flow is 'source_to_target', the relation is (j,i), means information is passed from x_j to x_i'"""
        super(wNGN, self).__init__(aggr=aggr, flow=flow)
        self.msg_fnc_ret = Seq(
            Lin(3,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,msg_dim)
        )
        
        self.msg_fnc_ant = Seq(
            Lin(3,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,msg_dim)
        )

        self.msg_fnc_euc = Seq(
            Lin(2,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,msg_dim)
        )
        

        self.node_fnc_x = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,1)
        )
        
        self.node_fnc_y = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,1)
        )
        
        self.node_fnc_z = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,1)
        )

    def forward(self, x, edge_index):
        # x has shape [N, number_of_features]
        # edge_index has shape [2,E]
        x = x
        return self.propagate(edge_index, x=x)

    def message(self, x_i, x_j):
        tmp = torch.cat([x_i[:,0], x_j[:,0]])
        tmp = tmp.reshape(2,-1)
        tmp = tmp.t()
        Len = int(x_i[:,0].shape[0])/int(self.weights.shape[0])
        w = self.weights.repeat(int(Len),1)
        w = w.clone().detach()
        w = w.to(torch.float32)
        w = w.cuda()

        tmp1 = torch.cat([tmp,w[:,0].reshape(-1,1)],dim=1)
        tmp2 = torch.cat([tmp,w[:,1].reshape(-1,1)],dim=1)
        tmp3 = torch.cat([tmp[:,1].reshape(-1,1),w[:,2].reshape(-1,1)],dim=1)
        return self.msg_fnc_ret(tmp1)+ self.msg_fnc_ant(tmp2) + self.msg_fnc_euc(tmp3)


        #return self.msg_fnc_ret(tmp)*w[:,0].reshape(-1,1) + self.msg_fnc_ant(tmp)*w[:,1].reshape(-1,1)

    def update(self, aggr_out, x=None):
        if self.ndim==1:
            fx = self.node_fnc_x(x)
            dxdt = fx+aggr_out
            return torch.cat([x+dxdt*self.delt_t,dxdt], dim=1)
            #dxdt = fx+aggr_out
            #return torch.cat([x+dxdt*self.delt_t,dxdt], dim=1)
        elif self.ndim==2:
            fx = self.node_fnc_x(x)
            fy = self.node_fnc_y(x)
            dxdt = fx+aggr_out
            dydt = fy
            x_update = x[:,0].reshape(-1,1)+dxdt*self.delt_t
            y_update = x[:,1].reshape(-1,1)+dydt*self.delt_t
            return torch.cat([x_update,y_update,dxdt,dydt], dim=1)
        elif self.ndim==3:
            fx = self.node_fnc_x(x)
            fy = self.node_fnc_y(x)
            fz = self.node_fnc_z(x)
            dxdt = fx+aggr_out
            dydt = fy
            dzdt = fz
            x_update = x[:,0].reshape(-1,1)+dxdt*self.delt_t
            y_update = x[:,1].reshape(-1,1)+dydt*self.delt_t
            z_update = x[:,2].reshape(-1,1)+dzdt*self.delt_t
            return torch.cat([x_update,y_update,z_update,dxdt,dydt,dzdt], dim=1)


class wNeuG(wNGN):
     def __init__(
 		self, n_f, msg_dim, ndim, delt_t, weights,
 		edge_index, aggr='add', hidden=50, nt=1):
            super(wNeuG, self).__init__(n_f, msg_dim, ndim, delt_t, weights, hidden=hidden, aggr=aggr)
            self.delt_t = delt_t
            self.nt = nt
            self.edge_index = edge_index
            self.ndim = ndim
            self.weights = weights
    
     def prediction(self, g, augment=False, augmentation=3):
            #x is [n, n_f]f
            x = g.x
            ndim = self.ndim
            if augment:
                augmentation = torch.randn(1, ndim)*augmentation
                augmentation = augmentation.repeat(len(x), 1).to(x.device)
                x = x.index_add(1, torch.arange(ndim).to(x.device), augmentation)
        
            edge_index = g.edge_index
            return self.propagate(
                    edge_index, size=(x.size(0), x.size(0)),
                    x=x)

    
     def loss(self, g,square=False, **kwargs):
            if square:
                return torch.sum((g.y[:,0] - self.prediction(g)[:,0])**2)
            else:
                return torch.sum(torch.abs(g.y - self.prediction(g)))
            
     def average_trajectories(self, g, **kwargs):
            if self.ndim == 1:
                xUpdate = self.prediction(g)[:,0].reshape(-1,1)
                return xUpdate
            if self.ndim == 2:
                out_dist_x,out_dist_y,xUpdate,yUpdate = self.SDI_weighted(g)
                return xUpdate, yUpdate
            if self.ndim == 3:
                out_dist_x,out_dist_y,out_dist_z,xUpdate,yUpdate,zUpdate = self.SDI_weighted(g)
                return xUpdate, yUpdate, zUpdate
            



class swNGN(MessagePassing):
    def __init__(self, n_f, msg_dim, ndim, delt_t, weights, hidden=50, aggr='add', flow='source_to_target'):

        """If flow is 'source_to_target', the relation is (j,i), means information is passed from x_j to x_i'"""
        super(swNGN, self).__init__(aggr=aggr, flow=flow)
        self.msg_fnc_ret = Seq(
            Lin(2,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,msg_dim)
        )
        
        self.msg_fnc_ant = Seq(
            Lin(2,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,msg_dim)
        )
        

        self.node_fnc_x = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,1)
        )
        
        self.node_fnc_y = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,1)
        )
        
        self.node_fnc_z = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,1)
        )

    def forward(self, x, edge_index):
        # x has shape [N, number_of_features]
        # edge_index has shape [2,E]
        x = x
        return self.propagate(edge_index, x=x)

    def message(self, x_i, x_j):
        tmp = torch.cat([x_i[:,0], x_j[:,0]])
        tmp = tmp.reshape(2,-1)
        tmp = tmp.t()
        Len = int(x_i[:,0].shape[0])/int(self.weights.shape[0])
        w = self.weights.repeat(int(Len),1)
        w = w.clone().detach()
        w = w.to(torch.float32)
        w = w.cuda()

        return self.msg_fnc_ret(tmp)*w[:,0].reshape(-1,1) + self.msg_fnc_ant(tmp)*w[:,1].reshape(-1,1)

    def update(self, aggr_out, x=None):
        if self.ndim==1:
            #fx = self.node_fnc_x(x)
            #dxdt = fx+aggr_out
            dxdt = aggr_out
            return torch.cat([dxdt*self.delt_t,dxdt], dim=1)
        elif self.ndim==2:
            fx = self.node_fnc_x(x)
            fy = self.node_fnc_y(x)
            dxdt = fx+aggr_out
            dydt = fy
            x_update = x[:,0].reshape(-1,1)+dxdt*self.delt_t
            y_update = x[:,1].reshape(-1,1)+dydt*self.delt_t
            return torch.cat([x_update,y_update,dxdt,dydt], dim=1)
        elif self.ndim==3:
            fx = self.node_fnc_x(x)
            fy = self.node_fnc_y(x)
            fz = self.node_fnc_z(x)
            dxdt = fx+aggr_out
            dydt = fy
            dzdt = fz
            x_update = x[:,0].reshape(-1,1)+dxdt*self.delt_t
            y_update = x[:,1].reshape(-1,1)+dydt*self.delt_t
            z_update = x[:,2].reshape(-1,1)+dzdt*self.delt_t
            return torch.cat([x_update,y_update,z_update,dxdt,dydt,dzdt], dim=1)


class swNeuG(swNGN):
     def __init__(
 		self, n_f, msg_dim, ndim, delt_t, weights,
 		edge_index, aggr='add', hidden=50, nt=1):
            super(swNeuG, self).__init__(n_f, msg_dim, ndim, delt_t, weights, hidden=hidden, aggr=aggr)
            self.delt_t = delt_t
            self.nt = nt
            self.edge_index = edge_index
            self.ndim = ndim
            self.weights = weights
    
     def prediction(self, g, augment=False, augmentation=3):
            #x is [n, n_f]f
            x = g.x
            ndim = self.ndim
            if augment:
                augmentation = torch.randn(1, ndim)*augmentation
                augmentation = augmentation.repeat(len(x), 1).to(x.device)
                x = x.index_add(1, torch.arange(ndim).to(x.device), augmentation)
        
            edge_index = g.edge_index
            return self.propagate(
                    edge_index, size=(x.size(0), x.size(0)),
                    x=x)

    
     def loss(self, g,square=False, **kwargs):
            if square:
                return torch.sum((g.y[:,0] - self.prediction(g)[:,0])**2)
            else:
                return torch.sum(torch.abs(g.y[:,0] - self.prediction(g)[:,0]))
            
     def average_trajectories(self, g, **kwargs):
            if self.ndim == 1:
                xUpdate = self.prediction(g)[:,0].reshape(-1,1)
                return xUpdate
            if self.ndim == 2:
                out_dist_x,out_dist_y,xUpdate,yUpdate = self.SDI_weighted(g)
                return xUpdate, yUpdate
            if self.ndim == 3:
                out_dist_x,out_dist_y,out_dist_z,xUpdate,yUpdate,zUpdate = self.SDI_weighted(g)
                return xUpdate, yUpdate, zUpdate



class InwNGN(MessagePassing):
    def __init__(self, n_f, msg_dim, ndim, weights, hidden=50, aggr='add', flow='source_to_target'):

        """If flow is 'source_to_target', the relation is (j,i), means information is passed from x_j to x_i'"""
        super(InwNGN, self).__init__(aggr=aggr, flow=flow)
        self.msg_fnc_ret = Seq(
            Lin(2,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,msg_dim)
        )
        
        self.msg_fnc_ant = Seq(
            Lin(2,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,msg_dim)
        )

        self.msg_fnc_euc = Seq(
            Lin(2,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,msg_dim)
        )
        

        self.node_fnc_x = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,1)
        )
        
        self.node_fnc_y = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,1)
        )
        
        self.node_fnc_z = Seq(
            Lin(n_f,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,1)
        )

        self.time_scale = Seq(
            Lin(1,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,hidden),
            ReLU(),
            Lin(hidden,1)
        )

    def forward(self, x, edge_index):
        # x has shape [N, number_of_features]
        # edge_index has shape [2,E]
        x = x
        return self.propagate(edge_index, x=x)

    def message(self, x_i, x_j):
        tmp = torch.cat([x_i[:,0], x_j[:,0]])
        tmp = tmp.reshape(2,-1)
        tmp = tmp.t()
        Len = int(tmp.shape[0])/int(self.weights.shape[0])
        w = self.weights.repeat(int(Len),1)
        w = w.clone().detach()
        w = w.to(torch.float32)
        w = w.cuda()

        #Tmp = tmp[:,1]-tmp[:,0]

        tmp1 = torch.cat([tmp[:,1].reshape(-1,1),w[:,0].reshape(-1,1)],dim=1)
        tmp2 = torch.cat([tmp[:,1].reshape(-1,1),w[:,1].reshape(-1,1)],dim=1)
        tmp3 = torch.cat([tmp[:,1].reshape(-1,1),w[:,2].reshape(-1,1)],dim=1)
        w1 = torch.zeros_like(w)
        w1[w != 0] = 1
        w1 = w1.to(torch.float32)
        w1 = w1.cuda()
        return self.msg_fnc_ret(tmp1)*w1[:,0].reshape(-1,1)+ self.msg_fnc_ant(tmp2)*w1[:,1].reshape(-1,1) + self.msg_fnc_euc(tmp3)*w1[:,2].reshape(-1,1)

        # tmp1 = torch.cat([tmp[:,1].reshape(-1,1),w[:,0].reshape(-1,1)],dim=1)
        # tmp2 = torch.cat([tmp[:,1].reshape(-1,1),w[:,1].reshape(-1,1)],dim=1)
        # tmp3 = torch.cat([tmp[:,1].reshape(-1,1),w[:,2].reshape(-1,1)],dim=1)
        # return self.msg_fnc_ret(tmp1)+ self.msg_fnc_ant(tmp2) + self.msg_fnc_euc(tmp3)

        #return self.msg_fnc_ret(tmp)*w[:,0].reshape(-1,1) + self.msg_fnc_ant(tmp)*w[:,1].reshape(-1,1) + self.msg_fnc_euc(tmp)*w[:,2].reshape(-1,1)

    def update(self, aggr_out, x=None):
        if self.ndim==1:
            t1 = np.full(int(x.shape[0]),1, dtype=int)
            t2 = np.full(int(x.shape[0]),3, dtype=int)
            t3 = np.full(int(x.shape[0]),6, dtype=int)
            t4 = np.full(int(x.shape[0]),9, dtype=int)
            # #t1 = t1.clone().detach()
            t1 = torch.from_numpy(t1).float()
            t1 = t1.cuda()
            # #t2 = t2.clone().detach()
            t2 = torch.from_numpy(t2).float()
            t2 = t2.cuda()
            # #t3 = t3.clone().detach()
            t3 = torch.from_numpy(t3).float()
            t3 = t3.cuda()
            # #t4 = t4.clone().detach()
            t4 = torch.from_numpy(t4).float()
            t4 = t4.cuda()

            # all1 = torch.cat([x,aggr_out,t1.reshape(-1,1)],dim=1)
            # all2 = torch.cat([x,aggr_out,t2.reshape(-1,1)],dim=1)
            # all3 = torch.cat([x,aggr_out,t3.reshape(-1,1)],dim=1)
            # all4 = torch.cat([x,aggr_out,t4.reshape(-1,1)],dim=1)
            T1 = self.time_scale(t1.reshape(-1,1))
            T2 = self.time_scale(t2.reshape(-1,1))
            T3 = self.time_scale(t3.reshape(-1,1))
            T4 = self.time_scale(t4.reshape(-1,1))



            fx = self.node_fnc_x(x)
            dxdt = fx+aggr_out


            # tmpx = torch.cat([x,aggr_out],dim=1)
            # dxdt = self.node_fnc_x(tmpx)


            y1 = dxdt*T1
            y2 = dxdt*T2
            y3 = dxdt*T3
            y4 = dxdt*T4
            return torch.cat([y1.reshape(-1,160),y2.reshape(-1,160),y3.reshape(-1,160),y4.reshape(-1,160)], dim=1)
            #dxdt = fx+aggr_out
            #return torch.cat([x+dxdt*self.delt_t,dxdt], dim=1)

            
        # only consider 1-dimensional situation

        elif self.ndim==2:
            fx = self.node_fnc_x(x)
            fy = self.node_fnc_y(x)
            dxdt = fx+aggr_out
            dydt = fy
            x_update = x[:,0].reshape(-1,1)+dxdt*self.delt_t
            y_update = x[:,1].reshape(-1,1)+dydt*self.delt_t
            return torch.cat([x_update,y_update,dxdt,dydt], dim=1)
        elif self.ndim==3:
            fx = self.node_fnc_x(x)
            fy = self.node_fnc_y(x)
            fz = self.node_fnc_z(x)
            dxdt = fx+aggr_out
            dydt = fy
            dzdt = fz
            x_update = x[:,0].reshape(-1,1)+dxdt*self.delt_t
            y_update = x[:,1].reshape(-1,1)+dydt*self.delt_t
            z_update = x[:,2].reshape(-1,1)+dzdt*self.delt_t
            return torch.cat([x_update,y_update,z_update,dxdt,dydt,dzdt], dim=1)


class InwNeuG(InwNGN):
     def __init__(
 		self, n_f, msg_dim, ndim, weights,
 		edge_index, aggr='add', hidden=50, nt=1):
            super(InwNeuG, self).__init__(n_f, msg_dim, ndim, weights, hidden=hidden, aggr=aggr)
            self.nt = nt
            self.edge_index = edge_index
            self.ndim = ndim
            self.weights = weights
    
     def prediction(self, g, augment=False, augmentation=3):
            #x is [n, n_f]f
            x = g.x
            ndim = self.ndim
            if augment:
                augmentation = torch.randn(1, ndim)*augmentation
                augmentation = augmentation.repeat(len(x), 1).to(x.device)
                x = x.index_add(1, torch.arange(ndim).to(x.device), augmentation)
        
            edge_index = g.edge_index
            return self.propagate(
                    edge_index, size=(x.size(0), x.size(0)),
                    x=x)

    
     def loss(self, g,square=False, **kwargs):
            if square:
                return torch.sum((g.y - self.prediction(g))**2)
            else:
                return torch.sum(torch.abs(g.y.reshape(-1,640) - self.prediction(g)))
            
     def average_trajectories(self, g, **kwargs):
            if self.ndim == 1:
                xUpdate = self.prediction(g)
                return xUpdate

