import os

from typing import Callable, Any
from dataclasses import dataclass

opt_group = {}
try:
    import rich_click as click
except ImportError:
    import click
else:
    opt_group = click.rich_click.OPTION_GROUPS

from easybuild.tools.options import EasyBuildOptions

DEBUG_EASYBUILD_OPTIONS = os.environ.get('DEBUG_EASYBUILD_OPTIONS', '').lower() in ('1', 'true', 'yes', 'y')

class OptionExtracter(EasyBuildOptions):
    def __init__(self, *args, **kwargs):
        self._option_dicts = {}
        super().__init__(*args, **kwargs)

    def add_group_parser(self, opt_dict, descr, *args, prefix='', **kwargs):
        super().add_group_parser(opt_dict, descr, *args, prefix=prefix, **kwargs)
        self._option_dicts[descr[0]] = (prefix, opt_dict)

extracter = OptionExtracter(go_args=[])

def register_hidden_param(ctx, param, value):
    """Register a hidden parameter in the context."""
    if not hasattr(ctx, 'hidden_params'):
        ctx.hidden_params = {}
    ctx.hidden_params[param.name] = value

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
            # 'help': '123',
            'default': self.default,
            'show_default': True,
        }

        if self.default is False or self.default is True:
            kwargs['is_flag'] = True

        if isinstance(self.default, (list, tuple)):
            kwargs['multiple'] = True
            kwargs['type'] = click.STRING

        return click.option(
            *decls,
            expose_value=False,
            callback=register_hidden_param,
            **kwargs
        )

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
