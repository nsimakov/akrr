"""
Responsible for serving the RESTful AKRR API.
"""

import os
import random
import string
import time
import traceback
import datetime

import logging as log

import bottle
from bottle import response, request

import akrr.db
from akrr.akrrerror import AkrrError
from . import bottle_api_json_formatting

import MySQLdb
import MySQLdb.cursors


from . import cfg
from . import daemon
from .util import log


apiroot = cfg.restapi_apiroot

app = bottle.Bottle()
app.install(bottle_api_json_formatting.JsonFormatting())

# Add global exception handling, all non-bottle exception will be placed in bottle.HTTPError and return to client


def error_translation(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except bottle.BottleException as e:
            raise e
        except Exception as e:
            raise bottle.HTTPError(400, str(e))
    return wrapper


app.install(error_translation)

# queue to exchange the orders with main akrr process
proc_queue_to_master = None
proc_queue_from_master = None


class SSLWSGIRefServer(bottle.ServerAdapter):
    """
    HTTPS server
    """

    def __init__(self, host='127.0.0.1', port=8090, certfile='server.pem', **options):
        self.certfile = certfile
        if not os.path.isfile(certfile):
            raise ValueError('Cannot locate certificate', certfile)
        super(SSLWSGIRefServer, self).__init__(host, port, **options)

    def run(self, handler):
        from wsgiref.simple_server import make_server, WSGIRequestHandler
        import ssl

        if self.quiet:
            class QuietHandler(WSGIRequestHandler):
                def log_request(self, *args, **kw):
                    pass

            self.options['handler_class'] = QuietHandler
        srv = make_server(self.host, self.port, handler, **self.options)
        srv.socket = ssl.wrap_socket(
            srv.socket,
            certfile=self.certfile,  # path to certificate
            server_side=True)
        srv.serve_forever()


DEFAULT_PAGE = 0
DEFAULT_PAGE_SIZE = 10


def validate_task_variable_value(k, v):
    """validate value of task variable, reformat if needed/possible
    raise error if value is incorrect
    return value or reformated value"""
    return daemon.validate_task_parameters(k, v)


###############################################################################
# Authentication

# all issued_tokens
# format
# issued_tokens[token]={'token':token,'expiration':expiration,'read':readrights,'write':writerights}
issued_tokens = {}


def generate_token():
    """
    generate unique token id
    """
    length = 32
    new_token = ''.join(
        random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(length))
    while new_token in list(issued_tokens.keys()):
        new_token = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length))
    return new_token


def check_expired_tokens():
    """
    check and delete expired tokens
    """
    tokens = list(issued_tokens.keys())
    epoch_time = int(time.time())
    for token in tokens:
        if issued_tokens[token]['expiration'] < epoch_time:
            del issued_tokens[token]


def auth_by_passwd(user, passwd):
    if user == cfg.restapi_rw_username and passwd == cfg.restapi_rw_password:
        return True
    if user == cfg.restapi_ro_username and passwd == cfg.restapi_ro_password:
        return True

    raise bottle.HTTPError(401, "Incorrect username or password")


def auth_by_token_for_read(token, _):
    if token in issued_tokens:
        if issued_tokens[token]['expiration'] < int(time.time()):
            check_expired_tokens()
            raise bottle.HTTPError(401, "Access denied. Token Expired")
        check_expired_tokens()
        if issued_tokens[token]['read'] is True:
            return True
        else:
            raise bottle.HTTPError(403, "Access denied. Not enough rights for reads.")
    check_expired_tokens()
    raise bottle.HTTPError(401, "Access denied")


def auth_by_token_for_write(token, _):
    if token in issued_tokens:
        if issued_tokens[token]['expiration'] < int(time.time()):
            check_expired_tokens()
            raise bottle.HTTPError(401, "Access denied. Token Expired")
        check_expired_tokens()
        if issued_tokens[token]['write'] is True:
            return True
        else:
            raise bottle.HTTPError(403, "Access denied. Not enough rights for writes.")
    check_expired_tokens()
    raise bottle.HTTPError(401, "Access denied")


@app.hook('after_request')
def enable_cors():
    """
    You need to add some headers to each request.
    Don't use the wildcard '*' for Access-Control-Allow-Origin in production.
    """
    response.headers['Access-Control-Allow-Origin'] = 'https://xdmod-dev.ccr.buffalo.edu:9006'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Methods'] = 'PUT, GET, POST, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'


@app.get(apiroot + '/token')
@bottle.auth_basic(auth_by_passwd)
def get_token():
    user, passwd = bottle.request.auth
    token = generate_token()
    expiration = int(time.time()) + cfg.restapi_token_expiration_time
    readrights = False
    writerights = False
    if user == cfg.restapi_rw_username:
        readrights = True
        writerights = True
    if user == cfg.restapi_ro_username:
        readrights = True
        writerights = False
    issued_tokens[token] = {'token': token, 'expiration': expiration, 'read': readrights, 'write': writerights}
    return {'token': token}


# CREATE =======================================================================
@app.post(apiroot + '/scheduled_tasks')
@bottle.auth_basic(auth_by_token_for_write)
def create_scheduled_tasks():
    """
    Create a new scheduled task w/ the form parameters provided.
    """
    # parameters needed to create new task
    must_params = ['resource',
                   'app',
                   'time_to_start',
                   'repeat_in',
                   'resource_param',
                   'app_param',
                   'task_param',
                   'group_id']
    # default values for some parameters
    params = {'time_to_start': None,
              'repeat_in': None,
              'app_param': '{}',
              'task_param': '{}',
              'group_id': ''}

    for k in list(bottle.request.forms.keys()):
        log.debug("Received: %r=>%r" % (k, bottle.request.forms[k]))
        if k not in must_params:
            raise bottle.HTTPError(400, 'Unknown parameter %s' % (k,))
        params[k] = validate_task_variable_value(k, bottle.request.forms[k])

    for k in must_params:
        if k not in params:
            raise bottle.HTTPError(400, 'Parameter %s is not set' % (k,))

    from . import daemon

    sch = daemon.AkrrDaemon(adding_new_tasks=True)
    try:
        task_id = sch.add_task(params['time_to_start'], params['repeat_in'], params['resource'], params['app'],
                               params['resource_param'], params['app_param'], params['task_param'],
                               params['group_id'], None)
    except Exception:
        raise bottle.HTTPError(400, 'Can not submit task to scheduled_tasks queue:' + traceback.format_exc())
    del sch

    return {
        "success": True,
        "message": "Task successfully created!",
        "data": {'task_id': task_id}
    }


