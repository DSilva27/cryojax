import itertools

import jax
import jax.numpy as jnp
import numpy as np
import pytest
from jax import config
from jaxtyping import install_import_hook

from cryojax.image import downsample_with_fourier_cropping


with install_import_hook("cryojax", "typeguard.typechecked"):
    from cryojax.constants import (
        get_tabulated_scattering_factor_parameters,
        peng1996_scattering_factor_parameter_table,
    )
    from cryojax.coordinates import make_coordinate_grid
    from cryojax.data import read_atoms_from_pdb
    from cryojax.image import ifftn
    from cryojax.simulator import (
        FourierVoxelGridPotential,
        GaussianMixtureAtomicPotential,
        RealVoxelGridPotential,
    )


config.update("jax_enable_x64", True)


def test_fourier_vs_real_voxel_potential_agreement(sample_pdb_path):
    """
    Integration test ensuring that the VoxelGrid classes
    produce comparable electron densities when loaded from PDB.
    """
    n_voxels_per_side = (128, 128, 128)
    voxel_size = 0.5

    # Load the PDB file
    atom_positions, atom_elements = read_atoms_from_pdb(sample_pdb_path)
    # Load scattering factor parameters and build atomistic potential
    atom_a_factors, atom_b_factors = get_tabulated_scattering_factor_parameters(
        atom_elements, peng1996_scattering_factor_parameter_table
    )
    atomic_potential = GaussianMixtureAtomicPotential(
        atom_positions, atom_a_factors, atom_b_factors
    )
    # Build the grid
    coordinate_grid = make_coordinate_grid(n_voxels_per_side, voxel_size)
    potential_as_real_voxel_grid = atomic_potential.as_real_voxel_grid(coordinate_grid)
    fourier_potential = FourierVoxelGridPotential.from_real_voxel_grid(
        potential_as_real_voxel_grid, voxel_size
    )
    # Since Voxelgrid is in Frequency space by default, we have to first
    # transform back into real space.
    fvg_real = ifftn(jnp.fft.ifftshift(fourier_potential.fourier_voxel_grid)).real

    vg = RealVoxelGridPotential.from_real_voxel_grid(
        potential_as_real_voxel_grid, voxel_size
    )

    np.testing.assert_allclose(fvg_real, vg.real_voxel_grid, atol=1e-12)


def test_downsampled_voxel_potential_agreement(sample_pdb_path):
    """Integration test ensuring that rasterized voxel grids roughly
    agree with downsampled versions.
    """
    # Parameters for rasterization
    shape = (64, 64, 64)
    voxel_size = 0.5
    # Downsampling parameters
    downsampling_factor = 1.05
    downsampled_shape = (
        int(shape[0] / downsampling_factor),
        int(shape[1] / downsampling_factor),
        int(shape[2] / downsampling_factor),
    )
    downsampled_voxel_size = voxel_size * downsampling_factor
    # Create coordinate grid at each specification
    low_resolution_coordinate_grid = make_coordinate_grid(
        downsampled_shape, downsampled_voxel_size
    )
    high_resolution_coordinate_grid = make_coordinate_grid(shape, voxel_size)
    # Load the PDB file
    atom_positions, atom_elements = read_atoms_from_pdb(sample_pdb_path)
    # Load scattering factor parameters and build atomistic potential
    atom_a_factors, atom_b_factors = get_tabulated_scattering_factor_parameters(
        atom_elements, peng1996_scattering_factor_parameter_table
    )
    atomic_potential = GaussianMixtureAtomicPotential(
        atom_positions, atom_a_factors, atom_b_factors
    )
    # Build the grids
    low_resolution_potential_grid = atomic_potential.as_real_voxel_grid(
        low_resolution_coordinate_grid
    )
    high_resolution_potential_grid = atomic_potential.as_real_voxel_grid(
        high_resolution_coordinate_grid
    )
    downsampled_potential_grid = downsample_with_fourier_cropping(
        high_resolution_potential_grid, downsampling_factor
    )

    assert low_resolution_potential_grid.shape == downsampled_potential_grid.shape


