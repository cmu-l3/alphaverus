# Standard library imports
import argparse
import json
import logging
import os
import random
import time
from glob import glob

# Third party imports
import numpy as np

# Local imports
from convert_single import main as convert_main
from exploit_model import run_exploit_model
from rebase_error_fix import main as tree_search_main
from utils import load_yaml
from verify_translations import check_pairs

# Sleep for a random time b/w 0 and 30 seconds. This is to avoid multiple controllers from starting at the same time.
time.sleep(random.randint(0, 30))
print('Sleep Done')

BATCH_SIZE = 64

parser = argparse.ArgumentParser(description='Run the whole pipeline')


def update_solved_files(experiment_state):
    files = glob(f'saved_programs/iter{experiment_state["current_iteration"]}/convert_*/*.rs')
    for file in files:
        file_name = os.path.split(file)[-1]
        prog_num, num_ver, num_errors = file_name.split('=')[1].split('_')[:3]
        num_ver = int(num_ver)
        num_errors = int(num_errors)
        if num_ver!=0 and num_errors==0:
            # We have a hit baby
            if prog_num not in experiment_state['solved_files']:
                experiment_state['solved_files'][prog_num] = []
            experiment_state['solved_files'][prog_num].append(file)

            # Delete the corresponding key from syntactic_files
            if prog_num in experiment_state['syntactic_files']:
                del experiment_state['syntactic_files'][prog_num]

        elif num_errors!=0:
            if prog_num not in experiment_state['syntactic_files']:
                experiment_state['syntactic_files'][prog_num] = []
            experiment_state['syntactic_files'][prog_num].append((file, num_ver, num_errors))
            experiment_state['syntactic_files'][prog_num].sort(key = lambda x: x[1]/(x[1]+x[2]), reverse = True)
    # Delete all keys that are present in solved_files from syntactic_files
    common_keys = set(experiment_state['solved_files'].keys()).intersection(set(experiment_state['syntactic_files'].keys()))
    for key in common_keys:
        del experiment_state['syntactic_files'][key]
    return experiment_state

class ExperimentLock:
    def __init__(self):
        self.acquired = False

    def __enter__(self):
        for _ in range(60):
            if os.path.exists('experiment_state.json.lock'):
                time.sleep(1)
            else:
                open('experiment_state.json.lock', 'w').close()
                self.acquired = True
                return self
        raise Exception('Could not acquire the lock')

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.acquired:
            try:
                os.remove('experiment_state.json.lock')
            except:
                pass

def load_experiment_state():
    for _ in range(60):
        if os.path.exists('experiment_state.json.lock'):
            time.sleep(1)
        else:
            return json.load(open('experiment_state.json')) 
    print('Could not load the experiment state, Lock file looks stale. Manually intervene')
    time.sleep(600)
    raise Exception('Could not load the experiment state, Lock file looks stale. Manually intervene')

def acquire_lock():
    lock = ExperimentLock()
    return lock

def release_lock():
    # Note: Be careful with this function. This should be called only after acquiring the lock
    try:
        os.remove('experiment_state.json.lock')
    except:
        pass

def save_experimet_state(experiment_state, is_locked=False):
    if is_locked:
        # Lock already acquired, just save
        with open('experiment_state.json', 'w') as f:
            json.dump(experiment_state, f, indent=4)
        return

    # Need to acquire lock first
    for _ in range(60):
        if os.path.exists('experiment_state.json.lock'):
            time.sleep(1)
        else:
            try:
                with ExperimentLock():
                    with open('experiment_state.json', 'w') as f:
                        json.dump(experiment_state, f, indent=4)
                return
            except:
                # Ensure lock is cleaned up if save fails
                try:
                    os.remove('experiment_state.json.lock')
                except:
                    pass
                raise
    raise Exception('Could not save the experiment state, Lock file looks stale. Manually intervene')

def create_max_gens_list(config, solved_files):

    num_repeats = config['CONVERT']['MAX_GENS']//BATCH_SIZE
    # Create a list of form (i, j) where i is the problem number, and j is the repeat number
    num_programs = min(config['MAX_PROGRAMS'], len(json.load(open(config['PROGRAMS_FILE']))))
    max_gens_list = [(i, j) for i in range(num_programs) for j in range(num_repeats)]
    max_gens_list = [x for x in max_gens_list if str(x[0]) not in solved_files]
    # Shuffle the list
    random.shuffle(max_gens_list)
    return max_gens_list
    
