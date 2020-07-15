# Code for caluclating the Henry's Constants for a variety of gas mixutres.

import ast
import copy
import csv
import glob
import itertools
import math
import matplotlib
import numpy as np
import os
import random
import re
import scipy.stats as ss
import yaml

from collections import OrderedDict
import matplotlib as mpl
from matplotlib import pyplot as plt

import time
import tensorflow as tf
import tensorflow_probability as tfp


# ----- General Use -----
def yaml_loader(filepath):
    with open(filepath, 'r') as yaml_file:
        data = yaml.load(yaml_file)
    return data


def import_simulated_data(sim_results, sort_by_gas=False, gas_for_sorting=None):
    with open(sim_results) as file:
        reader = csv.DictReader(file, delimiter='\t')
        reader_list = list(reader)
        keys = reader.fieldnames

        for row in reader_list:
            # Isolate Mass Data since currently being assigned to single key
            mass_data_temp = [float(val) for val in row[keys[2]].split(' ')]
            num_gases = len(row)-len(mass_data_temp)-2
            # Reassign Compositions
            for i in range(num_gases):
                row[keys[-num_gases+i]] = row[keys[i+3]]
            # Reassign Masses
            for i in range(num_gases*2+2):
                row[keys[i+2]] = mass_data_temp[i]

        if sort_by_gas == True:
            reader_list = sorted(reader_list, key=lambda k: k[gas_for_sorting+'_comp'], reverse=False)

        return keys, reader_list


# ----- Prediciting Compositions -----
def load_henrys_data(figure_path, gases):
    data_hg_all = []
    data_air_all = []
    data_combo_all = []
    for gas in gases:
        filename_hg = '/Users/brian_day/Desktop/HC_Work/HenrysConstants_Analysis_Results/'+str(gas)+'_AllRatios/_henrys_coefficients_hg.csv'
        filename_air = '/Users/brian_day/Desktop/HC_Work/HenrysConstants_Analysis_Results/'+str(gas)+'_AllRatios/_henrys_coefficients_air.csv'
        data_hg = read_kH_results(filename_hg)
        data_air = read_kH_results(filename_air)
        data_hg_all.extend([data_hg])
        data_air_all.extend([data_air])

        data_combo_temp = []
        for row_hg in data_hg:
            row_combo_temp = {}
            for row_air in data_air:
                if row_hg['MOF'] == row_air['MOF']:
                    row_combo_temp['Gas'] = row_hg['Gas']
                    row_combo_temp['MOF'] = row_hg['MOF']
                    row_combo_temp['Maximum Composition'] = row_hg['Maximum Composition']
                    row_combo_temp['Pure Air Mass'] = row_air['Pure Air Mass']
                    if row_hg['k_H'] != None and row_air['k_H'] != None:
                        # Should be minus KH air since we fit it for increasing air, not increasing henry's gas (i.e. decreasing air).
                        row_combo_temp['k_H'] = row_hg['k_H']-row_air['k_H']
                    else:
                        row_combo_temp['k_H'] = None
            if row_combo_temp != {}:
                data_combo_temp.extend([row_combo_temp])
        data_combo_all.extend([data_combo_temp])

    return data_hg_all, data_air_all, data_combo_all


def filter_mof_list_and_average_pure_air_masses(mof_list, data_combo_all, min_allowed_comp=0.05):
    data_combo_avg = []
    for mof in mof_list:
        temp_collection = []
        for array in data_combo_all:
            for row in array:
                if row['MOF'].split('_')[0] == mof:
                    temp_collection.extend([row])

        max_comps = [row['Maximum Composition'] for row in temp_collection]

        if min(max_comps) < min_allowed_comp:
            continue

        pure_air_mass_all = []
        for row in temp_collection:
            if row['Pure Air Mass'] != None:
                pure_air_mass_all.extend([row['Pure Air Mass']])

        pure_air_mass_average = sum(pure_air_mass_all)/len(pure_air_mass_all)
        for row in temp_collection:
            if row['Pure Air Mass'] != None:
                row['Pure Air Mass'] = pure_air_mass_average

        data_combo_avg.extend([temp_collection])

    mof_list_filtered = [row[0]['MOF'].split('_')[0] for row in data_combo_avg]

    return mof_list_filtered, data_combo_avg


def reformat_henrys_data(mof_list_filtered, data_hg_all, data_air_all, data_combo_avg):
    data_hg_reformatted = {}
    for mof in mof_list_filtered:
        temp_dict_manual = {}
        for array in data_hg_all:
            for row in array:
                if row['MOF'].split('_')[0] == mof:
                    gas = row['Gas']
                    temp_dict_manual[gas+'_kH'] = row['k_H']
        data_hg_reformatted[mof] = temp_dict_manual

    data_air_reformatted = {}
    for mof in mof_list_filtered:
        temp_dict_manual = {}
        for array in data_air_all:
            for row in array:
                if row['MOF'].split('_')[0] == mof:
                    gas = row['Gas']
                    temp_dict_manual[gas+'_kH'] = row['k_H']
        data_air_reformatted[mof] = temp_dict_manual

    data_combo_reformatted = {}
    for mof in mof_list_filtered:
        temp_dict_manual = {}
        for array in data_combo_avg:
            for row in array:
                if row['MOF'].split('_')[0] == mof:
                    temp_dict_manual['Pure Air Mass'] = row['Pure Air Mass']
                    gas = row['Gas']
                    temp_dict_manual[gas+'_kH'] = row['k_H']
        data_combo_reformatted[mof] = temp_dict_manual

    return data_hg_reformatted, data_air_reformatted, data_combo_reformatted


def create_pseudo_simulated_data_from_dict(mof_list, comps, gases, henrys_data):

    psd_dict = copy.deepcopy(comps)

    for row in psd_dict:
        for mof in mof_list:
            mass = 0
            for gas in gases:
                if gas == 'Air':
                    mass += henrys_data[mof]['Pure Air Mass']
                else:
                    mass += henrys_data[mof][gas+'_kH']*row[gas+'_comp']
            row[mof] = mass

    return psd_dict


def create_pseudo_simulated_data_from_array(mof_list, comps, gases, henrys_data):

    masses_pure_air = [henrys_data[mof]['Pure Air Mass'] for mof in mof_list]
    khs = [[henrys_data[mof][gas+'_kH'] for gas in gases] for mof in mof_list]
    simulated_masses = [masses_pure_air + np.sum(np.multiply(khs, row), axis=1) for row in comps]

    return simulated_masses


