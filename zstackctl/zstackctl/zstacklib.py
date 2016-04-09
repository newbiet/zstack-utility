#!/usr/bin/env python
# encoding: utf-8
import ansible.runner
import os
import sys
import urllib2
from urllib2 import URLError
from datetime import datetime
import logging
import json
from logging.handlers import TimedRotatingFileHandler

# set global default value
start_time = datetime.now()
logger = logging.getLogger("deploy-ha-Log")
pip_url = ""
zstack_root = ""
host = ""
pkg_zstacklib = ""
yum_server = ""
trusted_host = ""


class AgentInstallArg(object):
    def __init__(self, trusted_host, pip_url, virtenv_path, init_install):
        self.trusted_host = trusted_host
        self.pip_url = pip_url
        self.virtenv_path = virtenv_path
        self.init_install = init_install
        self.agent_name = None
        self.agent_root = None
        self.pkg_name = None
        self.virtualenv_site_packages = None


class ZstackLibArgs(object):
    def __init__(self):
        self.yum_repo = None
        self.yum_server = None
        self.distro = None
        self.distro_version = None
        self.zstack_root = None
        self.host_post_info = None


class Log(object):
    def __init__(self):
        self.level = None
        self.details = None


class Error(object):
    def __init__(self):
        self.code = None
        self.description = None
        self.details = None


class Msg(object):
    def ___init__(self):
        self.type = None
        self.data = None


class AnsibleStartResult(object):
    def __init__(self):
        self.result = None
        self.post_url = None
        self.host = None


class HostPostInfo(object):
    def __init__(self):
        self.host = None
        self.vip= None
        self.post_url = None
        self.private_key = None
        self.host_inventory = None
        self.start_time = None
        self.rabbit_password = None
        self.mysql_password = None
        self.mysql_userpassword = None


class PipInstallArg(object):
    def __init__(self):
        self.name = None
        self.extra_args = None
        self.version = None
        self.virtualenv = None
        self.virtualenv_site_packages = None


class CopyArg(object):
    def __init__(self):
        self.src = None
        self.dest = None
        self.args = None


class FetchArg(object):
    def __init__(self):
        self.src = None
        self.dest = None
        self.args = None


class UnarchiveArg(object):
    def __init__(self):
        self.src = None
        self.dest = None
        self.args = None


def create_log(logger_dir):
    if not os.path.exists(logger_dir):
        os.makedirs(logger_dir)
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler = logging.handlers.RotatingFileHandler(logger_dir + "deploy.log", maxBytes=100 * 1024 * 1024,
                                                   backupCount=30)
    handler.setFormatter(fmt)
    logger.addHandler(handler)


def post_msg(msg, post_url):
    logger.info(msg.data.details)
    if msg.type == "log":
        data = json.dumps({"level": msg.data.level, "details": msg.data.details})
    elif msg.type == "error":
        data = json.dumps({"code": msg.data.code, "description": msg.data.description, "details": msg.data.details})
        # This output will capture by management log
        print msg.data.description + "\nReason: " + msg.data.details
    else:
        logger.info("ERROR: undefined message type: %s" % msg.type)
        sys.exit(1)
    if post_url == "":
        logger.info("Warning: no post_url defined by user")
        return 0
    try:
        headers = {"content-type": "application/json"}
        req = urllib2.Request(post_url, data, headers)
        response = urllib2.urlopen(req)
        response.close()
    except URLError, e:
        logger.debug(e.reason)
        logger.info("Please check the post_url: %s and check the server status" % post_url)
        print "Please check the post_url: %s and check the server status" % post_url
        sys.exit(1)


def handle_ansible_start(ansible_start):
    msg = Msg()
    error = Error()
    error.code = "ansible.1000"
    error.description = "ERROR: Can't start ansible process"
    error.details = "Can't start ansible process to host: %s Reason: %s  \n" % (ansible_start.host,
                                                                                ansible_start.result)
    msg.type = "error"
    msg.data = error
    post_msg(msg, ansible_start.post_url)


