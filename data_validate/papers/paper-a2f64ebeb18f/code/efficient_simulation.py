# EXPERIMENT: efficient_simulation
# DEPENDS: analytical_prep
# Efficient Monte Carlo using the factorised sampling distribution of mean and variance.
import numpy as np
import pandas as pd
from scipy.stats import chi, norm
import os

np.random.seed(42)  # reproducibility

# Load analytical table for comparison
df_ana = pd.read_csv('/data/workspace/analytical_results.csv')
available_n = set(df_ana['n'])

# Subset of n to simulate: every available n ≤ 200, plus a few larger n
sim_n = [n for n in df_ana['n'] if n <= 200] + [300, 500, 1000]
sim_n = sorted(set(sim_n))

# Base number of replicates: efficient method is cheap, so use a constant large M
M = 200000  # yields low MC error even at large n

results = []
print("NOTE: Using SYNTHETIC data — not real observations")
print(f"Simulating {len(sim_n)} n-values, M={M} replicates each.")

for n in sim_n:
    df_var = n - 1
    # Sample standard deviations from chi distribution scaled by sigma=1
    chi_samples = chi.rvs(df_var, size=M)            # ~ chi(df=n-1)
    s = chi_samples / np.sqrt(df_var)                # unbiased factor → s estimate
    # Sample means ~ N(0, 1/n)
    sample_means = norm.rvs(0, 1.0 / np.sqrt(n), size=M)

    est_sem = s / np.sqrt(n)                         # estimated SEM
    true_sem_val = 1.0 / np.sqrt(n)

    # Metrics
    emp_sem = np.std(sample_means, ddof=1)           # empirical SEM
    avg_est_sem = np.mean(est_sem)
    bias_sem = avg_est_sem - true_sem_val
    mse_est = np.mean((est_sem - true_sem_val) ** 2)

    # Get analytical MSE for this n from precomputed table
    idx = np.argmin(np.abs(df_ana['n'].values - n))
    mse_analytic = df_ana['MSE_analytical'].iloc[idx] if df_ana['n'].iloc[idx] == n else np.nan

    results.append({
        'n': n, 'M': M,
        'true_sem': true_sem_val,
        'emp_sem': emp_sem,
        'avg_est_sem': avg_est_sem,
        'bias_sem': bias_sem,
        'mse_est': mse_est,
        'mse_analytic': mse_analytic
    })

    if n % 10 == 0 or n <= 10:
        print(f"n={n:4d}  emp_sem={emp_sem:.6f}  avg_est_sem={avg_est_sem:.6f}  bias={bias_sem:.6e}  mse_est={mse_est:.6e}")

df_sim = pd.DataFrame(results)
df_sim.to_csv('/data/workspace/simulation_results.csv', index=False)

# RESULT lines for key n
for n_mark in [5, 10, 50, 100, 500]:
    idx = np.argmin(np.abs(df_sim['n'] - n_mark))
    row = df_sim.iloc[idx]
    n_act = row['n']
    print(f"RESULT[emp_sem_n{n_act}]= {row['emp_sem']:.6f}")
    print(f"RESULT[bias_sem_n{n_act}]= {row['bias_sem']:.6e}")
    print(f"RESULT[mse_est_n{n_act}]= {row['mse_est']:.6e}")
    print(f"RESULT[mse_analytic_n{n_act}]= {row['mse_analytic']:.6e}")

# Fit slope log(emp sem) vs log(n) for n>=10
idx_fit = df_sim['n'] >= 10
if idx_fit.sum() > 3:
    log_n = np.log10(df_sim['n'][idx_fit].values)
    log_sem = np.log10(df_sim['emp_sem'][idx_fit].values)
    slope, intercept = np.polyfit(log_n, log_sem, 1)
    print(f"RESULT[slope_sem_loglog]= {slope:.5f}")
print("Efficient simulation completed.")