def calculate_element_pmf(mof_list, simulated_data, breath_sample, error_type='fixed', error_amount=0.01):

    element_pmf  = copy.deepcopy(simulated_data)
    counter = 0
    for row in element_pmf:
        # Added counter to monitor speed
        counter += 1
        if int(counter % 20000) == 0:
            print('\t',counter)
        # Calculate Probability
        for mof in mof_list:
            exp_mass = breath_sample[mof]
            exp_error = breath_sample[mof+'_error']
            sim_mass = row[mof]

            # Create distribution and calculate PMF
            a, b = 0, np.inf
            if error_type == 'fixed':
                mu, sigma = float(exp_mass), float(error_amount)
            elif error_type == 'relative':
                mu, sigma = float(exp_mass), float(exp_error)
            else:
                raise(NameError('Invalid Error Type!'))
            alpha, beta = ((a-mu)/sigma), ((b-mu)/sigma)

            prob_singlepoint = ss.truncnorm.pdf(float(sim_mass), alpha, beta, loc=mu, scale=sigma)
            row[mof+'_pmf'] = prob_singlepoint

    # Normalize Probabilities
    norm_factor_dict = {mof:0 for mof in mof_list}

    for row in element_pmf:
        for mof in mof_list:
            norm_factor_dict[mof] += row[mof+'_pmf']

    for row in element_pmf:
        for mof in mof_list:
            row[mof+'_pmf'] = row[mof+'_pmf'] / norm_factor_dict[mof]

    return element_pmf


def calculate_array_pmf(element_pmf, array, comps):
    array_pmf = copy.deepcopy(element_pmf)

    for row in array_pmf:
        array_pmf_temp = 1
        for mof in array:
            array_pmf_temp *= row[mof+'_pmf']
        row['Array_pmf'] = array_pmf_temp

    norm_factor_array = np.sum([row['Array_pmf'] for row in array_pmf])
    if norm_factor_array > 0:
        for row in array_pmf:
            row['Array_pmf'] = row['Array_pmf']/norm_factor_array
    else:
        raise(NameError('Total Array Probability 0. Check breath sample and error type/value.'))

    array_pmf_sorted = sorted(array_pmf, key=lambda k: k['Array_pmf'], reverse = True)

    return array_pmf, array_pmf_sorted


def calculate_element_and_array_pmf_tf(simulated_masses, breath_sample_masses, std_dev=0.01):

    distributions = tfp.distributions.TruncatedNormal(simulated_masses, std_dev, 0, np.inf)
    element_pmfs = distributions.prob(breath_sample_masses)
    element_norm_factors = 1/np.sum(element_pmfs, axis=0)
    element_pmfs_normalized = np.multiply(element_norm_factors, element_pmfs)

    array_pmfs = np.prod(element_pmfs_normalized, axis=1)
    array_norm_factor = 1/np.sum(array_pmfs, axis=0)
    array_pmfs_normalized = np.multiply(array_norm_factor, array_pmfs)

    array_pmfs_normalized_sorted = sorted(array_pmfs_normalized, reverse=True)
    sorted_indicies = list(reversed(np.argsort(array_pmfs_normalized)))

    return element_pmfs_normalized, array_pmfs_normalized, array_pmfs_normalized_sorted, sorted_indicies


def subdivide_grid_from_dict(array_pmf_sorted, gases, spacing):

    # old_points_to_keep = array_pmf_sorted[0:int(np.ceil(len(array_pmf_sorted)*fraction_to_keep))]
    old_points_to_keep = array_pmf_sorted
    new_grid_points = []

    for point in old_points_to_keep:
        old_point = [point[gas+'_comp'] for gas in gases if gas != 'Air']
        new_points_by_component = []
        for i in range(len(old_point)):
            temp_set = []
            temp_set.extend([old_point[i]])
            if old_point[i]+spacing[i] <= 1:
                temp_set.extend([old_point[i]+spacing[i]])
            if old_point[i]-spacing[i] >= 0:
                temp_set.extend([old_point[i]-spacing[i]])
            new_points_by_component.extend([temp_set])
        new_grid_points_temp = list(itertools.product(*new_points_by_component))
        new_grid_points.extend(new_grid_points_temp)

    # Remove Duplicate Points
    new_grid_points = list(set(new_grid_points))

    # Reformat New Grid Points as Dict
    gases_wout_air = [gas for gas in gases if gas != 'Air']
    grid_as_dict = []
    for point in new_grid_points:
        temp_dict = {}
        for i in range(len(gases_wout_air)):
            temp_dict[gases_wout_air[i]+'_comp'] = point[i]
        grid_as_dict.extend([temp_dict])

    for row in grid_as_dict:
        total_comp = 0
        for gas in gases:
            if gas != 'Air':
                total_comp += row[gas+'_comp']
        row['Air_comp'] = 1-total_comp

    new_grid_points = grid_as_dict

    return new_grid_points


def subdivide_grid_from_array(comps, gases, spacing):

    new_grid_points = []
    for point in comps:
        new_points_by_component = []
        for i in range(len(point)):
            temp_set = []
            temp_set.extend([point[i]])
            if point[i]+spacing[i] <= 1:
                temp_set.extend([point[i]+spacing[i]])
            if point[i]-spacing[i] >= 0:
                temp_set.extend([point[i]-spacing[i]])
            new_points_by_component.extend([temp_set])
        new_grid_points_temp = list(itertools.product(*new_points_by_component))
        new_grid_points.extend(new_grid_points_temp)

    # Remove Duplicate Points
    new_grid_points = list(set(new_grid_points))

    return new_grid_points


def bin_compositions_by_convergence_status(comps, gases, convergence_status, array_pmf):
    # Determine which gases are used to create bins
    gases_to_bin_by = []
    for gas in gases:
        if gas != 'Air' and convergence_status[gas] == False:
            gases_to_bin_by.extend([gas])

    # Create bins and convert to a dictionary fromat for clarity
    all_comps_by_gas = {gas:[] for gas in gases_to_bin_by}
    for gas in gases_to_bin_by:
        all_comps_by_gas[gas] = list(set([comp[gas+'_comp'] for comp in comps]))
    bins = list(itertools.product(*[all_comps_by_gas[gas] for gas in gases_to_bin_by]))
    bins_as_dict = [{gases_to_bin_by[i]:bin[i] for i in range(len(gases_to_bin_by))} for bin in bins]

    # Convert bins to tuples, and create list for storing full composition set, and for element/array pmf of bins
    bins_as_keys = [tuple(bin.items()) for bin in bins_as_dict]
    comps_by_bins = {key:[] for key in bins_as_keys}
    pmf_by_bins = {key:[] for key in bins_as_keys}
    bin_pmf_by_bins = {key:{mof:0 for mof in array} for key in bins_as_keys}

    # Assign compositions to bins
    for row in comps:
        bin_key = tuple({gas:row[gas+'_comp'] for gas in gases_to_bin_by}.items())
        comps_by_bins[bin_key].extend([row])

    # Assign probability data to bins
    for row in array_pmf:
        bin_key = tuple({gas:row[gas+'_comp'] for gas in gases_to_bin_by}.items())
        pmf_by_bins[bin_key].extend([row])

    # Determine bin pmf
    for key in bins_as_keys:
        bin_pmf_by_bins[key]['Array_PMF'] = 0
        for row in pmf_by_bins[key]:
            for mof in array:
                bin_pmf_by_bins[key][mof] += row[mof+'_pmf']
            bin_pmf_by_bins[key]['Array_PMF'] += row['Array_pmf']

    return comps_by_bins, pmf_by_bins, bin_pmf_by_bins


