import os
import sys

try:
    import click as original_click
except ImportError:
    def eb():
        """Placeholder function to inform the user that `click` is required."""
        print("Using `eb2` requires `click` to be installed. Either use `eb` or install `click` with `pip install click`.")
        print("`eb2` also uses `rich` and `rich_click` as optional dependencies for enhanced CLI experience.")
        print("Exiting...")
        sys.exit(0)
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
                if value != opt.default:
                    if value:
                        args.append(f"--{key}")
                    else:
                        args.append(f"--disable-{key}")
            else:

                if isinstance(value, (list, tuple)) and value:
                    # Flatten nested lists if necessary
                    if isinstance(value[0], list):
                        value = sum(value, [])
                # Match the type of the option with the default to see if we need to add it
                if value and isinstance(value, list) and isinstance(opt.default, tuple):
                    value = tuple(value)
                if value and isinstance(value, tuple) and isinstance(opt.default, list):
                    value = list(value)
                value_is_default = (value == opt.default)

                value_flattened = value
                if isinstance(value, (list, tuple)):
                    if 'path' in opt.type:
                        delim = os.pathsep
                    elif 'str' in opt.type:
                        delim = ','
                    elif 'url' in opt.type:
                        delim = '|'
                    else:
                        raise ValueError(f"Unsupported type for {key}: {opt.type}")
                    value_flattened = delim.join(value)

                if opt.action == 'store_or_None':
                    if value is None or value == ():
                        continue
                    if value_is_default:
                        args.append(f"--{key}")
                    else:
                        args.append(f"--{key}={value_flattened}")
                elif value and not value_is_default:
                    if value:
                        args.append(f"--{key}={value_flattened}")
                    else:
                        args.append(f"--{key}")
        for arg in args:
            print(f"ARG: {arg}")

        args.extend(other_args)
        main_with_hooks(args=args)