# READ =========================================================================
@app.route(apiroot + '/scheduled_tasks', method='options')
@app.get(apiroot + '/scheduled_tasks')
@bottle.auth_basic(auth_by_token_for_read)
def get_scheduled_tasks():
    """
    Retrieve a list of all of the currently scheduled tasks.

    raises a 400 if any of the query parameters fail validation.
    raises a 401 if the user does not have a valid session.
    raises a 403 if the user is not authorized to perform this action.
    raises a 500 if an internal server error occurs ( ie. a database falls down etc. )
    """
    # default values for some parameters
    params = {'app': None,
              'resource': None}

    for k in list(bottle.request.forms.keys()):
        log.debug("Received: %r=>%r" % (k, bottle.request.forms[k]))
        if k not in params:
            raise ValueError('Unknown parameter %s' % (k,))
        params[k] = validate_task_variable_value(k, bottle.request.forms[k])

    query = "SELECT * FROM scheduled_tasks"

    if params['app'] is not None or params['resource'] is not None:
        query = query + " WHERE"

        if params['app']:
            query = query + " app='%s'" % params['app']

        if params['app'] is not None and params['resource'] is not None:
            query = query + " AND"

        if params['resource']:
            query = query + " resource='%s'" % params['resource']

    query = query + " ORDER BY time_to_start ASC"

    db, cur = akrr.db.get_akrr_db(True)
    cur.execute(query)
    tasks = cur.fetchall()

    cur.close()
    db.close()

    return tasks


@app.get(apiroot + '/scheduled_tasks/<task_id:int>')
@bottle.auth_basic(auth_by_token_for_read)
def get_scheduled_task(task_id):
    """
    Retrieve scheduled tasks.
    """
    db, cur = akrr.db.get_akrr_db(True)

    cur.execute('''SELECT * FROM scheduled_tasks
            WHERE task_id=%s''', (task_id,))
    task = cur.fetchall()

    cur.close()
    db.close()
    if len(task) == 1:
        return task[0]
    else:
        raise bottle.HTTPError(404, 'No tasks found with that id.')


# UPDATE =======================================================================
@app.post(apiroot + '/scheduled_tasks/<task_id:int>')
@bottle.auth_basic(auth_by_token_for_write)
def update_scheduled_tasks(task_id):
    """
    Attempts to update the scheduled task identified by the route parameter 'id'
    with the provided form parameters.
    
    If task already make it to active queue or done, the derivative task will be modified (same parent_id)
    """

    # is the task still in scheduled queue and what time left till it execution
    db, cur = akrr.db.get_akrr_db(True)
    cur.execute('''SELECT * FROM scheduled_tasks
            WHERE task_id=%s''', (task_id,))
    possible_task = cur.fetchall()
    cur.close()
    db.close()

    update_values = {}

    for k in list(bottle.request.forms.keys()):
        update_values[k] = validate_task_variable_value(k, bottle.request.forms[k])

    if len(possible_task) == 1:
        # task still in scheduled_tasks queue
        task = possible_task[0]
        if task['time_to_start'] > datetime.datetime.now() + datetime.timedelta(minutes=2):
            # have time to update it
            try:
                daemon.update_task_parameters(task_id, update_values, update_derived_task=True)

                return {
                    "success": True,
                    "message": "Task successfully updated!",
                }
            except Exception as e:
                raise bottle.HTTPError(400, str(e))

    # still here, ask master to do the job
    m_request = {
        'fun': 'update_task_parameters',
        'args': (task_id, update_values),
        'kargs': {'update_derived_task': True}
    }
    proc_queue_to_master.put(m_request)
    while not proc_queue_from_master.empty():
        pass
    m_response = proc_queue_from_master.get()

    if ("success" in m_response) and (m_response["success"] is True):
        m_response["message"] = "Task successfully updated!"

    return m_response


# DELETE =======================================================================
@app.delete(apiroot + '/scheduled_tasks/<task_id:int>')
@bottle.auth_basic(auth_by_token_for_write)
def delete_scheduled_task_by_id(task_id):
    """
    Attempts to delete the scheduled task identified by the route parameter 'task_id'.
    If task makes to active queue will delete it and will delete new scheduled task (in case if task was periodic)
    
    if task still in scheduled_tasks queue and its execution time is at lest in 5 minutes in the future, delete it by
    itself otherwise ask master to delete it
    """

    # is the task still in scheduled queue and what time left till it execution
    db, cur = akrr.db.get_akrr_db(True)
    cur.execute('''SELECT * FROM scheduled_tasks
            WHERE task_id=%s''', (task_id,))
    possible_task = cur.fetchall()
    cur.close()
    db.close()

    if len(possible_task) == 1:
        # task still in scheduled_tasks queue
        task = possible_task[0]
        if task['time_to_start'] > datetime.datetime.now() + datetime.timedelta(minutes=2):
            # have time to delete it
            try:
                daemon.delete_task(task_id, remove_from_scheduled_queue=True, remove_from_active_queue=True,
                                   remove_derived_task=True)

                return {
                    "success": True,
                    "message": "Task successfully deleted!",
                }
            except Exception as e:
                raise bottle.HTTPError(400, str(e))

    # still here, ask master to do the job
    m_request = {
        'fun': 'delete_task',
        'args': (task_id,),
        'kargs': {'remove_from_scheduled_queue': True, 'remove_from_active_queue': True, 'remove_derived_task': True}
    }
    proc_queue_to_master.put(m_request)
    while not proc_queue_from_master.empty():
        pass
    m_response = proc_queue_from_master.get()

    if ("success" in m_response) and (m_response["success"] is True):
        m_response["message"] = "Task successfully deleted!"

    return m_response


# Active task queue
@app.get(apiroot + '/active_tasks')
@bottle.auth_basic(auth_by_token_for_read)
def get_all_active_tasks():
    """
    Retrieve tasks from active_tasks queue.
    """
    db, cur = akrr.db.get_akrr_db(True)

    cur.execute('''SELECT * FROM active_tasks''')
    task = cur.fetchall()

    cur.close()
    db.close()
    return task


