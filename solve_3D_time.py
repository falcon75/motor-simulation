import numpy as np
import pandas as pd
from petsc4py import PETSc
from mpi4py import MPI

from dolfinx import fem, io
from dolfinx.common import Timer, timing
from dolfinx.cpp.fem.petsc import (discrete_gradient,
                                interpolation_matrix)
from dolfinx.fem import (Function, FunctionSpace, VectorFunctionSpace,
                        form, locate_dofs_topological, petsc)
from dolfinx.mesh import locate_entities_boundary
from dolfinx.io import VTXWriter
from ufl import (TestFunction, TrialFunction, FiniteElement, VectorElement, 
                curl, dx, inner, cross, SpatialCoordinate, Measure)

from utils import update_current_density
from generate_team30_meshes_3D import domain_parameters, model_parameters



# ## -- Parameters -- ##

num_phases = 1
steps_per_phase = 100
freq = model_parameters["freq"]
T = num_phases * 1 / freq
dt_ = 1.0 / steps_per_phase * 1 / freq

mu_0 = model_parameters["mu_0"]
omega_J = 2 * np.pi * freq

single_phase = False
mesh_dir = "meshes"
ext = "single" if single_phase else "three"
fname = f"{mesh_dir}/{ext}_phase3D"

output = True
write_stats = True

domains, currents = domain_parameters(single_phase)
degree = 1


## -- Load Mesh -- ##

with io.XDMFFile(MPI.COMM_WORLD, f"{fname}.xdmf", "r") as xdmf:
    mesh = xdmf.read_mesh(name="Grid")
    ct = xdmf.read_meshtags(mesh, name="Grid")

tdim = mesh.topology.dim
mesh.topology.create_connectivity(tdim - 1, 0)
with io.XDMFFile(MPI.COMM_WORLD, f"{fname}_facets.xdmf", "r") as xdmf:
    ft = xdmf.read_meshtags(mesh, name="Grid")



## -- Functions and Spaces -- ##

x = SpatialCoordinate(mesh)
cell = mesh.ufl_cell()
dt = fem.Constant(mesh, dt_)

DG0 = fem.FunctionSpace(mesh, ("DG", 0))
mu_R = fem.Function(DG0)
sigma = fem.Function(DG0)
density = fem.Function(DG0)

for (material, domain) in domains.items():
    for marker in domain:
        cells = ct.find(marker)
        mu_R.x.array[cells] = model_parameters["mu_r"][material]
        p = model_parameters["sigma"][material]
        sigma.x.array[cells] = model_parameters["sigma"][material]
        density.x.array[cells] = model_parameters["densities"][material]

Omega_n = domains["Cu"] + domains["Stator"] + domains["Air"] + domains["AirGap"]
Omega_c = domains["Rotor"] + domains["Al"]

dx = Measure("dx", domain=mesh, subdomain_data=ct)
nedelec_elem = FiniteElement("N1curl", cell, degree)
A_space = FunctionSpace(mesh, nedelec_elem)

A = TrialFunction(A_space)
v = TestFunction(A_space)

A_prev = fem.Function(A_space)
J0z = fem.Function(DG0)

ndofs = A_space.dofmap.index_map.size_global * A_space.dofmap.index_map_bs



## -- Weak Form -- ##

a = dt * 1 / mu_R * inner(curl(A), curl(v)) * dx(Omega_c + Omega_n)
a += sigma * mu_0 * inner(A, v) * dx(Omega_c + Omega_n)
a = form(a)

L = dt * mu_0 * J0z * v[2] * dx(Omega_n)
L += sigma * mu_0 * inner(A_prev, v) * dx(Omega_c + Omega_n)
L = form(L)



## -- BCs and Assembly -- ##

def boundary_marker(x):
    return np.full(x.shape[1], True)

boundary_facets = locate_entities_boundary(mesh, dim=tdim - 1, marker=boundary_marker)
boundary_dofs = locate_dofs_topological(A_space, entity_dim=tdim - 1, entities=boundary_facets)

zeroA = fem.Function(A_space)
zeroA.x.array[:] = 0
bc = fem.dirichletbc(zeroA, boundary_dofs)

