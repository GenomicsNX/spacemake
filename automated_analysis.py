import numpy as np
import pandas as pd
import scanpy as sc

dge_path = snakemake.input[0]

# umi cutoff 
umi_cutoff = int(snakemake.wildcards['umi_cutoff'])

results_file = snakemake.output['res_file']

adata = sc.read_text(dge_path, delimiter='\t').T

# this is only needed for combined dge-s
#metadata_cols = ['hamming_distance', 'y_pos', 'x_pos']
#metadata_indices = np.in1d(adata.var_names, metadata_cols)
#metadata_matrix = adata[:, metadata_indices].X.T
#
#adata = adata[:, ~metadata_indices]
#
#metadata = pd.DataFrame({
#    'x_pos': metadata_matrix[0],
#    'y_pos': metadata_matrix[1],
#    'hamming_distance': metadata_matrix[2]
#}, index = adata.obs.index)
#
## set metadata for cells
#adata.obs = metadata

# filter out cells based on umi, and genes based on number of cells
sc.pp.filter_cells(adata, min_counts=umi_cutoff)
sc.pp.filter_cells(adata, min_genes=50)
sc.pp.filter_genes(adata, min_cells=3)

# calculate mitochondrial gene percentage
mito_genes = adata.var_names.str.startswith('Mt-') | adata.var_names.str.startswith('mt-')

adata.obs['percent_mito'] = np.sum(adata[:, mito_genes].X, axis=1) / np.sum(adata.X, axis=1)
adata.obs['n_counts'] = adata.X.sum(axis=1)

# filter by percentage mito and n_genes
if adata.shape[0] > 0:
    adata = adata[adata.obs.n_genes < 2500, :]

if adata.shape[0] > 0:
    adata = adata[adata.obs.percent_mito < 0.05, :]

# calculate log(cpm)
sc.pp.normalize_total(adata, target_sum=1e6)
sc.pp.log1p(adata)

# save the log-normalised counts in the .raw attribute
adata.raw = adata

# identify highly variable genes if we have any observations
nrow, ncol = adata.shape

if nrow > 0 and ncol > 0:
    sc.pp.highly_variable_genes(adata, min_mean=1, max_mean = 50, min_disp=0.5)
    # filter out genes which are not highly variable
    adata = adata[:, adata.var.highly_variable]
        
    sc.pp.regress_out(adata, ['n_counts', 'percent_mito'])
    sc.pp.scale(adata, max_value=10)
    
    # PCA ANALYSIS
    sc.tl.pca(adata, svd_solver='arpack')
    
    # get number of pcs-s identified. Sometimes can be smaller than 50, if
    # less than 50 cells pass the threshold
    n_pcs = adata.uns['pca']['variance'].size
    # limit the number of pcs to 50
    n_pcs = n_pcs if n_pcs < 50 else 50
    
    # Compute the neighborhood graph
    sc.pp.neighbors(adata, n_pcs=n_pcs)
    
    # compute UMAP
    # for a very low number of cells, scipy will throw an error here
    try:
        sc.tl.umap(adata)   
    except TypeError:
        pass
    
    # find out the clusters
    sc.tl.leiden(adata)
    
    # finding marker genes
    sc.tl.rank_genes_groups(adata, 'leiden', method='t-test')

adata.write(results_file)