def filter_binned_comps_by_probability(comps_by_bins, pmf_by_bins, bin_pmf_by_bins, gases, fraction_to_keep=0.037):

    # Sort bin pmfs, and filter
    bin_pmf_by_bins_sorted = sorted(bin_pmf_by_bins.items(), key=lambda item: item[1]['Array_PMF'], reverse=True)
    bins_to_keep = [item[0] for item in bin_pmf_by_bins_sorted[0:int(np.ceil(len(bin_pmf_by_bins_sorted)*fraction_to_keep**0.5))] ]

    # Unbin remaining compositions, and filter by comp. pmf
    array_pmf_after_bin_filtering = [comp for bin in bins_to_keep for comp in pmf_by_bins[bin]]
    array_pmf_after_bin_filtering_sorted = sorted(array_pmf_after_bin_filtering, key=lambda k: k['Array_pmf'], reverse = True)
    comps_to_keep = array_pmf_after_bin_filtering_sorted[0:int(np.ceil(len(array_pmf_after_bin_filtering_sorted)*fraction_to_keep**0.5))]
    comps_to_keep_clean = [ {gas+'_comp':row[gas+'_comp'] for gas in gases} for row in comps_to_keep ]

    return comps_to_keep_clean


def filter_unbinned_comps_by_probability(array_pmf_sorted, gases, fraction_to_keep=0.037):

    # Unbin remaining compositions, and filter by comp. pmf
    # array_pmf_sorted = sorted(array_pmf, key=lambda k: k['Array_pmf'], reverse = True)
    comps_to_keep = array_pmf_sorted[0:int(np.ceil(len(array_pmf_sorted)*fraction_to_keep))]
    comps_to_keep_clean = [ {gas+'_comp':row[gas+'_comp'] for gas in gases} for row in comps_to_keep ]

    return comps_to_keep_clean


def check_prediciton_of_known_comp(henrys_data_no_air_effect, henrys_data_only_air_effect, henrys_data_combo, gases, mof_list, known_comp):

    # Create set of gases without Air
    gases_no_air = [gas for gas in gases if gas != 'Air']

    # Calculate the predicted mass (total and by component)
    predicted_mass = {}
    for mof in mof_list:
        temp_dict={}
        mass_temp = 0
        for gas in gases:
            # Get adsorbed mass of pure air mixture
            if gas == 'Air':
                mass_temp += henrys_data_combo[mof]['Pure Air Mass']
                temp_dict['Pure Air Mass'] = henrys_data_combo[mof]['Pure Air Mass']
                mass_temp_air_only = henrys_data_combo[mof]['Pure Air Mass']
                # Remove air displaced by other components
                for gas_2 in gases_no_air:
                    mass_temp_air_only += -henrys_data_only_air_effect[mof][gas_2+'_kH']*known_comp[gas_2+'_comp']
                temp_dict[gas+'_mass'] = mass_temp_air_only
            # Get adsorbed mass of Henry's Gases
            else:
                mass_temp += henrys_data_combo[mof][gas+'_kH']*known_comp[gas+'_comp']
                temp_dict[gas+'_mass'] = henrys_data_no_air_effect[mof][gas+'_kH']*known_comp[gas+'_comp']
            temp_dict['Total_mass'] = mass_temp

        predicted_mass[mof] = temp_dict

    return predicted_mass


def format_predicted_mass_as_breath_sample(predicted_mass, true_comp, run_id, random_error=False, random_seed=1):
    breath_sample = {}
    breath_sample['Run ID New'] = run_id
    np.random.seed(random_seed)
    for key in predicted_mass.keys():
        breath_sample[key] = predicted_mass[key]['Total_mass']
        if random_error != False:
            breath_sample[key+'_error'] = np.random.uniform(-1*random_error, random_error)
            breath_sample[key] += breath_sample[key+'_error']
        else:
            breath_sample[key+'_error'] = 0.0
    for key in true_comp.keys():
        breath_sample[key] = true_comp[key]

    return breath_sample


def check_prediciton_of_known_comp_range(henrys_data_no_air_effect, henrys_data_only_air_effect, henrys_data_combo, gases, mof_list, known_comp):

    # Create set of gases without Air
    gases_no_air = [gas for gas in gases if gas != 'Air']

    # Calculate the predicted mass (total and by component)
    predicted_mass = {}
    for mof in mof_list:
        temp_dict={}
        mass_temp_lb = 0
        mass_temp_ub = 0
        for gas in gases:

            # Get adsorbed mass of pure air mixture
            if gas == 'Air':
                temp_dict['Pure Air Mass'] = henrys_data_combo[mof]['Pure Air Mass']
                mass_temp_lb += henrys_data_combo[mof]['Pure Air Mass']
                mass_temp_ub += henrys_data_combo[mof]['Pure Air Mass']
                mass_temp_air_only_lb = henrys_data_combo[mof]['Pure Air Mass']
                mass_temp_air_only_ub = henrys_data_combo[mof]['Pure Air Mass']

                # Remove air displaced by other components
                for gas_2 in gases_no_air:
                    mass_temp_air_only_lb += -henrys_data_only_air_effect[mof][gas_2+'_kH']*max(known_comp[gas_2+'_comp'])
                    mass_temp_air_only_ub += -henrys_data_only_air_effect[mof][gas_2+'_kH']*min(known_comp[gas_2+'_comp'])
                temp_dict[gas+'_mass'] = [mass_temp_air_only_lb, mass_temp_air_only_ub]

            # Get adsorbed mass of Henry's Gases
            else:
                mass_temp_lb += henrys_data_combo[mof][gas+'_kH']*min(known_comp[gas+'_comp'])
                mass_temp_ub += henrys_data_combo[mof][gas+'_kH']*max(known_comp[gas+'_comp'])

                temp_dict[gas+'_mass'] = list(henrys_data_no_air_effect[mof][gas+'_kH']*np.array(known_comp[gas+'_comp']))

            temp_dict['Total_mass'] = [mass_temp_lb, mass_temp_ub]

        predicted_mass[mof] = temp_dict

    return predicted_mass