# Active task queue
@app.get(apiroot + '/active_tasks/<task_id:int>')
@bottle.auth_basic(auth_by_token_for_read)
def get_active_tasks(task_id):
    """
    Retrieve task from active_tasks queue.
    """
    db, cur = akrr.db.get_akrr_db(True)

    cur.execute('''SELECT * FROM active_tasks WHERE task_id=%s''', (task_id,))
    task = cur.fetchall()

    cur.close()
    db.close()
    if len(task) == 1:
        task = task[0]
        try:
            from . import akrr_task
            task_dir = akrr_task.get_local_task_dir(task['resource'], task['app'], task['datetime_stamp'])
            log_file = os.path.join(task_dir, 'proc', 'log')
            with open(log_file, "r") as fin:
                log_file_content = fin.read()

            task['log'] = log_file_content
        except Exception as e:
            raise e

        return task
    else:
        raise bottle.HTTPError(404, 'No tasks found with that id.')


@app.put(apiroot + '/active_tasks/<task_id:int>')
@bottle.auth_basic(auth_by_token_for_write)
def update_active_tasks(task_id):
    """
    the updatable parameter is next_check_time, i.e. renew status
    """
    # check input
    if len(list(bottle.request.forms.keys())) == 1 and 'next_check_time' not in list(bottle.request.forms.keys()):
        raise bottle.HTTPError(400, 'Only next_check_time can be updated in active tasks!')
    if len(list(bottle.request.forms.keys())) > 1 and 'next_check_time' in list(bottle.request.forms.keys()):
        raise bottle.HTTPError(400, 'Only next_check_time can be updated in active tasks!')
        # raise bottle.HTTPError(400, 'Only next_check_time can be updated in active tasks!')
    update_values = {}
    for k in list(bottle.request.forms.keys()):
        update_values[k] = validate_task_variable_value(k, bottle.request.forms[k])
    if 'next_check_time' not in list(bottle.request.forms.keys()):
        update_values['next_check_time'] = validate_task_variable_value('next_check_time',
                                                                        datetime.datetime.now().strftime(
                                                                         "%Y-%m-%d %H:%M:%S"))

    # get task
    db, cur = akrr.db.get_akrr_db(True)

    cur.execute('''SELECT * FROM active_tasks
            WHERE task_id=%s''', (task_id,))
    task = cur.fetchall()

    # loop to ensure that nobody working on this task right now
    while True:
        if len(task) != 1:
            raise bottle.HTTPError(404, 'No tasks found with that id.')

        if task[0]['task_lock'] == 0:
            break

        time.sleep(cfg.scheduled_tasks_loop_sleep_time * 0.45)

        cur.execute('''SELECT * FROM active_tasks
            WHERE task_id=%s''', (task_id,))
        task = cur.fetchall()
    #
    cur.execute('''UPDATE active_tasks
            SET next_check_time=%s
            WHERE task_id=%s''', (update_values['next_check_time'], task_id))
    cur.close()
    db.close()
    return {
        "success": True,
        "message": "Task successfully updated!"
    }


@app.delete(apiroot + '/active_tasks/<task_id:int>')
@bottle.auth_basic(auth_by_token_for_read)
def delete_active_tasks(task_id):
    """
    delete task from active_tasks queue.
    """
    # is the task still in scheduled queue and what time left till it execution
    db, cur = akrr.db.get_akrr_db(True)
    cur.execute('''SELECT * FROM active_tasks
            WHERE task_id=%s''', (task_id,))
    possible_task = cur.fetchall()
    cur.close()
    db.close()

    if len(possible_task) == 1:
        # task still in scheduled_tasks queue
        task = possible_task[0]
        if task['time_to_start'] > datetime.datetime.now() + datetime.timedelta(minutes=2):
            # have time to delete it
            try:
                daemon.delete_task(task_id, remove_from_scheduled_queue=True, remove_from_active_queue=True,
                                   remove_derived_task=True)

                return {
                    "success": True,
                    "message": "Task successfully deleted!",
                }
            except Exception as e:
                raise bottle.HTTPError(400, str(e))
    else:
        return {
            "success": False,
            "message": "Task is not in active queue",
        }
    # still here, ask master to do the job
    m_request = {
        'fun': 'delete_task',
        'args': (task_id,),
        'kargs': {'removeFromScheduledQueue': False, 'removeFromActiveQueue': True, 'removeDerivedTask': False}
    }
    proc_queue_to_master.put(m_request)
    while not proc_queue_from_master.empty():
        pass
    m_response = proc_queue_from_master.get()

    if ("success" in m_response) and (m_response["success"] is True):
        m_response["message"] = "Task successfully deleted!"

    return m_response


# Completed tasks
@app.get(apiroot + '/completed_tasks/<task_id:int>')
@bottle.auth_basic(auth_by_token_for_read)
def get_completed_tasks(task_id):
    """
    Retrieve task from completed_tasks.
    """
    db, cur = akrr.db.get_akrr_db(True)

    cur.execute('''SELECT * FROM completed_tasks
            WHERE task_id=%s''', (task_id,))
    task = cur.fetchall()

    cur.execute('''SELECT * FROM akrr_xdmod_instanceinfo
            WHERE instance_id=%s''', (task_id,))
    task_instanceinfo = cur.fetchall()

    cur.execute('''SELECT * FROM akrr_errmsg
            WHERE task_id=%s''', (task_id,))
    task_errmsg = cur.fetchall()

    cur.close()
    db.close()

    r = {}
    if len(task) == 1:
        r['completed_tasks'] = task[0]
        if len(task_instanceinfo) == 1:
            r['akrr_xdmod_instanceinfo'] = task_instanceinfo[0]
        if len(task_errmsg) == 1:
            r['akrr_errmsg'] = task_errmsg[0]
        return r
    else:
        raise bottle.HTTPError(404, 'No tasks found with that id.')


# generic task queue
@app.get(apiroot + '/tasks/<task_id:int>')
@bottle.auth_basic(auth_by_token_for_read)
def get_tasks(task_id):
    """
    Retrieve task from any queue.
    response is:
    data:{queue:scheduled_tasks/active_tasks/completed_tasks
        data:{data from respective get}
    }
    
    """
    # check in scheduled_tasks queue
    try:
        r = get_scheduled_task(task_id)
        return {'queue': 'scheduled_tasks', 'data': r}
    except bottle.HTTPError as e:
        if e.status_code == 404 and e.body == 'No tasks found with that id.':
            pass
        else:
            raise e
    # check in active_tasks queue
    try:
        r = get_active_tasks(task_id)
        return {'queue': 'active_tasks', 'data': r}
    except bottle.HTTPError as e:
        if e.status_code == 404 and e.body == 'No tasks found with that id.':
            pass
        else:
            raise e
    # check in completed_tasks
    try:
        r = get_completed_tasks(task_id)
        return {'queue': 'completed_tasks', 'data': r}
    except bottle.HTTPError as e:
        if e.status_code == 404 and e.body == 'No tasks found with that id.':
            pass
        else:
            raise e
    # if still here, cannot find such task
    raise bottle.HTTPError(404, 'No tasks found with that id.')


