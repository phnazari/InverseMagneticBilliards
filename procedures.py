import os
import torch
from pathlib import Path

from ml.models import ReLuModel
from dynamics import Orbit

from helper import Training, Minimizer, Diagnostics
from conf import MODELDIR, GRAPHICSDIR, TODAY
from physics import Action
from util import batch_jacobian, get_todays_graphics_dir, mkdir, grad, get_approx_type


def training_procedure(**kwargs):
    training = Training(**kwargs)
    training.train()
    training.plot_loss()
    training.generate_readme(kwargs.get("a"), kwargs.get("b"), kwargs.get(
        "mu"), kwargs.get("k"), kwargs.get("num_epochs"), kwargs.get("batch_size"))


def minimization_procedure(a, b, k, mu, n_epochs=100, dir=None, exact_deriv=True, helicity="pos", exact_G=False, frequency=(1, 1), show=True, plot_points=True):
    # load model
    filename = os.path.join(MODELDIR, dir, "model.pth")

    mode = dir.split("/")[-3]
    subdir = dir.split("/")[-2]

    print(f"LOADING model from {filename}")
    G_hat = ReLuModel(input_dim=2, output_dim=1)
    G_hat.load_state_dict(torch.load(filename)["model_state_dict"])

    # choose generating fn
    if exact_G:
        # if not exact_deriv and mode != "classic":
        #    print("Error: Exact G only available for classic case")
        #    exit(1)
        G = Action(a, b, k, mu, mode=mode).exact
    else:
        G = G_hat

    assert frequency[0] < frequency[1], "m must be less than n"

    # initialize an orbit
    orbit = Orbit(a=a,
                  b=b,
                  k=k,
                  mu=mu,
                  frequency=frequency,
                  mode=mode,
                  helicity=helicity,
                  init="uniform")

    # initialize and execute minimizer
    minimizer = Minimizer(a,
                          b,
                          k,
                          mu,
                          orbit,
                          G,
                          mode=mode,
                          exact_deriv=exact_deriv,
                          n_epochs=n_epochs,
                          frequency=frequency)

    # minimize action
    minimizer.minimize(exact_deriv=exact_deriv)

    # initialize diagnostics
    diagnostics = Diagnostics(a,
                              b,
                              k,
                              mu,
                              orbit=orbit,
                              mode=mode,
                              subdir=subdir)

    # check if the frequency is correct
    observed_frequency = diagnostics.frequency()

    print(
        f"Expected Frequency: (m, n) = {frequency}. Observed Frequency: (m, n) = {observed_frequency}")

    # plot the orbit
    img_dir = get_todays_graphics_dir(mode, subdir, add=str(frequency))

    if mode == "classic":
        # build up dirname
        approx_type = get_approx_type(exact_G, exact_deriv)

        # img_dir = os.path.join(img_dir, "exact" if exact_G else "approx")
        img_dir = os.path.join(img_dir, approx_type)
        mkdir(img_dir)

    #orbit.plot(img_dir=img_dir, show=show)

    #diagnostics.error(G, show=show, img_dir=img_dir)

    # diagnostics.landscape(grad(G_hat, norm=True), n=150)
    #diagnostics.landscape(G,
    #                      img_dir=img_dir,
    #                      show=show,
    #                      plot_points=plot_points)

    # plot the gradient analysis
    # diagnostics.landscape(minimizer.discrete_action.grad_norm,
    #                      img_dir=img_dir,
    #                      show=show,
    #                      plot_points=plot_points,
    #                      filename="landsacpe_grad_norm.png")

    # grad_loss = torch.linalg.norm(batch_jacobian(
    #    self.discrete_action, self.orbit.phi))

    # plot the minimization loss
    #minimizer.plot(img_dir=img_dir, show=show)

    # plot the gradient analysis
    # diagnostics.derivative(dir)

    # plot whether the reflection_law is satisfied
    d1s, d2s = diagnostics.physics(img_dir=img_dir, show=show)

    return d1s, d2s