def isolate_mass_by_component(predicted_mass, simulated_mass, gases, mof_list):
    # Initialize Dict
    adsorbed_masses = {gas:[] for gas in gases}
    adsorbed_masses_error = {gas:[] for gas in gases}
    predicted_masses = {gas:[] for gas in gases}

    # Get experimental masses and errors
    for mof in mof_list_filtered:
        for gas in gases:
            if gas == 'Air':
                adsorbed_masses[gas].extend([simulated_mass[mof]['N2_mass']+simulated_mass[mof]['O2_mass']])
                adsorbed_masses_error[gas].extend([simulated_mass[mof]['N2_error']+simulated_mass[mof]['O2_error']])
            else:
                adsorbed_masses[gas].extend([simulated_mass[mof][gas+'_mass']])
                adsorbed_masses_error[gas].extend([simulated_mass[mof][gas+'_error']])

    # Get predicted masses
    for mof in mof_list_filtered:
        for gas in gases:
            predicted_masses[gas].extend([predicted_mass[mof][gas+'_mass']])

    # Total mass for experimental data
    adsorbed_mass_total = np.zeros(len(adsorbed_masses[gases[0]]))
    adsorbed_mass_error_total = np.zeros(len(adsorbed_masses_error[gases[0]]))
    for gas in gases:
        adsorbed_mass_total = np.add(adsorbed_mass_total, adsorbed_masses[gas])
        adsorbed_mass_error_total = np.add(adsorbed_mass_error_total, adsorbed_masses_error[gas])
    adsorbed_masses['Total'] = list(adsorbed_mass_total)
    adsorbed_masses_error['Total'] = list(adsorbed_mass_error_total)

    # Total mass for predicted data
    if len(predicted_masses[gases[0]][0]) == 1:
        predicted_mass_total = np.zeros(len(predicted_masses[gases[0]]))
        for gas in gases:
            predicted_mass_total = np.add(predicted_mass_total, predicted_masses[gas])
        predicted_masses['Total'] = list(predicted_mass_total)

    else:
        predicted_mass_total = np.zeros([len(predicted_masses[gases[0]]),2])
        for gas in gases:
            predicted_mass_total = np.add(predicted_mass_total, predicted_masses[gas])
        predicted_masses['Total'] = list(predicted_mass_total)

    return adsorbed_masses, adsorbed_masses_error, predicted_masses


def plot_predicted_mass_for_each_MOF(adsorbed_masses, adsorbed_masses_error, predicted_masses, gases, known_comp, mof_list, filepath=None, sample_number=None):

    gases_w_total = copy.deepcopy(gases)+['Total']
    for gas in gases_w_total:
        x = np.linspace(1,len(adsorbed_masses[gas]),len(adsorbed_masses[gas]))
        if gas != 'Total':
            bs_str = 'Mole Fraction = '+str(np.round(known_comp[gas+'_comp'],7))
        else:
            bs_str = 'Mole Fraction = 1'
        plt.figure(figsize=(5,5), dpi=600)
        plt.errorbar(x,adsorbed_masses[gas],adsorbed_masses_error[gas], marker='o', markersize=3, elinewidth=1, linewidth=0, alpha=0.7,label='Simulated')

        predicted_masses_midpoint = [0.5*np.sum(val) for val in predicted_masses[gas]]
        predicted_masses_error = [abs(0.5*np.subtract(*val)) for val in predicted_masses[gas]]
        plt.errorbar(x+0.25,predicted_masses_midpoint,predicted_masses_error, marker='o', markersize=3, elinewidth=1, linewidth=0, alpha=0.7,label='Predicted')

        plt.xticks(range(1,len(mof_list)+1), mof_list, rotation=45, ha='right', fontsize=8)
        plt.ylabel('Adsorbed Mass [mg/g Framework]')
        plt.grid(alpha=0.3)
        plt.legend(loc='upper left')
        if filepath != None:
            if sample_number != None:
                plt.title('Breath Sample #'+str(sample_number)+'\n'+gas+', '+bs_str)
                plt.tight_layout()
                plt.savefig(filepath+'Sample_'+str(sample_number)+'/'+gas+'_mass.png')
            else:
                plt.title(gas+'\n'+bs_str)
                plt.tight_layout()
                plt.savefig(filepath+gas+'_mass.png')
        plt.close()


def comps_to_dict(comps, gases):
    comps_as_dict = []
    for row in comps:
        temp_dict = {}
        for i in range(len(gases)):
            temp_dict[gases[i]+'_comp'] = row[i]
        comps_as_dict.extend([temp_dict])

    return comps_as_dict


def load_breath_samples(breath_filepath, mof_list_filtered):
    # N.B. Somehow, only 48 diseased breath samples...
    # 2 Breath samples had negative concentrations, and thus never ran - Fix this in create comps
    files = list(glob.glob(breath_filepath+'*/*.csv'))

    # Create a set of all breath samples for all mofs (from filtered list)
    all_breath_samples = []
    for file in files:
        mof = re.split('/|_', file)[-2]
        if mof == 'v2':
            mof = mof = re.split('/|_', file)[-3]
        if mof in mof_list_filtered:
            _, breath_sample = import_simulated_data(file)
            all_breath_samples.extend(breath_sample)

    # Join results of the same breath sample
    num_samples = int(len(all_breath_samples)/len(mof_list_filtered))
    all_breath_samples_joined = []
    run_id_new = 0
    for row in all_breath_samples[0:num_samples]:

        # Create a temp_dict to add all mof data too
        temp_dict = {}
        run_id_new += 1
        row['Run ID New'] = run_id_new
        temp_dict['Run ID New'] = run_id_new
        gases = ['argon', 'ammonia', 'CO2', 'N2', 'O2']
        for gas in gases:
            temp_dict[gas+'_comp'] = row[gas+'_comp']

        # Create a comp_dict to see if same sample
        comp_dict = {}
        gases = ['argon', 'ammonia', 'CO2', 'N2', 'O2']
        for gas in gases:
            comp_dict[gas+'_comp'] = row[gas+'_comp']

        # Check all subsequent rows for match
        for row_2 in all_breath_samples:
            # row_count += 1
            comp_dict_2 = {}
            gases = ['argon', 'ammonia', 'CO2', 'N2', 'O2']
            for gas in gases:
                comp_dict_2[gas+'_comp'] = row_2[gas+'_comp']

            if comp_dict == comp_dict_2:
                row_2['Run ID New'] = run_id_new
                mof = row_2['MOF'].split('_')[0]
                temp_dict[mof] = row_2['total_mass']
                temp_dict[mof+'_error'] = row_2['total_mass_error']

        all_breath_samples_joined.extend([temp_dict])

    return all_breath_samples, all_breath_samples_joined


