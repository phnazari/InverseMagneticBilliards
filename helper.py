import os
import torch
from torch.utils.data import DataLoader
import numpy as np
from pathlib import Path
from datetime import datetime
from matplotlib import pyplot as plt

from data.datasets import ReturnMapDataset, ImplicitUDataset, GeneratingFunctionDataset
from physics import DiscreteAction
from dynamics import Orbit
from ml.training import train_model
from ml.models import ReLuModel
from util import batch_jacobian, angle_between, sigmoid_scaled
from settings import MODELDIR, DATADIR, GRAPHICSDIR


class Training:
    def __init__(self, num_epochs=100, cs="Custom", type="ReturnMap", train_dataset="train50k.npy"):
        self.num_epochs = num_epochs
        self.cs = cs
        self.type = type
        self.train_dataset = train_dataset

        self.model = None
        self.training_loss = 0
        self.validation_loss = 0
        self.jac_loss = 0

        self.today = datetime.today().strftime("%Y-%m-%d")

    def train(self):
        # relevant directories
        data_dir = os.path.join(DATADIR, self.type, self.cs)
        model_dir = os.path.join(MODELDIR, self.type, self.cs, self.today)
        Path(model_dir).mkdir(parents=True, exist_ok=True)

        if self.type == "ReturnMap":
            Dataset = ReturnMapDataset
            input_dim = 2
            output_dim = 2
        elif self.type == "ImplicitU":
            Dataset = ImplicitUDataset
            input_dim = 2
            output_dim = 1
        elif self.type == "GeneratingFunction":
            Dataset = GeneratingFunctionDataset
            input_dim = 2
            output_dim = 1
        else:
            return

        # datasets
        train_dataset = Dataset(os.path.join(data_dir, self.train_dataset))
        validation_dataset = Dataset(os.path.join(data_dir, "validate10k.npy"))

        # model
        model = ReLuModel(input_dim=input_dim, output_dim=output_dim)

        # train
        model, training_loss, validation_loss = train_model(model,
                                                            train_dataset,
                                                            validation_dataset,
                                                            torch.nn.MSELoss(),
                                                            self.num_epochs,
                                                            dir=model_dir)

        self.model = model
        self.training_loss = training_loss
        self.validation_loss = validation_loss

    def plot_loss(self):
        graphics_dir = os.path.join(
            GRAPHICSDIR, self.type, self.cs, self.today)
        Path(graphics_dir).mkdir(parents=True, exist_ok=True)
        graphic_filename = os.path.join(graphics_dir, "loss.png")

        fig = plt.figure()
        plt.suptitle(self.type)
        plt.plot(self.training_loss, label="train", c="navy")
        plt.plot(self.validation_loss, label="validation", c="pink")
        plt.yscale("log")
        plt.xscale("log")
        plt.legend(loc="upper right")
        plt.savefig(graphic_filename)

        plt.show()


class Minimizer:
    def __init__(self, orbit, action_fn, n_epochs=50, frequency=(), *args, **kwargs):
        self.orbit = orbit
        self.n_epochs = n_epochs
        self.optimizer = torch.optim.Adam([orbit.phi], lr=1e-2)
        self.action_fn = action_fn
        self.frequency = frequency
        self.m, self.n = frequency

        self.discrete_action = DiscreteAction(action_fn, orbit=orbit, **kwargs)

        self.grad_losses = []
        self.m_losses = []

    def minimize(self):
        grad_losses = []
        m_losses = []
        for epoch in range(self.n_epochs):
            self.optimizer.zero_grad()

            # calculate the gradient loss
            grad_loss = torch.linalg.norm(
                batch_jacobian(self.discrete_action, self.orbit.phi))
            # print(batch_jacobian(self.discrete_action, self.orbit.phi).shape)
            # grad_loss = batch_jacobian(self.discrete_action, self.orbit.phi).sum()

            if len(self.frequency) != 0:
                phi_centered = self.orbit.phi - self.orbit.phi[0]
                diff = phi_centered - torch.roll(phi_centered, -1)
                m_approx = torch.sum(sigmoid_scaled(diff, alpha=10))
                m_loss = (m_approx - self.m)**2

            else:
                m_loss = torch.tensor([0], requires_grad=True)

            total_loss = grad_loss

            # do a gradient descent step
            total_loss.backward()
            self.optimizer.step()

            # since we have only learned the model in the interval [2, 2pi], we move the point there
            with torch.no_grad():
                self.orbit.phi.remainder_(2*np.pi)

            # save losses
            grad_losses.append(grad_loss.item())
            m_losses.append(m_loss)

            # log the result
            print('Epoch: {}, Loss: {:.4f}'.format(epoch+1, grad_loss))

        self.grad_losses = torch.tensor(grad_losses)
        self.m_losses = torch.tensor(m_losses)

    def plot(self):
        fig = plt.figure()
        fig.suptitle("Minimization Loss")
        plt.xlabel("epoch")
        plt.ylabel("loss")
        plt.plot(self.grad_losses)
        # if len(self.m_losses) > 0:
        #    plt.plot(self.m_losses)

        plt.show()