def handle_ansible_failed(description, result, host_post_info):
    msg = Msg()
    error = Error()
    host = host_post_info.host
    post_url = host_post_info.post_url
    start_time = host_post_info.start_time
    end_time = datetime.now()
    # Fix python2.6 compatible issue: no total_seconds() attribute for timedelta
    td = end_time - start_time
    cost_time = (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10 ** 6) / 10 ** 6.0 * 1000
    error.code = "ansible.1001"
    error.description = "[ HOST: %s ] " % host_post_info.host + description + " [ cost %sms to finish ]" % int(cost_time)
    if 'stderr' in result['contacted'][host]:
        error.details = "[ HOST: %s ] " % host_post_info.host + "ERROR: \n" + result['contacted'][host]['stderr']
    elif 'msg' in result['contacted'][host]:
        error.details = "[ HOST: %s ] " % host_post_info.host +  "ERROR: \n" + result['contacted'][host]['msg']
    msg.type = "error"
    msg.data = error
    post_msg(msg, post_url)


def handle_ansible_info(details, host_post_info, level):
    msg = Msg()
    log = Log()
    post_url = host_post_info.post_url
    start_time = host_post_info.start_time
    end_time = datetime.now()
    # Fix python2.6 compatible issue: no total_seconds() attribute for timedelta
    td = end_time - start_time
    cost_time = (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10 ** 6) / 10 ** 6.0 * 1000
    log.level = level
    if "SUCC" in details:
        log.details = "[ HOST: %s ] " % host_post_info.host + details + " [ cost %sms to finish ]" % int(cost_time)
    else:
        log.details = "[ HOST: %s ] " % host_post_info.host + details
    msg.type = "log"
    msg.data = log
    post_msg(msg, post_url)


def agent_install(install_arg, host_post_info):
    handle_ansible_info("INFO: Start to install %s .................." % install_arg.agent_name, host_post_info, "INFO")
    pip_install_arg = PipInstallArg()
    pip_install_arg.extra_args = "\"--trusted-host %s -i %s\"" % (install_arg.trusted_host, install_arg.pip_url)
    # upgrade only
    if install_arg.init_install is False:
        handle_ansible_info("INFO: Only need to upgrade %s .................." % install_arg.agent_name, host_post_info,
                            "INFO")
        pip_install_arg.extra_args = "\"--trusted-host %s -i %s -U \"" % (install_arg.trusted_host, install_arg.pip_url)

    pip_install_arg.name = "%s/%s" % (install_arg.agent_root, install_arg.pkg_name)
    pip_install_arg.virtualenv = install_arg.virtenv_path
    pip_install_arg.virtualenv_site_packages = install_arg.virtualenv_site_packages
    if pip_install_package(pip_install_arg, host_post_info) is False:
        command = "rm -rf %s && rm -rf %s" % (install_arg.virtenv_path, install_arg.agent_root)
        run_remote_command(command, host_post_info)
        sys.exit(1)