def load_breath_samples_alt(filename):
    gases = ['Argon', 'Ammonia', 'CO2', 'N2', 'O2']
    new_keys = {'Argon': 'argon_comp', 'Ammonia': 'ammonia_comp', 'CO2': 'CO2_comp', 'N2': 'N2_comp', 'O2': 'O2_comp'}

    with open(filename) as file:
        reader = csv.DictReader(file, delimiter='\t')
        reader_list = list(reader)
        for i in range(len(reader_list)):
            reader_list[i]['Run ID New'] = int(i+1)
            for gas in gases:
                reader_list[i][new_keys[gas]] = reader_list[i].pop(gas)
        keys = reader.fieldnames

    return keys, reader_list


def reload_full_breath_sample(breath_sample, all_breath_samples):
    breath_sample_full = []
    for row in all_breath_samples:
        if row['Run ID New'] == breath_sample['Run ID New']:
            breath_sample_full .extend([row])

    return breath_sample_full


def reformat_full_breath_sample(breath_sample_full):
    breath_sample_full_reformatted = {}
    for row in breath_sample_full:
        breath_sample_full_reformatted[row['MOF'].split('_')[0]] = row

    return breath_sample_full_reformatted


def get_true_composoition(breath_sample, gases):
    # Isolate breath sample composition
    true_comp = {}
    for gas in gases:
        true_comp[gas+'_comp'] = float(breath_sample[gas+'_comp'])
    true_comp['Air_comp'] = true_comp['N2_comp']+true_comp['O2_comp']
    del true_comp['N2_comp']
    del true_comp['O2_comp']

    return true_comp


def calculate_all_arrays_list(mof_list, num_mofs):
    mof_array_list = []
    mof_array_list.extend(list(itertools.combinations(mof_list, num_mofs)))

    return mof_array_list


def import_prediction_data(prediction_results):
    with open(prediction_results) as file:
        reader = csv.reader(file, delimiter='\t')
        reader_list = list(reader)
        keys = reader_list[0]

        prediction_results = []
        for i in range(len(reader_list[1::])):
            if int(i+0) % 4 == 0:
                temp_dict = OrderedDict()
                temp_dict[keys[0]] = int(reader_list[i+1][0])
            elif int(i+3) % 4 == 0:
                temp_dict[keys[1]] = str(reader_list[i+1][0])
            elif int(i+2) % 4 == 0:
                temp_dict[keys[2]] = ast.literal_eval(reader_list[i+1][0])
            elif int(i+1) % 4 == 0:
                temp_dict[keys[3]] = ast.literal_eval(reader_list[i+1][0])
                prediction_results.extend([temp_dict])

        return keys, prediction_results


def plot_algorithm_progress_single_samples(gases, all_comp_sets, true_comp, cycle_nums, run_id, filepath):
    colors = mpl.cm.get_cmap('RdBu')
    color0 = colors(0.80)
    color1 = colors(0.20)

    for gas in gases:
        comp_range = all_comp_sets[gas]
        true_comp_as_array = true_comp[gas+'_comp']*np.ones(len(cycle_nums))
        plt.figure(figsize=(4.5,4.5), dpi=300)
        plt.rcParams['font.size'] = 12

        if gas == 'CO2':
            gas_for_title = '$Carbon$'+' '+'$Dioxide$'
        else:
            gas_for_title = '$' + gas[0].upper() + gas[1::] + '$'

        plt.title(gas_for_title, fontsize=16)
        plt.plot(cycle_nums, true_comp_as_array, '--', color='dimgrey', label='True Composition')
        plt.xlabel('Cycle Number', fontsize=16)
        xticks = [i for i in range(len(cycle_nums)) if i % 2==0]
        plt.xticks(xticks, fontsize=12)
        plt.ylabel('Mole Fraction', fontsize=16)
        plt.yticks(fontsize=12)
        plt.ticklabel_format(axis="y", style="sci", scilimits=(-1,3), useMathText=True)
        for n in range(len(cycle_nums)):
            if n == 0:
                plt.plot([cycle_nums[n],cycle_nums[n]], comp_range[n], 'o-', color=color0, label='Predicted')
            else:
                plt.plot([cycle_nums[n],cycle_nums[n]], comp_range[n], 'o-', color=color0, label=None)
        plt.legend(fontsize=12, bbox_to_anchor=(0.5,-0.15), loc='upper center', ncol=2)
        plt.tight_layout(rect=(0,0.05,1,1))
        plt.savefig(filepath+'breath_sample_prediction_algorithm_'+gas+'.png')
        plt.close()


def plot_predicted_vs_true_for_all_breath_samples(gases, gas_limits, predicted_comps, true_comps, filepath=None, sort_data=False, sort_by=None):
    from matplotlib.ticker import AutoMinorLocator
    from matplotlib.ticker import FixedLocator

    colors = mpl.cm.get_cmap('RdBu')
    color0 = colors(0.80)
    color1 = colors(0.20)

    xlim_value = int(len(predicted_comps)+1)
    predicted_comps_copy = copy.deepcopy(predicted_comps)
    for gas in gases:
        plt.figure(figsize=(4.5,4.5), dpi=600)
        plt.rcParams['font.size'] = 12
        plt.ticklabel_format(axis="y", style="sci", scilimits=(-1,0), useMathText=True)
        plt.xlim([0,xlim_value])
        plt.xlabel('Sample Number', fontsize=16)
        plt.xticks(fontsize=12)
        plt.ylim([gas_limits[gas][0],gas_limits[gas][1]*1.00])
        plt.ylabel('Mole Fraction', fontsize=16)
        plt.yticks(fontsize=12)
        if gas == 'CO2':
            gas_for_title = '$Carbon$'+' '+'$Dioxide$'
        else:
            gas_for_title = '$' + gas[0].upper() + gas[1::] + '$'
        plt.title(gas_for_title, fontsize=16)

        x = np.linspace(1,len(predicted_comps),len(predicted_comps))
        true_comps_by_component = [row[gas+'_comp'] for row in true_comps]

        predicted_comps = predicted_comps_copy
        if sort_data == True:
            if sort_by == 'all':
                sorted_indicies = list(np.argsort(true_comps_by_component))
                true_comps_by_component_temp = list(sorted(true_comps_by_component))
                true_comps_by_component = true_comps_by_component_temp
                predicted_comps_temp = [predicted_comps[index] for index in sorted_indicies]
                predicted_comps = predicted_comps_temp
            elif sort_by != None:
                true_comps_sort_by = [row[sort_by+'_comp'] for row in true_comps]
                sorted_indicies = list(np.argsort(true_comps_sort_by))
                true_comps_by_component_temp = [true_comps_by_component[index] for index in sorted_indicies]
                true_comps_by_component = true_comps_by_component_temp
                predicted_comps_temp = [predicted_comps[index] for index in sorted_indicies]
                predicted_comps = predicted_comps_temp
            else:
                raise(NameError('Invalid Gas for sorting!'))

        plt.plot(x,true_comps_by_component, marker='o', markersize=4, linewidth=0, alpha=0.7, color=color0, label='True')

        predicted_comps_midpoint = [0.5*np.sum(row[gas]) for row in predicted_comps]
        predicted_comps_error = [abs(0.5*np.subtract(*row[gas])) for row in predicted_comps]
        plt.errorbar(x,predicted_comps_midpoint,predicted_comps_error, marker='o', markersize=4, elinewidth=1, linewidth=0, alpha=0.7, color=color1, label='Predicted')

        minor_locator1 = FixedLocator(np.linspace(5,xlim_value-1,10))
        plt.gca().xaxis.set_minor_locator(minor_locator1)
        plt.grid(which='minor', alpha=0.3)
        plt.legend(fontsize=12, bbox_to_anchor=(0.5,-0.15), loc='upper center', ncol=2, markerscale=1.5)
        plt.tight_layout(rect=(0,0.05,1,1))
        if filepath != None:
            filename = 'breath_sample_prediciton_'+gas+'.png'
            plt.savefig(filepath+filename)
        plt.close()


