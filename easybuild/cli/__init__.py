import os

try:
    import rich_click as click
    import click as original_click
except ImportError:
    import click
    import click as original_click

try:
    from rich.traceback import install
except ImportError:
    pass
else:
    install(suppress=[
        click, original_click
    ])

from .options import EasyBuildCliOption, EasyconfigParam

from easybuild.main import main_with_hooks


@click.command()
@EasyBuildCliOption.apply_options
@click.pass_context
@click.argument('other_args', nargs=-1, type=EasyconfigParam(), required=False)
def eb(ctx, other_args):
    """EasyBuild command line interface."""
    args = []
    for key, value in getattr(ctx, 'hidden_params', {}).items():
        key = key.replace('_', '-')
        opt = EasyBuildCliOption.OPTIONS_MAP[key]
        if value in ['False', 'True']:
            value = value == 'True'
        if isinstance(value, bool):
            if value:
                args.append(f"--{key}")
        else:
            if isinstance(value, (list, tuple)) and value:
                # Flatten nested lists if necessary
                if isinstance(value[0], list):
                    value = sum(value, [])
            # Match the type of the option with the default to see if we need to add it
            if isinstance(value, list) and isinstance(opt.default, tuple):
                value = tuple(value)
            if value and value != opt.default:
                if isinstance(value, (list, tuple)):
                    if 'path' in opt.type:
                        delim = os.pathsep
                    elif 'str' in opt.type:
                        delim = ','
                    elif 'url' in opt.type:
                        delim = '|'
                    else:
                        raise ValueError(f"Unsupported type for {key}: {opt.type}")
                    value = delim.join(value)

                # print(f"--Adding {key}={value} to args")
                args.append(f"--{key}={value}")

    args.extend(other_args)

    main_with_hooks(args=args)
