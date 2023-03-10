import os
from procedures import training_procedure, minimization_procedure
from data.generate import generate_dataset


if __name__ == "__main__":
    # table properties
    a = 2
    b = 1

    # magnetic properties
    mu = 1/5

    cs = "custom"
    mode = "classic"
    type = "generatingfunction"
    subdir = "ellipse"

    execs = ["minimize"]
    for exec in execs:
        if exec == "generate":
            generate_dataset(a,
                             b,
                             mu,
                             100000,
                             "train100k.npy",
                             cs=cs,
                             subdir=subdir,
                             mode=mode,
                             type=type)
        elif exec == "train":
            training_procedure(a=a,
                               b=b,
                               mu=mu,
                               num_epochs=256,
                               type=type,
                               cs=cs,
                               subdir=subdir,
                               mode=mode,
                               train_dataset="train100k.npy",
                               save=True,
                               batch_size=512)
        elif exec == "minimize":
            minimization_procedure(
                a,
                b,
                mu,
                exact=True,
                frequency=(2, 5),
                helicity="pos",
                n_epochs=2000,
                dir=os.path.join(type, cs, mode, subdir, "2023-03-14")
            )