def main():


    # Let's start by reading the config file
    config = load_yaml('config.yaml')

    dafny_programs = json.load(open(config['PROGRAMS_FILE']))

    # Now let's read the experiment_state.json
    experiment_state = load_experiment_state()

    if len(experiment_state)==0:
        # Let's initialize the experiment_state
        experiment_state = {
            'current_iteration' : 0,
            'iteration_progress' : {
                'convert' : {
                    'max_gens' : create_max_gens_list(config, []),
                    'generations_done' : [],
                    'running_generations' : [],
                    'completed' : False
                },
                'tree' : {
                    'all_progs_to_run' : [],
                    'progs_done' : [],
                    'progs_running' : [],
                    'completed' : False
                }
            },
            'solved_files' : dict(), # Note, this will be a dict of list, where key is program number, and list is list of solves. Each list will be sorted, with best solution first
            'syntactic_files' : dict(),
            'solved_pairs' : [], # Note, this is just a List[Tuple]
            'error_pairs'  : [], # Note, this is just a List[Tuple[str, str, str]]. Note, last entry indicates the program number 
            'critic_pairs' : []
        }
        with acquire_lock():
            save_experimet_state(experiment_state, is_locked=True)

    # Now let's look at the experiment state.
    iteration_number = experiment_state['current_iteration']
    iteration_progress = experiment_state['iteration_progress']

    if experiment_state['iteration_progress']['convert']['completed'] == True:
        if experiment_state['iteration_progress']['tree']['completed'] == False:

            # Assert: We are in the tree phase

            to_do = list(set(experiment_state['iteration_progress']['tree']['all_progs_to_run']).difference(set(experiment_state['iteration_progress']['tree']['progs_done']).union(set(experiment_state['iteration_progress']['tree']['progs_running']))))
            if len(to_do) == 0 and len(experiment_state['iteration_progress']['tree']['progs_running'])!=0:
                # We can't do anything but wait, so quitting instead.
                print('Going to sleep for 1 hour')
                time.sleep(3600)
                # We will max wait for 1 hours, and after which we will transfer all progrs_running to progs_done
                with acquire_lock():
                    experiment_state = json.load(open('experiment_state.json'))
                    if len(experiment_state['iteration_progress']['tree']['progs_running'])==0:
                        # Someone already did this
                        release_lock()
                        return
                    experiment_state['iteration_progress']['tree']['progs_done'].extend(experiment_state['iteration_progress']['tree']['progs_running'])
                    experiment_state['iteration_progress']['tree']['progs_running'] = []
                    save_experimet_state(experiment_state, is_locked=True)
                return
            elif len(to_do) == 0 and len(experiment_state['iteration_progress']['tree']['progs_running'])==0:

                # Add a custom lock to tell others that we are updating the state, so go to sleep
                if os.path.exists('experiment_state_over.json.lock'):
                    print('Going to sleep for 10 minutes')
                    time.sleep(600)
                    return
                open('experiment_state_over.json.lock', 'w').close()

                with acquire_lock():
                    experiment_state = json.load(open('experiment_state.json'))
                    experiment_state['iteration_progress']['tree']['completed'] = True

                    os.makedirs('histories', exist_ok=True)
                    with open(f'histories/iter{iteration_number}_nodel.json', 'w') as f:
                        json.dump(experiment_state, f, indent=4)

                    # Tree search solved_files are added automatically, we have to just update the solved pairs, delete any key present in solved_files from syntactic files, and then create error_pairs
                    experiment_state['solved_pairs'] = []
                    solved_file_keys_to_delete = []
                    for prog_num, files in experiment_state['solved_files'].items():
                        # Score files based on which has the lowest number of assert statements, followed by lowest number of non-empty lines, followed by lowest number of characters
                        files.sort(key = lambda x: (x.count('assert'), x.count('\n'), len(x)))

                        # We should also, check if the translation is correct or not
                        faulty_pairs = check_pairs([(dafny_programs[int(prog_num)], open(files[0]).read())])
                        print(faulty_pairs)
                        faulty_pairs_conditions = []
                        print(faulty_pairs_conditions)
                        print()
                        faulty_pairs_common = set(faulty_pairs).union(set(faulty_pairs_conditions))
                        faulty_pairs = list(faulty_pairs_common)

                        exec_based_critic, all_faults = run_exploit_model(open(files[0]).read(), experiment_state['critic_pairs'])
                        if exec_based_critic:
                            for fault in all_faults:
                                experiment_state['critic_pairs'].append((open(files[0]).read(), fault))
                                                                     
                        if len(faulty_pairs)!=0 or exec_based_critic:

                            print('We have a faulty pair', prog_num)

                            to_del_indices = []
                            faulty_code = open(files[0]).read()
                            for i, (x,y,z) in enumerate(experiment_state['error_pairs']):
                                if z.strip() == faulty_code.strip():
                                    print('Deleting an error triplet')
                                    to_del_indices.append(i)
                            experiment_state['error_pairs'] = [experiment_state['error_pairs'][i] for i in range(len(experiment_state['error_pairs'])) if i not in to_del_indices]
                            
                            # Now let's check for the first correct file
                            to_del_for_solved_files = [0]
                            delete_all_flag = False
                            for i in range(1, min(6, len(files))):
                                f_pairs_temp = check_pairs([(dafny_programs[int(prog_num)], open(files[i]).read())])
                                f_pairs_temp_conditions = []
                                f_pairs_temp_common = set(f_pairs_temp).union(set(f_pairs_temp_conditions))
                                f_pairs_temp = list(f_pairs_temp_common)

                                exec_based_critic, all_faults = run_exploit_model(open(files[i]).read(), experiment_state['critic_pairs'])
                            
                                if exec_based_critic:
                                    for fault in all_faults:
                                        experiment_state['critic_pairs'].append((open(files[i]).read(), fault))

                                if len(f_pairs_temp)!=0 or exec_based_critic:
                                    print('Another to delete file inside solved_files', prog_num)
                                    to_del_for_solved_files.append(i)
                                    if i==5:
                                        delete_all_flag = True
                                else:
                                    # Okay, this file is good
                                    break
                            print("Deleteing solved files", to_del_for_solved_files)
                            if delete_all_flag:
                                experiment_state['solved_files'][prog_num] = []
                            else:
                                experiment_state['solved_files'][prog_num] = [files[i] for i in range(len(files)) if i not in to_del_for_solved_files]
                        if len(experiment_state['solved_files'][prog_num])==0:
                            # Delete the key itself
                            solved_file_keys_to_delete.append(prog_num)
                            continue

                        experiment_state['solved_pairs'].append((dafny_programs[int(prog_num)], experiment_state['solved_files'][prog_num][0]))

                    critic_pairs_indices = dict()
                    for x,y in experiment_state['critic_pairs']:
                        if x in critic_pairs_indices:
                            critic_pairs_indices[x].append(y)
                        else:
                            critic_pairs_indices[x] = [y]
                    experiment_state['critic_pairs'] = [(x, np.random.choice(y)) for x,y in critic_pairs_indices.items()]

                    for key in solved_file_keys_to_delete:
                        del experiment_state['solved_files'][key]
                    
                    common_keys = set(experiment_state['solved_files'].keys()).intersection(set(experiment_state['syntactic_files'].keys()))
                    for key in common_keys:
                        del experiment_state['syntactic_files'][key]

                    try:
                        all_keys = list(experiment_state['syntactic_files'].keys())
                        for key in all_keys:
                            to_del_indices = []
                            for i, (prog, x, y) in enumerate(experiment_state['syntactic_files'][key]):
                                # Extract iter number of format iter{iter_num}
                                iter_num = int(prog.split('iter')[1].split('/')[0])
                                print(iter_num)
                                if iter_num < iteration_number - 2:
                                    to_del_indices.append(i)
                            experiment_state['syntactic_files'][key] = [experiment_state['syntactic_files'][key][i] for i in range(len(experiment_state['syntactic_files'][key])) if i not in to_del_indices]
                            if len(experiment_state['syntactic_files'][key]) == 0:
                                del experiment_state['syntactic_files'][key]
                    except Exception as e:
                        print('Error in deleting syntactic files', e)



                    critic_pairs_indices = dict()
                    for x,y in experiment_state['critic_pairs']:
                        if x in critic_pairs_indices:
                            critic_pairs_indices[x].append(y)
                        else:
                            critic_pairs_indices[x] = [y]
                    experiment_state['critic_pairs'] = [(x, np.random.choice(y)) for x,y in critic_pairs_indices.items()]

                    os.makedirs('histories', exist_ok=True)
                    with open(f'histories/iter{iteration_number}.json', 'w') as f:
                        json.dump(experiment_state, f, indent=4)

                    experiment_state['current_iteration'] += 1
                    experiment_state['iteration_progress'] = {
                        'convert' : {
                            'max_gens' : create_max_gens_list(config, experiment_state['solved_files']),
                            'generations_done' : [],
                            'running_generations' : [],
                            'completed' : False
                        },
                        'tree' : {
                            'all_progs_to_run' : [],
                            'progs_done' : [],
                            'progs_running' : [],
                            'completed' : False
                        }
                    }

                    save_experimet_state(experiment_state, is_locked=True)

                    # Now we can release the lock
                    os.remove('experiment_state_over.json.lock')

                    return

            else:
                    # The idea is we will run only one program, and then update and quit
                program_to_run = to_do[0]
                with acquire_lock():
                    experiment_state['iteration_progress']['tree']['progs_running'].append(program_to_run)
                    save_experimet_state(experiment_state, is_locked=True)
                config['SAVE_DIR'] = f'saved_programs/iter{iteration_number}/tree_{program_to_run}'
                config['PROGRAM_FILE'] = program_to_run
                config['error_pairs'] = experiment_state['error_pairs']
                logger = logging.getLogger('tree_search')
                error_triplets, correct_file_loc = tree_search_main(config, logger)
                
                # If just want to do Pass@1, comment the next 2 lines, else keep them here. Note: In paper, we use Pass@1
                # if error_triplets is None:
                #     error_triplets, correct_file_loc = tree_search_main(config, logger)
                    
                if error_triplets is not None:
                    with acquire_lock():
                        experiment_state = json.load(open('experiment_state.json'))
                        experiment_state['error_pairs'].extend(error_triplets)
                        # Update the solved files
                        prog_number = program_to_run.split('=')[-1].split('_')[0]
                        if prog_number not in experiment_state['solved_files']:
                            experiment_state['solved_files'][prog_number] = []
                        experiment_state['solved_files'][prog_number].append(correct_file_loc)
                        save_experimet_state(experiment_state, is_locked=True)
                        # release_lock()
                with acquire_lock():
                    experiment_state = json.load(open('experiment_state.json'))
                    # Note: there is a fatal issue. if whatever reason, we are unable to delete from progs_running, progress will be stalled. In order to handle this run `check_log_files.py` in background. 
                    try:
                        experiment_state['iteration_progress']['tree']['progs_running'].remove(program_to_run)
                        experiment_state['iteration_progress']['tree']['progs_done'].append(program_to_run)
                    except Exception as e:
                        print('Error in removing from progs_running', e)
                    save_experimet_state(experiment_state, is_locked=True)
                    # release_lock()
                return

                    
        else:
            # We need to go to next iteration
            print('We shouldn\' have reached here')
            return
            
    assert experiment_state['iteration_progress']['convert']['completed'] == False

    if len(iteration_progress['convert']['max_gens'])!=0:
        # Some more generations need to be done.

        config['BATCH_SIZE'] = BATCH_SIZE # Ideally, it should remain 32, but may change based on gpu
        config['PROMPT_RANDOM_EXAMPLES'] = [(x[0], open(x[1]).read()) for x in experiment_state['solved_pairs']] # Note, we later might 
        with acquire_lock():
            # Read the first file of max_gens
            # Load the experiment state
            experiment_state = json.load(open('experiment_state.json'))
            print('Running Generations Length', len(experiment_state['iteration_progress']['convert']['running_generations']))
            config['PROGRAM_NUMBER'] = experiment_state['iteration_progress']['convert']['max_gens'][0][0]
            REPEAT_NUMBER = experiment_state['iteration_progress']['convert']['max_gens'][0][1]
            # Remove the first element from max_gens
            experiment_state['iteration_progress']['convert']['max_gens'] = experiment_state['iteration_progress']['convert']['max_gens'][1:]
            print('Appending', (config['PROGRAM_NUMBER'], REPEAT_NUMBER))
            experiment_state['iteration_progress']['convert']['running_generations'].append((config['PROGRAM_NUMBER'], REPEAT_NUMBER))
            save_experimet_state(experiment_state, is_locked=True)
            print('Running Generations Length after appending', len(experiment_state['iteration_progress']['convert']['running_generations']))

        config['SAVE_DIR'] = f'saved_programs/iter{iteration_number}/convert_{REPEAT_NUMBER}'

        # solved_pairs = 
        print('Should have appended', (config['PROGRAM_NUMBER'], REPEAT_NUMBER))
        open(f'ds/{config["PROGRAM_NUMBER"]}_{REPEAT_NUMBER}.rs', 'w').write(dafny_programs[config['PROGRAM_NUMBER']])
        try:
            convert_main(config)
        except Exception as e:
            import traceback
            open(f'ds5/{config["PROGRAM_NUMBER"]}_{REPEAT_NUMBER}.rs', 'w').write(str(e) + '\n' + traceback.format_exc())
            print('Error in convert', e)
            with acquire_lock():
                experiment_state = json.load(open('experiment_state.json'))
                experiment_state['iteration_progress']['convert']['running_generations'].remove([config['PROGRAM_NUMBER'], REPEAT_NUMBER])
                # Add back to max_gens
                experiment_state['iteration_progress']['convert']['max_gens'].append([config['PROGRAM_NUMBER'], REPEAT_NUMBER])
                save_experimet_state(experiment_state, is_locked=True)
            return



        open(f'ds2/{config["PROGRAM_NUMBER"]}_{REPEAT_NUMBER}.rs', 'w').write(dafny_programs[config['PROGRAM_NUMBER']])
        print('Should have been appended', (config['PROGRAM_NUMBER'], REPEAT_NUMBER))


        with acquire_lock():
            experiment_state = json.load(open('experiment_state.json'))
            print('Running Generations Length before removing', len(experiment_state['iteration_progress']['convert']['running_generations']))
            experiment_state['iteration_progress']['tree']['all_progs_to_run'] = [experiment_state['syntactic_files'][k][0][0] for k in experiment_state['syntactic_files'].keys()]
            experiment_state['iteration_progress']['convert']['generations_done'].append((config['PROGRAM_NUMBER'], REPEAT_NUMBER))
            experiment_state['iteration_progress']['convert']['running_generations'].remove([config['PROGRAM_NUMBER'], REPEAT_NUMBER])
            save_experimet_state(experiment_state, is_locked=True)
            print('Running Generations Length after removing', len(experiment_state['iteration_progress']['convert']['running_generations']))
            open(f'ds3/{config["PROGRAM_NUMBER"]}_{REPEAT_NUMBER}.rs', 'w').write(dafny_programs[config['PROGRAM_NUMBER']])

        return
    else:
        if len(experiment_state['iteration_progress']['convert']['running_generations'])!=0:
            # We should wait for the running generations to finish
            print('Going to sleep, but not for more than 20 minutes')
            time.sleep(1200)
            # return
            experiment_state = load_experiment_state()
        if experiment_state['iteration_progress']['convert']['completed'] == False:
            # Looks like progress was stopped in middle. Let's update the solved files
            with acquire_lock():
                experiment_state = update_solved_files(experiment_state)
                experiment_state['iteration_progress']['tree']['all_progs_to_run'] = [experiment_state['syntactic_files'][k][0][0] for k in experiment_state['syntactic_files'].keys()]

                experiment_state['iteration_progress']['convert']['completed'] = True
                save_experimet_state(experiment_state, is_locked=True)
            return
        else:
            print('Strange Condiiton encountered, quitting')
            return

if __name__ == '__main__':
    main()