def _get_resource_apps(resource, application):
    query = """
    SELECT DISTINCT
        ST.resource,
        ST.app
    FROM
        mod_akrr.scheduled_tasks AS ST
    LEFT JOIN mod_akrr.resources AS R
        ON R.name = ST.resource
    WHERE R.name LIKE %s
        AND ST.app LIKE %s
    ORDER BY resource, app

    """ if resource and application else """
    SELECT DISTINCT
        ST.resource,
        ST.app
    FROM
        mod_akrr.scheduled_tasks AS ST
    LEFT JOIN mod_akrr.resources AS R
        ON R.name = ST.resource
    WHERE ST.app LIKE %s
    ORDER BY resource, app
    """ if application else """
    SELECT DISTINCT
        ST.resource,
        ST.app
    FROM
        mod_akrr.scheduled_tasks AS ST
    LEFT JOIN mod_akrr.resources AS R
        ON R.name = ST.resource
    WHERE R.name LIKE %s
    ORDER BY resource, app
    """ if resource else """
    SELECT DISTINCT
        ST.resource,
        ST.app
    FROM
        mod_akrr.scheduled_tasks AS ST
    LEFT JOIN mod_akrr.resources AS R
        ON R.name = ST.resource
    ORDER BY resource, app
    """

    parameters = ("%{0}%".format(resource), "%{0}%".format(application)) if resource and application else \
        ("%{0}%".format(application),) if application else ("%{0}%".format(resource),) if resource else ()
    print(query, parameters)
    rows = None
    try:
        connection, cursor = akrr.db.get_akrr_db(True)
        cursor.execute(query, parameters)
        rows = cursor.fetchall()
    except MySQLdb.Error as e:
        log.error("An error was encountered while trying to retrieve the requested tasks. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    except Exception as e:
        log.error("There was an unexpected error enountered while trying to retrieve the requested tasks. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")

    return rows


def _get_resource_app_status(resource, application):
    query = """
    SELECT
        ST.task_id,
        R.name,
        AKD.name AS app_kernel,
        CASE WHEN RA.enabled THEN 'ENABLED'
        WHEN NOT RA.enabled THEN 'DISABLED'
        ELSE 'NOT SET' END  status
    FROM mod_akrr.resource_app_kernels RA
    JOIN mod_akrr.resources AS R
         ON R.id = RA.resource_id
    JOIN mod_akrr.app_kernels AS AKD
         ON AKD.id = RA.app_kernel_id
    JOIN mod_akrr.scheduled_tasks ST
         ON R.name = ST.resource
         AND AKD.name = ST.app
    WHERE
            R.name LIKE %s
        AND AKD.name LIKE %s
    ORDER BY R.name, AKD.name
    """ if resource and application else """
    SELECT
        ST.task_id,
        R.name,
        AKD.name AS app_kernel,
        CASE WHEN RA.enabled THEN 'ENABLED'
        WHEN NOT RA.enabled THEN 'DISABLED'
        ELSE 'NOT SET' END  status
    FROM mod_akrr.resource_app_kernels RA
    JOIN mod_akrr.resources AS R
         ON R.id = RA.resource_id
    JOIN mod_akrr.app_kernels AS AKD
         ON AKD.id = RA.app_kernel_id
    JOIN mod_akrr.scheduled_tasks ST
         ON R.name = ST.resource
         AND AKD.name = ST.app
    WHERE
            AKD.name LIKE %s
    ORDER BY R.name, AKD.name
    """ if application else """
    SELECT
        ST.task_id,
        R.name,
        AKD.name AS app_kernel,
        CASE WHEN RA.enabled THEN 'ENABLED'
        WHEN NOT RA.enabled THEN 'DISABLED'
        ELSE 'NOT SET' END  status
    FROM mod_akrr.resource_app_kernels RA
    JOIN mod_akrr.resources AS R
         ON R.id = RA.resource_id
    JOIN mod_akrr.app_kernels AS AKD
         ON AKD.id = RA.app_kernel_id
    JOIN mod_akrr.scheduled_tasks ST
         ON R.name = ST.resource
         AND AKD.name = ST.app
    WHERE
            R.name LIKE %s
    ORDER BY R.name, AKD.name
    """ if resource else """
    SELECT
        ST.task_id,
        R.name,
        AKD.name AS app_kernel,
        CASE WHEN RA.enabled THEN 'ENABLED'
        WHEN NOT RA.enabled THEN 'DISABLED'
        ELSE 'NOT SET' END  status
    FROM mod_akrr.resource_app_kernels RA
    JOIN mod_akrr.resources AS R
         ON R.id = RA.resource_id
    JOIN mod_akrr.app_kernels AS AKD
         ON AKD.id = RA.app_kernel_id
    JOIN mod_akrr.scheduled_tasks ST
         ON R.name = ST.resource
         AND AKD.name = ST.app
    ORDER BY R.name, AKD.name
    """

    parameters = ("%{0}%".format(resource), "%{0}%".format(application)) if resource and application \
        else ("%{0}%".format(application),) if application \
        else ("%{0}%".format(resource),) if resource \
        else ()
    rows = None
    try:
        connection, cursor = akrr.db.get_ak_db(True)
        cursor.execute(query, parameters)
        rows = cursor.fetchall()
    except MySQLdb.Error as e:
        log.error("An error was encountered while trying to retrieve the requested tasks. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    except Exception as e:
        log.error("There was an unexpected error enountered while trying to retrieve the requested tasks. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")

    return rows


@app.get(apiroot + '/tasks')
@bottle.auth_basic(auth_by_token_for_read)
def get_unique_tasks():
    """
    Retrieve the list of currently scheduled tasks ( resource / application pairings ) from
    mod_akrr.

    :return: a JSON encoded representation of the mod_akrr.scheduled_tasks table (resource, app) .
    """

    # RETRIEVE: the query parameters that were provided, if any. x
    try:
        resource = request.query.resource
        application = request.query.app
        status = request.query.status

        if status:
            return _get_resource_app_status(resource, application)
        else:
            return _get_resource_apps(resource, application)
    except UnicodeError as e:
        s = "There was a problem while trying to extract the query parameters from the request. %s: %s" % \
            (e.args[0] if len(e.args) >= 1 else "", e.args[1] if len(e.args) >= 2 else "")
        log.error(s)
        raise AkrrError(s)


@app.route(apiroot + '/resources', method='options')
@app.get(apiroot + '/resources')
@bottle.auth_basic(auth_by_token_for_read)
def get_resources():
    """
    Retrieve the contents of the mod_akrr.resources table filtered by the provided resource filter if applicable.

    :return: a JSON encoded representation (name, id) of the modw.resourcefact table.
    """

    # RETRIEVE: the query parameters, if any were provided.
    try:
        resource_filter = request.query.resource
        exact_flag = request.query.exact
    except UnicodeError as e:
        log.error("Unable to retrieve query parameters for GET:resources. %s: %s", e.args[0], e.args[1])
        raise AkrrError("Unable to retrieve query parameters for GET:resources. %s: %s" % (e.args[0], e.args[1]))

    # DETERMINE: which query we need to run based on the parameters supplied.
    query = """
    SELECT name, id FROM mod_akrr.resources AS RF WHERE RF.name = %s
    """ if resource_filter and exact_flag else """
    SELECT name, id FROM mod_akrr.resources AS RF WHERE RF.name LIKE %s
    """ if resource_filter else """
    SELECT name, id FROM mod_akrr.resources
    """

    results = None
    try:
        # RETRIEVE: a connection and cursor instance for the XDMoD database.
        connection, cursor = akrr.db.get_akrr_db(True)

        # Make sure we execute the correct query with the correct parametersresources
        if resource_filter:
            resource_filter = "%{0}%".format(resource_filter) if not exact_flag else resource_filter

            cursor.execute(query, ['%{0}%'.format(resource_filter)])
        else:
            cursor.execute(query)

        # RETRIEVE: the results and save them for returning.
        results = cursor.fetchall()
    except MySQLdb.Error as e:
        log.error("There was a SQL Error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    except Exception as e:
        log.error("There was an unexpected error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")

    return results


@app.route(apiroot + '/kernels', method='options')
@app.get(apiroot + '/kernels')
@bottle.auth_basic(auth_by_token_for_read)
def get_kernels():
    """
    Retrieve a list of the records currently in the mod_akrr.app_kernels table
    filtered by the provided query parameters.

    :return: a JSON encoded representation (name, id) of the mod_akrr.app_kernels table.
    """

    def str_to_bool(value):
        return value and value.lower() in ('yes', 'true', 't', '1')

    # RETRIEVE: the provided query parameters, if any.
    try:
        kernel_filter = request.query.kernel
        disabled = str_to_bool(request.query.disabled)
    except UnicodeError as e:
        log.error("Unable to retrieve query parameters for GET:kernels. %s: %s", e.args[0], e.args[1])
        raise AkrrError("Unable to retrieve query parameters for GET:kernels. %s: %s" % (e.args[0], e.args[1]))

    query = """
    SELECT AK.id,
           CASE WHEN AK.name REGEXP '.core$' = 1 THEN SUBSTR(AK.name, 1, CHAR_LENGTH(AK.name) - 5)
           ELSE AK.name END name,
           AK.enabled,
           AK.nodes_list
    FROM mod_akrr.app_kernels AK
    WHERE AK.name = %s
    ORDER BY AK.name
    """ if kernel_filter and disabled else """
    SELECT AK.id,
           CASE WHEN AK.name REGEXP '.core$' = 1 THEN SUBSTR(AK.name, 1, CHAR_LENGTH(AK.name) - 5)
           ELSE AK.name END name,
           AK.enabled,
           AK.nodes_list
    FROM mod_akrr.app_kernels AK
    WHERE AK.name = %s
      AND AK.enabled = TRUE
    ORDER BY AK.name
    """ if kernel_filter else """
    SELECT AK.id,
           CASE WHEN AK.name REGEXP '.core$' = 1 THEN SUBSTR(AK.name, 1, CHAR_LENGTH(AK.name) - 5)
           ELSE AK.name END name,
           AK.enabled,
           AK.nodes_list
    FROM mod_akrr.app_kernels AK
    WHERE AK.enabled = TRUE
    ORDER BY AK.name
    """ if not disabled else """
    SELECT AK.id,
           CASE WHEN AK.name REGEXP '.core$' = 1 THEN SUBSTR(AK.name, 1, CHAR_LENGTH(AK.name) - 5)
           ELSE AK.name END name,
           AK.enabled,
           AK.nodes_list
    FROM mod_akrr.app_kernels AK
    ORDER BY AK.name
    """

    results = None
    try:
        # RETRIEVE: a connection and cursor instance for the XDMoD database.
        connection, cursor = akrr.db.get_akrr_db(True)

        # Make sure we execute the correct query with the correct parametersresources
        if kernel_filter:
            cursor.execute(query, [kernel_filter])
        else:
            cursor.execute(query)

        # RETRIEVE: the results and save them for returning.
        results = cursor.fetchall()
    except MySQLdb.Error as e:
        log.error("There was a SQL Error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    except Exception as e:
        log.error("There was an unexpected error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")

    return results


def _turn_resource_on(resource, application):
    """

    :type resource str
    :type application str

    :param resource:
    :param application:
    :return:
    """

    exists = _does_resource_app_kernel_exist(resource, application)
    has_resource = len(resource) > 0
    has_application = len(application) > 0

    if exists:
        queries = ("""
        UPDATE mod_akrr.resource_app_kernels RA
        SET RA.enabled = TRUE
        WHERE
               RA.resource_id IN (
                    SELECT
                        R.id
                    FROM mod_akrr.resources AS R
                    WHERE R.name = %s
           AND RA.app_kernel_id IN (
                    SELECT
                        AKD.id
                    FROM mod_akrr.app_kernels AKD
                    WHERE AKD.name = %s
                )
            )
        """) if resource and application else ("""
        UPDATE mod_akrr.resource_app_kernels RA
        SET RA.enabled = TRUE
        WHERE
            RA.resource_id IN (
                    SELECT
                        R.id
                    FROM mod_akrr.resources AS R
                    WHERE R.name = %s
            );

        """), (
            """
             UPDATE mod_akrr.resources R
             SET R.enabled = TRUE
             WHERE
                R.name LIKE %s
            """
        )
        parameters = ((resource, application), (resource,)) if resource and application \
            else ((resource,), (resource,))
    else:
        resource_exists = _resource_exists(resource)
        app_kernel_exists = _app_kernel_exists(application)

        if has_resource and not resource_exists:
            raise bottle.HTTPError(
                400,
                'Unable to find the provided resource [%r]' % (resource,)
            )

        if has_application and not app_kernel_exists:
            raise bottle.HTTPError(
                400,
                'Unable to find the provided app kernel [%r]' % (application,)

            )

        queries = ("""
        INSERT INTO mod_akrr.resource_app_kernels
        (resource_id, app_kernel_id, enabled)
        SELECT
            R.id,
            AK.id,
            TRUE
        FROM mod_akrr.resources R, mod_akrr.app_kernels AK
        WHERE
            R.name = %s
            AND AK.name = %s;
        """,) if has_resource and has_application and resource_exists and app_kernel_exists else \
            ("""
        UPDATE mod_akrr.resources R SET R.enabled = TRUE WHERE R.name = %s;
        """, """
        UPDATE mod_akrr.resource_app_kernels AK
        SET AK.enabled = TRUE
        WHERE AK.resource_id = ( SELECT R.id FROM mod_akrr.resources R WHERE R.name = %s)
        """)
        parameters = ((resource, application),) if has_resource and has_application \
            and resource_exists and app_kernel_exists else \
            ((resource,), (resource,))

    queries_and_parameters = list(zip(queries, parameters))
    try:
        connection, cursor = akrr.db.get_akrr_db()
        result = 0
        for (query, parameter) in queries_and_parameters:
            print(query, parameter)
            result += cursor.execute(query, parameter)
        return result
    except MySQLdb.Error as e:
        log.error("There was a SQL Error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    except Exception as e:
        log.error("There was an unexpected error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")


def _does_resource_app_kernel_exist(resource, app_kernel):
    """
    Determines whether or not there is currently a record of the provided 'app_kernel'
    being related to the provided 'resource'.

    :param resource:    the name of the 'resource' to be queried.
    :param app_kernel:  the name of the 'app_kernel' to be queried.
    :return: true if there is a record relating them, false if not
    """

    db, cur = akrr.db.get_akrr_db(True)
    cur.execute("""
    SELECT 1
    FROM mod_akrr.resource_app_kernels RAK
    JOIN mod_akrr.resources R
      ON RAK.resource_id = R.id
    JOIN mod_akrr.app_kernels AK
      ON RAK.app_kernel_id = AK.id
    WHERE
      R.name = %s
      AND AK.name = %s
    """, (resource, app_kernel))
    rows = cur.fetchall()
    return len(rows) > 0


def _resource_exists(resource):
    """
    Determine whether the resource or app_kernel exists based on their name values.

    :param resource:   the resource to check.
    :return: true if it exists, false if it doesn't
    """
    connection, cursor = akrr.db.get_akrr_db(True)
    cursor.execute("""
    SELECT 1 FROM mod_akrr.resources R WHERE R.name = %s
    """, (resource,))
    rows = cursor.fetchall()
    return len(rows) > 0


def _app_kernel_exists(app_kernel):
    """
    Determines whether or not the provided app_kernel name exists.

    :param app_kernel:
    :return: True if it exists, false if it doesn't
    """
    connection, cursor = akrr.db.get_akrr_db(True)
    cursor.execute("""
    SELECT 1 FROM mod_akrr.app_kernels AK WHERE AK.name = %s
    """, (app_kernel,))
    rows = cursor.fetchall()
    return len(rows) > 0

def _turn_resource_off(resource, application):
    """

    :type resource str
    :type application str

    :param resource:
    :param application:
    :return:
    """

    exists = _does_resource_app_kernel_exist(resource, application)
    has_resource = len(resource) > 0
    has_application = len(application) > 0

    if exists:
        queries = ("""
        UPDATE mod_akrr.resource_app_kernels RA
        SET RA.enabled = FALSE
        WHERE
               RA.resource_id IN (
                    SELECT
                        R.id
                    FROM mod_akrr.resources AS R
                    WHERE R.name = %s
           AND RA.app_kernel_id IN (
                    SELECT
                        AKD.id
                    FROM mod_akrr.app_kernels AKD
                    WHERE AKD.name = %s
                )
            )
        """) if resource and application else ("""
        UPDATE mod_akrr.resource_app_kernels RA
        SET RA.enabled = FALSE
        WHERE
            RA.resource_id IN (
                    SELECT
                        R.id
                    FROM mod_akrr.resources AS R
                    WHERE R.name = %s
            );

        """), (
            """
             UPDATE mod_akrr.resources R
             SET R.enabled = FALSE
             WHERE
                R.name LIKE %s
            """
        )
        parameters = (resource, application) if resource and application \
            else ((resource,), (resource,))
    else:
        resource_exists = _resource_exists(resource)
        app_kernel_exists = _app_kernel_exists(application)

        if has_resource and not resource_exists:
            raise bottle.HTTPError(
                400,
                'Unable to find the provided resource [%r]' % (resource,)
            )

        if has_application and not app_kernel_exists:
            raise bottle.HTTPError(
                400,
                'Unable to find the provided app kernel [%r]' % (application,)

            )

        queries = ("""
        INSERT INTO mod_akrr.resource_app_kernels
        (resource_id, app_kernel_id, enabled)
        SELECT
            R.id,
            AK.id,
            FALSE
        FROM mod_akrr.resources R, mod_akrr.app_kernels AK
        WHERE
            R.name = %s
            AND AK.name = %s;
        """) if has_resource and has_application and resource_exists and app_kernel_exists else \
            ("""
        UPDATE mod_akrr.resources R SET R.enabled = FALSE WHERE R.name = %s;
        """, """
        UPDATE mod_akrr.resource_app_kernels AK
        SET AK.enabled = FALSE
        WHERE AK.resource_id = ( SELECT R.id FROM mod_akrr.resources R WHERE R.name = %s)
        """)
        parameters = (resource, application) if has_resource and has_application \
            and resource_exists and app_kernel_exists else \
            ((resource,), (resource,))

    queries_and_parameters = list(zip(queries, parameters))
    try:
        connection, cursor = akrr.db.get_akrr_db()
        result = 0
        for (query, parameter) in queries_and_parameters:
            print(query, parameter)
            result += cursor.execute(query, parameter)
        return result
    except MySQLdb.Error as e:
        log.error("There was a SQL Error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    except Exception as e:
        log.error("There was an unexpected error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")


@app.put(apiroot + '/resources/<resource>/on')
@bottle.auth_basic(auth_by_token_for_write)
def turn_resource_on(resource):
    """

    :type resource str

    :param resource:
    :return:
    """

    # ATTEMPT: to retrieve any query parameters
    try:
        application_filter = request.forms.application
    except UnicodeError as e:
        s = "Unable to retrieve query parameters for GET:resources. %s: %s" % (e.args[0], e.args[1])
        log.error(s)
        raise AkrrError(s)

    return {'updated': _turn_resource_on(resource, application_filter)}


@app.put(apiroot + '/resources/<resource>/off')
@bottle.auth_basic(auth_by_token_for_write)
def turn_resource_off(resource):
    """

    :type resource str

    :param resource:
    :return:
    """

    # ATTEMPT: to retrieve any query parameters
    try:
        application_filter = request.forms.application
    except UnicodeError as e:
        s = "Unable to retrieve query parameters for GET:resources. %s: %s" % (e.args[0], e.args[1])
        log.error(s)
        raise AkrrError(s)

    return {'updated': _turn_resource_off(resource, application_filter)}


@app.get(apiroot + '/walltime')
@bottle.auth_basic(auth_by_token_for_read)
def get_walltime_all():
    """
    Get list of all default walltimes
    """
    results = None
    try:
        # RETRIEVE: a connection and cursor instance for the XDMoD database.
        connection, cursor = akrr.db.get_akrr_db(True)

        # Make sure we execute the correct query with the correct parametersresources
        cursor.execute(
            "SELECT id,resource,app,walltime_limit,resource_param,app_param,"
            "last_update,comments FROM akrr_default_walltime_limit")

        # RETRIEVE: the results and save them for returning.
        results = cursor.fetchall()
    except MySQLdb.Error as e:
        log.error("There was a SQL Error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    except Exception as e:
        log.error("There was an unexpected error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")

    return results


@app.get(apiroot + '/walltime/<walltime_id:int>')
@bottle.auth_basic(auth_by_token_for_read)
def get_walltime(walltime_id):
    """
    Get default walltimes
    """
    results = None
    try:
        # RETRIEVE: a connection and cursor instance for the XDMoD database.
        connection, cursor = akrr.db.get_akrr_db(True)

        # Make sure we execute the correct query with the correct parametersresources
        cursor.execute(
            "SELECT resource,app,walltime_limit,resource_param,app_param,"
            "last_update,comments FROM akrr_default_walltime_limit WHERE id=%s",
            (walltime_id,))
        results = cursor.fetchall()
        if len(results) > 0:
            return results[0]
        else:
            raise bottle.HTTPError(400, 'walltime with id %d does not exists' % (walltime_id,))

    except MySQLdb.Error as e:
        log.error("There was a SQL Error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    except Exception as e:
        log.error("There was an unexpected error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")

    return results


@app.post(apiroot + '/walltime/<resource>/<app>')
@bottle.auth_basic(auth_by_token_for_write)
def upsert_walltime(resource, m_app):
    """
    add/update new default walltime
    """
    # parameters needed to create new task
    must_params = ['resource',
                   'app',
                   'resource_param',
                   'app_param',
                   'walltime',
                   'comments']
    # default parameters
    params = {'resource': resource,
              'app': m_app,
              'app_param': '{}',
              'resource_param': '{}',
              'comments': ""
              }

    for k in list(bottle.request.forms.keys()):
        print("Received: %r=>%r" % (k, bottle.request.forms[k]))
        if k not in must_params:
            raise bottle.HTTPError(400, 'Unknown parameter %s' % (k,))
        params[k] = validate_task_variable_value(k, bottle.request.forms[k])

    for k in must_params:
        if k not in params:
            raise bottle.HTTPError(400, 'Parameter %s is not set' % (k,))

    try:
        # RETRIEVE: a connection and cursor instance for the XDMoD database.
        connection, cursor = akrr.db.get_akrr_db(True)

        cursor.execute('''SELECT * FROM akrr_default_walltime_limit
        WHERE resource = %s and app=%s and resource_param=%s and app_param=%s''',
                       (resource, m_app, params['resource_param'], params['app_param']))
        results = cursor.fetchall()
        if len(results) > 0:
            cursor.execute('''UPDATE akrr_default_walltime_limit 
                SET walltime_limit=%s,
                    last_update=NOW(),
                    comments=%s
                WHERE
                 resource = %s and app=%s and resource_param=%s and app_param=%s''',
                           (params['walltime'], params['comments'], resource, app, params['resource_param'],
                            params['app_param']))
            return {'updated': True}
        else:
            cursor.execute(
                "INSERT INTO akrr_default_walltime_limit (resource,app,walltime_limit,"
                "resource_param,app_param,last_update,comments)"
                "VALUES(%s,%s,%s,%s,%s,NOW(),%s)", (
                    resource, m_app, params['walltime'], params['resource_param'],
                    params['app_param'], params['comments']))
            return {'created': True}

            # RETRIEVE: the results and save them for returning.
            # results = cursor.fetchall()
    except MySQLdb.Error as e:
        log.error("There was a SQL Error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    except Exception as e:
        log.error("There was an unexpected error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    return {'updated': False}


@app.get(apiroot + '/walltime/<resource>/<app>')
@bottle.auth_basic(auth_by_token_for_read)
def get_walltime_by_resource_app(resource, m_app):
    """
    get default walltime
    """
    # parameters needed to create new task
    must_params = ['resource',
                   'app',
                   'resource_param',
                   'app_param',
                   'walltime',
                   'comments']
    # default parameters
    params = {'resource': resource,
              'app': m_app,
              'app_param': '{}',
              'resource_param': '{}',
              'comments': ""
              }

    for k in list(bottle.request.forms.keys()):
        print("Received: %r=>%r" % (k, bottle.request.forms[k]))
        if k not in must_params:
            raise bottle.HTTPError(400, 'Unknown parameter %s' % (k,))
        params[k] = validate_task_variable_value(k, bottle.request.forms[k])

    for k in must_params:
        if k not in params:
            raise bottle.HTTPError(400, 'Parameter %s is not set' % (k,))

    try:
        # RETRIEVE: a connection and cursor instance for the XDMoD database.
        connection, cursor = akrr.db.get_akrr_db(True)

        cursor.execute('''SELECT * FROM akrr_default_walltime_limit
        WHERE resource = %s and app=%s and resource_param=%s and app_param=%s''',
                       (resource, m_app, params['resource_param'], params['app_param']))
        results = cursor.fetchall()
        if len(results) > 0:
            return results[0]
        else:
            raise bottle.HTTPError(400, 'There is no default walltime for this configuration')

        # RETRIEVE: the results and save them for returning.
        # results = cursor.fetchall()
    except MySQLdb.Error as e:
        log.error("There was a SQL Error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    except Exception as e:
        log.error("There was an unexpected error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    return {'updated': False}


@app.post(apiroot + '/walltime/<walltime_id:int>')
@bottle.auth_basic(auth_by_token_for_write)
def update_walltime_by_id(walltime_id):
    """
    add/update new default walltime
    """
    # parameters needed to create new task
    must_params = ['walltime',
                   'comments']
    # default parameters
    params = {
        'comments': ""
    }

    for k in list(bottle.request.forms.keys()):
        print("Received: %r=>%r" % (k, bottle.request.forms[k]))
        if k not in must_params:
            raise bottle.HTTPError(400, 'Unknown parameter %s' % (k,))
        params[k] = validate_task_variable_value(k, bottle.request.forms[k])

    for k in must_params:
        if k not in params:
            raise bottle.HTTPError(400, 'Parameter %s is not set' % (k,))

    try:
        # RETRIEVE: a connection and cursor instance for the XDMoD database.
        connection, cursor = akrr.db.get_akrr_db(True)

        cursor.execute('''SELECT * FROM akrr_default_walltime_limit
        WHERE id = %s''', (walltime_id,))
        results = cursor.fetchall()
        if len(results) > 0:
            cursor.execute('''UPDATE akrr_default_walltime_limit 
                SET walltime_limit=%s,
                    last_update=NOW(),
                    comments=%s
                WHERE id = %s''',
                           (params['walltime'], params['comments'], walltime_id))
            return {'updated': True}
        else:
            raise bottle.HTTPError(400, 'walltime with id %d does not exists' % (walltime_id,))
        # RETRIEVE: the results and save them for returning.
        # results = cursor.fetchall()
    except MySQLdb.Error as e:
        log.error("There was a SQL Error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    except Exception as e:
        log.error("There was an unexpected error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    return {'updated': False}


@app.delete(apiroot + '/walltime/<walltime_id:int>')
@bottle.auth_basic(auth_by_token_for_write)
def delete_walltime(walltime_id):
    """
    delete default walltime
    """
    try:
        # RETRIEVE: a connection and cursor instance for the XDMoD database.
        connection, cursor = akrr.db.get_akrr_db(True)

        cursor.execute('''SELECT * FROM akrr_default_walltime_limit
        WHERE id = %s''', (walltime_id,))
        results = cursor.fetchall()
        if len(results) > 0:
            cursor.execute('''DELETE FROM akrr_default_walltime_limit
                WHERE id = %s''', (walltime_id,))
        else:
            raise bottle.HTTPError(400, 'walltime with id %d does not exists' % (walltime_id,))
    except MySQLdb.Error as e:
        log.error("There was a SQL Error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    except Exception as e:
        log.error("There was an unexpected error while attempting to retrieve the specified resources. %s: %s",
                  e.args[0] if len(e.args) >= 1 else "",
                  e.args[1] if len(e.args) >= 2 else "")
    return {'deleted': False}


def start_rest_api(m_proc_queue_to_master=None, m_proc_queue_from_master=None):
    print("Starting REST-API Service")
    # make sure that reloading is off and debugging is turned on.
    issued_tokens['test'] = {'token': 'test', 'expiration': int(time.time()) + cfg.restapi_token_expiration_time,
                             'read': True, 'write': True}
    global proc_queue_to_master
    global proc_queue_from_master
    proc_queue_to_master = m_proc_queue_to_master
    proc_queue_from_master = m_proc_queue_from_master

    srv = SSLWSGIRefServer(host=cfg.restapi_host, port=cfg.restapi_port, certfile=cfg.restapi_certfile)
    # bottle.run(app,server=srv, debug=True, reloader=False)
    print("Before bottle.run")
    bottle.run(app, server=srv, debug=True, reloader=False)


@app.post(apiroot + '/scheduler/no_new_tasks')
@bottle.auth_basic(auth_by_token_for_write)
def scheduler_no_new_tasks():
    """
    Temporary stop new tasks start up
    """
    global proc_queue_to_master
    m_request = {
        'fun': 'daemon_no_new_tasks',
        'args': tuple(),
        'kargs': {}
    }
    proc_queue_to_master.put(m_request)
    while not proc_queue_from_master.empty():
        pass
    m_response = proc_queue_from_master.get()

    if ("success" in m_response) and (m_response["success"] is True):
        m_response["message"] = "Temporary stopped new tasks start up!"

    return m_response


@app.post(apiroot + '/scheduler/no_active_tasks_check')
@bottle.auth_basic(auth_by_token_for_write)
def scheduler_no_active_tasks_check():
    """
    Temporary stop active tasks status checking
    """
    global proc_queue_to_master
    m_request = {
        'fun': 'daemon_no_active_tasks_check',
        'args': tuple(),
        'kargs': {}
    }
    proc_queue_to_master.put(m_request)
    while not proc_queue_from_master.empty():
        pass
    m_response = proc_queue_from_master.get()

    if ("success" in m_response) and (m_response["success"] is True):
        m_response["message"] = "Temporary stopped active tasks status checking!"

    return m_response


@app.post(apiroot + '/scheduler/new_tasks_on')
@bottle.auth_basic(auth_by_token_for_write)
def scheduler_no_active_tasks_check():
    """
    Allow new task to be started
    """
    global proc_queue_to_master
    m_request = {
        'fun': 'daemon_new_tasks_on',
        'args': tuple(),
        'kargs': {}
    }
    proc_queue_to_master.put(m_request)
    while not proc_queue_from_master.empty():
        pass
    m_response = proc_queue_from_master.get()

    if ("success" in m_response) and (m_response["success"] is True):
        m_response["message"] = "Allowed new task to be started!"

    return m_response


if __name__ == '__main__':
    start_rest_api()