def plot_prediction_error_for_all_breath_samples(gases, predicted_comps, true_comps, filepath=None):
    from matplotlib.ticker import AutoMinorLocator
    from matplotlib.ticker import FixedLocator

    colors = mpl.cm.get_cmap('RdBu')
    color0 = colors(0.80)
    color1 = colors(0.20)

    xlim_value = int(len(predicted_comps)+1)
    for gas in gases:
        plt.figure(figsize=(5,5), dpi=600)
        plt.xlim([0,xlim_value])
        plt.xlabel('Sample Number', fontsize=16)
        plt.xticks(fontsize=12)
        # plt.ylim(gas_limits[gas])
        plt.ylabel('Percent Error', fontsize=16)
        plt.yticks(fontsize=12)
        if gas == 'CO2':
            gas_for_title = '$Carbon$'+' '+'$Dioxide$'
        else:
            gas_for_title = '$' + gas[0].upper() + gas[1::] + '$'
        plt.title(gas_for_title, fontsize=16)

        x = np.linspace(1,len(predicted_comps),len(predicted_comps))
        true_comps_by_component = [row[gas+'_comp'] for row in true_comps]
        true_value_error = np.zeros(len(true_comps_by_component))
        plt.plot(x,true_value_error, marker='o', markersize=4, linewidth=0, alpha=0.7, color=color0, label='True')

        predicted_comps_midpoint = [0.5*np.sum(row[gas]) for row in predicted_comps]
        predicted_comps_error = [abs(0.5*np.subtract(*row[gas])) for row in predicted_comps]
        percent_error_midpoint = np.divide(np.add(predicted_comps_midpoint,np.multiply(-1,true_comps_by_component)),true_comps_by_component)*100
        percent_error_error = np.divide(predicted_comps_error,true_comps_by_component)*100
        if max(abs(percent_error_midpoint))+max(percent_error_error) <= 5:
            plt.ylim([-5,5])
        plt.errorbar(x,percent_error_midpoint,percent_error_error, marker='o', markersize=4, elinewidth=1, linewidth=0, alpha=0.7, color=color1, label='Predicted')

        minor_locator1 = FixedLocator(np.linspace(5,xlim_value-1,10))
        plt.gca().xaxis.set_minor_locator(minor_locator1)
        plt.grid(which='minor', alpha=0.3)
        plt.legend(bbox_to_anchor=(0.5,-0.15), loc='upper center', ncol=2, fontsize=12)
        plt.tight_layout(rect=(0,0.05,1,1))
        if filepath != None:
            filename = 'breath_sample_prediction_error_'+gas+'.png'
            plt.savefig(filepath+filename)
        plt.close()


def composition_prediction_algorithm(array, henrys_data, gases, comps, spacing, convergence_limits, breath_sample, num_cycles=10, pmf_convergence=1, fraction_to_keep=0.037, error_type='fixed', error_amount=0.10):

    # Initialize all values
    cycle_nums = [0]
    all_comp_sets = {gas:[] for gas in gases}
    final_comp_set = {gas:[] for gas in gases}
    convergence_status = {gas: False for gas in gases if gas !='Air'}

    # Record Initial Composition Range
    for gas in gases:
        #Get min/max component mole frac
        all_molefrac = [row[gas+'_comp'] for row in comps]
        min_molefrac = min(all_molefrac)
        max_molefrac = max(all_molefrac)
        all_comp_sets[gas].extend([[min_molefrac, max_molefrac]])

    for i in range(num_cycles):
        # Keep track of cycles
        print('Cycle = ',i+1)
        print('Number of Comps. =', len(comps))
        cycle_nums.extend([i+1])

        # Convert from composition space to mass space to probability space
        print('\tCreate Pseudo-simulated Data...')
        pseudo_simulated_data = create_pseudo_simulated_data_from_dict(array, comps, gases, henrys_data)
        print('\tCalculating Element Probability / Normalizing...')
        element_pmf = calculate_element_pmf(array, pseudo_simulated_data, breath_sample, error_type=error_type, error_amount=error_amount)
        print('\tCalculating Array Probability / Normalizing ...')
        array_pmf, array_pmf_sorted = calculate_array_pmf(element_pmf, array, comps)

        # Calculate min/max array pmf, and percent difference
        # min_array_pmf = array_pmf_sorted[-1]['Array_pmf']
        # max_array_pmf = array_pmf_sorted[0]['Array_pmf']
        # if min_array_pmf > 0:
        #     percent_difference = (max_array_pmf-min_array_pmf)/min_array_pmf*100
        # else:
        #     percent_difference = np.inf

        # Filter Out Low-Probability Compositions
        # print('\tFiltering Low-probability Compositions.')
        # if True not in convergence_status.values():
        #     comps = filter_unbinned_comps_by_probability(array_pmf_sorted, gases, fraction_to_keep=fraction_to_keep)
        # else:
        #     comps_by_bins, pmf_by_bins, bin_pmf_by_bins = bin_compositions_by_convergence_status(comps, gases, convergence_status, array_pmf)
        #     comps = filter_binned_comps_by_probability(comps_by_bins, pmf_by_bins, bin_pmf_by_bins, gases, fraction_to_keep=fraction_to_keep)
        # print('\tNumber of Comps. after filtering = ', len(comps))

        # Check / Update convergence status
        for gas in gases:
            #Get min/max component mole frac
            all_molefrac = [row[gas+'_comp'] for row in comps]
            min_molefrac = min(all_molefrac)
            max_molefrac = max(all_molefrac)
            molefrac_diff = max_molefrac-min_molefrac
            all_comp_sets[gas].extend([[min_molefrac, max_molefrac]])

            # Check Convergence
            final_comp_set[gas] = [min_molefrac, max_molefrac]
            if gas != 'Air':
                if molefrac_diff <= convergence_limits[gas]:
                    convergence_status[gas] = True
                else:
                    convergence_status[gas] = False

        # Check if exiting, Determine exit condition
        # Optipns are:
        #   (1) Max Number of Cycles Reached
        #   (2) All gases determined within desired range
        if False not in convergence_status.values() or i >= num_cycles-1:
            if False not in convergence_status.values() and i >= num_cycles-1:
                exit_condition = 'Compositions Converged & Maximum Number of Cycles Reached.'
            elif False not in convergence_status.values():
                exit_condition = 'Compositions Converged.'
            elif i >= num_cycles-1:
                exit_condition = 'Maximum Number of Cycles Reached.'

            print('Converged - Exiting!\n\n')

            return final_comp_set, exit_condition, cycle_nums, all_comp_sets, element_pmf,  array_pmf_sorted

        else:
            print('\tSubdividing Grid...\n')
            spacing = [value*0.5 for value in spacing]
            old_points_to_keep = array_pmf_sorted[0:int(np.ceil(len(array_pmf_sorted)*fraction_to_keep))]
            print('\tNumber of Comps. after filtering = ', len(old_points_to_keep))
            comps = subdivide_grid_from_dict(old_points_to_keep, gases, spacing)


