Good project — the GWTC catalog is rich enough that there are real correlations to find, but also plenty of traps where low-number statistics can fool you. Let me think about what would make a strong Paradigm prompt for this.
A few things to consider before the prompt itself:
You'll want to point Paradigm at the actual data release. The GWTC-3 catalog (and the recent O4 updates if available) is publicly hosted by the LIGO-Virgo-KAGRA collaboration on Zenodo and through GWOSC. The most useful format is the parameter estimation summary table (the posterior medians and 90% credible intervals for each event), rather than the full posterior samples, since an LLM agent can parse a CSV/table but can't meaningfully work with millions of posterior draws.
You should also decide whether you want Paradigm to work purely with the tabular data you provide, or also pull in literature context. Given how Paradigm works, the latter seems natural — let the agents discover what correlations have already been reported (chi_eff vs mass ratio, the mass gap, hierarchical merger signatures) so they can contextualize rather than just rediscover known results.
Here's a prompt draft:

Research Prompt: Statistical Analysis of the LIGO-Virgo-KAGRA Gravitational-Wave Transient Catalog
You are given the complete catalog of compact binary merger detections from the LIGO-Virgo-KAGRA (LVK) collaboration through the end of O4a (GWTC-3 + any O4a public data releases). The dataset is attached as a CSV and contains parameter estimation summary statistics for each event, including: component masses (m1, m2), chirp mass, mass ratio (q), effective inspiral spin (chi_eff), precession spin parameter (chi_p), luminosity distance, redshift, network SNR, final remnant mass and spin, and source classification (BBH, BNS, NSBH).
Goal: Conduct an exploratory statistical analysis of this catalog to identify, characterize, and interpret correlations between merger parameters. Go beyond simple pairwise scatter plots — apply appropriate statistical methods (accounting for measurement uncertainties and selection effects where possible) and connect any findings to the astrophysical formation channels they might constrain.
Specific directions to explore (non-exhaustive):

Mass distribution structure. Look for features in the primary mass spectrum: the lower mass gap (~3–5 Msun), any pile-up near ~35 Msun potentially related to pulsational pair-instability supernovae (PPISN), and the upper mass gap (~50–120 Msun). Are there events that challenge these boundaries? What do they imply?
Spin-mass correlations. Investigate whether chi_eff correlates with primary mass, mass ratio, or redshift. Low or symmetric chi_eff distributions may favor dynamical formation in dense stellar environments, while systematically positive chi_eff suggests isolated binary evolution with tidal alignment. Does the data show any transition between regimes?
Mass ratio distribution. Characterize the distribution of q. Is it consistent with being uniform, or is there evidence for a preference toward equal masses or asymmetric systems? Does the mass ratio correlate with other parameters (spin, total mass)?
Redshift evolution. With the growing catalog, is there any evidence for the merger rate or population properties evolving with redshift? This connects to the delay time distribution between star formation and merger.
Outliers and subpopulations. Identify any events that are statistical outliers in multi-dimensional parameter space. Do they cluster into identifiable subpopulations (e.g., candidate hierarchical mergers with high mass and high spin)?

Methodological notes:

Parameter estimation uncertainties are large for many events. Any claimed correlation must be assessed against the measurement errors — do not treat median values as precise measurements.
Selection effects matter: LIGO/Virgo is more sensitive to higher-mass, nearby systems. Correlations with distance/redshift must account for this.
Use the existing LVK population analysis papers (particularly the GWTC-3 population paper, Abbott et al. 2023) as context. The goal is not to redo their hierarchical Bayesian analysis but to find complementary insights or check whether simple statistical approaches recover consistent results.
Clearly distinguish between previously known results you are confirming and any novel or unexpected correlations.

Resources:

Abbott et al. (2023), "Population of Merging Compact Binaries Inferred Using Gravitational Waves through GWTC-3" (arXiv:2111.03634)
Fishbach & Holz (2020), on mass distribution features
Callister et al. (2021), on spin distribution and formation channels

Output: A paper presenting the analysis, including publication-quality figures showing the key correlations discovered, discussion of their statistical significance, and interpretation in terms of formation channels and stellar/binary physics. Focus on novel findings that have not been reported in the literature, if any.

Data is provided in data/shared/LIGO-events.csv
