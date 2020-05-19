# this script is simply to run many experimental conditions for subsequent evaluation

import neuro_shooting.command_line_execution_tools as ce
import copy
import os

import argparse

def setup_cmdline_parsing():
    parser = argparse.ArgumentParser('Simple functional mapping')
    parser.add_argument('--gpu', type=int, default=0, help='Enable GPU computation on specified GPU.')
    parser.add_argument('--path_to_python', type=str, default=os.popen('which python').read().rstrip(), help='Full path to python in your conda environment.')
    parser.add_argument('--nr_of_seeds', type=int, default=1, help='Number of consecutive random seeds which we should run; i.e., number of random runs')
    parser.add_argument('--starting_seed_id', type=int, default=0, help='Seed that we start with.')
    parser.add_argument('--fcn', type=str, default='cubic', choices=['cubic','quadratic'])
    parser.add_argument('--shooting_model', type=str, default='updown', choices=['univeral','periodic','dampened_updown','simple', '2nd_order', 'updown', 'general_updown'])
    parser.add_argument('--output_base_directory', type=str, default='sfm_results', help='Main directory that the results will be stored in')
    args = parser.parse_args()

    return args

def create_experiment_name(basename,d):

    name = basename
    for k in d:
        name += '_{}_{}'.format(k,d[k])
    return name

def merge_args(run_args_template,add_args):

    merged_args = copy.deepcopy(run_args_template)

    for k in add_args:
        v = add_args[k]
        if (v is True) or (v is False): # check if v is binary
            if v:
                merged_args[k] = None # just add the flag
        else:
            merged_args[k] = v

    return merged_args

def run_experiment(pars_template,pars):
    pass

if __name__ == '__main__':

    args = setup_cmdline_parsing()

    run_args_template = {
        'shooting_model': args.shooting_model,
        #'viz': None,
        'niters': 1,
        'unfreeze_parameters_at_iter': 50,
        'save_figures': None,
        'viz_freq': 300,
        'fcn': args.fcn,
        'optimize_over_data_initial_conditions': None #[True, False]  # we can add binary flags like this
    }

    run_args_to_sweep = {
        'nr_of_particles': [2,5,15,25,50], # number of particles needs to be at least 2
        'inflation_factor': [4,8,16,32],
    }

    swept_parameter_list = ce.recursively_sweep_parameters(pars_to_sweep=run_args_to_sweep)

    # base settings
    seeds = list(range(0+args.starting_seed_id,args.nr_of_seeds+args.starting_seed_id)) # do 10 runs each, we can also specify this manually [1,20] # seeds we iterate over (for multiple runs)
    python_script = 'simple_functional_mapping_example.py'
    output_base_directory = args.output_base_directory

    if not os.path.exists(output_base_directory):
        os.mkdir(output_base_directory)

    # now go over all these parameter structures and run the experiments
    for d in swept_parameter_list:
        for sidx, seed in enumerate(seeds):
            basename = 'run_{:02d}_{}_{}'.format(sidx,args.fcn,args.shooting_model)
            experiment_name = create_experiment_name(basename,d)
            output_directory = os.path.join(output_base_directory,experiment_name)
            log_file = os.path.join(output_directory,'runlog.log')

            if not os.path.exists(output_directory):
                os.mkdir(output_directory)

            run_args = merge_args(run_args_template=run_args_template,add_args=d)
            # add the output-directory
            run_args['output_directory'] = output_directory
            run_args['seed'] = seed

            print('Running {}'.format(experiment_name))

            ce.run_command_with_args(python_script=python_script,
                                     run_args=run_args,
                                     path_to_python=args.path_to_python,
                                     cuda_visible_devices=args.gpu,
                                     log_file=log_file)

    print('Done processing')