def composition_prediction_algorithm_new(array, henrys_data, gases, comps, spacing, convergence_limits, breath_sample_masses, num_cycles=10, fraction_to_keep=0.037, std_dev=0.10):

    # Initialize all values
    cycle_nums = [0]
    all_comp_sets = {gas:[] for gas in gases}
    final_comp_set = {gas:[] for gas in gases}
    convergence_status = {gas: False for gas in gases if gas !='Air'}

    # Record Initial Composition Range
    for i in range(len(gases)):
        #Get min/max component mole frac
        gas = gases[i]
        all_molefrac = [comps[j][i] for j in range(len(comps))]
        min_molefrac = min(all_molefrac)
        max_molefrac = max(all_molefrac)
        all_comp_sets[gas].extend([[min_molefrac, max_molefrac]])

    for i in range(num_cycles):
        # Keep track of cycles
        print('Cycle = ',i+1)
        print('Number of Comps. =', len(comps))
        cycle_nums.extend([i+1])

        # Convert from composition space to mass space to probability space
        print('\tCreate Pseudo-simulated Data...')
        # start_time = time.time()
        simulated_masses = create_pseudo_simulated_data_from_array(array, comps, gases, henrys_data)
        # elapsed_time = time.time() - start_time
        # print('\t\tt =',elapsed_time,' s')

        print('\tCalculating Element / Array Probability')
        # start_time = time.time()
        element_pmfs_normalized, array_pmfs_normalized, array_pmfs_normalized_sorted, sorted_indicies = calculate_element_and_array_pmf_tf(simulated_masses, breath_sample_masses, std_dev=std_dev)
        # elapsed_time = time.time() - start_time
        # print('\t\tt =',elapsed_time,' s')

        # Filter Out Low-Probability Compositions
        print('\tFiltering Low-probability Compositions.')
        filtered_indicies = sorted_indicies[0:int(np.ceil(fraction_to_keep*len(sorted_indicies)))]
        filtered_comps = [comps[index] for index in filtered_indicies]
        print('\tNumber of Comps. after filtering = ', len(filtered_comps))

        # Check / Update convergence status
        for g in range(len(gases)):
            #Get min/max component mole frac
            gas = gases[g]
            all_molefrac = [filtered_comps[j][g] for j in range(len(filtered_comps))]
            min_molefrac = min(all_molefrac)
            max_molefrac = max(all_molefrac)
            molefrac_diff = max_molefrac-min_molefrac
            all_comp_sets[gas].extend([[min_molefrac, max_molefrac]])

            # Check Convergence
            final_comp_set[gas] = [min_molefrac, max_molefrac]
            if gas != 'Air':
                if molefrac_diff <= convergence_limits[gas]:
                    convergence_status[gas] = True
                else:
                    convergence_status[gas] = False

        # Check if exiting, Determine exit condition
        # Optipns are:
        #   (1) Max Number of Cycles Reached
        #   (2) All gases determined within desired range
        if False not in convergence_status.values() or i >= num_cycles-1:
            if False not in convergence_status.values() and i >= num_cycles-1:
                exit_condition = 'Compositions Converged & Maximum Number of Cycles Reached.'
            elif False not in convergence_status.values():
                exit_condition = 'Compositions Converged.'
            elif i >= num_cycles-1:
                exit_condition = 'Maximum Number of Cycles Reached.'

            print('Converged - Exiting!\n\n')

            return final_comp_set, exit_condition, cycle_nums, all_comp_sets, element_pmfs_normalized, array_pmfs_normalized

        else:
            print('\tSubdividing Grid...\n')
            spacing = [value*0.5 for value in spacing]
            comps = subdivide_grid_from_array(filtered_comps, gases, spacing)


