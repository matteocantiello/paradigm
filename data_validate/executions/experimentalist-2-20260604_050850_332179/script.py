import re
import numpy as np
import scipy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')
workspace = Path('/data/workspace')
workspace.mkdir(parents=True, exist_ok=True)
# EXPERIMENT: plot_analysis
# DEPENDS: analytical_prep, efficient_simulation
# Produce publication-quality figures comparing simulation with theory.
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_style("whitegrid")
plt.rcParams.update({'font.size': 12})

# Load precomputed data
df_ana = pd.read_csv('/data/workspace/analytical_results.csv')
df_sim = pd.read_csv('/data/workspace/simulation_results.csv')

# Figure 1: comprehensive 2x2 panel
fig, axes = plt.subplots(2, 2, figsize=(12, 10))

# Panel A: Empirical SEM scaling (log-log)
ax = axes[0,0]
n_fine = np.logspace(np.log10(2), np.log10(1000), 200)
ax.loglog(n_fine, 1.0 / np.sqrt(n_fine), 'k-', lw=2, label=r'Theory: $1/\sqrt{n}$')
ax.loglog(df_sim['n'], df_sim['emp_sem'], 'ro', markersize=4, label='Simulation')
ax.set_xlabel('Sample size n')
ax.set_ylabel('Standard error of sample mean')
ax.set_title('A) SEM scaling (log-log)')
ax.legend(frameon=True, fancybox=True)
ax.grid(True, alpha=0.4)

# Panel B: Relative bias of estimated SEM
ax = axes[0,1]
rel_bias = (df_sim['bias_sem'] / df_sim['true_sem']) * 100
ax.semilogx(df_sim['n'], rel_bias, 'bo-', markersize=4)
ax.axhline(0, color='k', linestyle='--')
ax.set_xlabel('Sample size n')
ax.set_ylabel('Relative bias of estimated SEM (%)')
ax.set_title('B) Bias of sample SEM estimator')
ax.grid(True, alpha=0.4)

# Panel C: MSE of estimated SEM
ax = axes[1,0]
ax.loglog(df_ana['n'], df_ana['MSE_analytical'], 'k-', lw=2, label='Analytical MSE')
ax.loglog(df_sim['n'], df_sim['mse_est'], 'rs', markersize=3, label='Simulated MSE')
ax.set_xlabel('Sample size n')
ax.set_ylabel('Mean Squared Error')
ax.set_title('C) MSE of estimated SEM')
ax.legend(frameon=True, fancybox=True)
ax.grid(True, alpha=0.4)

# Panel D: c4 factor
ax = axes[1,1]
ax.semilogx(df_ana['n'], df_ana['c4'], 'g-', lw=2, label=r'$c_4(n)$')
ax.axhline(1, color='k', linestyle='--', label='1.0')
ax.set_xlabel('Sample size n')
ax.set_ylabel('c4 factor')
ax.set_title('D) Bias correction factor c4(n)')
ax.legend(frameon=True, fancybox=True)
ax.grid(True, alpha=0.4)

plt.tight_layout()
plt.savefig('/data/workspace/figure_sem_scaling_complete.png', dpi=150, bbox_inches='tight')
plt.close()

# Figure 2: Single panel verifying 1/sqrt(n) with fitted curve
fig, ax = plt.subplots(figsize=(8, 6))
idx_fit = df_sim['n'] >= 10
log_n = np.log10(df_sim['n'].values)
log_emp = np.log10(df_sim['emp_sem'].values)
# Fit slope for all n >= 10
slope, intercept = np.polyfit(log_n[idx_fit], log_emp[idx_fit], 1)
fit_y = 10**(intercept + slope * log_n)

ax.loglog(df_sim['n'], df_sim['emp_sem'], 'o', markersize=5, label='Simulation')
ax.loglog(n_fine, 1.0/np.sqrt(n_fine), 'k-', lw=2, label=r'Theory: $1/\sqrt{n}$')
ax.loglog(df_sim['n'], fit_y, 'r--', lw=1.5, label=f'Fit slope = {slope:.3f}')
ax.set_xlabel('Sample size n')
ax.set_ylabel('Standard error of sample mean')
ax.set_title('Verification of $1/\sqrt{n}$ scaling law')
ax.legend(frameon=True, fancybox=True)
ax.grid(True, alpha=0.4)

plt.tight_layout()
plt.savefig('/data/workspace/figure_scaling_fit.png', dpi=150, bbox_inches='tight')

# Print a few RESULT lines for completeness
print(f"RESULT[slope_sem_loglog]= {slope:.5f}")
# Show relative MSE error for a few n
for n_mark in [5, 10, 50, 100, 500]:
    idx = np.argmin(np.abs(df_sim['n'] - n_mark))
    n_act = df_sim['n'].iloc[idx]
    mse_sim = df_sim['mse_est'].iloc[idx]
    mse_ana = df_sim['mse_analytic'].iloc[idx]
    if n_act == n_mark:
        print(f"RESULT[mse_ratio_n{n_act}]= {mse_sim/mse_ana - 1:.5f}")
print("Plotting and analysis completed.")