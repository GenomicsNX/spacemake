from spacemake.errors import *

# barcode flavor parsing and query functions
class dotdict(dict):
    """dot.notation access to dictionary attributes"""

    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def parse_barcode_flavors(
    config,
    bc_default_settings=dict(
        bc1_ref="",
        bc2_ref="",
        cell_raw="None",
        score_threshold=0.0,
        min_opseq_score=22,
        bam_tags="CR:{cell},MI:{UMI}",
    ),
):
    """
    Reads the 'barcode_flavor' from 'knowledge' section of the config.yaml.
    parses and gathers the settings for barcode flavors
    """
    preprocess_settings = {}
    for flavor, flavor_settings in config['barcode_flavors'].items():
        # for each flavor, also retrieve the configuration
        # first make a copy of the default values
        d = dict(bc_default_settings)
        d.update(flavor_settings)
        preprocess_settings[flavor] = dotdict(d)

    res = dotdict(
        dict(
            preprocess_settings=preprocess_settings,
        )
    )

    return res

# all barcode flavor info from config.yaml
# is kept here for convenient lookup
bc_flavor_data = parse_barcode_flavors(config)

def get_bc_preprocess_settings(wildcards):
    """
    This function will return a dictionary of information
    on the read1 preprocessing, according to barcode_flavor
    """
    flavor = project_df.get_metadata('barcode_flavor', project_id = wildcards.project,
            sample_id = wildcards.sample)
    if flavor not in bc_flavor_data.preprocess_settings:
        raise Exception(flavor)

    settings = bc_flavor_data.preprocess_settings[flavor]

    return settings

def get_demux_indicator(wildcards):
    demux_dir = project_df.get_metadata(
        "demux_dir", sample_id=wildcards.sample, project_id=wildcards.project
    )

    return expand(demux_indicator, demux_dir=demux_dir)


def get_star_input_bam(wildcards):
    if wildcards.polyA_adapter_trimmed == '.polyA_adapter_trimmed':
        return {'reads': tagged_polyA_adapter_trimmed_bam}
    else:
        return {'reads': tagged_bam}

def get_final_bam(wildcards):
    is_merged = project_df.get_metadata('is_merged',
        project_id = wildcards.project,
        sample_id = wildcards.sample)

    if is_merged:
        return [final_merged_bam]
    else:
        return [final_bam]

def get_dge_input_bam(wildcards):
    is_merged = project_df.get_metadata('is_merged',
        project_id = wildcards.project,
        sample_id = wildcards.sample)

    if wildcards.mm_included == '.mm_included':
        out = {'reads': final_bam_mm_included_pipe}
    else:
        out = {'reads': get_final_bam(wildcards)}

    return out

def get_species_genome_annotation(wildcards):
    # This function will return 2 things required by STAR:
    #    - annotation (.gtf file)
    #    - genome (.fa file)
    if 'species' not in wildcards.keys():
        species = project_df.get_metadata(
            "species", project_id=wildcards.project, sample_id=wildcards.sample
        )
    else:
        species = wildcards.species

     
    files = project_df.config.get_variable('species', name=species)
    
    return files

def get_star_index(wildcards):
    # This function will return 1 things required by STAR:
    #    - index directory
    species = project_df.get_metadata(
        "species", project_id=wildcards.project, sample_id=wildcards.sample
    )
    return {'index': expand(star_index, species = species)[0]}

def get_rRNA_genome(wildcards):
    files = project_df.config.get_variable('species', name=species)

    return [files['rRNA_genome']]

def get_bt2_rRNA_index(wildcards):
    species = project_df.get_metadata(
        "species", project_id=wildcards.project, sample_id=wildcards.sample
    )

    files = project_df.config.get_variable('species', name=species)

    if 'rRNA_genomes' in files:
        return {'index': expand(bt2_rRNA_index_dir, species = species)[0]}
    
    return []

def get_run_modes_from_sample(project_id, sample_id):
    run_mode_names = project_df.get_metadata('run_mode', project_id=project_id, sample_id=sample_id)
    
    run_modes = {}

    for run_mode in run_mode_names:
        run_modes[run_mode] = project_df.config.get_run_mode(run_mode)\
            .variables

    return run_modes

