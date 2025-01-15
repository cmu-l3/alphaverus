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
import os

MODE = int(sys.argv[1]) if len(sys.argv)>=2 else 0
FILE_NAME = sys.argv[2] if len(sys.argv)>=3 else 'hint_pairs/he3_x.txt'
ITERATION_NUMBER = int(sys.argv[3])

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


ERROR_EXEMPLARS_FILE = f'/data/user_data/pranjala/verus_iterative_gpt_assisted24/histories/iter{ITERATION_NUMBER}.json'


program = open(FILE_NAME).read()
file_name = save_code_to_file(program, VERUS_FILE_SUFFIX)
output, error_messsage = run_code(file_name)
paran_close = '}'
paran_open = '{'
paran = '{}'


hints_fill_format = {
    'role': 'user',
    'content': [
        {
            'type': 'text',
            'text': f'''Given a Verus program with function signature, preconditions, postconditions, and code, fix the errors present in the code. Your task is to provide only the corrected body of the function, without repeating the function signature, requires, ensures, or specs. Focus on fixing proof statements or adjusting the code to ensure correct compilation. Do not modify function signatures, requires clauses, ensures clauses, or specs.
```rust
<function_body>
{paran_close} // End of function
fn main() {paran}
{paran_close} // verus!
```

Below is the program::
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
[Function Body, with closing paranthesis and empty main function]
```

Important: For outputting the code, follow the same format as shown in examples and as described in the prompt.
''',
        },
    ]
}

def filter_codes(eps):
    # Find the last function index
    indices = []
    for x in eps:
        x = x[0]
        idx = x[:x.find('fn main()')].rfind('fn ')
        idx2 = x[idx:].find('\n{')
        indices.append(idx+idx2+2)

    # Do diff b/w eps[i][0] and eps[i][2]
    import difflib
    all_diffs = []
    examples_to_keep = []
    for i in range(len(eps)):
        diff = list(difflib.Differ().compare(eps[i][0].split('\n'), eps[i][2].split('\n')))
        # Check if there is any addition or deletion in the diff
        all_diffs.append(diff)
        for line_num, d in enumerate(diff):
            if d.startswith('+ ') or d.startswith('- '):
                change_position = sum(len(line) + 1 for line in eps[i][0].split('\n')[:line_num])
                if indices[i] < change_position:
                    print(f'Example {i+1}:')
                    examples_to_keep.append(eps[i])
                break
    return examples_to_keep

def strip_body(code):
    idx = code[:code.find('fn main()')].rfind('fn ') 
    non_body_code = code[:idx+code[idx:].find('\n{')+2].strip()
    completion = code[idx+code[idx:].find('\n{')+3:].strip()
    return non_body_code, completion

if ERROR_EXEMPLARS_FILE is None or not os.path.exists(ERROR_EXEMPLARS_FILE):
    history = [hints_fill_format]
