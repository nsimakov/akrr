# Directory with Dockers for nwchem

The nwchem Docker has 2 "versions"

This one is based off of an existing nwchem docker from Dockerhub: nwchemorg/nwchem-qc:latest

The Dockerfile is just adding a few things to work with akrr, namely adding a script that runs the appropriate amount of processes with mpirun.

So you should be able to just build the Docker image right away.

For running the docker, you do need to specify some extra things to ensure that everything runs appropriately

```bash
docker run --shm-size 8g --cap-add=SYS_PTRACE <nwchem docker>

```
The other docker directory has the nwchem version used on ubhpc.


## Building Docker Container

```bash
docker build -f ./docker/enzo/spack_builder.dockerfile -t spack-ubuntu-builder:enzo .
docker run -it --rm  --shm-size=4g spack-ubuntu-builder:enzo

docker build -f ./docker/enzo/spack_installer.dockerfile -t nsimakov/appker:enzo .

docker run -it --rm  --shm-size=4g nsimakov/appker:enzo
docker run -it --rm  --shm-size=4g nsimakov/appker:enzo -c gcc_openblas_openmpi
docker run -it --rm  --shm-size=4g nsimakov/appker:enzo -c icc_mkl_impi
docker run -it --rm  --shm-size=4g nsimakov/appker:enzo -view nwchem_icc_mkl_impi_x86_64

sudo singularity build ../enzo.simg docker-daemon://nsimakov/appker:enzo
docker push nsimakov/appker:enzo
```
