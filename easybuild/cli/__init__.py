try:
    import rich_click as click
except ImportError:
    import click

try:
    from rich.traceback import install
except ImportError:
    pass
else:
    install(suppress=[click])

from .options import EasyBuildCliOption

from easybuild.main import main_with_hooks

@click.command()
@EasyBuildCliOption.apply_options
@click.pass_context
@click.argument('other_args', nargs=-1, type=click.UNPROCESSED, required=False)
def eb(ctx, other_args):
    """EasyBuild command line interface."""
    args = []
    for key, value in ctx.hidden_params.items():
        key = key.replace('_', '-')
        if isinstance(value, bool):
            if value:
                args.append(f"--{key}")
        else:
            if value and value != EasyBuildCliOption.OPTIONS_MAP[key].default:
                if isinstance(value, (list, tuple)):
                    value = ','.join(value)
                args.append(f"--{key}={value}")

    args.extend(other_args)

    main_with_hooks(args=args)
