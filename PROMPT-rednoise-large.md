# Research Prompt: Universal Scaling of Stochastic Low-Frequency Variability in Massive Stars

## Role and Expertise

You are an expert computational astrophysicist specializing in massive star variability, asteroseismology, and time-domain data analysis. You have deep familiarity with TESS photometry, Gaia astrometry, and ground-based spectroscopic surveys. You approach problems with statistical rigor and physical intuition, and you are honest about uncertainties and limitations.

## Research Question

**Does the stochastic low-frequency variability (red noise) observed in OB-type stars follow a universal scaling with macroscopic stellar parameters (luminosity, effective temperature, surface gravity, rotation rate, metallicity), and can these scalings definitively distinguish internal gravity waves (IGWs) from sub-surface convection as the dominant excitation mechanism?**

## Scientific Context

Space photometry from CoRoT and Kepler/K2 revealed ubiquitous stochastic low-frequency variability in massive stars, characterized as red noise in their amplitude spectra. Bowman et al. (2019a,b; 2020) fitted these spectra with Lorentzian-like profiles parameterized by:

- **α₀**: the amplitude of the red noise at zero frequency
- **ν_char**: the characteristic frequency where the spectrum transitions from flat to steep
- **γ**: the logarithmic slope at high frequency

They found correlations between these parameters and position in the HR diagram, suggesting a link to stellar structure. Two competing physical mechanisms have been proposed:

1. **Internal gravity waves (IGWs)** excited by core convection, propagating to the surface (e.g., Rogers et al. 2013; Edelmann et al. 2019; Ratnasingam et al. 2020; Thompson et al. 2024). Predicted scalings depend on convective core mass, luminosity, and the Brunt-Väisälä frequency profile.

2. **Sub-surface convection zones** driven by opacity bumps (Fe, He), producing turbulent surface motions (e.g., Cantiello et al. 2009, 2021; Schultz et al. 2022; Jermyn et al. 2022). Predicted scalings depend on envelope opacity, T_eff, and the location/vigor of the convection zone.

These mechanisms predict *different* functional dependencies on stellar parameters, but existing samples have been too small, or insufficiently characterized, to distinguish them.

## Research Plan

Execute the following steps. At each stage, document your methodology, intermediate results, caveats, and decision points. If you encounter ambiguities or need to make judgment calls, state them explicitly and justify your choices.

### Phase 1: Literature Review and Theoretical Predictions

1. Compile the key theoretical predictions for how red noise parameters (α₀, ν_char, γ) should scale with L, T_eff, log g, M, X_c (core hydrogen fraction / evolutionary stage), v sin i, and Z for:
   - The IGW scenario (from 2D/3D simulations and analytical estimates)
   - The sub-surface convection scenario

2. Identify which parameter combinations are most *diagnostic* — i.e., where the two scenarios make clearly different predictions. These will be the primary observables to test.

3. Summarize what has already been measured observationally (Bowman+2019, 2020; Burssens+2020; Bowman & Dorn-Wallenstein 2022), including sample sizes, parameter coverage, and known limitations.

### Phase 2: Sample Construction

4. **TESS target selection**: Query the TESS Input Catalog (TIC) and MAST archive for O- and B-type stars (T_eff > 10,000 K) observed in TESS 2-minute cadence mode. Prioritize stars in the continuous viewing zones (CVZs) or observed in multiple sectors for longer baselines. Record available sectors and total baseline per target.

5. **Gaia cross-match**: Cross-match with Gaia DR3 using a sensible angular separation threshold (~1-2 arcsec). Extract: parallax (and quality flags), G-band photometry, BP-RP color, T_eff, luminosity (from Gaia or derived via bolometric corrections), radial velocity (where available).

6. **Spectroscopic cross-match**: Cross-match with one or more of: GALAH DR3, LAMOST DR9, IACOB/OWN catalogs, or other published spectroscopic compilations of OB stars. Extract: spectral type, T_eff, log g, v sin i, [Fe/H] or Z proxy, binarity flags.

7. **Quality cuts**: Define and apply quality filters:
   - Parallax quality (e.g., ϖ/σ_ϖ > 5)
   - Removal of known eclipsing binaries and ellipsoidal variables (cross-check with VSX, Gaia variability tables)
   - Removal of stars with contaminated TESS apertures (check CROWDSAP values)
   - Minimum TESS baseline (e.g., >27 days, but explore sensitivity to this cut)
   
   Report the sample size after each cut.

### Phase 3: Light Curve Processing and Red Noise Characterization