def get_dge_extra_params(wildcards):
    dge_type = wildcards.dge_type

    extra_params = ""

    if dge_type == ".exon":
        extra_params = ""
    elif dge_type == ".intron":
        extra_params = "LOCUS_FUNCTION_LIST=null LOCUS_FUNCTION_LIST=INTRONIC"
    elif dge_type == ".all":
        extra_params = "LOCUS_FUNCTION_LIST=INTRONIC"
    if dge_type == ".Reads_exon":
        extra_params = "OUTPUT_READS_INSTEAD=true"
    elif dge_type == ".Reads_intron":
        extra_params = "OUTPUT_READS_INSTEAD=true LOCUS_FUNCTION_LIST=null"+\
                "LOCUS_FUNCTION_LIST=INTRONIC"
    elif dge_type == ".Reads_all":
        extra_params = "OUTPUT_READS_INSTEAD=true LOCUS_FUNCTION_LIST=INTRONIC"

    if wildcards.mm_included == '.mm_included':
        extra_params = extra_params + " READ_MQ=0"

    return extra_params

def get_files_to_merge(pattern, project, sample, **kwargs):
    # recursive function to find all files to merge. a merged sample can be merged
    # from merged samples. to avoid cyclic dependencies, here we look for all files
    # which are the dependencies of the underlying samples
    is_merged = project_df.get_metadata('is_merged',
        project_id = project,
        sample_id = sample)

    files = []

    if not is_merged:
        files = expand(pattern, sample=sample, project=project, **kwargs)
    else:
        merge_ix = project_df.get_metadata('merged_from',
            sample_id = sample,
            project_id = project)

        for (p, s) in merge_ix:
            files = files + get_files_to_merge(project = p, sample = s, pattern = pattern, **kwargs)

    return list(set(files))

def get_files_to_merge_snakemake(pattern):
    # inner function to be returned
    def get_merged_pattern(wildcards):
        kwargs = {}
        
        # konvert wildcards to dict
        for key, value in wildcards.items():
            kwargs[key] = value

        files = get_files_to_merge(pattern = pattern, **kwargs)
        
        return files

    return get_merged_pattern

def get_ribo_depletion_log(wildcards):
    is_merged = project_df.get_metadata('is_merged',
        sample_id = wildcards.sample,
        project_id = wildcards.project)

    if is_merged:
        return [merged_ribo_depletion_log]
    else:
        return [ribo_depletion_log]

def get_top_barcodes(wildcards):
    if wildcards.n_beads == 'spatial':
        return {"top_barcodes": spatial_barcodes}
    if wildcards.dge_cleaned == "":
        return {"top_barcodes": top_barcodes}
    else:
        return {'top_barcodes': top_barcodes_clean}

def get_dge_from_run_mode(
        project_id,
        sample_id,
        run_mode
    ):
    run_mode_variables = project_df.config.get_run_mode(run_mode).variables
    
    dge_type = '.exon'
    dge_cleaned = ''
    polyA_adapter_trimmed = ''
    mm_included = ''

    if run_mode_variables['polyA_adapter_trimming']:
        polyA_adapter_trimmed = '.polyA_adapter_trimmed'

    if run_mode_variables['count_intronic_reads']:
        dge_type = '.all'

    if run_mode_variables['count_mm_reads']:
        mm_included = '.mm_included'

    if run_mode_variables['clean_dge']:
        dge_cleaned = '.cleaned'

    # select which pattern
    # if sample is not spatial, we simply select the normal, umi_filtered
    # dge, with the top_n barcodes
    # otherwise, if sample is spatial, either we return he whole dge, containing
    # all beads, or the a meshgrid
    if not project_df.is_spatial(project_id = project_id,\
            sample_id = sample_id):
        dge_out_pattern = dge_out_h5ad
        dge_out_summary_pattern = dge_out_h5ad_obs
    elif run_mode_variables['mesh_data']:
        dge_out_pattern = dge_spatial_mesh
        dge_out_summary_pattern = dge_spatial_mesh_obs
    else:
        dge_out_pattern = dge_spatial
        dge_out_summary_pattern = dge_spatial_obs

    dge_out_file = expand(dge_out_pattern,
            project = project_id,
            sample = sample_id,
            dge_type = dge_type,
            dge_cleaned = dge_cleaned,
            polyA_adapter_trimmed = polyA_adapter_trimmed,
            mm_included = mm_included,
            n_beads = run_mode_variables['n_beads'],
            spot_diameter_um = run_mode_variables['mesh_spot_diameter_um'],
            spot_distance_um = run_mode_variables['mesh_spot_distance_um'])

    dge_out_summary_file = expand(dge_out_summary_pattern,
            project = project_id,
            sample = sample_id,
            dge_type = dge_type,
            dge_cleaned = dge_cleaned,
            polyA_adapter_trimmed = polyA_adapter_trimmed,
            mm_included = mm_included,
            spot_diameter_um = run_mode_variables['mesh_spot_diameter_um'],
            spot_distance_um = run_mode_variables['mesh_spot_distance_um'],
            n_beads = run_mode_variables['n_beads'])

    return {'dge_summary': dge_out_summary_file,
            'dge': dge_out_file}