class Diagnostics:
    def __init__(self, orbit=None, cs="Custom", type="ReturnMap", *args, **kwargs):
        self.orbit = orbit

        self.cs = cs
        self.type = type

    def reflection_angle(self, unit="rad"):
        us = self.orbit.get_u()
        tangents = self.orbit.table.tangent(self.orbit.phi).T

        einfallswinkel = angle_between(us, tangents)
        ausfallswinkel = angle_between(torch.roll(tangents, -1, dims=0), us)

        if unit == "deg":
            einfallswinkel = einfallswinkel/2/np.pi*360
            ausfallswinkel = ausfallswinkel/2/np.pi*360

        return einfallswinkel, ausfallswinkel

    def reflection(self, unit="deg"):
        einfallswinkel, ausfallswinkel = self.reflection_angle(unit=unit)
        error = torch.abs(100*(einfallswinkel - ausfallswinkel)/einfallswinkel)

        fig = plt.figure()
        fig.suptitle("Error in Reflection Law")
        plt.xlabel("Point")
        plt.ylabel("Error [%]")
        # plt.errorbar(np.arange(len(error)), error.detach(), fmt=".")
        plt.plot(error.detach())
        # plt.yscale("log")

        plt.show()

    def frequency(self):
        phi_centered = self.orbit.phi - self.orbit.phi[0]

        diff = phi_centered - torch.roll(phi_centered, -1)
        m = torch.sum(diff > 0).item()
        n = len(self.orbit)

        # m_approx = torch.sum(torch.nn.Sigmoid()(360*diff)).item()

        return (m, n)

    def gradient(self, a, b, dir):
        # TODO: when training model, save the gradient loss. Then we just need to load it here
        # TODO: can remove the action_fn as an initialization variable if this is implemented

        model_dir = os.path.join(MODELDIR, dir)

        train_settings = torch.load(os.path.join(model_dir, "model.pth"))

        model = ReLuModel(input_dim=2, output_dim=1)

        data_dir = os.path.join(DATADIR, self.type, self.cs)

        validation_dataset = GeneratingFunctionDataset(
            os.path.join(data_dir, "validate10k.npy"))
        validation_loader = DataLoader(
            validation_dataset, batch_size=1024, shuffle=True, pin_memory=True)

        jac_diff_losses = []
        jac_emp_losses = []
        jac_ex_losses = []

        for epoch in range(1, train_settings["epochs"] + 1):

            epoch_jac_diff_loss = 0.0
            epoch_jac_emp_loss = 0.0
            epoch_jac_ex_loss = 0.0

            for inputs, targets in validation_loader:
                epoch_settings = torch.load(os.path.join(
                    model_dir, "epochs", str(epoch), "model.pth"))

                model.load_state_dict(epoch_settings["model_state_dict"])

                # calculate empirical jacobian
                jac_emp = torch.squeeze(
                    batch_jacobian(model.model, inputs))

                # calculate exact jacobian
                orbit = Orbit(a, b)
                orbit.set_phi(inputs)

                discrete_action = DiscreteAction(None, orbit, exact=True)
                jac_ex = batch_jacobian(discrete_action, inputs)

                # compute jacobian loss
                new_jac_diff_loss = torch.linalg.norm(
                    jac_emp - jac_ex, ord="fro").pow(2).item()

                new_jac_ex_loss = torch.linalg.norm(
                    jac_ex, ord="fro").pow(2).item()
                new_jac_emp_loss = torch.linalg.norm(
                    jac_emp, ord="fro").pow(2).item()

                # save epoch loss
                epoch_jac_diff_loss += new_jac_diff_loss
                epoch_jac_emp_loss += new_jac_emp_loss
                epoch_jac_ex_loss += new_jac_ex_loss

            jac_diff_loss = epoch_jac_diff_loss / len(validation_dataset)
            jac_emp_loss = epoch_jac_emp_loss / len(validation_dataset)
            jac_ex_loss = epoch_jac_ex_loss / len(validation_dataset)
            jac_diff_losses.append(jac_diff_loss)
            jac_emp_losses.append(jac_emp_loss)
            jac_ex_losses.append(jac_ex_loss)

            print("Epoch: {}. Diff Loss: {:.4f}. Emp Loss:{:.4f}. Ex Loss: {:.4f}".format(
                epoch, jac_diff_loss, jac_emp_loss, jac_ex_loss))

        fig = plt.figure()
        fig.suptitle("Gradient Errors")
        plt.xlabel("Epoch")
        plt.ylabel("Error")
        plt.plot(jac_diff_losses, label="difference")
        plt.plot(jac_emp_losses, label="empirical")
        plt.plot(jac_ex_losses, label="exact")
        plt.legend()

        plt.show()
