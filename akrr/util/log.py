from logging import INFO, DEBUG
from logging import basicConfig, critical, error, warning, info, debug, getLogger, exception

from . import colorize

verbose = False
error_count = 0
warning_count = 0


def debug2(msg, *args, **kwargs):
    """
    more verbose logging
    """
    if getLogger().level < 10:
        debug(msg, *args, **kwargs)


def dry_run(msg, *_, **__):
    print("DryRun: "+msg)


def empty_line():
    print()


def log_input(message, *args):
    if message:
        if len(args) > 0:
            formatted_message = message.format(*args)
        else:
            formatted_message = message
    else:
        formatted_message = ''

    print('[' + colorize.purple('INPUT') + ']: ' + formatted_message)


def test_log():
    critical("test critical")
    error("test error")
    exception("test exception")
    warning("test warning")
    info("test info")
