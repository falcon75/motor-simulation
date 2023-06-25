
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

https://github.com/falcon75/motor-simulation/assets/39418626/7e075b13-f643-46c0-977f-a87003e95345


https://github.com/falcon75/motor-simulation/assets/39418626/97d08b0d-a462-4f03-9267-e7fd72e7dd9b
