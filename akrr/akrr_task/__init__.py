
import os
import sys
import datetime
import re

from ..util import log
from .. import cfg
from .akrr_task_base import AkrrTaskHandlerBase
from .akrr_task_appker import AkrrTaskHandlerAppKer
from .akrr_task_bundle import AkrrTaskHandlerBundle


def get_local_task_dir(resource_name, app_name, time_stamp, task_is_active=True, version=None):
    if task_is_active:
        task_dir = os.path.join(cfg.data_dir, resource_name, app_name, time_stamp)
        if not os.path.isdir(task_dir):
            raise IOError("Directory %s does not exist or is not directory." % task_dir)
        return task_dir
    else:
        if version is not None and version==1:
            task_dir = os.path.join(cfg.completed_tasks_dir, resource_name, app_name, time_stamp)
        else:
            time_stamp_split = time_stamp.split(".")
            if len(time_stamp_split) > 3:
                year = time_stamp_split[0]
                month = time_stamp_split[1]
                day = time_stamp_split[2]
                task_dir = os.path.join(cfg.completed_tasks_dir, resource_name, app_name, year, month, time_stamp)
            else:
                task_dir = os.path.join(cfg.completed_tasks_dir, resource_name, app_name, time_stamp)

        if not os.path.isdir(task_dir):
            raise IOError("Directory %s does not exist or is not directory." % task_dir)
        return task_dir


def get_local_task_proc_dir(resource_name, app_name, time_stamp, task_is_active=True):
    return os.path.join(get_local_task_dir(resource_name, app_name, time_stamp, task_is_active=task_is_active), 'proc')


original_stderr = None
original_stdout = None
log_file = None


def redirect_stdout_to_log(log_filename):
    global original_stderr
    global original_stdout
    global log_file

    if log_file is not None:
        raise IOError("stdout was already redirected once")

    log_file = open(log_filename, "a")
    original_stderr = sys.stderr
    original_stdout = sys.stdout

    sys.stderr = log_file
    sys.stdout = log_file

    time_now = datetime.datetime.today().strftime("%Y-%m-%d %H:%M:%S")
    log.info(">>> " + time_now + " " + ">" * 96)


def redirect_stdout_back():
    global original_stderr
    global original_stdout
    global log_file

    if log_file is not None:

        time_now = datetime.datetime.today().strftime("%Y-%m-%d %H:%M:%S")
        log.info("<<< " + time_now + " " + "<" * 96 + "\n")

        sys.stderr = original_stderr
        sys.stdout = original_stdout

        log_file.close()

        original_stderr = None
        original_stdout = None
        log_file = None
    else:
        raise IOError("stdout was not redirected here")


def get_new_task_handler(task_id, resource_name, app_name, resource_param, app_param, task_param):
    """
    return new instance of TaskHandler.
    if `app_name` is "*bundle*" it return AkrrTaskHandlerBundle to handle bundled task
    otherwise it return AkrrTaskHandlerAppKer to handle single appkernel task.
    """
    if app_name.count("bundle") > 0:
        return AkrrTaskHandlerBundle(task_id, resource_name, app_name, resource_param, app_param, task_param)
    else:
        return AkrrTaskHandlerAppKer(task_id, resource_name, app_name, resource_param, app_param, task_param)


def get_task_handler_from_task_proc_dir(task_proc_dir):
    """
    return previously saved instance of TaskHandler
    using `task_proc_dir` as reference
    """
    if os.path.isdir(task_proc_dir):
        last_pickled_state = -1
        for f in os.listdir(task_proc_dir):
            m = re.match(r"(\d+).st", f, 0)
            if m is not None:
                i_state = int(m.group(1))
                if i_state > last_pickled_state:
                    last_pickled_state = i_state
        if last_pickled_state < 0:
            raise IOError("Can not find pickled file (%s/*.st) for task handler" % task_proc_dir)
        pickle_filename = os.path.join(task_proc_dir, "%06d.st" % last_pickled_state)
        log.info("Read pickled task handler from:\n\t%s\n" % pickle_filename)
        return get_task_handler_from_pkl(pickle_filename)
    else:
        raise IOError("Can not find task proc dir (%s) for task handler loading" % task_proc_dir)


def get_task_handler(resource_name, app_name, time_stamp):
    """
    return previously saved instance of TaskHandler
    using `resource_name`, `app_name`, `time_stamp` as reference
    """

    task_proc_dir = get_local_task_proc_dir(resource_name, app_name, time_stamp)
    return get_task_handler_from_task_proc_dir(task_proc_dir)


def get_task_handler_from_job_dir(job_dir):
    """
    Get previously saved TaskHandler from its `job_dir`
    """
    task_proc_dir = os.path.abspath(os.path.join(job_dir, "..", "proc"))
    return get_task_handler_from_task_proc_dir(task_proc_dir)


def get_task_handler_from_pkl(pickle_filename: str) -> AkrrTaskHandlerBase:
    """
    Load task handle from pkl file
    """

    def _unpickle_task_handler(filename: str) -> AkrrTaskHandlerBase:
        import pickle
        fin = open(filename, "rb")
        m_task_handler = pickle.load(fin)
        fin.close()
        return m_task_handler

    th = _unpickle_task_handler(pickle_filename)

    # import copy
    # renew and update some variables
    # th.old_status = copy.deepcopy(th.status)
    # th._old_method_to_run_next = copy.deepcopy(th._method_to_run_next)

    th.resource = cfg.find_resource_by_name(th.resourceName)
    th.app = cfg.find_app_by_name(th.appName)

    # Set old status and old method to run next to this one
    th.set_old_method_to_run_next_to_current

    # if openstack set remote_access_node to instance ip
    if th.resource['batch_scheduler'].lower() == "openstack" and getattr(th, "openstack_server_ip", None) is not None:
            th.resource['remote_access_node'] = getattr(th, "openstack_server_ip", None)

    return th


def dump_task_handler(th: AkrrTaskHandlerBase):
    """
    Save task handler state
    """
    th.LastPickledState += 1
    pickle_filename = os.path.join(th.taskDir, "proc/", "%06d.st" % th.LastPickledState)
    import pickle
    resource = th.resource
    app = th.app
    th.resource = None
    th.app = None

    fout = open(pickle_filename, "wb")
    pickle.dump(th, fout, cfg.task_pickling_protocol)
    fout.close()

    log.info("Saved pickled task handler to:\n\t%s" % pickle_filename)
    th.resource = resource
    th.app = app