A_out = Function(A_space)
A = petsc.assemble_matrix(a, bcs=[bc])
A.assemble()
b = fem.petsc.create_vector(L)



## --- AMS Solver Setup --- ##

ksp = PETSc.KSP().create(mesh.comm)
ksp.setOptionsPrefix(f"ksp_{id(ksp)}")
ksp.setOperators(A)
pc = ksp.getPC()
opts = PETSc.Options()

ams_options = {"pc_hypre_ams_cycle_type": 1,
                    "pc_hypre_ams_tol": 1e-8,
                    "ksp_atol": 1e-10, "ksp_rtol": 1e-8,
                    "ksp_initial_guess_nonzero": True,
                    "ksp_type": "gmres",
                    "ksp_norm_type": "unpreconditioned"
                    }

pc.setType("hypre")
pc.setHYPREType("ams")

option_prefix = ksp.getOptionsPrefix()
opts.prefixPush(option_prefix)
for option, value in ams_options.items():
    opts[option] = value
opts.prefixPop()

W = FunctionSpace(mesh, ("CG", degree))
G = discrete_gradient(W._cpp_object, A_space._cpp_object)
G.assemble()

X = VectorElement("CG", mesh.ufl_cell(), degree)
Q = FunctionSpace(mesh, X)
Pi = interpolation_matrix(Q._cpp_object, A_space._cpp_object)
Pi.assemble()

pc.setHYPREDiscreteGradient(G)
pc.setHYPRESetInterpolations(dim=mesh.geometry.dim, ND_Pi_Full=Pi)

ksp.setFromOptions()
pc.setUp()
ksp.setUp()



## -- Time simulation -- ##

W1 = VectorFunctionSpace(mesh, ("Discontinuous Lagrange", degree))

if output:
    B_output = Function(W1)
    B_vtx = VTXWriter(mesh.comm, f"output_3D_B.bp", [B_output._cpp_object])

t = 0
results = []

for i in range(num_phases * steps_per_phase):

    A_out.x.array[:] = 0
    t += dt_

    ## -- Update Current and Re-assemble LHS -- ##
    update_current_density(J0z, omega_J, t, ct, currents)
    with b.localForm() as loc_b:
            loc_b.set(0)
    b = petsc.assemble_vector(L)
    petsc.apply_lifting(b, [a], bcs=[[bc]])
    b.ghostUpdate(addv=PETSc.InsertMode.ADD, mode=PETSc.ScatterMode.REVERSE)
    petsc.set_bc(b, [bc])
    max_b = max(b.array)

    ## -- Solve -- ##
    with Timer(f"solve"):
        ksp.solve(b, A_out.vector)
        A_out.x.scatter_forward()

    ## -- Compute B -- ##
    el_B = VectorElement("DG", cell, max(degree - 1, 1))
    VB = fem.FunctionSpace(mesh, el_B)
    B = fem.Function(VB)
    B_3D = curl(A_out)
    Bexpr = fem.Expression(B_3D, VB.element.interpolation_points())
    B.interpolate(Bexpr)

    ## -- Compute F -- ##
    E = - (A_out - A_prev) / dt
    f = cross(sigma * E, B)
    F = fem.Function(VB)
    fexpr = fem.Expression(f, VB.element.interpolation_points())
    F.interpolate(fexpr)
    
    A_prev.x.array[:] = A_out.x.array # Set A_prev
    
    ## -- Write B -- ##
    if output:
        B_output_1 = Function(W1)
        B_output_1.interpolate(B)
        B_output.x.array[:] = B_output_1.x.array[:]
        B_vtx.write(t)

    min_cond = model_parameters['sigma']['Cu']
    stats = {"step": i, "ndofs": ndofs, "min_cond": min_cond, "solve_time": timing(f"solve")[1],
              "iterations": ksp.its, "reason": ksp.getConvergedReason(), 
              "norm_A": np.linalg.norm(A_out.x.array), "max_b": max_b}
    print(stats)
    results.append(stats)
    
    if write_stats:
        df = pd.DataFrame.from_dict(results)
        df.to_csv(f'output_3D_stats.csv', mode="w")
