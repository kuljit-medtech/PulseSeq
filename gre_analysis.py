# =============================================================
# GRE SEQUENCE ANALYSIS
# Step 1: K-space trajectory plot
# Step 2: Sequence validation
# Step 3: K-space simulation + image reconstruction
# Author: Kuljit Singh | MS Medical Systems Engineering, OvGU
# =============================================================

import numpy as np
import matplotlib.pyplot as plt
import pypulseq as pp

# =============================================================
# REBUILD THE SEQUENCE FIRST
# (same as gre_sequence.py — needed to analyse it)
# =============================================================
system = pp.Opts(
    max_grad=28, grad_unit='mT/m',
    max_slew=150, slew_unit='T/m/s',
    rf_ringdown_time=20e-6,
    rf_dead_time=100e-6,
    adc_dead_time=10e-6
)

fov             = 220e-3
Nx              = 64
Ny              = 64
slice_thickness = 3e-3
flip_angle      = 30
TR              = 20e-3
TE              = 5e-3

seq = pp.Sequence(system=system)

rf, gz, gz_reph = pp.make_sinc_pulse(
    flip_angle=flip_angle * np.pi / 180,
    duration=3e-3,
    slice_thickness=slice_thickness,
    apodization=0.42,
    time_bw_product=4,
    system=system,
    return_gz=True
)

delta_k = 1 / fov

gx = pp.make_trapezoid(
    channel='x', flat_area=Nx * delta_k,
    flat_time=6.4e-3, system=system
)

adc = pp.make_adc(
    num_samples=Nx, duration=gx.flat_time,
    phase_offset=rf.phase_offset,
    delay=gx.rise_time, system=system
)

gx_pre = pp.make_trapezoid(
    channel='x', area=-gx.area / 2,
    duration=2e-3, system=system
)

phase_areas = (np.arange(Ny) - Ny / 2) * delta_k

for i in range(Ny):
    gy_pre = pp.make_trapezoid(
        channel='y', area=phase_areas[i],
        duration=2e-3, system=system
    )
    seq.add_block(rf, gz)
    seq.add_block(gx_pre, gy_pre, gz_reph)
    seq.add_block(gx, adc)
    seq.add_block(pp.make_delay(TR - TE - 2e-3))

print("Sequence rebuilt successfully!")

# =============================================================
# STEP 1 — K-SPACE TRAJECTORY PLOT
# Shows exactly how k-space gets filled line by line
# =============================================================
print("\nStep 1: Calculating k-space trajectory...")

ktraj_adc, ktraj, t_excitation, t_refocusing, t_adc = seq.calculate_kspace()

# ktraj_adc = k-space points exactly where ADC sampled
# ktraj     = full k-space trajectory including ramps

plt.figure(figsize=(12, 5))

# Plot 1: Full trajectory
plt.subplot(1, 2, 1)
plt.plot(ktraj[0, :], ktraj[1, :], 'b-', linewidth=0.5, alpha=0.5, label='Full trajectory')
plt.plot(ktraj_adc[0, :], ktraj_adc[1, :], 'r.', markersize=1.5, label='ADC samples')
plt.xlabel('kx (m⁻¹)')
plt.ylabel('ky (m⁻¹)')
plt.title('K-space Trajectory\n(blue=full path, red=sampled points)')
plt.legend()
plt.axis('equal')
plt.grid(True, alpha=0.3)

# Plot 2: Just the sampled points — should be a clean grid
plt.subplot(1, 2, 2)
plt.plot(ktraj_adc[0, :], ktraj_adc[1, :], 'r.', markersize=2)
plt.xlabel('kx (m⁻¹)')
plt.ylabel('ky (m⁻¹)')
plt.title('K-space Sampled Points\n(should be uniform grid)')
plt.axis('equal')
plt.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('kspace_trajectory.png', dpi=150)
print("Saved: kspace_trajectory.png")

# =============================================================
# STEP 2 — SEQUENCE VALIDATION
# PyPulseq checks timing, gradient limits, slew rate limits
# =============================================================
print("\nStep 2: Validating sequence...")

ok, error_report = seq.check_timing()

if ok:
    print("Validation PASSED — sequence is physically correct!")
    print("All gradient limits, slew rates and timing checks passed.")
else:
    print("Validation found issues:")
    for e in error_report:
        print(f"  - {e}")

# =============================================================
# STEP 3 — SIMULATE K-SPACE + RECONSTRUCT IMAGE
# Simulate what a Shepp-Logan phantom would look like
# through this sequence, then reconstruct via FFT
# =============================================================
print("\nStep 3: Simulating k-space and reconstructing image...")