def create_uniform_comp_list(gases, gas_limits, spacing, filename=None, imply_final_gas_range=True, imply_final_gas_spacing=False, filter_for_1=True, round_at=None):
    """
    Function used to create a tab-delimited csv file of gas compositions for a set of gases with a
    range of compositions. The compositions of the final gas in the list is calculated so that the
    total mole fraction of the system is equal to 1 by default. This is true even if the composition
    is supplied, however this behavior can be turned off, in which case the list will contain only
    compositions in the given range which total to 1.
    """

    # Calculate the valid range of compositions for the final gas in the list.
    if len(gases) == len(gas_limits)+1:
        lower_limit_lastgas = 1-np.sum([limit[1] for limit in gas_limits])
        if lower_limit_lastgas < 0:
            lower_limit_lastgas = 0
        upper_limit_lastgas = 1-np.sum([limit[0] for limit in gas_limits])
        if upper_limit_lastgas > 1:
            upper_limit_lastgas = 1
        gas_limits_new = [limit for limit in gas_limits]
        gas_limits_new.append([lower_limit_lastgas, upper_limit_lastgas])
    elif len(gases) == len(gas_limits):
        if imply_final_gas_range == True:
            lower_limit_lastgas = 1-np.sum([limit[1] for limit in gas_limits[:-1]])
            if lower_limit_lastgas < 0:
                lower_limit_lastgas = 0
            upper_limit_lastgas = 1-np.sum([limit[0] for limit in gas_limits[:-1]])
            if upper_limit_lastgas > 1:
                upper_limit_lastgas = 1
            gas_limits_new = [limit for limit in gas_limits[:-1]]
            gas_limits_new.append([lower_limit_lastgas, upper_limit_lastgas])
        else:
            gas_limits_new = gas_limits

    # Determine the number of points for each gas for the given range and spacing.
    if len(spacing) == 1:
        number_of_values = [(limit[1]-limit[0])/spacing+1 for limit in gas_limits_new]
        number_of_values_as_int = [int(value) for value in number_of_values]
        if number_of_values != number_of_values_as_int:
            print('Bad combination of gas limits and spacing! Double check output file.')
        comps_by_gas = [np.linspace(gas_limits_new[i][0], gas_limits_new[i][1], number_of_values_as_int[i]) for i in range(len(gas_limits_new))]
        all_comps = list(itertools.product(*comps_by_gas))

    elif len(spacing) == len(gas_limits_new)-1:
        number_of_values = [(gas_limits_new[i][1]-gas_limits_new[i][0])/spacing[i]+1 for i in range(len(gas_limits_new)-1)]
        number_of_values_as_int = [int(value) for value in number_of_values]
        comps_by_gas = [np.linspace(gas_limits_new[i][0], gas_limits_new[i][1], number_of_values_as_int[i]) for i in range(len(gas_limits_new)-1)]
        all_comps_except_last = list(itertools.product(*comps_by_gas))
        all_comps = []
        for row in all_comps_except_last:
            total = np.sum(row)
            last_comp = 1 - total
            if last_comp >=0 and last_comp >= gas_limits_new[-1][0] and last_comp <= gas_limits_new[-1][1]:
                row += (last_comp,)
            all_comps.extend([row])

    elif len(spacing) == len(gas_limits_new):
        number_of_values = np.round([(gas_limits_new[i][1]-gas_limits_new[i][0])/spacing[i]+1 for i in range(len(gas_limits_new))], 5)
        number_of_values_as_int = [int(value) for value in number_of_values]
        if imply_final_gas_spacing == True:
            comps_by_gas = [np.linspace(gas_limits_new[i][0], gas_limits_new[i][1], number_of_values_as_int[i]) for i in range(len(gas_limits_new)-1)]
            all_comps_except_last = list(itertools.product(*comps_by_gas))
            all_comps = []
            for row in all_comps_except_last:
                total = np.sum(row)
                last_comp = 1 - total
                if last_comp >=0 and last_comp >= gas_limits_new[-1][0] and last_comp <= gas_limits_new[-1][1]:
                    row += (last_comp,)
                all_comps.extend([row])
        if imply_final_gas_spacing == False:
            if False in (number_of_values == number_of_values_as_int):
                print('Bad combination of gas limits and spacing! Double check output file.')
            comps_by_gas = [np.linspace(gas_limits_new[i][0], gas_limits_new[i][1], number_of_values_as_int[i]) for i in range(len(gas_limits_new))]
            all_comps = list(itertools.product(*comps_by_gas))

    # Filter out where total mole fractions != 1
    all_comps_final = []
    if filter_for_1 == True:
        for row in all_comps:
            if round_at != None:
                row = np.round(row, round_at)
            if np.sum(row) == 1:
                all_comps_final.extend([row])
    else:
        all_comps_final = all_comps

    # Write to file.
    if filename != None:
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile, delimiter='\t', quotechar='|', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(gases)
            writer.writerows(all_comps_final)

    return comps_by_gas, all_comps_final


def read_kH_results(filename):
    with open(filename, newline='') as csvfile:
        output_data = csv.reader(csvfile, delimiter="\t")
        output_data = list(output_data)
        full_array = []
        for i in range(len(output_data)):
            row = output_data[i][0]
            row = row.replace('nan', '\'nan\'')
            row = row.replace('inf', '\'inf\'')
            row = row.replace('-\'inf\'', '\'-inf\'')
            temp_array = []
            temp_row = ast.literal_eval(row)
            # if type(temp_row['R^2']) == str or temp_row['R^2'] < 0:
            #     continue
            temp_array.append(temp_row)
            full_array.extend(temp_array)
        return full_array


def invert_matrix(array):
    if np.shape(array)[0] == np.shape(array)[1]:
        inv = np.linalg.inv(array)
    else:
        inv = np.linalg.pinv(array)

    return inv


def analytical_solution(array, gases, henrys_data_array, breath_sample_masses, added_error=None):
    pure_air_masses = [henrys_data_array[mof]['Pure Air Mass'] for mof in array]
    m_prime = [breath_sample_masses[i] - pure_air_masses[i] for i in range(len(breath_sample_masses))]
    henrys_matrix = [[henrys_data_array[mof][gas+'_kH'] for gas in gases] for mof in array]

    array_inv = invert_matrix(henrys_matrix)
    if added_error == None or added_error == 0:
        m_prime_new = m_prime
    else:
        m_prime_new = [value + random.uniform(-1,1)*1e-4 for value in m_prime]

    soln = np.matmul(array_inv, m_prime_w_error)
    soln_in_dict_format = {gases[i]+'_comp':soln[i] for i in range(len(gases))}

    return soln_in_dict_format


def calculate_KLD_for_cycle(array_pmfs):
    # This function requires NORMALIZED pmf values.

    num_points = len(array_pmfs)
    kld_max = math.log2(num_points)
    kld = sum( [float(pmf)*math.log2(float(pmf)*num_points) for pmf in array_pmfs if pmf != 0] )
    kld_norm = kld/kld_max

    return kld_norm


def calculate_p_max(num_elements, stddev):
    # This will be a (very close) approximations of p_max, since it is a truncated normal, and thus the value at the mean could change slightly subject to the contraint that the area under the curve, which goes to infinity, is exactly 1.
    distributions = tfp.distributions.TruncatedNormal(100, stddev, 0, np.inf)
    element_pmf_max = distributions.prob(100)
    array_pmf_max = element_pmf_max ** num_elements

    return array_pmf_max


def calculate_p_ratio(array_pmfs_sorted, p_max):
    """
    As long as each sensing element has a known associated std. dev. which is independent of composition, the maximum probability which could be assigned to a single point can be determined by mutliplyinf the individual max probabilities for each element. Thus, we can determine the ratio of the assigned probability of the maximum probability and use this as a metric to see how the predicition is improving.

    May need to adjust earlier function to report non-normalized element and/or array pmf.
    """
    all_p_ratios = [p_i/p_max for p_i in array_pmfs_sorted]

    return p_ratios
