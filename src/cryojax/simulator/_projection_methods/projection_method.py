"""
Methods for integrating the scattering potential onto the exit plane.
"""

from abc import abstractmethod
from typing import Generic, TypeVar
from typing_extensions import override

from equinox import AbstractVar, Module
from jaxtyping import Array, Complex

from ...image import maybe_rescale_pixel_size
from .._instrument_config import InstrumentConfig
from .._potential import AbstractVoxelPotential


PotentialT = TypeVar("PotentialT")
VoxelPotentialT = TypeVar("VoxelPotentialT", bound="AbstractVoxelPotential")


class AbstractPotentialProjectionMethod(Module, Generic[PotentialT], strict=True):
    """Base class for a method of extracting projections of a potential."""

    @abstractmethod
    def compute_fourier_projected_potential(
        self,
        potential: PotentialT,
        config: InstrumentConfig,
    ) -> Complex[Array, "{config.padded_y_dim} {config.padded_x_dim//2+1}"]:
        """Compute the scattering potential in the exit plane at
        the `InstrumentConfig` settings.

        **Arguments:**

        - `potential`: The scattering potential representation.
        - `wavelength_in_angstroms`: The wavelength of the electron beam.
        - `config`: The configuration of the resulting image.
        """
        raise NotImplementedError


class AbstractVoxelPotentialProjectionMethod(
    AbstractPotentialProjectionMethod[VoxelPotentialT],
    Generic[VoxelPotentialT],
    strict=True,
):
    """Base class for a method of extracting projections of a voxel-based potential."""

    pixel_rescaling_method: AbstractVar[str]

    @abstractmethod
    def compute_raw_fourier_projected_potential(
        self,
        potential: VoxelPotentialT,
        config: InstrumentConfig,
    ) -> Complex[Array, "{config.padded_y_dim} {config.padded_x_dim//2+1}"]:
        raise NotImplementedError

    @override
    def compute_fourier_projected_potential(
        self,
        potential: VoxelPotentialT,
        config: InstrumentConfig,
    ) -> Complex[Array, "{config.padded_y_dim} {config.padded_x_dim//2+1}"]:
        raw_fourier_projected_potential = self.compute_raw_fourier_projected_potential(
            potential, config
        )
        return maybe_rescale_pixel_size(
            potential.voxel_size * raw_fourier_projected_potential,
            potential.voxel_size,
            config.pixel_size,
            is_real=False,
            shape_in_real_space=config.padded_shape,
        )
