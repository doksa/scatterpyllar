"""Creates a filter bank with all necessary information"""
import numpy as np
from morlet_2d_noDC import morlet_2d_noDC
from gabor_2d import gabor_2d
import time

import sys
sys.path.append('/Users/doksa/Dropbox/Projects/mkl_fft')
import mkl_fft


def ispow2(N):

    return 0 == (N & (N - 1))


def periodize_filter(filt):

    if filt.dtype is np.dtype('float32'):
        cast = np.float32
    elif filt.dtype is np.dtype('complex64'):
        cast = np.complex64

    N = filt.shape[0]  # filter is square

    assert ispow2(N), 'Filter size must be an integer power of 2.'

    J = int(np.log2(N))
    filt_multires = dict()
    for j in range(J):
        # NTM: 0.5 is a cute trick for higher dimensions!
        mask = np.hstack((np.ones(N / 2**(1 + j)), 0.5, np.zeros(N - N / 2**(j + 1) - 1))) \
            + \
            np.hstack(
                (np.zeros(N - N / 2**(j + 1)), 0.5, np.ones(N / 2**(1 + j) - 1)))

        mask.shape = N, 1

        filt_lp = filt * mask * mask.T
        if 'cast' in locals():
            filt_lp = cast(filt_lp)

        # Remember: C contiguous, last index varies "fastest" (contiguous in
        # memory) (unlike Matlab)
        fold_size = (2**j, N / 2**j, 2**j, N / 2**j)
        filt_multires[j] = filt_lp.reshape(fold_size).sum(axis=(0, 2))

    return filt_multires


def fourier_multires(N, J=4, L=8, l1renorm=True, spiral=False, dtype='single', fft_choice='mkl_fft'):

    fft, ifft, fft2, ifft2, rfft, irfft = select_fft(fft_choice)

    assert ispow2(N), 'Filter size must be an integer power of 2.'

    lambda_list = [(j, l) for j in range(1, J + 1) for l in range(L)]
    filters = morlet_filter_bank_2d(
        (N, N), J=J, L=L, spiral=spiral, fft_choice=fft_choice)

    # Compute the lowpass filter phi at all resolutions
    phi_allres = periodize_filter(filters['phi'])

    filters_multires = dict(N=N, J=J, L=L,
                            resolution=range(J),
                            phi=phi_allres,
                            psi=dict(filt_list=[]))

    # Allocate filter memory for all resolutions
    for res in range(J):
        filters_multires['psi']['filt_list'].append(
            np.zeros((J * L,) + (N / 2**res, N / 2**res), dtype=dtype))

        # Address the filters in a nice way
        for i_lam, lam in enumerate(lambda_list):
            filters_multires['psi'][(lam, res)] = \
                filters_multires['psi']['filt_list'][res][i_lam]

    for lam in lambda_list:
        psi_allres = periodize_filter(filters['psi'][lam])

        # Copy the filter where it belongs at all resolutions
        for res in range(J):
            filters_multires['psi'][(lam, res)][:] = psi_allres[res]

            if l1renorm is True:
                filters_multires['psi'][(lam, res)][:] /= \
                    np.sum(np.abs(ifft2(filters_multires['psi'][(lam, res)])))

    return filters_multires


def select_fft(fft_choice):
    # TO DO: don't have this in various files. Have only one copy.

    if fft_choice == 'fftw':
        fft_module = pyfftw.interfaces.numpy_fft
    elif fft_choice == 'fftpack':
        # Fortran FFTPACK from scipy
        fft_module = scipy.fftpack
    elif fft_choice == 'fftpack_lite':
        # C FFTPACK light from numpy
        fft_module = np.fft
    elif fft_choice == 'mkl_fft':
        fft_module = mkl_fft

    else:
        raise ValueError('Non-existing FFT library requested.')

    fft = fft_module.fft
    ifft = fft_module.ifft
    fft2 = fft_module.fft2
    ifft2 = fft_module.ifft2
    rfft = fft_module.rfft
    irfft = fft_module.irfft

    return fft, ifft, fft2, ifft2, rfft, irfft


