from typing import Union, List, Sequence

from akrr.akrrerror import AkrrException


def which(program: str) -> Union[str, None]:
    """
    return full path of executable.
    If program is full path return it
    otherwise look in PATH. If still executable is not found return None.
    """
    import os

    def is_exe(file_path):
        return os.path.isfile(file_path) and os.access(file_path, os.X_OK)

    file_dir, _ = os.path.split(program)
    if file_dir:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


def clear_from_build_in_var(dict_in: dict) -> dict:
    """
    Return dict without  build-in variable and modules emerged in dict_in from exec function call
    """
    import inspect

    tmp = {}
    exec('wrong_fields_dict="wrong_fields_dict"', tmp)
    tmp.pop('wrong_fields_dict')
    wrong_fields = list(tmp.keys())

    dict_out = {}
    for key, val in dict_in.items():
        if inspect.ismodule(val):
            continue
        if wrong_fields.count(key) > 0:
            continue
        dict_out[key] = val

    return dict_out


def exec_files_to_dict(*files: str, var_in: dict = None) -> dict:
    """
    execute python from files and return dict with variables from that files.
    If var_in is specified initiate variables dictionary with it.
    """
    if var_in is None:
        tmp = {}
    else:
        import copy
        tmp = copy.deepcopy(var_in)

    for f in files:
        with open(f, "r") as file_in:
            exec(file_in.read(), tmp)
    return clear_from_build_in_var(tmp)


def clean_unicode(s):
    if s is None:
        return None

    if type(s) is bytes:
        s = s.decode("utf-8")

    replacements = {
        '\u2018': "'",
        '\u2019': "'",
    }
    for src, dest in replacements.items():
        s = s.replace(src, dest)
    return s


def format_recursively(s: str, d: dict, keep_double_brackets: bool = False) -> str:
    """
    Recursively format sting `s` using dictionary `d` until where are no more substitution.
    Return resulting string.

    Double curly brackets are escaped, for example "{{variable}}" would be NOT substituted.

    If `keep_double_brackets` set to try at the end all double curly brackets are replaced
    by single brackets. This is done for creation of batch bash scripts, with bracked used
    for variables.
    """
    s = s.replace('{{', 'LeFtyCurlyBrackets')
    s = s.replace('}}', 'RiGhTyCurlyBrackets')
    s0 = s.format(**d)
    count = 1
    while s0 != s:
        s = s0
        s = s.replace('{{', 'LeFtyCurlyBrackets')
        s = s.replace('}}', 'RiGhTyCurlyBrackets')
        s0 = s.format(**d)
        count += 1
        if count > 100:
            raise AkrrException("Template ERROR too many nesting templates")
    if keep_double_brackets:
        s0 = s0.replace('LeFtyCurlyBrackets', '{{')
        s0 = s0.replace('RiGhTyCurlyBrackets', '}}')
    else:
        s0 = s0.replace('LeFtyCurlyBrackets', '{')
        s0 = s0.replace('RiGhTyCurlyBrackets', '}')
    return s0


def replace_at_var_at(s: str, ds: List[dict]):
    """
    Replaces @variable@ in string `s` by ds[furthest]['variable'].
    `ds` is list of dictionaries
    """
    d = {}
    # print "#"*80
    for di in ds:
        d.update(di)
    while s.find("@") >= 0:
        # print s
        at1 = s.find("@")
        at2 = s.find("@", at1 + 1)
        var_name = s[at1 + 1:at2]
        var_value = d[var_name]
        s = s.replace("@" + var_name + "@", str(var_value))
    return s


def floats_are_close(a: float, b: float, rel_tol: float = 1.0e-7) -> bool:
    from math import fabs
    if a == 0 and b == 0:
        return True
    if a == 0:
        if b <= rel_tol:
            return True
        else:
            return False
    if b == 0:
        if a <= rel_tol:
            return True
        else:
            return False

    rel_diff = fabs(2.0*(a-b)/(a+b))

    if rel_diff <= rel_tol:
        return True

    return False


def is_int(s: str) -> bool:
    try:
        int(s)
        return True
    except ValueError:
        return False


def is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def get_float_or_int(a: Union[str, float, int]) -> Union[int, float]:
    """return float or int"""
    if isinstance(a, (int, float)):
        return a
    if isinstance(a, str):
        if is_int(a):
            return int(a)
        else:
            return float(a)
    raise ValueError("Unknown type")

def get_int_float_or_str(a: Union[str, float, int]) -> Union[int, float,str]:
    """return float or int"""
    if isinstance(a, (int, float)):
        return a
    if isinstance(a, str):
        if is_int(a):
            return int(a)
        elif is_float(a):
            return float(a)
    return a

def strip_empty_lines(m_str):
    """
    remove empty lines
    """
    out = ""
    for line in m_str.split('\n'):
        if not line.strip() == '':
            out += line + "\n"
    return out


def get_full_path(cur_dir, path):
    """
    return full path if path is relative to cur_dir
    if path is full path return it
    """
    import os.path
    if len(path) == 0:
        return cur_dir
    if path[0] == "/":
        return path
    return os.path.abspath(os.path.join(cur_dir, path))


def get_list_from_comma_sep_values(in_str):
    """
    Get list of strings from string with comma separated values.
    If in_str is not string return it without change.
    """
    if in_str is None:
        return None
    elif isinstance(in_str, str):
        if in_str.count(",") > 0:
            return in_str.split(",")
        else:
            return [in_str]
    else:
        return in_str


def smart_str_merge(str_list: Sequence[str], middle: str = ",", last: str = "or"):
    """
    Merge string as "val1, val2 or val3
    """
    s = ""
    for v in str_list:
        if v == str_list[0]:
            s += v
        elif v == str_list[-1]:
            s += " " + last + " " + v
        else:
            s += middle + " " + v
    return s


def base_gzip_encode(value: str) -> str:
    import os
    return os.popen('echo "%s"|gzip -9|base64' % value).read().replace('\n', '')


def base_gzip_decode(value: str) -> str:
    import os
    return os.popen('echo "%s"|base64 -d|gzip -d' % value).read()


def make_dirs(path, verbose=True):
    """
    Recursively create directories if not in dry run mode
    """
    import akrr
    from akrr import akrrerror
    import os
    from akrr.util import log

    if not akrr.dry_run:
        if os.path.isdir(path):
            if verbose:
                log.debug2("Directory %s already exists.", path)
        elif not os.path.exists(path):
            if verbose:
                log.debug2("Creating directory: {}".format(path))
            os.makedirs(path, mode=0o755)
        else:
            raise akrrerror.AkrrError("Can not create directory %s, because it exists and is not directory" % path)
    else:
        log.dry_run("make_dirs(%s)", path)


def progress_bar(progress: float = None):
    import sys

    bar_width = 50
    if progress is None:
        bar_progress = bar_width
    else:
        bar_progress = int(round(progress*bar_width))
    bar_todo = bar_width - bar_progress
    sys.stdout.write("[" + "#" * bar_progress + " " * bar_todo + "]")
    sys.stdout.flush()
    if progress is None:
        sys.stdout.write("\n")
        sys.stdout.flush()
    else:
        sys.stdout.write("\b" * (bar_width + 2))


