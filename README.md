
# Motor Simulation

### Efficient, Scalable, 3D Induction Motor Simulation

This project builds on [this 2D TEAM30 model and solver](https://github.com/Wells-Group/TEAM30) by Jørgen S. Dokken and Igor A. Baratta, making use of their [3D mesh generation](./generate_team30_meshes_3D.py) and adapting their magnetostatic formulation. Full detail of this project can be found in the report.

### Dependencies
- Python 3.11 (may work with earlier versions)
- MPI
- PETSc with Hypre
- FENICSx

``` bash
# Example Usage
python3 generate_team30_meshes_3D.py --three --res 0.005
python3 solve_3D_time.py
```

https://github.com/falcon75/motor-simulation/assets/39418626/f3b3410d-8a4d-48a7-8bdb-d514ef65693a

https://github.com/falcon75/motor-simulation/assets/39418626/59dd7949-152b-483f-9948-e90caf282bfd