class TestBuildRealSpaceVoxelsFromAtoms:
    @pytest.mark.parametrize("largest_atom", range(0, 3))
    def test_maxima_are_in_right_positions(self, toy_gaussian_cloud, largest_atom):
        """
        Test that the maxima of the potential are in the correct positions.
        """
        (
            atom_positions,
            ff_a,
            ff_b,
            n_voxels_per_side,
            voxel_size,
        ) = toy_gaussian_cloud
        ff_a = ff_a.at[largest_atom].add(1.0)
        coordinate_grid = make_coordinate_grid(n_voxels_per_side, voxel_size)

        # Build the potential
        atomic_potential = GaussianMixtureAtomicPotential(atom_positions, ff_a, ff_b)
        real_voxel_grid = atomic_potential.as_real_voxel_grid(coordinate_grid)

        # Find the maximum
        maximum_index = jnp.argmax(real_voxel_grid)
        maximum_position = coordinate_grid.reshape(-1, 3)[maximum_index]

        # Check that the maximum is in the correct position
        assert jnp.allclose(maximum_position, atom_positions[largest_atom])

    def test_integral_is_correct(self, toy_gaussian_cloud):
        """
        Test that the maxima of the potential are in the correct positions.
        """
        (
            atom_positions,
            ff_a,
            ff_b,
            n_voxels_per_side,
            voxel_size,
        ) = toy_gaussian_cloud
        coordinate_grid = make_coordinate_grid(n_voxels_per_side, voxel_size)

        # Build the potential
        atomic_potential = GaussianMixtureAtomicPotential(atom_positions, ff_a, ff_b)
        real_voxel_grid = atomic_potential.as_real_voxel_grid(coordinate_grid)

        integral = jnp.sum(real_voxel_grid) * voxel_size**3
        assert jnp.isclose(integral, jnp.sum(4 * jnp.pi * ff_a))

    def test_fourier_transform(self, toy_gaussian_cloud):
        (
            atom_positions,
            ff_a,
            ff_b,
            n_voxels_per_side,
            voxel_size,
        ) = toy_gaussian_cloud
        coordinate_grid = make_coordinate_grid(n_voxels_per_side, voxel_size)
        # Build the potential
        atomic_potential = GaussianMixtureAtomicPotential(atom_positions, ff_a, ff_b)
        real_voxel_grid = atomic_potential.as_real_voxel_grid(coordinate_grid)
        fourier_potential = FourierVoxelGridPotential.from_real_voxel_grid(
            real_voxel_grid, voxel_size
        )
        fourier_voxel_grid = fourier_potential.fourier_voxel_grid
        bin_size = 1 / (voxel_size) / n_voxels_per_side[0]
        num_atoms = atom_positions.shape[0]

        translational_phase_factor = lambda i, j, k, atom_position: jnp.exp(
            -1j
            * 2
            * jnp.pi
            * jnp.dot(atom_position, jnp.array([i - 64, j - 64, k - 64]))
            / (n_voxels_per_side[0] * voxel_size)
        )
        # Verify generated fourier_voxel_grid agrees with scattering equation in Peng.
        # Check up to 1/4 Nyquist Frequency in each axis.
        frequency_array = np.fromiter(
            itertools.product(np.arange(64, 80), repeat=3), "i,i,i"
        ).view(("i", 3))
        for frequency in frequency_array:
            [i, j, k] = frequency
            predicted_value = 0
            frequency_magnitude = np.sqrt((64 - i) ** 2 + (64 - j) ** 2 + (64 - k) ** 2)
            for atom_index in range(0, num_atoms):
                atom_contribution = jnp.sum(
                    ff_a[atom_index]
                    * 4
                    * jnp.pi
                    * (voxel_size) ** -3
                    * jnp.exp(
                        -ff_b[atom_index]
                        * ((1 / 2) * bin_size * frequency_magnitude) ** 2
                    )
                    * translational_phase_factor(i, j, k, atom_positions[atom_index])
                )

                predicted_value = predicted_value + atom_contribution

            fourier_grid_value = fourier_voxel_grid[k][j][i]
            assert jnp.isclose((predicted_value), (fourier_grid_value), rtol=1e-4)


class TestBuildVoxelsFromTrajectories:
    def test_indexing_matches_individual_calls(self, toy_gaussian_cloud):
        (
            atom_positions,
            ff_a,
            ff_b,
            n_voxels_per_side,
            voxel_size,
        ) = toy_gaussian_cloud
        second_set_of_positions = atom_positions + 1.0
        traj = jnp.stack([atom_positions, second_set_of_positions], axis=0)
        coordinate_grid = make_coordinate_grid(n_voxels_per_side, voxel_size)

        make_voxel_grids = jax.vmap(
            lambda pos, ff_a, ff_b, coords: GaussianMixtureAtomicPotential(
                pos, ff_a, ff_b
            ).as_real_voxel_grid(coords),
            in_axes=[0, None, None, None],
        )
        traj_voxels = make_voxel_grids(traj, ff_a, ff_b, coordinate_grid)

        voxel1 = GaussianMixtureAtomicPotential(
            atom_positions, ff_a, ff_b
        ).as_real_voxel_grid(coordinate_grid)

        voxel2 = GaussianMixtureAtomicPotential(
            second_set_of_positions, ff_a, ff_b
        ).as_real_voxel_grid(coordinate_grid)

        np.testing.assert_allclose(traj_voxels[0], voxel1, atol=1e-12)
        np.testing.assert_allclose(traj_voxels[1], voxel2, atol=1e-12)
