import os
from dotenv import load_dotenv

load_dotenv()

VERUS_PATH = os.getenv('VERUS_PATH', 'verus')  # Default to 'verus' if not set

def extract_code(res, add_main=True):
    start = res.find('```')
    end = res[start+3:].find('```')
    # pick line after first ticks, and upto second ticks
    if end!=-1:
        res_to_save = res[start + res[start:].find('\n'):start+3+end].strip()
    else:
        res_to_save = res[start + res[start:].find('\n'):].strip()

    if add_main and res_to_save.find('main()')==-1:
        res_to_save += '\n\nfn main() {}'
    return res_to_save

def save_code_to_file(code, file_suffix = ''):
    with open(f'temp{file_suffix}.rs', 'w') as f:
        f.write(code)
    return f'temp{file_suffix}.rs'

def extract_and_save_code(res, file_suffix = ''):
    res_to_save = extract_code(res)
    return save_code_to_file(res_to_save, file_suffix)


def run_code(file_name, timeout_duration=10):
    import subprocess
    try:
        result = subprocess.run(
            [VERUS_PATH, file_name, '--multiple-errors', '100'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_duration  # Timeout in seconds
        )
        return result.stdout.decode('utf-8'), result.stderr.decode('utf-8')
    except subprocess.TimeoutExpired:
        return "", "Process timed out after {} seconds".format(timeout_duration)


DEBUG_SAFE_CODE_CHANGE = False
import tempfile
import subprocess

def code_change_is_safe(
    origin,
    changed,
    verus_path,
    target_mode=True,
    util_path="../utils",
    inter=False,
    debug=True,
):
    if debug and DEBUG_SAFE_CODE_CHANGE:
        print("Debug mode is on, skip code change checking")
        return True

    orig_f = tempfile.NamedTemporaryFile(
        mode="w", delete=False, prefix="llm4v_orig", suffix=".rs"
    )
    orig_f.write(origin)
    orig_f.close()

    changed_f = tempfile.NamedTemporaryFile(
        mode="w", delete=False, prefix="llm4v_changed", suffix=".rs"
    )
    changed_f.write(changed)
    changed_f.close()

    cargopath = util_path + "/lynette/source/Cargo.toml"

    opts = []
    if inter:
        opts = ["--asserts-anno"]
    elif target_mode:
        opts = ["-t"]

    verus_compare_cmd = (
        ["cargo", "run", "--manifest-path", cargopath, "--", "compare"]
        + opts
        + [orig_f.name, changed_f.name]
    )
    m = subprocess.run(verus_compare_cmd, capture_output=True, text=True)

    if m.returncode == 0:
        return True
    elif m.returncode == 1:
        err_m = m.stdout.strip()
        if err_m == "Files are different":
            return False
        else:
            print(f"Error in comparing code changes: {err_m}")
            return True
    else:
        err_m = m.stderr.strip()
        if "unwrap()" in err_m:
            print(f"Error in comparing code changes: {err_m}")
            return True
    breakpoint()

    return True