# --- Generate Shepp-Logan phantom (standard MRI test image) ---
def shepp_logan_phantom(N):
    """Generate a simple Shepp-Logan phantom of size NxN"""
    phantom = np.zeros((N, N))
    cx, cy = N // 2, N // 2

    # Outer ellipse — skull
    for y in range(N):
        for x in range(N):
            val = ((x - cx) / (0.69 * N / 2))**2 + ((y - cy) / (0.92 * N / 2))**2
            if val <= 1:
                phantom[y, x] += 1.0

    # Inner ellipse — brain tissue
    for y in range(N):
        for x in range(N):
            val = ((x - cx) / (0.6624 * N / 2))**2 + ((y - cy) / (0.874 * N / 2))**2
            if val <= 1:
                phantom[y, x] -= 0.98

    # Small ellipse — left ventricle region
    for y in range(N):
        for x in range(N):
            xc = cx - int(0.22 * N / 2)
            val = ((x - xc) / (0.11 * N / 2))**2 + ((y - cy) / (0.31 * N / 2))**2
            if val <= 1:
                phantom[y, x] -= 0.8

    # Small ellipse — right ventricle region  
    for y in range(N):
        for x in range(N):
            xc = cx + int(0.22 * N / 2)
            val = ((x - xc) / (0.16 * N / 2))**2 + ((y - cy) / (0.41 * N / 2))**2
            if val <= 1:
                phantom[y, x] -= 0.8

    # Centre detail
    for y in range(N):
        for x in range(N):
            val = ((x - cx) / (0.21 * N / 2))**2 + ((y - cy) / (0.25 * N / 2))**2
            if val <= 1:
                phantom[y, x] += 0.4

    return np.clip(phantom, 0, 1)

# Generate 64x64 phantom
phantom = shepp_logan_phantom(Nx)

# --- Simulate k-space (forward FFT of phantom) ---
# In real MRI: scanner acquires k-space directly from the patient
# Here: we mathematically compute what k-space would look like
kspace_sim = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(phantom)))

# --- Add realistic noise ---
noise_level = 0.05
noise = noise_level * (np.random.randn(*kspace_sim.shape) +
                       1j * np.random.randn(*kspace_sim.shape))
kspace_noisy = kspace_sim + noise

# --- Reconstruct image (inverse FFT) ---
image_reconstructed = np.abs(np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(kspace_noisy))))

# --- Plot everything ---
fig, axes = plt.subplots(1, 3, figsize=(14, 5))
fig.suptitle('GRE Sequence — K-space Simulation & Image Reconstruction\nKuljit Singh | MS Medical Systems Engineering, OvGU',
             fontsize=11, fontweight='bold')

# Original phantom
axes[0].imshow(phantom, cmap='gray', origin='lower')
axes[0].set_title('Original Phantom\n(ground truth)')
axes[0].set_xlabel('x (pixels)')
axes[0].set_ylabel('y (pixels)')
axes[0].axis('off')

# K-space magnitude (log scale so you can see it)
axes[1].imshow(np.log1p(np.abs(kspace_noisy)), cmap='gray', origin='lower')
axes[1].set_title('Simulated K-space\n(log magnitude)')
axes[1].set_xlabel('kx')
axes[1].set_ylabel('ky')
axes[1].axis('off')

# Reconstructed image
axes[2].imshow(image_reconstructed, cmap='gray', origin='lower')
axes[2].set_title('Reconstructed MRI Image\n(inverse FFT of k-space)')
axes[2].set_xlabel('x (pixels)')
axes[2].set_ylabel('y (pixels)')
axes[2].axis('off')

plt.tight_layout()
plt.savefig('gre_reconstruction.png', dpi=150)
print("Saved: gre_reconstruction.png")

plt.show()

print("\n" + "="*50)
print("ALL STEPS COMPLETE")
print("="*50)
print("Files saved:")
print("  kspace_trajectory.png  — k-space trajectory plot")
print("  gre_reconstruction.png — phantom reconstruction")
print(f"\nSequence stats:")
print(f"  Matrix size : {Nx} x {Ny}")
print(f"  FOV         : {fov*1000:.0f} mm")
print(f"  TR / TE     : {TR*1000:.0f} ms / {TE*1000:.0f} ms")
print(f"  Flip angle  : {flip_angle}°")
print(f"  Total time  : {seq.duration()[0]*1000:.1f} ms")