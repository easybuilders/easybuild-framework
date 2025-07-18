# import logging
import os

from typing import Callable, Any
from dataclasses import dataclass

from click.shell_completion import CompletionItem
from easybuild.tools.options import EasyBuildOptions

opt_group = {}
try:
    import rich_click as click
except ImportError:
    import click
else:
    opt_group = click.rich_click.OPTION_GROUPS
    opt_group.clear()  # Clear existing groups to avoid conflicts


class OptionExtracter(EasyBuildOptions):
    def __init__(self, *args, **kwargs):
        self._option_dicts = {}
        super().__init__(*args, **kwargs)

    def add_group_parser(self, opt_dict, descr, *args, prefix='', **kwargs):
        super().add_group_parser(opt_dict, descr, *args, prefix=prefix, **kwargs)
        self._option_dicts[descr[0]] = (prefix, opt_dict)


extracter = OptionExtracter(go_args=[])


class DelimitedPathList(click.Path):
    """Custom Click parameter type for delimited lists."""
    name = 'pathlist'

    def __init__(self, *args, delimiter=',', resolve_full: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.delimiter = delimiter
        self.resolve_full = resolve_full

    def convert(self, value, param, ctx):
        if not isinstance(value, str):
            raise click.BadParameter(f"Expected a comma-separated string, got {value}")
        res = value.split(self.delimiter)
        if self.resolve_full:
            res = [os.path.abspath(v) for v in res]
        return res

    def shell_complete(self, ctx, param, incomplete):
        others, last = ([''] + incomplete.rsplit(self.delimiter, 1))[-2:]
        # logging.warning(f"Shell completion for delimited path list: others={others}, last={last}")
        dir_path, prefix = os.path.split(last)
        dir_path = dir_path or '.'
        # logging.warning(f"Shell completion for delimited path list: dir_path={dir_path}, prefix={prefix}")
        possibles = []
        for path in os.listdir(dir_path):
            if not path.startswith(prefix):
                continue
            full_path = os.path.join(dir_path, path)
            if os.path.isdir(full_path):
                if self.dir_okay:
                    possibles.append(full_path)
                    possibles.append(full_path + os.sep)
            elif os.path.isfile(full_path):
                if self.file_okay:
                    possibles.append(full_path)
        start = f'{others}{self.delimiter}' if others else ''
        res = [CompletionItem(f"{start}{path}") for path in possibles]
        # logging.warning(f"Shell completion for delimited path list: res={possibles}")
        return res


class DelimitedString(click.ParamType):
    """Custom Click parameter type for delimited strings."""
    name = 'strlist'

    def __init__(self, *args, delimiter=',', **kwargs):
        super().__init__(*args, **kwargs)
        self.delimiter = delimiter

    def convert(self, value, param, ctx):
        if isinstance(value, str):
            return value.split(self.delimiter)
        raise click.BadParameter(f"Expected a string or a comma-separated string, got {value}")

    def shell_complete(self, ctx, param, incomplete):
        last = incomplete.rsplit(self.delimiter, 1)[-1]
        return super().shell_complete(ctx, param, last)


@dataclass
class OptionData:
    name: str
    description: str
    type: str
    action: str
    default: Any
    group: str = None
    short: str = None
    meta: dict = None
    lst: list = None

    def __post_init__(self):
        if self.short is not None and not isinstance(self.short, str):
            raise TypeError(f"Short option must be a string, got {type(self.short)}")
        if self.meta is not None and not isinstance(self.meta, dict):
            raise TypeError(f"Meta must be a dictionary, got {type(self.meta)}")
        if self.lst is not None and not isinstance(self.lst, (list, tuple)):
            raise TypeError(f"List must be a list or tuple, got {type(self.lst)}")

    def to_click_option_dec(self):
        """Convert OptionData to a click.Option."""
        decls = [f"--{self.name}"]
        if self.short:
            decls.insert(0, f"-{self.short}")

        kwargs = {
            'help': self.description,
            'default': self.default,
            'show_default': True,
            'type': None
        }

        if self.type in ['strlist', 'strtuple']:
            kwargs['type'] = DelimitedString(delimiter=',')
            kwargs['multiple'] = True
        elif self.type in ['pathlist', 'pathtuple']:
            # kwargs['type'] = DelimitedPathList(delimiter=os.pathsep)
            kwargs['type'] = DelimitedPathList(delimiter=',')
            kwargs['multiple'] = True
        elif self.type in ['urllist', 'urltuple']:
            kwargs['type'] = DelimitedString(delimiter='|')
            kwargs['multiple'] = True
        elif self.type == 'choice':
            if self.lst is None:
                raise ValueError(f"Choice type requires a list of choices for option {self.name}")
            kwargs['type'] = click.Choice(self.lst, case_sensitive=False)
        elif self.type in ['int', int]:
            kwargs['type'] = click.INT
        elif self.type in ['float', float]:
            kwargs['type'] = click.FLOAT
        elif self.type in ['str', str]:
            kwargs['type'] = click.STRING
        elif self.type is None:
            if self.default is False or self.default is True:
                kwargs['is_flag'] = True
                kwargs['type'] = click.BOOL
            elif isinstance(self.default, (list, tuple)):
                kwargs['multiple'] = True
                kwargs['type'] = click.STRING

        # if kwargs['type'] is None:
        #     print(f"Warning: No type specified for option {self.name}, defaulting to STRING")

        # actions = set()
        # for opt in EasyBuildCliOption.OPTIONS:
        #     actions.add(opt.action)
        # print(f"Registered {len(EasyBuildCliOption.OPTIONS)} options with actions: {actions}")
        # # Registered 296 options with actions: {
        # #     'store_infolog', 'add_flex', 'append', 'add', 'store_true', 'store_debuglog', 'store_or_None',
        # #     'store_warninglog', 'store', 'extend', 'regex'
        # # }

        # Actions:
        #     - shorthelp : hook for shortend help messages
        #     - confighelp : hook for configfile-style help messages
        #     - store_debuglog : turns on fancylogger debugloglevel
        #         - also: 'store_infolog', 'store_warninglog'
        #     - add : add value to default (result is default + value)
        #         - add_first : add default to value (result is value + default)
        #         - extend : alias for add with strlist type
        #         - type must support + (__add__) and one of negate (__neg__) or slicing (__getslice__)
        #     - add_flex : similar to add / add_first, but replaces the first "empty" element with the default
        #         - the empty element is dependent of the type
        #             - for {str,path}{list,tuple} this is the empty string
        #         - types must support the index method to determine the location of the "empty" element
        #         - the replacement uses +
        #         - e.g. a strlist type with value "0,,1"` and default [3,4] and action add_flex will
        #             use the empty string '' as "empty" element, and will result in [0,3,4,1] (not [0,[3,4],1])
        #             (but also a strlist with value "" and default [3,4] will result in [3,4];
        #             so you can't set an empty list with add_flex)
        #     - date : convert into datetime.date
        #     - datetime : convert into datetime.datetime
        #     - regex: compile str in regexp
        #     - store_or_None
        #     - set default to None if no option passed,
        #     - set to default if option without value passed,
        #     - set to value if option with value passed

        #     Types:
        #     - strlist, strtuple : convert comma-separated string in a list resp. tuple of strings
        #     - pathlist, pathtuple : using os.pathsep, convert pathsep-separated string in a list resp. tuple of strings
        #         - the path separator is OS-dependent
        #     - urllist, urltuple: convert string seperated by '|' to a list resp. tuple of strings

        # def take_action(self, action, dest, opt, value, values, parser):
        #     if action == "store":
        #         setattr(values, dest, value)
        #     elif action == "store_const":
        #         setattr(values, dest, self.const)
        #     elif action == "store_true":
        #         setattr(values, dest, True)
        #     elif action == "store_false":
        #         setattr(values, dest, False)
        #     elif action == "append":
        #         values.ensure_value(dest, []).append(value)
        #     elif action == "append_const":
        #         values.ensure_value(dest, []).append(self.const)
        #     elif action == "count":
        #         setattr(values, dest, values.ensure_value(dest, 0) + 1)
        #     elif action == "callback":
        #         args = self.callback_args or ()
        #         kwargs = self.callback_kwargs or {}
        #         self.callback(self, opt, value, parser, *args, **kwargs)
        #     elif action == "help":
        #         parser.print_help()
        #         parser.exit()
        #     elif action == "version":
        #         parser.print_version()
        #         parser.exit()
        #     else:
        #         raise ValueError("unknown action %r" % self.action)

        #     return 1

        return click.option(
            *decls,
            expose_value=False,
            callback=self.register_hidden_param,
            **kwargs
        )

    @staticmethod
    def register_hidden_param(ctx, param, value):
        """Register a hidden parameter in the context."""
        if not hasattr(ctx, 'hidden_params'):
            ctx.hidden_params = {}
        ctx.hidden_params[param.name] = value


class EasyBuildCliOption():
    OPTIONS: list[OptionData] = []
    OPTIONS_MAP: dict[str, OptionData] = {}

    @classmethod
    def apply_options(cls, function: Callable) -> Callable:
        """Decorator to apply EasyBuild options to a function."""
        group_data = {}
        for opt_obj in cls.OPTIONS:
            group_data.setdefault(opt_obj.group, []).append(f'--{opt_obj.name}')
            function = opt_obj.to_click_option_dec()(function)
        lst = []
        for key, value in group_data.items():
            lst.append({
                'name': key,
                # 'description': f'Options for {key}',
                'options': value
            })
        opt_group[function.__name__] = lst
        return function

    @classmethod
    def register_option(cls, group: str, name: str, data: tuple, prefix: str = '') -> None:
        """Register an EasyBuild option."""
        if prefix:
            name = f"{prefix}-{name}"
        if name == 'help':
            return
        short = None
        meta = None
        lst = None
        descr, typ, action, default, *others = data
        while others:
            opt = others.pop(0)
            if isinstance(opt, str):
                if short is not None:
                    raise ValueError(f"Short option already set: {short} for {name}")
                short = opt
            elif isinstance(opt, dict):
                if meta is not None:
                    raise ValueError(f"Meta already set: {meta} for {name}")
                meta = opt
            elif isinstance(opt, (list, tuple)):
                if lst is not None:
                    raise ValueError(f"List already set: {lst} for {name}")
                lst = opt
            else:
                raise ValueError(f"Unexpected type for others: {type(others[0])} in {others}")

        opt = OptionData(
            group=group,
            name=name,
            description=descr,
            type=typ,
            action=action,
            default=default,
            short=short,
            meta=meta,
            lst=lst
        )
        cls.OPTIONS_MAP[name] = opt
        cls.OPTIONS.append(opt)


for grp, dct in extracter._option_dicts.items():
    prefix, dct = dct
    if dct is None:
        continue
    for key, value in dct.items():
        EasyBuildCliOption.register_option(grp, key, value, prefix=prefix)