def morlet_filter_bank_2d(shape, Q=1, L=8, J=4,
                          sigma_phi=.8,
                          sigma_psi=.8,
                          xi_psi=None,
                          slant_psi=None,
                          min_margin=None,
                          spiral=False,
                          dtype='single',
                          fft_choice='mkl_fft'):
    """Creates a multiscale bank of filters

    Creates and indexes filters at several scales and orientations

    Parameters
    ----------

    shape : {tuple, list, ndarray}
        shape=(2,)
        Tuple indicating the shape of the filters to be generated

    Q : {integer}
        Number of scales per octave (constant-Q filter bank)

    J : {integer}
        Total number of scales

    L : {integer}
        Number of orientations

    sigma_phi : {float}
        standard deviation of low-pass mother wavelet

    sigma_psi : {float}
        standard deviation of the envelope of the high-pass psi_0

    xi_psi : {float}
        frequency peak of the band-pass mother wavelet

    slant_psi : {float}
        ratio between axes of elliptic envelope. Smaller means more
        orientation selective

    min_margin : {integer}
        Padding for convolution
    """

    fft, ifft, fft2, ifft2, rfft, irfft = select_fft(fft_choice)

    # non-independent default values
    if xi_psi is None:
        xi_psi = .5 * np.pi * (2 ** (-1. / Q) + 1)
    if slant_psi is None:
        slant_psi = 4. / L
    if min_margin is None:
        min_margin = sigma_phi * 2 ** (float(J) / Q)

    # potentially do some padding here
    filter_shape = shape

    max_scale = 2 ** (float(J - 1) / Q)

    lowpass_spatial = np.real(gabor_2d(filter_shape, sigma_phi * max_scale,
                                       0., 0., 1.))
    lowpass_fourier = np.zeros(filter_shape, dtype=dtype)

    # TO DO: figure out why the following assignment doesn't work with mkl_fft
    lowpass_fourier = fft2(lowpass_spatial)

    little_wood_paley = np.zeros(lowpass_spatial.shape, dtype=dtype)

    lambda_list = [(j, l) for j in range(1, J + 1) for l in range(L)]

    filt_list = np.zeros((J * L,) + filter_shape, dtype=dtype)
    filters = dict(phi=lowpass_fourier, psi=dict(filt_list=filt_list),
                   lam=lambda_list, J=J, L=L, Q=Q)

    if spiral is False:
        angles = np.arange(L) * np.pi / L
    else:
        angles = np.arange(L) * 2 * np.pi / L

    for i_lam, lam in enumerate(lambda_list):
        if spiral is False:
            scale = 2 ** (float(lam[0] - 1) / Q)
        else:
            scale = 2 ** (float(lam[0] - 1) / Q + float(lam[1]) / L)

        angle = angles[lam[1]]

        band_pass_filter = filt_list[i_lam]  # this is a view
        filter_spatial = morlet_2d_noDC(filter_shape,
                                        sigma_psi * scale,
                                        xi_psi / scale,
                                        angle,
                                        slant_psi)

        band_pass_filter[:] = np.real(fft2(filter_spatial))
        filters['psi'][lam] = band_pass_filter

        # TO DO: be more careful here if not fourier_multires
        little_wood_paley += np.abs(band_pass_filter) ** 2

    little_wood_paley = np.fft.fftshift(little_wood_paley)
    lwp_max = little_wood_paley.max()

    for filt in filters['psi']['filt_list']:
        filt /= np.sqrt(lwp_max / 2)

    filters['littlewood_paley'] = little_wood_paley

    return filters


# if __name__ == "__main__":
#     Q, J, L = 1, 4, 8
#     sigma_psi = 8
#     sigma_phi = 8
#     filters = morlet_filter_bank_2d((128, 128), Q=Q, J=J, L=L,
#                                     sigma_psi=sigma_psi,
#                                     sigma_phi=sigma_phi,
#                                     xi_psi=np.pi / 16.)

#     import pylab as pl
#     pl.figure()
#     pl.subplot(2 * J + 1, L, 1)
#     pl.imshow(np.fft.fftshift(filters['phi']))
#     pl.axis('off')
#     pl.gray()
#     pl.subplot(2 * J + 1, L, 2)
#     pl.imshow(filters['littlewood_paley'])
#     pl.axis('off')
#     for j in range(J):
#         for l in range(L):
#             pl.subplot(2 * J + 1, L, 1 + (2 * j + 1) * L + l)
#             pl.imshow(np.real(np.fft.fftshift(filters['psi'][j][l])))
#             pl.axis('off')
#             pl.subplot(2 * J + 1, L, 1 + (2 * j + 2) * L + l)
#             pl.imshow(np.imag(np.fft.fftshift(filters['psi'][j][l])))
#             pl.axis('off')

#     pl.show()