def yum_enable_repo(name, enablerepo, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url

    handle_ansible_info("INFO: Starting enable yum repo %s ... " % name, host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='yum',
        module_args='name=' + name + ' enablerepo=' + enablerepo + " state=present",
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)

    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: Enable yum repo failed"
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            details = "SUCC: yum enable repo %s " % enablerepo
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def yum_check_package(name, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Searching yum package %s ... " % name, host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='shell',
        module_args='rpm -q %s ' % name,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    status = result['contacted'][host]['rc']
    if status == 0:
        details = "SUCC: The package %s exist in system" % name
        handle_ansible_info(details, host_post_info, "INFO")
        return True
    else:
        details = "SUCC: The package %s not exist in system" % name
        handle_ansible_info(details, host_post_info, "INFO")
        return False


def yum_install_package(name, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting yum install package %s ... " % name, host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='shell',
        module_args='rpm -q %s ' % name,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    status = result['contacted'][host]['rc']
    if status == 0:
        details = "SKIP: The package %s exist in system" % name
        handle_ansible_info(details, host_post_info, "INFO")
        return True
    else:
        details = "Installing package %s ..." % name
        handle_ansible_info(details, host_post_info, "INFO")
        runner = ansible.runner.Runner(
            host_list=host_inventory,
            private_key_file=private_key,
            module_name='yum',
            module_args='name=' + name + ' disable_gpg_check=no  state=latest',
            pattern=host
        )
        result = runner.run()
        logger.debug(result)
        if 'failed' in result['contacted'][host]:
            description = "ERROR: YUM install package %s failed" % name
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            details = "SUCC: yum install package %s successful!" % name
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def yum_remove_package(name, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting yum remove package %s ... " % name, host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='shell',
        module_args='yum list installed ' + name,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    status = result['contacted'][host]['rc']
    if status == 0:
        details = "Removing %s ... " % name
        handle_ansible_info(details, host_post_info, "INFO")
        runner = ansible.runner.Runner(
            host_list=host_inventory,
            private_key_file=private_key,
            module_name='yum',
            module_args='name=' + name + ' state=absent',
            pattern=host
        )
        result = runner.run()
        logger.debug(result)
        if 'failed' in result['contacted'][host]:
            description = "ERROR: Yum remove package %s failed!" % name
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            details = "SUCC: Remove package %s " % name
            handle_ansible_info(details, host_post_info, "INFO")
            return True
    else:
        details = "SKIP: The package %s is not exist in system" % name
        handle_ansible_info(details, host_post_info, "INFO")
        return True


def apt_update_cache(cache_valid_time, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting apt update cache ", host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='apt',
        module_args='update_cache=yes cache_valid_time=%d' % cache_valid_time,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: Apt update cache failed!"
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            details = "SUCC: apt update cache successful! "
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def apt_install_packages(name, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting apt install package %s ... " % name, host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='apt',
        module_args='name=' + name + ' state=present',
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: Apt install %s failed!" % name
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            details = "SUCC: apt install package %s " % name
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def pip_install_package(pip_install_arg, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    name = pip_install_arg.name
    host = host_post_info.host
    post_url = host_post_info.post_url
    version = pip_install_arg.version
    if pip_install_arg.extra_args is not None:
        extra_args = '\"' + '--disable-pip-version-check ' + pip_install_arg.extra_args.split('"')[1] + '\"'
    else:
        extra_args = None
    virtualenv = pip_install_arg.virtualenv
    virtualenv_site_packages = pip_install_arg.virtualenv_site_packages
    handle_ansible_info("INFO: Pip installing module %s ..." % name, host_post_info, "INFO")
    option = 'name=' + name
    param_dict = {}
    param_dict_raw = dict(version=version, extra_args=extra_args, virtualenv=virtualenv,
                          virtualenv_site_packages=virtualenv_site_packages)
    for item in param_dict_raw:
        if param_dict_raw[item] is not None:
            param_dict[item] = param_dict_raw[item]
    option = 'name=' + name + ' ' + ' '.join(['{0}={1}'.format(k, v) for k, v in param_dict.iteritems()])
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='pip',
        module_args=option,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: pip install package %s failed!" % name
            handle_ansible_failed(description, result, host_post_info)
            return False
        else:
            details = "SUCC: Install python module %s " % name
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def copy(copy_arg, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    src = copy_arg.src
    dest = copy_arg.dest
    args = copy_arg.args
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting copy %s to %s ... " % (src, dest), host_post_info, "INFO")
    if args is not None:
        copy_args = 'src=' + src + ' dest=' + dest + ' ' + args
    else:
        copy_args = 'src=' + src + ' dest=' + dest

    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='copy',
        module_args=copy_args,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: copy %s to %s failed!" % (src, dest)
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            change_status = "changed:" + str(result['contacted'][host]['changed'])
            details = "SUCC: copy %s to %s, the change status is %s" % (src, dest, change_status)
            handle_ansible_info(details, host_post_info, "INFO")
            # pass the copy result to outside
            return change_status

def fetch(fetch_arg, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    src = fetch_arg.src
    dest = fetch_arg.dest
    args = fetch_arg.args
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting fetch %s to %s ... " % (src, dest), host_post_info, "INFO")
    if args is not None:
        fetch_args = 'src=' + src + ' dest=' + dest + ' ' + args
    else:
        fetch_args = 'src=' + src + ' dest=' + dest

    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='fetch',
        module_args=fetch_args,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: fetch file from %s to %s failed!" % (src, dest)
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            change_status = "changed:" + str(result['contacted'][host]['changed'])
            details = "SUCC: fetch %s to %s, the change status is %s" % (src, dest, change_status)
            handle_ansible_info(details, host_post_info, "INFO")
            # pass the fetch result to outside
            return change_status

def run_remote_command(command, host_post_info):
    counter = 0
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting run command [ %s ] ..." % command, host_post_info, "INFO")
    def _run_remote_command(counter):
        runner = ansible.runner.Runner(
            host_list=host_inventory,
            private_key_file=private_key,
            module_name='shell',
            module_args=command,
            pattern=host
        )
        result = runner.run()
        print result
        logger.debug(result)
        if result['contacted'] == {}:
            ansible_start = AnsibleStartResult()
            ansible_start.host = host
            ansible_start.post_url = post_url
            ansible_start.result = result
            handle_ansible_start(ansible_start)
            sys.exit(1)
        else:
            if 'rc' not in result['contacted'][host]:
                if counter < 3:
                    counter = counter + 1
                    _run_remote_command(counter)
                else:
                    description = "ERROR: command %s failed! Please make sure network is stable!" % command
                    handle_ansible_failed(description, result, host_post_info)
                    sys.exit(1)
            else:
                status = result['contacted'][host]['rc']
                if status == 0:
                    details = "SUCC: shell command: '%s' " % command
                    handle_ansible_info(details, host_post_info, "INFO")
                    return True
                else:
                    description = "ERROR: command %s failed!" % command
                    handle_ansible_failed(description, result, host_post_info)
                    sys.exit(1)
    _run_remote_command(counter)
    return True

def check_command_status(command, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting run command [ %s ] ..." % command, host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='shell',
        module_args=command,
        pattern=host
    )
    result = runner.run()
    print result
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        status = result['contacted'][host]['rc']
        if status == 0:
            details = "SUCC shell command: '%s' return 0 " % command
            handle_ansible_info(details, host_post_info, "INFO")
            return True
        else:
            description = "ERROR: shell command %s return 1" % command
            handle_ansible_failed(description, result, host_post_info)
            return False


def check_pip_version(version, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Check pip version %s exist ..." % version, host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='shell',
        module_args="pip --version | grep %s" % version,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        status = result['contacted'][host]['rc']
        if status == 0:
            details = "SUCC: Check pip-%s exist in system " % version
            handle_ansible_info(details, host_post_info, "INFO")
            return True
        else:
            details = "INFO: Check pip-%s is not exist in system" % version
            handle_ansible_info(details, host_post_info, "INFO")
            return False


def file_dir_exist(name, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting check file or dir exist %s ... " % name, host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='stat',
        module_args=name,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        status = result['contacted'][host]['stat']['exists']
        if status is True:
            details = "INFO: %s exist" % name
            handle_ansible_info(details, host_post_info, "INFO")
            return True
        else:
            details = "INFO: %s not exist" % name
            handle_ansible_info(details, host_post_info, "INFO")
            return False


def file_operation(file, args, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting change file %s ... " % file, host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='file',
        module_args=args,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        status = result['contacted'][host]['rc']
        if status == 0:
            details = "INFO: %s changed successfully" % file
            handle_ansible_info(details, host_post_info, "INFO")
            return True
        else:
            details = "INFO: %s not be changed" % file
            handle_ansible_info(details, host_post_info, "INFO")
            return False


def get_remote_host_info(host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting get remote host %s info ... " % host, host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='setup',
        module_args='filter=ansible_distribution*',
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        (distro, version) = [result['contacted'][host]['ansible_facts']['ansible_distribution'],
                             int(result['contacted'][host]['ansible_facts']['ansible_distribution_major_version'])]
        handle_ansible_info("SUCC: Get remote host %s info successful" % host, host_post_info, "INFO")
        return (distro, version)


def set_ini_file(file, section, option, value, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting update file %s section %s ... " % (file, section), host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='ini_file',
        module_args='dest=' + file + ' section=' + section + ' option=' + option + " value=" + value,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        details = "SUCC: Update file: %s option: %s value %s" % (file, option, value)
        handle_ansible_info(details, host_post_info, "INFO")
    return True


def check_and_install_virtual_env(version, trusted_host, pip_url, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting install virtualenv-%s ... " % version, host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='shell',
        module_args='virtualenv --version | grep %s' % version,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        status = result['contacted'][host]['rc']
        if status == 0:
            details = "SUCC: The virtualenv-%s exist in system" % version
            handle_ansible_info(details, host_post_info, "INFO")
            return True
        else:
            extra_args = "\"--trusted-host %s -i %s \"" % (trusted_host, pip_url)
            pip_install_arg = PipInstallArg()
            pip_install_arg.extra_args = extra_args
            pip_install_arg.version = version
            pip_install_arg.name = "virtualenv"
            return pip_install_package(pip_install_arg, host_post_info)


def service_status(name, args, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Changing service status %s" % name, host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='service',
        module_args="name=%s " % name + args,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: change service status failed!"
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            details = "SUCC: Service status changed"
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def update_file(dest, args, host_post_info):
    '''Use this function to change the file content'''
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Updating file %s" % dest, host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='lineinfile',
        module_args="dest=%s %s" % (dest, args),
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: Update file %s failed" % dest
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            details = "SUCC: Update file %s" % dest
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def change_iptables(args, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Changing iptables", host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='iptables',
        module_args=args,
        pattern=host
    )
    result = runner.run()
    print result
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: change iptables: %s failed" % args
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            details = "SUCC: change iptables with %s" % args
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def set_selinux(args, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Changing service status", host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='selinux',
        module_args=args,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: set selinux to %s failed" % args
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            details = "SUCC: Reset selinux to %s" % args
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def authorized_key(user, key_path, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    if not os.path.exists(key_path):
        logger.info("key_path %s is not exist!" % key_path)
        sys.exit(1)
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Updating key %s to host %s" % (key_path, host), host_post_info, "INFO")
    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='shell',
        module_args="cat %s" % key_path,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        key = result['contacted'][host]['stdout']
        key = '\'' + key + '\''
        args = "user=%s key=%s" % (user, key)
        runner = ansible.runner.Runner(
            host_list=host_inventory,
            private_key_file=private_key,
            module_name='authorized_key',
            module_args="user=%s key=%s" % (user, key),
            pattern=host
        )
        result = runner.run()
        logger.debug(result)
        if 'failed' in result['contacted'][host]:
            description = "ERROR: Authorized on remote host %s failed!" % host
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            details = "SUCC: update public key to host %s" % host
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def unarchive(unarchive_arg, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    src = unarchive_arg.src
    dest = unarchive_arg.dest
    args = unarchive_arg.args
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting unarchive %s to %s ... " % (src, dest), host_post_info, "INFO")
    if args != None:
        unarchive_args = 'src=' + src + ' dest=' + dest + ' ' + args
    else:
        unarchive_args = 'src=' + src + ' dest=' + dest

    runner = ansible.runner.Runner(
        host_list=host_inventory,
        private_key_file=private_key,
        module_name='unarchive',
        module_args=unarchive_args,
        pattern=host
    )
    result = runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: unarchive %s to %s failed!" % (src, dest)
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            details = "SUCC: unarchive %s to %s" % (src, dest)
            handle_ansible_info(details, host_post_info, "INFO")
            return True


class ZstackLib(object):
    def __init__(self, args):
        distro = args.distro
        yum_repo = args.yum_repo
        zstack_root = args.zstack_root
        host_post_info = args.host_post_info
        pip_version = "7.0.3"
        epel_repo_exist = file_dir_exist("path=/etc/yum.repos.d/epel.repo", host_post_info)
        if distro == "CentOS" or distro == "RedHat":
            # set ALIYUN mirror yum repo firstly avoid 'yum clean --enablerepo=alibase metadata' failed
            repo_aliyun_repo = CopyArg()
            repo_aliyun_repo.src = "files/zstacklib/zstack-aliyun-yum.repo"
            repo_aliyun_repo.dest = "/etc/yum.repos.d/zstack-aliyun-yum.repo"
            copy(repo_aliyun_repo, host_post_info)

            if yum_repo == "false":
                # yum_repo defined by user
                yum_install_package("libselinux-python", host_post_info)
                if epel_repo_exist is False:
                    copy_arg = CopyArg()
                    copy_arg.src = "files/zstacklib/epel-release-source.repo"
                    copy_arg.dest = "/etc/yum.repos.d/"
                    copy(copy_arg, host_post_info)
                    # install epel-release
                    yum_enable_repo("epel-release", "epel-release-source", host_post_info)
                    set_ini_file("/etc/yum.repos.d/epel.repo", 'epel', "enabled", "1", host_post_info)
                for pkg in ["python-devel", "python-setuptools", "python-pip", "gcc", "autoconf", "ntp", "ntpdate"]:
                    yum_install_package(pkg, host_post_info)
            else:
                # set 163 mirror yum repo
                repo_163_copy = CopyArg()
                repo_163_copy.src = "files/zstacklib/zstack-163-yum.repo"
                repo_163_copy.dest = "/etc/yum.repos.d/zstack-163-yum.repo"
                copy(repo_163_copy, host_post_info)
                # install libselinux-python and other command system libs from user defined repos
                # enable alibase repo for yum clean avoid no repo to be clean
                command = (
                          "yum clean --enablerepo=alibase metadata &&  pkg_list=`rpm -q libselinux-python python-devel "
                          "python-setuptools python-pip gcc autoconf ntp ntpdate | grep \"not installed\" | awk"
                          " '{ print $2 }'` && for pkg in $pkg_list; do yum --disablerepo=* --enablerepo=%s install "
                          "-y $pkg; done;") % yum_repo
                run_remote_command(command, host_post_info)

            # enable ntp service for RedHat
            command = 'chkconfig ntpd on; service ntpd restart'
            run_remote_command(command, host_post_info)

        elif distro == "Debian" or distro == "Ubuntu":
            # install dependency packages for Debian based OS
            apt_update_cache(86400, host_post_info)
            for pkg in ["python-dev", "python-setuptools", "python-pip", "gcc", "autoconf", "ntp", "ntpdate"]:
                apt_install_packages(pkg, host_post_info)

            # name: enable ntp service for Debian
            run_remote_command("update-rc.d ntp defaults; service ntp restart", host_post_info)

        else:
            logger.info("ERROR: Unsupported distribution")
            sys.exit(1)

        # check the pip 7.0.3 exist in system
        pip_match = check_pip_version(pip_version, host_post_info)
        if pip_match is False:
            # make dir for copy pip
            run_remote_command("mkdir -p %s" % zstack_root, host_post_info)
            # copy pip 7.0.3
            copy_arg = CopyArg()
            copy_arg.src = "files/pip-7.0.3.tar.gz"
            copy_arg.dest = "%s/pip-7.0.3.tar.gz" % zstack_root
            copy(copy_arg, host_post_info)
            # install pip 7.0.3
            pip_install_arg = PipInstallArg()
            pip_install_arg.extra_args = "\"--ignore-installed\""
            pip_install_arg.name = "%s/pip-7.0.3.tar.gz" % zstack_root
            pip_install_package(pip_install_arg, host_post_info)


def main():
    # Reserve for test api
    import jinja2

    host1_post_info = HostPostInfo()
    host1_post_info.host_inventory = "/etc/ansible/hosts"
    host1_post_info.host = "172.20.12.208"
    host1_post_info.post_url = "http://172.20.12.64:1234"
    host1_post_info.private_key = "/usr/local/zstack/apache-tomcat-7.0.35/webapps/zstack/WEB-INF/classes/ansible/rsaKeys/id_rsa"
    host1_post_info.rabbit_password = "zstack123"
    host1_post_info.mysql_password = "zstack123"
    host1_post_info.mysql_userpassword = 'zstack123'
    host2_post_info = HostPostInfo()
    host2_post_info.host_inventory = "/etc/ansible/hosts"
    host2_post_info.host = "172.20.12.83"
    host2_post_info.post_url = "http://172.20.12.64:1234"
    host2_post_info.private_key = "/usr/local/zstack/apache-tomcat-7.0.35/webapps/zstack/WEB-INF/classes/ansible/rsaKeys/id_rsa"
    host2_post_info.rabbit_password = "zstack123"
    host2_post_info.mysql_password = "zstack123"
    host2_post_info.mysql_userpassword = "zstack123"
    host1 = "172.20.12.208"
    host2 = "172.20.12.83"
    yum_repo = 'zstack-local'
    #command = "mysql -uroot -pzstack.mysql.password -e 'exit' >/dev/null 2>&1"
    #command = '''
    #mysql -uroot -pzstack.mysql.password -Bse 'show databases;
    #show databases;
    #use zstack_rest;
    #show tables;
    #select * from RestAPIVO where "uuid" = 123'
    #'''

#    command = "yum remove -y mariadb"
#    run_remote_command(command, host1_post_info)
#    run_remote_command(command, host2_post_info)
#    command = "hostnamectl set-hostname zstack-1"
#    run_remote_command(command, host1_post_info)
#    command = "hostnamectl set-hostname zstack-2"
#    run_remote_command(command, host2_post_info)
#    update_file("/etc/hosts", "line='%s zstack-1'" % host1, host1_post_info)
#    update_file("/etc/hosts", "line='%s zstack-2'" % host2, host1_post_info)
#    update_file("/etc/hosts", "line='%s zstack-1'" % host1, host2_post_info)
#    update_file("/etc/hosts", "line='%s zstack-2'" % host2, host2_post_info)
#    command = "iptables -A INPUT -s %s/32 -j ACCEPT && iptables-save > /dev/null 2>&1" % host2_post_info.host
#    run_remote_command(command, host1_post_info)
#    command = "iptables -A INPUT -s %s/32 -j ACCEPT && iptables-save > /dev/null 2>&1" % host1_post_info.host
#    run_remote_command(command, host2_post_info)
#    command = ("yum clean --enablerepo=zstack-local metadata && pkg_list=`rpm -q MariaDB-Galera-server xinetd rsync openssl-libs "
#                    " | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
#                    "--disablerepo=* --enablerepo=%s,mariadb install -y $pkg; done;") % yum_repo
#    run_remote_command(command, host1_post_info)
#    run_remote_command(command, host2_post_info)
#
#    copy_arg = CopyArg()
#    copy_arg.src = "/tmp/galera.cnf"
#    copy_arg.dest = "/etc/my.cnf.d/galera.cnf"
#    copy(copy_arg, host1_post_info)
#    copy_arg = CopyArg()
#    copy_arg.src = "/tmp/galera2.cnf"
#    copy_arg.dest = "/etc/my.cnf.d/galera.cnf"
#    copy(copy_arg, host2_post_info)
#    command = "service mysql stop && service mysql bootstrap"
#    run_remote_command(command, host1_post_info)
#    command = "service mysql restart"
#    run_remote_command(command, host2_post_info)
#    command = "service mysql restart"
#    run_remote_command(command, host1_post_info)

#
# check mysql
#
    mysql_username = "zstack"
    mysql_password = "zstack123"
    mysqlchk_raw_script = '''
    #!/bin/sh
    MYSQL_HOST= {{ host1 }}
    MYSQL_PORT="3306"
    MYSQL_USERNAME= {{ mysql_username }}
    MYSQL_PASSWORD= {{ mysql_password }}
    /usr/bin/mysql -h$MYSQL_HOST -u$MYSQL_USERNAME -p$MYSQL_PASSWORD -e "show databases;" > /dev/null
    if [ "$?" -eq 0 ]
    then
            # mysql is fine, return http 200
            /bin/echo -e "HTTP/1.1 200 OK"
            /bin/echo -e "Content-Type: Content-Type: text/plain"
            /bin/echo -e "MySQL is running."
    else
            # mysql is fine, return http 503
            /bin/echo -e "HTTP/1.1 503 Service Unavailable"
            /bin/echo -e "Content-Type: Content-Type: text/plain"
            /bin/echo -e "MySQL is *down*."
    fi
    '''
    mysqlchk_template = jinja2.Template(mysqlchk_raw_script)
    mysqlchk_script_host1 = mysqlchk_template.render({
        'host1': host1_post_info.host,
        'mysql_username': "zstack",
        'mysql_password': host1_post_info.mysql_userpassword
    })
    mysqlchk_script_host2 = mysqlchk_template.render({
        'host1': host2_post_info.host,
        'mysql_username': "zstack",
        'mysql_password': host2_post_info.mysql_userpassword
    })

    import tempfile
    host1_config, mysqlchk_script_host1_file = tempfile.mkstemp()
    os.fdopen(host1_config, 'w').write(mysqlchk_script_host1)
    host2_config, mysqlchk_script_host2_file = tempfile.mkstemp()
    os.fdopen(host2_config, 'w').write(mysqlchk_script_host2)
    os.close(host1_config)
    os.close(host2_config)

    #
    #test rabbitmq cluster
    #
    command = ("yum clean --enablerepo=zstack-local metadata && pkg_list=`rpm -q rabbitmq-server"
               " | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
               "--disablerepo=* --enablerepo=%s,mariadb install -y $pkg; done;") % yum_repo
    run_remote_command(command, host1_post_info)
    run_remote_command(command, host2_post_info)
    # clear erlang process for new deploy
    #command = "ps axu | grep -v 'grep'  | grep erlan |  awk '{ print $2 }' | xargs kill -9 && service rabbitmq-server stop"
    command = "echo True || pkill -f .*erlang.*  > /dev/null 2>&1 && rm -rf /var/lib/rabbitmq/* && service rabbitmq-server stop "
    run_remote_command(command, host1_post_info)
    run_remote_command(command, host2_post_info)
    #
    service_status("rabbitmq-server","state=started", host1_post_info)
    service_status("rabbitmq-server","state=stopped", host1_post_info)
    fetch_arg=FetchArg()
    fetch_arg.src = "/var/lib/rabbitmq/.erlang.cookie"
    fetch_arg.dest = "/tmp/erlang.cookie"
    fetch_arg.args = "fail_on_missing=yes flat=yes"
    fetch(fetch_arg, host1_post_info)

    copy_arg = CopyArg()
    copy_arg.src = "/tmp/erlang.cookie"
    copy_arg.dest = "/var/lib/rabbitmq/.erlang.cookie"
    copy_arg.args = "owner=rabbitmq group=rabbitmq mode=400"
    copy(copy_arg, host2_post_info)

    service_status("rabbitmq-server", "state=started", host1_post_info)
    service_status("rabbitmq-server", "state=started", host2_post_info)
    #todo : check the cluster status
    # add zstack2 to cluster
    command = "rabbitmqctl stop_app"
    run_remote_command(command, host2_post_info)
    command = "rabbitmqctl join_cluster rabbit@zstack-1"
    run_remote_command(command, host2_post_info)
    command = "rabbitmqctl start_app"
    run_remote_command(command, host2_post_info)
    #todo : check the cluster status
    # set policy let all nodes duplicate content
    command = "rabbitmqctl set_policy ha-all '^(?!amq\.).*' '{\"ha-mode\": \"all\"}'"
    run_remote_command(command, host1_post_info)
    # add zstack user in this cluster
    command = "rabbitmqctl add_user zstack 'zstack123'"
    run_remote_command(command, host1_post_info)
    command = "rabbitmqctl set_user_tags zstack administrator"
    run_remote_command(command, host1_post_info)
    command = "rabbitmqctl change_password zstack 'zstack123'"
    run_remote_command(command, host1_post_info)
    command = 'rabbitmqctl set_permissions -p \/ zstack ".*" ".*" ".*"'
    run_remote_command(command, host1_post_info)



    #test
#    command = '''
##!/bin/bash
#if [ ! -d ~/.ssh ]; then
#mkdir -p ~/.ssh
#chmod 700 ~/.ssh
#fi
#if [ ! -f ~/.ssh/authorized_keys ]; then
#touch ~/.ssh/authorized_keys
#chmod 600 ~/.ssh/authorized_keys
#fi
#pub_key=%s
#grep %s ~/.ssh/authorized_keys > /dev/null
#if [ $? -eq 1 ]; then
#echo %s >> ~/.ssh/authorized_keys
#fi
#if [ -x /sbin/restorecon ]; then
#/sbin/restorecon ~/.ssh ~/.ssh/authorized_keys
#fi
#exit 0
#''' % ("123sdfsdfdsfs", "123sdfsdfdsfs", "123sdfsdfdsfs")
#    run_remote_command(command, host1_post_info)
## todo : check the user privileges

#command = '''
    #        mysql -uroot -p -Bse 'grant ALL PRIVILEGES on *.* to zstack@"localhost" Identified by %s;
    #        grant ALL PRIVILEGES on *.* to zstack@"zstack-1" Identified by %s;
    #        grant ALL PRIVILEGES on *.* to zstack@"%%" Identified by %s;
    #        grant ALL PRIVILEGES on *.* to root@"%%" Identified by %s;
    #        grant ALL PRIVILEGES on *.* to root@"localhost" Identified by %s;
    #        grant ALL PRIVILEGES ON *.* TO root@"%%" IDENTIFIED BY %s WITH GRANT OPTION;
    #        flush privileges'
    #        ''' % ("zstack123","zstack123","zstack123","zstack123","zstack123","zstack123")
    #print command
    #run_remote_command(command, host1_post_info)

    #if init_install is True:
    #    self.command = "mysql -uroot -p -Bse \"show status like 'wsrep_%';\""
    #if check_command_status(command, host_post_info) is True:
    #    print "succ"
    #else:
    #    print "faild"

if __name__ == "__main__":
    main()
