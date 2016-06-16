import scatterpyllar.filters.morlet as spf
import scatterpyllar.core.scattering_transform as sp
import numpy as np
from scipy.misc import lena
import time
import cProfile

import sys
import mkl_fft


N = 256
J = int(np.log2(N))
L = 12

t = np.arange(N).reshape(N, 1)

# Some deterministic signal to facilitate comparisons with the Matlab version:
x = np.float32(np.cos(t) * np.cos(t.T))


# Filter generation is faster than in the Matlab version
start_time = time.time()
# why doesn't mkl_fft work here?
fb = spf.fourier_multires(N, J=J, L=L, fft_choice='fftpack_lite')
print("--- %s seconds ---" % (time.time() - start_time))

# This is how you can get all the keys to index filters if you need it:
print fb['psi'].keys()[:5]

# The actual transform is faster if we use mkl_fft
n_mc = 1
start_time = time.time()
for i in range(n_mc):
    S, scr = sp.scattering_transform(x, fb, fft_choice='fftpack_lite', localized=True)
print("--- %s seconds ---" % (time.time() - start_time))



# This is how you access coefficients in the second layer:
print S['coeffs'][((0, 0),(3, 1),(5, 1))]


# So indexing is done by tuples of (j, l) tuples. The one above indexes the
# following path through layers:
#
# Layer 0: (0, 0) (this is always the same) 
# Layer 1: (3, 1) meaning j = 3 (note that j starts from 1!), and l = 1;
#                 unlike with j, l = 1 indexes the second rotation (first 
#                 one you get for l = 0)
# Layer 2: (5, 1) analogously


# This is how you access coefficients in the first layer:
print S['coeffs'][((0, 0),(3, 1))]

# This is how you access the mean coeff in the zero-th layer (note the comma!):
print S['coeffs'][((0, 0),)]



