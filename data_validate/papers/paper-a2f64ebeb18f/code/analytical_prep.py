# EXPERIMENT: analytical_prep
# Compute analytical values: c4 factor, true SEM, expected SEM, and MSE.
import numpy as np
import pandas as pd
from scipy.special import gamma, gammaln
import os

def c4(n):
    """Unbiasedness factor for sample standard deviation (dof=1) under normality."""
    if n < 2:
        return np.nan
    return np.sqrt(2.0 / (n - 1)) * gamma(n / 2) / gamma((n - 1) / 2)

# Choose n values: denser for small n, sparser for large n
n_vals = np.unique(np.concatenate([
    np.arange(2, 51, 1),
    np.arange(55, 101, 5),
    np.arange(110, 201, 20),
    np.arange(250, 1001, 50)
]))
n_vals = np.sort(n_vals)

true_sem = 1.0 / np.sqrt(n_vals)
c4_vals = np.array([c4(n) for n in n_vals])
exp_sem = c4_vals / np.sqrt(n_vals)           # E[ s/√n ]
abs_bias = exp_sem - true_sem
rel_bias = abs_bias / true_sem
MSE_ana = 2.0 * (1.0 - c4_vals) / n_vals       # derived MSE = 2(1 - c4)/n

df = pd.DataFrame({
    'n': n_vals,
    'true_sem': true_sem,
    'c4': c4_vals,
    'exp_sem': exp_sem,
    'abs_bias': abs_bias,
    'rel_bias': rel_bias,
    'MSE_analytical': MSE_ana
})

os.makedirs('/data/workspace', exist_ok=True)
df.to_csv('/data/workspace/analytical_results.csv', index=False)

print("Analytical reference computed.")
for n_mark in [5, 10, 50, 100]:
    idx = np.argmin(np.abs(df['n'] - n_mark))
    print(f"RESULT[c4_n{df['n'].iloc[idx]}]= {df['c4'].iloc[idx]:.6f}")
    print(f"RESULT[MSE_analytical_n{df['n'].iloc[idx]}]= {df['MSE_analytical'].iloc[idx]:.6e}")
print("Analytical prep complete.")