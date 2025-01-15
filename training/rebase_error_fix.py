import math
import random
from run_llm_api import run_llm
from verus_utils import extract_and_save_code, run_code, save_code_to_file, extract_code
import sys

import re
from verus_error_utils import parse_error_message
import torch
from torch.nn import Softmax
import pickle
import multiprocessing
from functools import partial
from copy import deepcopy
import uuid

import sys
import json


TEMPERATURE = 0.1
VERUS_FILE_SUFFIX = str(random.randint(0, 10000))

def check_pairs(prog):
    idx = prog.rfind('fn ', 0, prog.rfind('fn ')) 
    main_idx = prog.find('fn main()')
    # Find first {, replace with "assert false"
    idx2 = prog.find('{', idx)
    prog_require = prog[:idx2] + '{\n\tassert (false);\n' + prog[idx2+1:]
    # Open a random file name
    random_file_name = f'temp{str(random.randint(0, 10000))}.rs'
    open(random_file_name,'w').write(prog_require)
    o,e = run_code(random_file_name)
    if '0 errors' in o:
        try: os.remove(random_file_name)
        except: ...
        return True

    prog_ensure = prog[:idx2] +'{}'+prog[main_idx:]
    open(random_file_name,'w').write(prog_ensure)
    o,e = run_code(random_file_name)
    try: os.remove(random_file_name)
    except: ...
    import re
    num_verified = re.search(r'(\d+) verified', o)
    num_verified = int(num_verified.group(1)) if num_verified else 0
    if '0 errors' in o and num_verified > 0:
        return True
    return False

def check_pairs_loop(prog):
    prog = '\n'.join([x for x in prog.split('\n') if x!=''])
    idx = prog.rfind('fn ', 0, prog.rfind('fn ')) 
    main_idx = prog.find('fn main()')
    function_of_concern = prog[idx:main_idx]
    last_bracket = function_of_concern[:function_of_concern.rfind('}')].rfind('}')

    lines = function_of_concern[:last_bracket+1].split('\n')
    final_code = prog[:idx] + '\n'.join(lines[:-2] + ['assert(false);'] + lines[-2:]) + function_of_concern[last_bracket+1:] + prog[main_idx:]
    random_file_name = f'temp{str(random.randint(0, 10000))}.rs'
    open(random_file_name,'w').write(final_code)
    o,e = run_code(random_file_name)
    try: os.remove(random_file_name)
    except: ...
    if '0 errors' in o and '0 verified' not in o:
        return True

    last_bracket = function_of_concern.rfind('}')
    lines = function_of_concern[:last_bracket+1].split('\n')
    final_code = prog[:idx] + '\n'.join(lines[:-2] + ['assert(false);'] + lines[-2:]) + function_of_concern[last_bracket+1:] + prog[main_idx:]
    random_file_name = f'temp{str(random.randint(0, 10000))}.rs'
    open(random_file_name,'w').write(final_code)
    o,e = run_code(random_file_name)
    try: os.remove(random_file_name)
    except: ...
    if '0 errors' in o and '0 verified' not in o:
        return True
    return False

