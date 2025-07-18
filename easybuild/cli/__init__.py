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

from .options import EasyBuildCliOption

from easybuild.main import main_with_hooks


@click.command()
@EasyBuildCliOption.apply_options
@click.pass_context
@click.argument('other_args', nargs=-1, type=click.UNPROCESSED, required=False)
def eb(ctx, other_args):
    """EasyBuild command line interface."""
    args = []
    for key, value in getattr(ctx, 'hidden_params', {}).items():
        key = key.replace('_', '-')
        if isinstance(value, bool):
            if value:
                args.append(f"--{key}")
        else:
            opt = EasyBuildCliOption.OPTIONS_MAP[key]
            if value and value != opt.default:
                if isinstance(value, (list, tuple)) and value:
                    if isinstance(value[0], list):
                        value = sum(value, [])
                    if 'path' in opt.type:
                        delim = os.pathsep
                    elif 'str' in opt.type:
                        delim = ','
                    elif 'url' in opt.type:
                        delim = '|'
                    else:
                        raise ValueError(f"Unsupported type for {key}: {opt.type}")
                    value = delim.join(value)
                print(f"--Adding {key}={value} to args")
                args.append(f"--{key}={value}")

    args.extend(other_args)

    main_with_hooks(args=args)
