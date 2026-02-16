Below a series of papers on red noise (also knows as stochastic low-frequency variability). Please have a read, look further into the relevant literature, and extract all the relevant data about red noise (in particular look at temperature, luminosity, nu_char (characteristic frequency), the power of the variability, and metallicity. The data is often provided in tables, sometimes you might have to download it from some repository. Aggregate and study possible correlations in the data.  Make plots of the trends, possibly overlap to properties of stellar models (look at some of the papers to get inspiration on what kind of plots you might want to prepare). For getting  stellar models, you can use MESA MIST models available online here: https://waps.cfa.harvard.edu/MIST/model_grids.html 
Here's a demo on how to use them https://waps.cfa.harvard.edu/MIST/read_mist_models_demo.html
Here's the python routine to plot https://github.com/jieunchoi/MIST_codes/blob/master/scripts/read_mist_models.py )
Important: Note that the luminosity in the MIST models is different from the spectroscopic luminosity in the Bowman samples ell. 

To convert 

ell_sun=(5777)**4.0/(274*100)  # Used for Spectroscopic HRD 
ell = (10**logt)**4.0/(10**logg)
ell=np.log10(ell/ell_sun) 

 
Compare the trend in the data with existing trends in different theoretical predictions for the origin of red noise. 
Draw conclusions on what is the most likely physical origin of this phenomena, or just come up with your own results and reflections on what you learned from the data. 


https://www.aanda.org/articles/aa/pdf/2024/12/aa51419-24.pdf
https://www.aanda.org/articles/aa/pdf/2022/12/aa43545-22.pdf
https://www.aanda.org/articles/aa/pdf/2020/08/aa38224-20.pdf
https://www.aanda.org/articles/aa/pdf/2019/01/aa33662-18.pdf
https://www.nature.com/articles/s41550-023-02040-7
https://iopscience.iop.org/article/10.3847/1538-4357/ac03b0/pdf
https://iopscience.iop.org/article/10.3847/1538-4357/ad38bc/pdf
https://iopscience.iop.org/article/10.1088/2041-8205/806/2/L33/pdf
