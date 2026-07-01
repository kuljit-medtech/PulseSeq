# =============================================================
# GRADIENT ECHO (GRE) PULSE SEQUENCE
# Designed using PyPulseq — outputs scanner-ready .seq file
# Author: Kuljit Singh | MS Medical Systems Engineering, OvGU
# =============================================================

import numpy as np
import matplotlib.pyplot as plt
import pypulseq as pp

# =============================================================
# STEP 1 - SYSTEM LIMITS
# Define what the scanner hardware can physically do
# =============================================================
system = pp.Opts(
    max_grad=28,            # maximum gradient strength in mT/m
    grad_unit='mT/m',
    max_slew=150,           # maximum slew rate T/m/s
    slew_unit='T/m/s',
    rf_ringdown_time=20e-6, # RF coil settling time after pulse
    rf_dead_time=100e-6,    # RF coil dead time before pulse
    adc_dead_time=10e-6     # ADC settling time
)

# =============================================================
# STEP 2 - SEQUENCE PARAMETERS
# =============================================================
fov             = 220e-3   # Field of View: 220mm
Nx              = 64       # Matrix size 64x64
Ny              = 64
slice_thickness = 3e-3     # Slice thickness: 3mm
flip_angle      = 30       # RF flip angle in degrees
TR              = 20e-3    # Repetition Time: 20ms
TE              = 5e-3     # Echo Time: 5ms

# =============================================================
# STEP 3 - CREATE SEQUENCE OBJECT
# =============================================================
seq = pp.Sequence(system=system)

# =============================================================
# STEP 4 - BUILD RF PULSE + SLICE SELECT GRADIENT
# Sinc pulse that tips magnetisation by flip_angle degrees
# =============================================================
rf, gz, gz_reph = pp.make_sinc_pulse(
    flip_angle=flip_angle * np.pi / 180,
    duration=3e-3,
    slice_thickness=slice_thickness,
    apodization=0.42,
    time_bw_product=4,
    system=system,
    return_gz=True
)

# =============================================================
# STEP 5 - READOUT GRADIENT + ADC
# =============================================================
delta_k = 1 / fov

gx = pp.make_trapezoid(
    channel='x',
    flat_area=Nx * delta_k,
    flat_time=6.4e-3,
    system=system
)

adc = pp.make_adc(
    num_samples=Nx,
    duration=gx.flat_time,
    phase_offset=rf.phase_offset,
    delay=gx.rise_time,
    system=system
)

# =============================================================
# STEP 6 - PRE-PHASER GRADIENT
# Moves to the start of k-space before reading
# =============================================================
gx_pre = pp.make_trapezoid(
    channel='x',
    area=-gx.area / 2,
    duration=2e-3,
    system=system
)

phase_areas = (np.arange(Ny) - Ny / 2) * delta_k

# =============================================================
# STEP 7 - BUILD SEQUENCE LOOP
# Repeat for each phase encode step = each line of k-space
# =============================================================
for i in range(Ny):
    gy_pre = pp.make_trapezoid(
        channel='y',
        area=phase_areas[i],
        duration=2e-3,
        system=system
    )

    seq.add_block(rf, gz)
    seq.add_block(gx_pre, gy_pre, gz_reph)
    seq.add_block(gx, adc)
    seq.add_block(pp.make_delay(TR - TE - 2e-3))

print("Sequence built successfully!")
print(f"Total duration: {seq.duration()[0]*1000:.1f} ms")

# =============================================================
# STEP 8 - PLOT TIMING DIAGRAM
# =============================================================
seq.plot()
plt.show()

# =============================================================
# STEP 9 - SAVE .seq FILE
# =============================================================
seq.write('gre_sequence.seq')
print("Saved: gre_sequence.seq")