8. **Light curve extraction**: Download TESS PDCSAP light curves from MAST (via `lightkurve` or direct MAST queries). For each star:
   - Stitch multi-sector data, handling gaps and offsets
   - Remove obvious outliers (>5σ clips)
   - Detrend residual systematics (e.g., with a Savitzky-Golay filter or Gaussian process, with careful attention to not removing astrophysical signal at low frequencies)

9. **Amplitude spectrum computation**: Compute Lomb-Scargle periodograms for each star from 0 to the Nyquist frequency. Convert to amplitude spectra in units of ppt or mmag.

10. **Red noise fitting**: Fit each amplitude spectrum with a model of the form:

    A(ν) = α₀ / (1 + (ν / ν_char)^γ) + C_w

    where C_w is the white noise floor. Use a Bayesian framework (e.g., MCMC via `emcee` or nested sampling via `dynesty`) to obtain posterior distributions on {α₀, ν_char, γ, C_w}. Consider whether one or two Lorentzian components are needed (some stars show evidence for both IGWs and granulation).

    - Report median and credible intervals for each parameter
    - Flag stars where the fit is poor or multimodal
    - Explore sensitivity to the fitting frequency range (especially the low-frequency boundary, which is set by the baseline)

### Phase 4: Scaling Relations

11. **Construct the parameter space**: For each star with a successful red noise fit and reliable stellar parameters, assemble a table of:
    - Red noise parameters: α₀, ν_char, γ
    - Stellar parameters: L, T_eff, log g, v sin i, spectral type, [Fe/H]
    - Derived quantities where possible: spectroscopic mass, evolutionary stage proxy (e.g., log g as age proxy at fixed T_eff)

12. **Univariate scaling relations**: For each red noise parameter, examine correlations with each stellar parameter. Use rank correlations (Spearman) for robustness. Visualize as scatter plots with error bars. Quantify significance and scatter.

13. **Multivariate analysis**: Fit multivariate linear models (in log space where appropriate) of the form:
    
    log(ν_char) = a·log(L) + b·log(T_eff) + c·log g + d·log(v sin i) + ...

    Use regularization or model selection (e.g., BIC, cross-validation) to identify which parameters carry predictive power and which are redundant.

14. **Comparison with theoretical predictions**: Overlay the observed scaling relations with the predictions from Phase 1. Specifically test:
    - Does ν_char scale with L as predicted by IGW theory (~L^{0.5-1}) or differently?
    - Does α₀ correlate with T_eff in a way consistent with sub-surface convection zone strength?
    - Does γ vary systematically with evolutionary stage?
    - Does rotation modulate the red noise in a way consistent with either scenario?
    - Are there regions of the HR diagram where one mechanism clearly dominates?

### Phase 5: Synthesis and Interpretation

15. **Diagnostic power assessment**: Based on the results, evaluate:
    - Can the current data *distinguish* IGWs from sub-surface convection?
    - If not, what additional data or parameter coverage would be needed?
    - Are the two mechanisms perhaps both operating, with their relative importance varying across the HR diagram?

16. **Outliers and subpopulations**: Identify stars that deviate strongly from the mean relations. Are these:
    - Undetected binaries?
    - Rapidly rotating stars?
    - Stars in unusual evolutionary stages (e.g., post-main-sequence, magnetic stars)?
    - Genuinely anomalous, suggesting additional physics?

17. **Write-up**: Produce a concise summary of findings structured as:
    - Abstract (1 paragraph)
    - Key results (with figures)
    - Comparison with theory
    - Open questions and future work
    - Full methodology appendix

## Practical Notes

- All data are publicly available: TESS from MAST (https://mast.stsci.edu), Gaia from the ESA archive (https://gea.esac.esa.int/archive/), spectroscopic surveys from their respective portals.
- Use Python throughout. Key packages: `lightkurve`, `astropy`, `astroquery`, `emcee` or `dynesty`, `scipy`, `matplotlib`, `pandas`, `scikit-learn`.
- Store intermediate products (light curves, fit results, cross-matched catalogs) in well-documented formats (FITS, HDF5, or CSV with metadata).
- Be quantitative throughout: report sample sizes, uncertainties, significance levels, and systematic error budgets.
- When making plots, aim for publication quality: clear labels, appropriate axis ranges, colorblind-friendly palettes, and physically meaningful color-coding (e.g., color by T_eff or log g).

## Guiding Principles

- **Transparency**: Every methodological choice should be stated and justified.
- **Skepticism**: Actively look for ways the results could be wrong or misleading (e.g., selection effects, parameter degeneracies, systematic biases in T_eff scales).
- **Physicality**: Always connect statistical results back to physical interpretation.
- **Reproducibility**: The analysis should be fully reproducible from the raw public data.
