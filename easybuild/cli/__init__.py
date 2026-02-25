from easybuild.main import main_with_hooks

try:
    import click as original_click
except ImportError:
    def eb():
        """Placeholder function to inform the user that `click` is required."""
        main_with_hooks()
        # print('Using `eb2` requires `click` to be installed.')
        # print('Either use `eb` or install `click` with `pip install click`.')
        # print('`eb2` also uses `rich` and `rich_click` as optional dependencies for enhanced CLI experience.')
        # print('Exiting...')
        # sys.exit(0)
else:
    try:
        import rich_click as click
    except ImportError:
        import click

    try:
        from rich.traceback import install
    except ImportError:
        pass
    else:
        install(suppress=[
            click, original_click
        ])

    from .options import EasyBuildCliOption, EasyconfigParam

    @click.command()
    @EasyBuildCliOption.apply_options
    @click.argument('other_args', nargs=-1, type=EasyconfigParam(), required=False)
    def eb(other_args):
        """EasyBuild command line interface."""
        # Really no need to re-build the arguments if we support the exact same syntax we can just let them pass
        # through to optparse
        main_with_hooks()
