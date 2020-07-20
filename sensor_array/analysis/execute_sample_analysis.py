import copy
import csv
import numpy as np
import os

import sample_analysis as sa


# ========= TEST SECTION ==========
"""
To Do list

-Write a function which reads the results from predicted breath Samples
-Visualize results in a way which makes sense
    - All samples (1-48), separated by component (4 plots total)
    - Same for true comp vs. simulated comp.
-Decide healthy/diseased cutoff & create a convolution matrix
-Generally, look for trends in data
    -When do we over/under predict ammonia (high/low CO2?)
    -Minimum and maximum deviation
    -After what percent cutoff do we stray from true comp
    -Should 'fraction_to_keep' be varied
        Since points start to cluster you can relax how many points to keep
    -Try other arrys/array Sizes
    -Vary Corys method to weight results by certain gas

"""

"""
Overall Procedure:
    1. Evaluate / normalize element probability
    2. Evaluate / normalize array probability
    3. Re-order compositions by probability (high to low)
    4. Keep top points / create new grid
        4.1 Remove duplicate Points
        4.2 Reformat as dict
    5. Repeat from Step 1
"""

# ===== Load Relevant Information =====
# config_file = mofs_filepath = sys.argv[1]
config_file = 'config_files/sample_analysis_config_tests.yaml'
data = sa.yaml_loader(config_file)

materials_config_file = data['materials_config_filepath']
materials_data = sa.yaml_loader(materials_config_file)
mof_list = materials_data['mof_list']

gases_full = data['gases']
gases = list(data['gases'].keys())
henrys_data_filepath = data['henrys_data_filepath']
breath_samples_filepath = data['breath_samples_filepath']
convergence_limits = {gas: gases_full[gas]['convergence_limits'] for gas in gases}
init_composition_limits = [gases_full[gas]['init_composition_limits'] for gas in gases]
init_composition_spacing = [gases_full[gas]['init_composition_spacing'] for gas in gases]

algorithm_type = data['algorithm_type']
array = data['array']
array_size = data['array_size']
array_index = data['array_index']
sample_types = data['sample_types']
true_comp_at_start = data['true_comp_at_start']
breath_samples_variation = data['breath_samples_variation']
fraction_to_keep = data['fraction_to_keep']
error_type_for_pmf = data['error_type_for_pmf']
error_amount_for_pmf = data['error_amount_for_pmf']
num_samples_to_test = data['num_samples_to_test']
num_cycles = data['num_cycles']
added_error_value = data['added_error_value']
seed_value = data['seed_value']
results_filepath = data['results_filepath']

# ----- Create filepath if it does not exist -----
if os.path.exists(results_filepath) != True:
    os.mkdir(results_filepath)


# ----- Load Henry's Coefficient Data ----
data_hg_all, data_air_all, data_combo_all = sa.load_henrys_data(henrys_data_filepath, gases)
mof_list_filtered, data_combo_avg = sa.filter_mof_list_and_average_pure_air_masses(mof_list, data_combo_all, min_allowed_comp=0.05)
data_hg_reformatted, data_air_reformatted, data_combo_reformatted = sa.reformat_henrys_data(mof_list_filtered, data_hg_all, data_air_all, data_combo_avg)
henrys_data = data_combo_reformatted
mof_list = mof_list_filtered

# ----- Create initial grid of points as a dictionary -----
if algorithm_type == 'scipy':
    gases_w_air = gases+['Air']
    comps_by_component, comps_raw = sa.create_uniform_comp_list(gases_w_air, init_composition_limits, init_composition_spacing, imply_final_gas_range=False, filter_for_1=False, round_at=None)
    comps_as_dict = sa.comps_to_dict(comps_raw, gases)
elif algorithm_type == 'tensorflow':
    comps_by_component, comps_raw = sa.create_uniform_comp_list(gases, init_composition_limits, init_composition_spacing, imply_final_gas_range=False, filter_for_1=False, round_at=None)
    comps_as_dict = sa.comps_to_dict(comps_raw, gases)

# ----- Determine array if necessary -----
if array == None:
    list_of_arrays = sa.calculate_all_arrays_list(mof_list_filtered, array_size)
    array = list_of_arrays[array_index]

henrys_data_array = {key: henrys_data[key] for key in array}


# ----- Run Prediction Algorithm for Breath Samples! -----

print('Beginning Analysis!')
print('Convergence Limits = ', convergence_limits)

