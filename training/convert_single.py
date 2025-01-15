from openai import OpenAI
import openai
import json
import argparse
from typing import List, Tuple
import pickle
import random
from verus_utils import extract_and_save_code, run_code, extract_code
from tqdm import tqdm
import uuid
import os


VERUS_FILE_SUFFIX = str(random.randint(0, 10000))

def check_pairs(prog):
    idx = prog.rfind('fn ', 0, prog.rfind('fn ')) 
    main_idx = prog.find('fn main()')
    # Find first {, replace with "assert false"
    idx2 = prog.find('{', idx)
    prog_require = prog[:idx2] + '{\n\tassert (false);\n' + prog[idx2+1:]
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

def main(config, returnAllResponses=False):

    print('INside convert', config)
    open(f'ds4/{config["PROGRAM_NUMBER"]}.rs', 'w').write('hello')

    SAVE_DIR = config['SAVE_DIR']
    PROMPT_RANDOM_EXAMPLES : List[Tuple[str, str]] = config['PROMPT_RANDOM_EXAMPLES']
    PROGRAMS_FILE = config['PROGRAMS_FILE']
    MODEL = config['MODEL_NAME']
    PROGRAM_NUMBER = config['PROGRAM_NUMBER']
    temperature = config['CONVERT']['TEMPERATURE']
    batch_size = config['BATCH_SIZE'] 

    programs = json.load(open(PROGRAMS_FILE))

    def pull_random_examples():
        import random
        choices = random.sample(PROMPT_RANDOM_EXAMPLES, k=min(50, 3*len(PROMPT_RANDOM_EXAMPLES)//4))
        messages = []
        for i,choice in enumerate(choices):
            messages.append({
                "role": "user",
                "content": f"Consider the following dafny code:\n```{choice[0]}```\n\nI want to convert this to verus code. Based on the syntax i gave you, convert the code to verus. Note, you may need to make some datatype related changes for it to work in verus. Specifically use the most appropriate ones from the syntax and code examples provided earlier. However, do not change invariant or specifications (ensures and requires clauses). Make sure to include the use statements, proper start of code using verus!, empty fn main() {paran} as done in examples"
            })
            messages.append({
                "role": "assistant",
                "content": f"```rust\n{choice[1].strip()}\n```"
            })
        return messages

    solved_programs = []
    all_responses = []

    program = programs[PROGRAM_NUMBER]

        
    client = openai.Client(
        base_url="http://127.0.0.1:30000/v1", api_key="EMPTY")

    paran = '{}'
    model = MODEL #'default'

    messages=[
        {
            "role": "system",
            "content": open('/data/user_data/pranjala/system_msg_syntax_examples_guidelines.txt').read() 
        },
        {
            "role": "user",
            "content": [
            {
                "type": "text",
                "text": f"Consider the following dafny code:\n```{program}``\n\nI want to convert this to verus code. Based on the syntax i gave you, convert the code to verus. Note, you may need to make some datatype related changes for it to work in verus. Specifically use the most appropriate ones from the syntax and code examples provided earlier. However, do not change invariant or specifications (ensures and requires clauses). Make sure to include the use statements, proper start of code using verus!, empty fn main() {paran} as done in examples"
            }
            ]
        }
    ]
    messages = messages[0:1] + pull_random_examples() + messages[1:]
    
    response = client.chat.completions.create(
        model=model,
        messages = messages,
        temperature=temperature,
        max_tokens=2048,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        response_format={
        "type": "text"
        },
        n=batch_size
    )
    all_responses.append(response)

    import uuid
    select_uuid = str(uuid.uuid4())
    dumped_filename = 'dumped_generations/' + select_uuid + f'_{model.split("/")[-1]}.pkl'

    with open(dumped_filename, 'wb') as f:
        pickle.dump(response, f)


    all_errs = []
    all_outs = []
    num_verifies = []
    good_indexes = []
    for _ in range(len(response.choices)):
        file_name = extract_and_save_code(response.choices[_].message.content, file_suffix=VERUS_FILE_SUFFIX)
        output, err = run_code(file_name)

        import re

        num_verified = re.search(r'(\d+) verified', output)
        num_verified = int(num_verified.group(1)) if num_verified else 0

        num_errors = re.search(r'(\d+) errors', output)
        num_errors = int(num_errors.group(1)) if num_errors else 0

        os.makedirs(f'{SAVE_DIR}/dumps', exist_ok=True)
        with open(f'{SAVE_DIR}/dumps/verified_prog={PROGRAM_NUMBER}_{num_verified}_{num_errors}_' + f'{select_uuid}_{_}' + '.rs', 'w') as f:
            f.write(extract_code(response.choices[_].message.content))


        extracted_code = extract_code(response.choices[_].message.content)
        if extracted_code.count('assume')>0:
            num_verifies.append(-1)
            continue
        # Remove all white spaces
        if extracted_code.replace(' ', '').replace('\n', '').replace('\t', '').replace('\r', '').find('ensurestrue')!=-1:
            num_verifies.append(-1)
            continue

        extracted_code_uncommented = '\n'.join([line for line in extracted_code.splitlines() if line.strip() and not line.strip().startswith("//")])
        if len(extracted_code_uncommented.splitlines())<(len([x for x in extracted_code.splitlines() if x.strip()!=''])//2):
            # This means, there are lot of comments in the code, that is going to mislead the critique module
            num_verifies.append(-1)
            continue

        if extracted_code_uncommented.find('ensures')==-1:
            num_verifies.append(-1)
            continue

        if extracted_code_uncommented.replace(' ', '').replace('\n', '').replace('\t', '').replace('\r', '').count('{}') >= 2:
            num_verifies.append(-1)
            continue

        if extracted_code.find('#[verifier::external]')!=-1:
            num_verifies.append(-1)
            continue

        if extracted_code.find('#[verifier::external_body]')!=-1:
            num_verifies.append(-1)
            continue

        if err.find('warning: unreachable statement')!=-1:
            num_verifies.append(-1)
            continue

        import re

        def is_valid_string(s):
            # Pattern to find '&mut' not followed by 'Vec', allowing for optional spaces
            pattern_invalid_ampersand_mut = r'&mut(?!\s*Vec\b)'
            
            if re.search(pattern_invalid_ampersand_mut, s):
                return False  # Invalid if '&mut' not followed by 'Vec' is found
            return True  # Valid string

        if not is_valid_string(extracted_code):
            num_verifies.append(-1)
            continue




        if num_verified==1 and num_errors==0:
            num_verifies.append(-1)
            continue
        if num_verified!=0 or num_errors!=0:
            print(num_verified, num_errors)
            good_indexes.append(_)
            os.makedirs(f'{SAVE_DIR}', exist_ok=True)
            with open(f'{SAVE_DIR}/verified_prog={PROGRAM_NUMBER}_{num_verified}_{num_errors}_' + f'{select_uuid}_{_}' + '.rs', 'w') as f:
                f.write(extract_code(response.choices[_].message.content))
            # print(err)
        num_verifies.append(num_verified)

        # Do a regex search for <number> verified
        if num_verified>0 and num_errors==0:

            # Let's verify triviality, 
            if check_pairs(extracted_code_uncommented):
                print('Trivially verified')
                num_verifies[-1] = -1
                continue
            if check_pairs_loop(extracted_code_uncommented):
                print('Trivially verified')
                num_verifies[-1] = -1
                continue
            solved_programs.append((PROGRAM_NUMBER, program, extracted_code))
        
        all_errs.append(err)
        all_outs.append(output)
        # print(output, err)
        # print('\n'*5)
    print(len(good_indexes), [num_verifies[_] for _ in good_indexes])
    # Delete the file_name
    try: os.system(f'rm -f {file_name}')
    except: ...
    if returnAllResponses:
        return solved_programs, all_responses
    else:
        return solved_programs
