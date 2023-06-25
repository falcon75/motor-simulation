# Copyright (C) 2021-2022 Jørgen S. Dokken and Igor A. Baratta
#
# SPDX-License-Identifier:    MIT

from typing import Dict

import numpy as np
from dolfinx import fem
from dolfinx import cpp

from generate_team30_meshes_3D import model_parameters

def update_current_density(J_0: fem.Function, omega: float, t: float, ct: cpp.mesh.MeshTags_int32,
                           currents: Dict[np.int32, Dict[str, float]]):
    """
    Given a DG-0 scalar field J_0, update it to be alpha*J*cos(omega*t + beta)
    in the domains with copper windings
    """
    J_0.x.array[:] = 0
    for domain, values in currents.items():
        _cells = ct.find(domain)
        J_0.x.array[_cells] = np.full(len(_cells), model_parameters["J"] * values["alpha"]
                                      * np.cos(omega * t + values["beta"]))