else:
    with open(ERROR_EXEMPLARS_FILE) as f:
        error_exemplars = json.load(f)['error_pairs']
    error_exemplars = filter_codes(error_exemplars)

    choices = random.sample(error_exemplars, k = 3*len(error_exemplars)//4)
    return_string = "Here are some examples of fixing verus code based on compiler error message:\n\n\n"
    for i,choice in enumerate(choices):
        
        return_string += f"# Verus Error Fixing Example {i+1}:\n\n## Incorrect Code:\n```rust\n{choice[0].strip()}\n```\n## Error Message:\n```\n{choice[1].strip()}\n```\n## Corrected Function Body after fixing the errors:\n```rust\n{strip_body(choice[2].strip())[1]}\n```\n"
        return_string += '\n\n'
    history = [{
        'role': 'system',
        'content': return_string
    }] + [hints_fill_format]


def evaluate_node(state):
    """ Evaluate the correctness of a given state. """
    generation = state[-1]['content']



    ec = extract_code(generation)
    if ec.strip().startswith('{'):
        ec = ec.strip()[1:]

    code = strip_body(program)[0] + ec.strip()

    file_name = f'temp{MODE}_{VERUS_FILE_SUFFIX}.rs'
    open(file_name, 'w').write(code)
    output, error = run_code(file_name)
    if error.find('this file contains an unclosed delimiter') != -1:
        code = code + paran_close
        open(file_name, 'w').write(code)
    output, error = run_code(file_name)
    error_msg = error

    if code.count('assume')>0:
        error_msg = 'Assume statements are not allowed' 
        return -1, error_msg
    
    if code.find('#[verifier::external]')!=-1:
        error_msg = 'External verifiers are not allowed' 
        return -1, error_msg
    if code.find('#[verifier::external_body]')!=-1:
        error_msg = 'External verifiers are not allowed' 
        return -1, error_msg
    
    extracted_code_uncommented = '\n'.join([line for line in code.splitlines() if line.strip() and not line.strip().startswith("//")])

    
    if error_msg.find('warning: unreachable statement')!=-1:
        error_msg = 'Unreachable statement found. Cannot verify' 
        return -1, error_msg


    
    if extracted_code_uncommented.replace(' ', '').replace('\n', '').replace('\t', '').replace('\r', '').count('{}') >= 2 + program.replace(' ', '').replace('\n', '').replace('\t', '').replace('\r', '').count('{}'):
        error_msg = 'Infinite loops are not allowed.' 
        return -1, error_msg
    
    def is_valid_string(s):
        # Pattern to find '&mut' not followed by 'Vec', allowing for optional spaces
        pattern_invalid_ampersand_mut = r'&mut(?!\s*Vec\b)'
        
        if re.search(pattern_invalid_ampersand_mut, s):
            return False  # Invalid if '&mut' not followed by 'Vec' is found
        return True  # Valid string

    if not is_valid_string(code):
        error_msg = 'Mutables for non-vec type are not allowed' 
        return -1, error_msg
    
    error_msg = error

    
    num_verified = re.search(r'(\d+) verified', output)
    num_verified = int(num_verified.group(1)) if num_verified else 0

    num_errors = re.search(r'(\d+) errors', output)
    num_errors = int(num_errors.group(1)) if num_errors else 0

    # Num_verified is simply -1 score
    if num_verified == 0 and num_errors == 0:
        print('Score is:', -1)
        return -1, error_msg
    score = num_verified/(num_verified+num_errors)

    normalized_score_for_one = 1/(num_verified+num_errors)
    
    if num_verified>20:
        # There is some issue
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

root = True


import os
if 'mbpp' in FILE_NAME:
    if MODE == 1:
        save_dir = f'solved_programs_final24_mbpp/tree_search/{ITERATION_NUMBER}-{MODE}/{uuid.uuid4()}-{os.path.split(FILE_NAME)[-1]}-{MODE}'
    else:  
        save_dir = f'solved_programs_final24_mbpp/tree_search/{ITERATION_NUMBER}/{uuid.uuid4()}-{os.path.split(FILE_NAME)[-1]}-{MODE}'
else:
    if MODE == 1:
        save_dir = f'solved_programs_final24_hev/tree_search/{ITERATION_NUMBER}-{MODE}/{uuid.uuid4()}-{os.path.split(FILE_NAME)[-1]}-{MODE}'
    else:
        save_dir = f'solved_programs_final24_hev/tree_search/{ITERATION_NUMBER}/{uuid.uuid4()}-{os.path.split(FILE_NAME)[-1]}-{MODE}'
os.makedirs(save_dir, exist_ok=True)

for iteration_number in range(10):
    print('Iteration Number:', iteration_number)
    if root:
        messages = run_llm(history, 'default', max_tokens = 1024, temperature = 1.0, n = 32)
    else:
        # Send an async request for each history
        run_llm_with_kwargs = partial(run_llm, model='default', max_tokens=1024, temperature=1.0, n=1)
        with multiprocessing.Pool(32) as pool:
            messages = pool.map(run_llm_with_kwargs, history)
        messages = [x[0] for x in messages if len(x)>0]
    if not root: 
        new_states = [history[i] + [{'role':'assistant', 'content' : x}] for i,x in enumerate(messages)]
    else:
        new_states = [history + [{'role':'assistant', 'content' : x}] for i,x in enumerate(messages)]

    if MODE == 0:
        scores = [evaluate_node(state) for state in new_states]
    elif MODE==1:
        actual_scores = [evaluate_node(state) for state in new_states]
        scores = [(1, actual_scores[_][1]) for _ in range(len(new_states))]
        actual_scores = [actual_scores[_][0] for _ in range(len(scores))]

    elif MODE==2:
        actual_scores = [evaluate_node(state)[0] for state in new_states]
        scores = [evaluate_node(state)[0] for state in new_states]
        # Pick the to-4 elements
        top4_index = sorted(range(len(scores)), key = lambda x: scores[x], reverse = True)[:4]
        # Set score as 1000 for the top 4 elements, and -1000 for al
        scores = [(1000,actual_scores[_][1]) if i in top4_index else (-1000,actual_scores[_][1]) for i in range(len(scores))]
        actual_scores = [actual_scores[_][0] for _ in range(len(scores))]

    error_messages = [x[1] for x in scores]
    scores = [x[0] for x in scores]

    index_to_keep = [i for i, x in enumerate(scores) if x>=0]

    if len(index_to_keep) == 0:
        print('No valid states found, retrying')
        continue

    new_states = [new_states[i] for i in index_to_keep]
    scores = [scores[i] for i in index_to_keep]
    error_messages = [error_messages[i] for i in index_to_keep]


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
                        'text': f"I got the following errors:\n ```{error_messages[i]}```\n Follow the previous format, suggesting how to fix all the errors. Then give the updated function body, making sure to close the function with a closing paranthesis and main function. Remember to just output the completion without the function signature, requires and ensures. Only the body of the function is required. Follow the previous format, strictly. Do not repeat the function signature, requires and ensures."
                    }   
                ]
            }]
    history = new_states
    root = False
    with open(f'{save_dir}/root_{iteration_number}.pkl', 'wb') as f:
        pickle.dump(history, f)

    if any([x>=1 for x in (scores if MODE==0 else actual_scores)]):
        print('Hell Yeah')
        for i, score in enumerate(scores):
            if score>=1:
                print('Saving the solution')
                with open(f'{save_dir}/solution_{iteration_number}.pkl', 'wb') as f:
                    pickle.dump(history[i], f)
                    break


        code = extract_code(history[i][-2]['content'])
        with open(f'{save_dir}/correct_code.rs', 'w') as f:
            f.write(code)

        sys.exit(0)