def evaluate_node(state):
    """ Evaluate the correctness of a given state. """
    generation = state[-1]['content']

    file_name = extract_and_save_code(generation, file_suffix=VERUS_FILE_SUFFIX)
    output, error = run_code(file_name)
    error_msg = error

    if extract_code(generation).count('assume')>0:
        error_msg = 'Assume statements are not allowed' 
        return -1, error_msg
    
    if extract_code(generation).find('#[verifier::external]')!=-1:
        error_msg = 'External verifiers are not allowed' 
        return -1, error_msg
    if extract_code(generation).find('#[verifier::external_body]')!=-1:
        error_msg = 'External verifiers are not allowed' 
        return -1, error_msg
    
    extracted_code_uncommented = '\n'.join([line for line in extract_code(generation).splitlines() if line.strip() and not line.strip().startswith("//")])
    if len(extracted_code_uncommented.splitlines())<(len([x for x in extract_code(generation).splitlines() if x.strip()!=''])//2):
        # This means, there are lot of comments in the code, that is going to mislead the critique module
        error_msg = 'Uncomment the code that you have written'
        return -1, error_msg
    if extracted_code_uncommented.find('ensures')==-1:
        error_msg = 'No ensures clause found' 
        return -1, error_msg
    
    if error_msg.find('warning: unreachable statement')!=-1:
        error_msg = 'Unreachable statement found. Cannot verify' 
        return -1, error_msg


    if extract_code(generation).replace(' ', '').replace('\n', '').replace('\t', '').replace('\r', '').find('ensurestrue')!=-1:
        error_msg = 'Cannot create trivial postcondition: Ensures true' 
        return -1, error_msg
    
    if extracted_code_uncommented.replace(' ', '').replace('\n', '').replace('\t', '').replace('\r', '').count('{}') >= 2:
        error_msg = 'Infinite loops are not allowed.' 
        return -1, error_msg
    
    def is_valid_string(s):
        # Pattern to find '&mut' not followed by 'Vec', allowing for optional spaces
        pattern_invalid_ampersand_mut = r'&mut(?!\s*Vec\b)'
        
        if re.search(pattern_invalid_ampersand_mut, s):
            return False  # Invalid if '&mut' not followed by 'Vec' is found
        return True  # Valid string

    if not is_valid_string(extract_code(generation)):
        error_msg = 'Mutables for non-vec type are not allowed' 
        return -1, error_msg
    

    



    # Now run the erro parsing function
    
    num_verified = re.search(r'(\d+) verified', output)
    num_verified = int(num_verified.group(1)) if num_verified else 0

    num_errors = re.search(r'(\d+) errors', output)
    num_errors = int(num_errors.group(1)) if num_errors else 0

    # Num_verified is simply -1 score
    if num_verified == 0 and num_errors == 0:
        print('Score is:', -1)
        return -1, error_msg
    if num_verified == 1 and num_errors == 0:
        print('Likely hacked the system, returning 0')
        return -1, error_msg
    score = num_verified/(num_verified+num_errors)

    normalized_score_for_one = 1/(num_verified+num_errors)
    
    if num_verified>20:
        print('Somehow, num_verified is greater than 20, possibly bug in parsing, returning 0', error)
        return -1, error_msg

    if num_errors == 0:
        if check_pairs(extracted_code_uncommented):
            print('Trivially verified')
            return -1, 'Trivially verified'
        if check_pairs_loop(extracted_code_uncommented):
            print('Trivially verified')
            return -1, 'Trivially verified'
        print('Hell Yeah', output)
        return 1, error_msg


    parsed_msgs = parse_error_message(error_msg)
    parsed_errors = [msg for msg in parsed_msgs if msg.type == 'error'][:-1]
    parsed_notes = [msg for msg in parsed_msgs if msg.type == 'note']
    
    # Every error is a -0.1
    score -= normalized_score_for_one*0.1*len(parsed_errors)
    # Every note is -0.05
    score -= normalized_score_for_one*0.04* len(parsed_notes)
    print('Score is:', score, num_verified, num_errors)
    return score, error_msg



import os


def get_system_message_from_error_exemplars(error_exemplars):
    
    # Randomly pick 10 random examples
    choices = random.sample(error_exemplars, k=min(100, 3*len(error_exemplars)//4))
    return_string = "Here are some examples of fixing verus code based on compiler error message:\n\n\n"
    for i,choice in enumerate(choices):
        return_string += f"# Verus Error Fixing Example {i+1}:\n\n## Incorrect Code:\n```rust\n{choice[0].strip()}\n```\n## Error Message:\n```\n{choice[1].strip()}\n```\n## Corrected Code after fixing the errors:\n```rust\n{choice[2].strip()}\n```\n"
        return_string += '\n\n'
    return return_string

def main(config, logger):

    if 'error_pairs' in config and len(config['error_pairs'])>0:
        print('See in nohup we have error_pairs in here')
        system_msg = get_system_message_from_error_exemplars(config['error_pairs'])
        init_state = [{
            'role': 'system',
            'content': system_msg
        }]
        print('Exemplars were used!')
    else:
        init_state = []

    root = True
    SAVE_DIR = config['SAVE_DIR']
    
    PROGRAM_NUMBER = config['PROGRAM_FILE']
    PROGRAM_FILE = config['PROGRAM_FILE']

    MAX_DEPTH = config['TREE']['MAX_DEPTH']

    save_dir = f'{SAVE_DIR}/{uuid.uuid4()}-{PROGRAM_NUMBER}-{0}'
    os.makedirs(save_dir, exist_ok=True)

    program = open(f'{PROGRAM_FILE}').read()
    file_name = save_code_to_file(program, VERUS_FILE_SUFFIX)
    output, error_messsage = run_code(file_name)
    hints_fill_format = {
        'role': 'user',
        'content': [
        {
            'type': 'text',
            'text': f'''Given a Verus program with function signature, preconditions, postconditions, and code, fix the errors present in the code. Effectively return the complete verys program by fixing all proof statements or adjusting the code, such that the code compiles correctly. Do no modify function signatures requires, ensures or specs. Repeat: Do not ever modify those lines in ensures clause, requires clause, function signatures. Just edit the proof. **Only in case of overflow errors**, you can make reasonable relaxations on the size of the input variables. For instance, considering the input length of array to be any value less than 10 is not reasonable. Similarly for integer inputs, considering them to be small numbers is not reasonable. Choose bigger bounds for relaxation. You can also use spec functions, to estimate the max value, and impose a condition accordingly. For instance, if error is integer overflow while doing multiplication, you can add requires statement such as: ```forall|k: int| 0 <= k < nums.len() ==> (0 <= #[trigger] nums[k] * #[trigger] nums[k] < i32::MAX)```** However, absolutely no other changes to precondition and postcondition are permitted! Below is the program::
```rust
{program}
```

The program has following error message:
```
{error_messsage}
````

Solution Format:
[Thoughts on Error Message]
[Thoughts on Error Resolution]
[Thoughts on Corner Cases, such as Overflow etc.]
```rust
[Complete Code]
```''',
            },
        ]
    } 

    history = init_state + [hints_fill_format]

    for iteration_number in range(MAX_DEPTH):
        if root:
            messages = run_llm(history, 'default', max_tokens = 1024, temperature = 0.7, n = 32)
        else:
            # Send an async request for each history
            run_llm_with_kwargs = partial(run_llm, model='default', max_tokens=1024, temperature=0.7, n=1)
            with multiprocessing.Pool(32) as pool:
                messages = pool.map(run_llm_with_kwargs, history)
            messages = [x[0] for x in messages if len(x)>0]
        if not root: 
            new_states = [history[i] + [{'role':'assistant', 'content' : x}] for i,x in enumerate(messages)]
        else:
            new_states = [history + [{'role':'assistant', 'content' : x}] for i,x in enumerate(messages)]

        scores = [evaluate_node(state) for state in new_states]

        error_messages = [x[1] for x in scores]
        scores = [x[0] for x in scores]

        index_to_keep = [i for i, x in enumerate(scores) if x>=0]

        if len(index_to_keep) == 0:
            print('No valid states found, retrying')
            continue

        new_states = [new_states[i] for i in index_to_keep]
        scores = [scores[i] for i in index_to_keep]
        error_messages = [error_messages[i] for i in index_to_keep]


        # Sample 32 instances from the new_states such that the probability of sampling an instance is proportional to the softmax of score
        softmax_scores = Softmax()(torch.tensor([x/TEMPERATURE for x in scores])).tolist()
        new_indices = random.choices([i for i in range(len(new_states))], weights = softmax_scores, k = 32)
        new_indices = sorted(new_indices)


        new_states = [deepcopy(new_states[i]) for i in new_indices]
        scores = [scores[i] for i in new_indices]
        error_messages = [deepcopy(error_messages[i]) for i in new_indices]

        for i in range(len(new_states)):
            new_states[i] += [{
                    'role' : 'user',
                    'content' : [
                        {
                            'type': 'text',
                        'text': f"I got the following errors:\n ```{error_messages[i]}```\n Follow the previous format, and fix all the errors. Then give the complete updated code. Remember, you are not allowed to modify preconditions and postconditions. Not even a single line edit is allowed for any requires of ensures conditions in all the functions. You can however impose a reasonable relaxation on the size of the input variables in case of overflow errors. However note that considering the input length of array to be any value less than 10 is not reasonable. Similarly for integer inputs, considering them to be small numbers is not reasonable. For instance, using n==0,1... is not allowed. Use big bounds such as n<1000. Remember this is the last resort for handling overflows."
                        }   
                    ]
                }]
        history = new_states
        root = False
        with open(f'{save_dir}/root_{iteration_number}.pkl', 'wb') as f:
            pickle.dump(history, f)

        if any([x>=1 for x in scores]):
            print('Hell Yeah')
            correct_idx = [i for i, score in enumerate(scores) if score>=1][0]
            for i, score in enumerate(scores):
                if score>=1:
                    print('Saving the solution')
                    with open(f'{save_dir}/solution_{iteration_number}.pkl', 'wb') as f:
                        pickle.dump(history[i], f)
                else:
                    print('Incorrect Instance')

            history = history[correct_idx]
            code = extract_code(history[-2]['content'])
            with open(f'{save_dir}/correct_code.rs', 'w') as f:
                f.write(code)

            error_triplets = []
            max_above_depth = 5
            only_assistant_messages = [x for x in history if x['role']=='assistant']
            for i in range(len(only_assistant_messages)-2, -1, -1):
                if max_above_depth==0:
                    break
                max_above_depth-=1
                erreneous_code = extract_code(only_assistant_messages[i]['content'])
                # Now run the code to get the error message
                file_name = save_code_to_file(erreneous_code, VERUS_FILE_SUFFIX)
                _, error_messsage = run_code(file_name)
                error_triplets.append((erreneous_code, error_messsage, code))
            return error_triplets, f'{save_dir}/correct_code.rs'
        
    return None, None