def get_qc_sheet_input_files(wildcards):
    # returns star_log, reads_type_out, strand_info
    # first checks the run modes, and returns either polyA_adapter_trimmed, untrimmed
    # or both
    project_id = wildcards.project
    sample_id = wildcards.sample

    is_merged = project_df.get_metadata('is_merged',
        project_id = wildcards.project,
        sample_id = wildcards.sample)

    run_modes = get_run_modes_from_sample(wildcards.project, wildcards.sample)

    is_polyA_adapter_trimmed = set([x['polyA_adapter_trimming'] for x in run_modes.values()])

    # if sample has both polyA trimmed and untrimmed mapped bam files
    if len(is_polyA_adapter_trimmed) == 2:
        polyA_adapter_trimmed_wildcard = ['', '.polyA_adapter_trimmed']
    elif True in is_polyA_adapter_trimmed:
        polyA_adapter_trimmed_wildcard = ['.polyA_adapter_trimmed']
    elif False in is_polyA_adapter_trimmed:
        polyA_adapter_trimmed_wildcard = ['']

    extra_args = {'sample': wildcards.sample,
                  'project': wildcards.project,
                  'polyA_adapter_trimmed': polyA_adapter_trimmed_wildcard}

    if is_merged:
        star_log_pattern = merged_star_log_file
    else:
        star_log_pattern = star_log_file

    to_return = {
        'star_log': expand(star_log_pattern, **extra_args),
        'reads_type_out': expand(reads_type_out, **extra_args),
        'strand_info': expand(strand_info, **extra_args)}

    for run_mode in run_modes:
        run_mode_dge = get_dge_from_run_mode(project_id, sample_id, run_mode)

        to_return[f'{run_mode}.dge_summary'] = run_mode_dge['dge_summary']

    return to_return

def get_bam_tag_names(project_id, sample_id):
    barcode_flavor = project_df.get_metadata('barcode_flavor', project_id = project_id,
            sample_id = sample_id)

    bam_tags = config["barcode_flavors"][barcode_flavor]["bam_tags"]

    tag_names = {}

    for tag in bam_tags.split(","):
        tag_name, tag_variable = tag.split(":")

        tag_names[tag_variable] = tag_name

    return tag_names

def get_puck_file(wildcards):
    if not project_df.is_spatial(project_id = wildcards.project,\
            sample_id = wildcards.sample):
        return []

    puck_barcode_file = project_df.get_metadata('puck_barcode_file',
            project_id = wildcards.project,
            sample_id = wildcards.sample)

    puck = project_df.get_metadata('puck',
        project_id = wildcards.project,
        sample_id = wildcards.sample)

    if puck_barcode_file == "none":
        return {'barcode_file' :config['pucks'][puck]['barcodes']}
    else:
        return {"barcode_file": puck_barcode_file}

def get_automated_analysis_dge_input(wildcards):
    # there are three options:
    # 1) no spatial dge
    # 2) spatial dge, no mesh
    # 3) spatial dge with a mesh
    return [get_dge_from_run_mode(
        project_id = wildcards.project,
        sample_id = wildcards.sample,
        run_mode = wildcards.run_mode)['dge']]
