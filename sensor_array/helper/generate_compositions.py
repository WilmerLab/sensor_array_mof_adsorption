import numpy as np
import itertools
import csv
import random
import scipy.stats as stats


def create_henrys_comp_list(henrys_gases, henrys_comps, background_gases, background_gas_ratios, filename=None):
    bg_gas_total = np.sum(background_gas_ratios)
    comp_list = []
    for i in range(len(henrys_comps)):
        hg_comp = henrys_comps[i]
        bg_comp = [(1-hg_comp)*ratio/bg_gas_total for ratio in background_gas_ratios]
        comp_list_temp = [hg_comp]
        comp_list_temp.extend(bg_comp)
        comp_list.append(comp_list_temp)

    if filename != None:
        gases = henrys_gases+background_gases
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile, delimiter='\t', quotechar='|', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(gases)
            writer.writerows(comp_list)

    return comp_list


def convert_dict_to_molefrac(gases_dict):
    for key in gases_dict:
        if 'Units' in gases_dict[key]:
            if gases_dict[key]['Units'] == 'percent':
                gases_dict[key]['Values'] = [val*0.01 for val in gases_dict[key]['Values']]
                gases_dict[key]['Units'] = 'molefrac'
            if gases_dict[key]['Units'] == 'ppm':
                gases_dict[key]['Values'] = [val*1e-6 for val in gases_dict[key]['Values']]
                gases_dict[key]['Units'] = 'molefrac'
            if gases_dict[key]['Units'] == 'ppb':
                gases_dict[key]['Values'] = [val*1e-9 for val in gases_dict[key]['Values']]
                gases_dict[key]['Units'] = 'molefrac'

    return gases_dict


def create_breath_samples(gases_dict, num_samples, filename=None, randomseed=69):
    """
    Dictionary format for the gases accepts the following keys:
        Gas - Name of Gas (should match RASPA name or alias)
        Type - Specifies how the gas should be handled when creating compositions
            bound - gas composition will follow a random unifrom sampling between the provided range
            stddev - gas composition will follow a normal distirbution centered around the first value with a standard deviation of the second value
            background - gas composition will be determined at the end in order to satisfy a total mole fraction of 1;
              currently only supports a single background gas, the rest should be specified by background-r
            ratio - gas composoition will be fall within a fixed range realtive to the composition of another gas
            background-r - gas compositon will be used to satsify total mole fraction equal to 1 and be within a fixed range relative to another gas
        Values -  Values will be interpreted differently depending on the specified type
            bound, background - Upper/lower bound on possible gas compositions
            stddev - first value is mean, second value is deviation
            ratio, background-r - Upper/lower bound on ratio of gas compositon, given as x/1
        Units - Specifies units used to interpret the input values, all output files will be written as mole_fraction;
          Currently accepted units are: ppb, ppm, percent, molefrac; This keyword is not necessary for ratio and background-r
        Gas-r - Used only for ratio and background-r, this keyword specfies which gas this should be determined relative to

    Gases will be processed in the following order: bounds = stddev > ratio > background > background-r
    """

    # Extract gases list from dictionary keys
    all_gases = list(gases_dict.keys())
    random.seed(randomseed)

    # Separate gases by type for handling
    gases = []
    ratio_gases = []
    background_gases = []
    background_r_gases = []
    for gas in all_gases:
        row = gases_dict[gas]
        if row['Type'] == 'bounds' or row['Type'] == 'stddev':
            gases.extend([gas])
        elif row['Type'] == 'ratio':
            ratio_gases.extend([gas])
        elif row['Type'] == 'background':
            background_gases.extend([gas])
        elif row['Type'] == 'background-r':
            background_r_gases.extend([gas])
        else:
            raise NameError('Invalid type for '+gas+'!')

    # Create composition list
    comp_list = []
    for i in range(num_samples):

        # Generate compositions for non-background gases
        temp_dict = {}
        for gas in gases:
            row = gases_dict[gas]
            v1, v2 = row['Values']
            if row['Type'] == 'bounds':
                temp_dict[gas] = random.uniform(v1, v2)
            elif row['Type'] == 'stddev':
                # temp_dict[gas] = random.gauss(v1,v2)
                lower_bound = 0
                upper_bound = 1
                mu = v1
                sigma = v2
                a = (lower_bound-mu)/sigma
                b = (upper_bound-mu)/sigma
                temp_dict[gas] = stats.truncnorm.rvs(a,b,loc=mu, scale=sigma, size=1)[0]

        for gas in ratio_gases:
            row = gases_dict[gas]
            rcomp = temp_dict[row['Gas-r']]
            temp_dict[gas] = random.uniform(rcomp*v1, rcomp*v2)

        # Generate (relative) compositions for background gases
        temp_dict_2 = {}
        for gas in background_gases:
            row = gases_dict[gas]
            temp_dict_2[gas] = 1

        for gas in background_r_gases:
            row = gases_dict[gas]
            rcomp = temp_dict_2[row['Gas-r']]
            v1, v2 = row['Values']
            ratio = random.uniform(v1, v2)
            comp = rcomp*ratio
            temp_dict_2[gas] = comp

        # Normalize background gas compositions and add to temp_dict
        total = sum(temp_dict.values())
        total_2 = sum(temp_dict_2.values())
        for key in temp_dict_2:
            temp_dict_2[key] = (temp_dict_2[key]/total_2)*(1-total)
            temp_dict[key] = temp_dict_2[key]

        comp_list.extend([temp_dict])

    # Write to file is desired
    if filename != None:

        gases = list(comp_list[0].keys())
        comp_list_only_values = []
        for row in comp_list:
            temp_array = []
            temp_array.extend([row[gas] for gas in gases])
            comp_list_only_values.extend([temp_array])

        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile, delimiter='\t', quotechar='|', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(gases)
            writer.writerows(comp_list_only_values)

    return comp_list