# Clean up this loop
for sample_type in sample_types:

    # ----- Load Breath Samples -----
    _, all_breath_samples_joined = sa.load_breath_samples_alt(breath_samples_filepath)

    # ========== Limit Breath Sample Range for Testing ==========
    all_breath_samples_joined = all_breath_samples_joined[0:num_samples_to_test]

    results_filename = 'breath_sample_prediciton_'+sample_type+'.csv'
    results_fullpath = results_filepath+results_filename
    sample_filename = 'breath_sample_'+sample_type+'.csv'
    sample_fullpath = results_filepath+sample_filename
    settings_filename = 'settings_'+sample_type+'.csv'
    settings_fullpath = results_filepath+settings_filename

    with open(settings_fullpath, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, delimiter='\t', quotechar='|', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['Sample Types = ', sample_type])
        writer.writerow(['Sample Modifications = ', breath_samples_variation])
        writer.writerow(['Added Error = ', added_error_value, 'mg/g framework'])
        writer.writerow(['Random Seed for Error = ', seed_value])
        writer.writerow(['True Comp at Start = ', true_comp_at_start])
        writer.writerow(['Gas Limits = ', init_composition_limits])
        writer.writerow(['Gas Spacing = ', init_composition_spacing])
        writer.writerow(['Number of Initial Comps. = ', len(comps_as_dict)])
        writer.writerow(['Fraction of Comps. Retained = ', fraction_to_keep])
        writer.writerow(['Error Type for Probability = ', error_type_for_pmf])
        writer.writerow(['Error Amount for Probability = ', error_amount_for_pmf])
        writer.writerow(['Convergence Limits = ', convergence_limits])

    # Make Folder to Add Plots to
    folder = sample_type+'/'
    os.mkdir(results_filepath+folder)

    # ----- Loop over all breath samples -----
    for i in range(len(all_breath_samples_joined)):

        print('Breath Sample = ', i)

        # Load single breath sample
        breath_sample = all_breath_samples_joined[i]
        run_id = breath_sample['Run ID New']

        # Get true comp and predicted mass
        gases_for_true_comp = gases+['N2', 'O2']
        true_comp = sa.get_true_composoition(breath_sample, gases_for_true_comp)
        true_comp_values = [true_comp[gas+'_comp'] for gas in gases]

        # Create copy of initial composition set, Add true comp explicitly if desired
        if algorithm_type == 'scipy':
            comps = copy.deepcopy(comps_as_dict)
        else:
            comps = copy.deepcopy(comps_raw)
        if true_comp_at_start == 'yes':
            if algorithm_type == 'scipy':
                comps.extend([true_comp])
            elif algorithm_type =='tensorflow':
                comps.extend([true_comp_values])

        # Alter breath sample if desired
        gases_temp = gases+['Air']
        predicted_mass = sa.check_prediciton_of_known_comp(data_hg_reformatted, data_air_reformatted, data_combo_reformatted, gases_temp, mof_list_filtered, true_comp)
        if breath_samples_variation == 'perfect':
            perfect_breath_sample = sa.format_predicted_mass_as_breath_sample(predicted_mass, true_comp, run_id, random_error=False)
            breath_sample = perfect_breath_sample
        elif breath_samples_variation == 'almost perfect':
            almost_perfect_breath_sample = sa.format_predicted_mass_as_breath_sample(predicted_mass, true_comp, run_id, random_error=added_error_value, random_seed=seed_value)
            breath_sample = almost_perfect_breath_sample
        breath_sample_masses = [breath_sample[mof] for mof in array]

        if algorithm_type == 'scipy':
            final_comp_set, exit_condition, cycle_nums, all_comp_sets, _, _  = sa.composition_prediction_algorithm(array, henrys_data_array, gases_temp, comps, init_composition_spacing, convergence_limits, breath_sample, num_cycles=num_cycles, pmf_convergence=1, fraction_to_keep=fraction_to_keep, error_type='fixed', error_amount=error_amount_for_pmf)
        elif algorithm_type == 'tensorflow':
            final_comp_set, exit_condition, cycle_nums, all_comp_sets, all_array_pmfs_nnempf, all_array_pmfs_normalized  = sa.composition_prediction_algorithm_new(array, henrys_data_array, gases, comps, init_composition_spacing, convergence_limits, breath_sample_masses, num_cycles=num_cycles, fraction_to_keep=fraction_to_keep, std_dev=error_amount_for_pmf)


        # Write Final Results to File
        if i == 0:
            with open(results_fullpath, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile, delimiter='\t', quotechar='|', quoting=csv.QUOTE_MINIMAL)
                writer.writerow(['Run ID', 'Exit Condition', 'Predicted Comp.', 'True Comp.'])
                writer.writerow([breath_sample['Run ID New']])
                writer.writerow(['Exit Status = ', exit_condition])
                writer.writerow([final_comp_set])
                writer.writerow([true_comp])
            with open(sample_fullpath, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile, delimiter='\t', quotechar='|', quoting=csv.QUOTE_MINIMAL)
                writer.writerow([breath_sample['Run ID New']])
                writer.writerow([breath_sample])
                writer.writerow([])
        else:
            with open(results_fullpath, 'a', newline='') as csvfile:
                writer = csv.writer(csvfile, delimiter='\t', quotechar='|', quoting=csv.QUOTE_MINIMAL)
                writer.writerow([breath_sample['Run ID New']])
                writer.writerow(['Exit Status = ', exit_condition])
                writer.writerow([final_comp_set])
                writer.writerow([true_comp])
            with open(sample_fullpath, 'a', newline='') as csvfile:
                writer = csv.writer(csvfile, delimiter='\t', quotechar='|', quoting=csv.QUOTE_MINIMAL)
                writer.writerow([breath_sample['Run ID New']])
                writer.writerow([breath_sample])
                writer.writerow([])

        # Write and Plot Results for Single Breath Sample
        full_sample_filepath = results_filepath+folder+'Sample_'+str(run_id)+'/'
        os.mkdir(full_sample_filepath)

        # Write cycle results
        cycle_results_filename = 'Sample'+str(run_id)+'.csv'
        cycle_results_fullpath = full_sample_filepath+cycle_results_filename
        with open(cycle_results_fullpath, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile, delimiter='\t', quotechar='|', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(['Cycle Nums.', *[gas for gas in gases]])
            for n in range(len(cycle_nums)):
                writer.writerow([cycle_nums[n], *[all_comp_sets[gas][n]for gas in gases]])

        # Use to see how the range of compositions evolved over each cycle - Make a function for this later.
        filepath_for_this_figure = full_sample_filepath
        sa.plot_algorithm_progress_single_samples(gases, all_comp_sets, true_comp, cycle_nums, run_id, filepath_for_this_figure)

        # Analyze Probability / KLD
        # This step is incredibly slow due to the RAM needs of large arrays - Need to add a file which we write to / read for the array_pmf values to speed up whti process.
        # Also need to add plot limits
        norm_factor = sa.calculate_p_max(len(array), error_amount_for_pmf)
        all_array_pmfs_nnempf_mod = [[value/norm_factor for value in row] for row in all_array_pmfs_nnempf]
        sa.plot_kld_progression_w_max_pmf(all_array_pmfs_nnempf_mod, all_array_pmfs_normalized, cycle_nums, figname=full_sample_filepath)
        sa.plot_all_array_pmf(all_array_pmfs_nnempf_mod, figname=full_sample_filepath)


    # ----- Reload saved results -----
    results_fullpath = results_filepath+'breath_sample_prediciton_'+sample_type+'.csv'

    keys, results = sa.import_prediction_data(results_fullpath)
    run_ids = [row[keys[0]] for row in results]
    predicted_comps = [row[keys[2]] for row in results]
    true_comps = [row[keys[3]] for row in results]

    gas_limits_as_dict = {gas: gases_full[gas]['init_composition_limits'] for gas in gases}
    sa.plot_predicted_vs_true_for_all_breath_samples(gases, gas_limits_as_dict, predicted_comps, true_comps, filepath=results_filepath+folder, sort_data=True, sort_by='ammonia')
    sa.plot_prediction_error_for_all_breath_samples(gases, predicted_comps, true_comps, filepath=results_filepath+folder)



# Write a function which keeps track of all compositions, bin them in the end and calculate KLD?
# Need to do this on a component basis
# NON BOUNDED LIKELIHOOD VALUE, NORMALIZE ONLY AFTER ENTIRE RUN IS COMPLETE, THEN BIN, THEN REUSE KLD
# Would need to eliminate double counted points (i.e. anything retained for 2+ cycles)
